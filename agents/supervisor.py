"""Supervisor (Orchestrator) for the multi-agent PR review system.

Reads `logic_comments` and `style_comments` from the shared `state`,
deduplicates and filters findings, prompts the heavy model
(`llama-3.3-70b-versatile`) to produce a professional GitHub PR review in
Markdown, and writes the result to `final_report` in the state.

Behavior guarantees:
- Uses the heavy model defined by the `MODEL_HEAVY` env var (default
  "llama-3.3-70b-versatile").
- Prompt: "Summarize inputs into a professional GitHub PR review (Markdown)."
- Eliminates duplicates and attempts to filter hallucinations by asking the
  model to only include items supported by the provided PR diff.
- Produces clearly separated sections for Security/Logic Issues and Style
  Suggestions (with emoji headings and bullets).

Returns:
        A dict with `final_report` string suitable to append to the shared state.
"""

from __future__ import annotations

import logging
import os
import re
from typing import List, Set

from dotenv import load_dotenv

from langchain_groq import ChatGroq

from core.state import AgentState

load_dotenv()

logger = logging.getLogger(__name__)


def _split_findings(text: str) -> List[str]:
    """
    Split an agent output into individual findings.

    Heuristic-based splitting: splits on common bullet characters.
    Trims and ignores very short/empty items. Preserves multi-line findings by
    splitting on bullet separators rather than raw newlines.

    Args:
        text (str): The agent output text to split into findings.

    Returns:
        List[str]: A list of individual findings as strings.

    Example:
        findings = _split_findings("- Issue one.\n- Issue two.")
        # findings == ["Issue one.", "Issue two."]
    """
    if not text:
        return []

    # Pattern to identify the start of a bullet point item (start of line)
    bullet_pattern = r"(?:^|\n)\s*(?:[-*•+]|\d+\.)\s+"

    # Use re.split to preserve multi-line findings (each bullet is a delimiter)
    parts = re.split(bullet_pattern, text)

    findings = []
    for part in parts:
        candidate = part.strip()
        # Ignore empty strings from split and tiny fragments
        if not candidate or len(candidate) < 12:
            continue
        findings.append(candidate)

    return findings


def _normalize(item: str) -> str:
    """
    Normalize a finding for deduplication.

    Args:
        item (str): The finding string to normalize.

    Returns:
        str: The normalized string suitable for deduplication.

    Example:
        norm = _normalize("  Bug found!  ")
        # norm == "bug found"
    """
    s = item.strip()
    s = re.sub(r"\s+", " ", s)
    s = s.lower()
    # Remove punctuation to improve deduplication
    s = re.sub(r"[^\w\s]", "", s)
    return s


def supervisor_node(state: AgentState) -> dict:
    """
    Create a final PR review from accumulated agent comments.

    Args:
        state (AgentState): Shared AgentState with `logic_comments`, `style_comments`,
        and `pr_diff`.

    Returns:
        dict: Dict containing `final_report` as a Markdown string.

    Example:
        state = AgentState(logic_comments=["- Bug found."],
        style_comments=["- Use snake_case."], pr_diff="diff...")
        result = supervisor_node(state)
        # result == {"final_report": "...markdown..."}
    """
    try:
        logic_comments = state.get("logic_comments", []) or []
        style_comments = state.get("style_comments", []) or []
        pr_diff = state.get("pr_diff", "") or ""

        # Support structured findings (dicts) or legacy plain-text strings.
        # Normalize into a list of dicts: {"category": "logic"|"style", "description": str}
        all_findings = []

        def _ingest(source, category_name):
            for item in source:
                if isinstance(item, dict):
                    desc = item.get("description") or item.get("text") or ""
                    cat = item.get("category") or category_name
                    if desc:
                        all_findings.append({"category": cat, "description": desc})
                elif isinstance(item, str):
                    for desc in _split_findings(item):
                        all_findings.append(
                            {"category": category_name, "description": desc}
                        )

        _ingest(logic_comments, "logic")
        _ingest(style_comments, "style")

        # Deduplicate while preserving readable order (by normalized description)
        seen: Set[str] = set()
        deduped: List[dict] = []
        for f in all_findings:
            desc = f.get("description", "")
            key = _normalize(desc)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(
                {"category": f.get("category", "style"), "description": desc}
            )

        # If nothing to report, short-circuit with an empty but helpful message
        if not deduped:
            empty_md = (
                "## Automated PR Review\n\n"
                "No issues were identified by the agents. If you expected results, "
                "please ensure the PR diff is provided and agents ran successfully."
            )
            logger.info("supervisor_node: No findings to summarize")
            return {"final_report": empty_md}

        # Truncate diff to avoid oversized prompts
        MAX_DIFF_CHARS = 2000
        truncated_diff = pr_diff[:MAX_DIFF_CHARS] + (
            "... [truncated]" if len(pr_diff) > MAX_DIFF_CHARS else ""
        )

        # Build the user prompt for the heavy model
        system_instructions = (
            "You are a professional GitHub code reviewer. Summarize the provided "
            "findings into a single, well-structured Markdown PR review."
        )
        user_prompt = (
            "Summarize inputs into a professional GitHub PR review (Markdown). "
            "Produce clear sections with emoji headings, short descriptive intro, "
            "and bullets. Separate 'Security/Logic Issues' and 'Style Suggestions'. "
            "Eliminate duplicates and do NOT hallucinate: only include issues that "
            "are supported by the provided PR diff or by the agent findings. "
            "If a finding is uncertain, mark it as a suggestion and note uncertainty.\n\n"
            "PR DIFF:\n" + truncated_diff + "\n\n"
            "AGENT FINDINGS (deduplicated):\n"
            + "\n".join(f"- [{f['category']}] {f['description']}" for f in deduped)
            + "\n\nRespond with final Markdown only (no extra commentary)."
        )

        # Invoke the heavy model
        model_name = os.getenv("MODEL_HEAVY", "llama-3.3-70b-versatile")
        llm = ChatGroq(temperature=0, model_name=model_name)

        messages = [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": user_prompt},
        ]

        response = llm.invoke(messages)
        try:
            final_report = response.content
        except AttributeError:
            final_report = str(response)

        if not isinstance(final_report, str):
            final_report = str(final_report)

        # Basic sanity: ensure both required sections exist; if model omitted them,
        # create a safe fallback structure using the deduped lists.
        # If either required section is missing, apply fallback formatting
        if "Security/Logic" not in final_report or "Style" not in final_report:
            logger.warning(
                "supervisor_node: Model output missing expected sections; applying fallback format"
            )
            # Improve categorization using a keyword regex with word boundaries
            security_keywords = [
                "security",
                "vulner",
                "bug",
                "null",
                "crash",
                "race",
                "leak",
                "inject",
            ]
            security_pattern = re.compile(
                r"\b(" + "|".join(security_keywords) + r")\b", re.IGNORECASE
            )

            security_items = [
                f["description"]
                for f in deduped
                if security_pattern.search(f["description"])
            ]
            style_items = [
                f["description"]
                for f in deduped
                if f["description"] not in security_items
            ]

            parts = [
                "# Automated PR Review 🧾\n",
                "## ⚠️ Security/Logic Issues\n",
            ]
            if security_items:
                parts.append("\n".join(f"- {s}" for s in security_items))
            else:
                parts.append("- No high-confidence security/logic issues found.")

            parts.append("\n\n## Style Suggestions\n")
            if style_items:
                parts.append("\n".join(f"- {s}" for s in style_items))
            else:
                parts.append("- No stylistic issues identified.")

            final_report = "\n".join(parts)

        # Write back to state and return
        logger.info("supervisor_node: Final report generated")
        return {"final_report": final_report}

    except Exception as e:
        logger.exception(
            "supervisor_node: Unexpected error while generating final report"
        )
        fallback = (
            "## Supervisor Error\n\n"
            f"An error occurred while generating the final report: {e}\n\n"
            "Please check agent outputs and try again."
        )
        return {"final_report": fallback}
