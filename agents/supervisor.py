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
    """Split an agent output into individual findings.

    Heuristic-based splitting: splits on common bullet characters and on
    paragraph boundaries. Trims and ignores very short/empty items.
    """
    if not text:
        return []

    # Normalize common bullet separators to newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Replace bullets like '-', '*', '•' or numbered lists with newline markers
    text = re.sub(r"(^|\n)\s*[-*•+]\s+", "\n- ", text)
    text = re.sub(r"(^|\n)\s*\d+\.\s+", "\n- ", text)

    parts = []
    for line in text.split("\n"):
        candidate = line.strip()
        if not candidate:
            continue
        # Remove leading dash if present from normalization
        if candidate.startswith("- "):
            candidate = candidate[2:].strip()
        # Ignore tiny fragments that are unlikely to be meaningful
        if len(candidate) < 12:
            continue
        parts.append(candidate)

    return parts


def _normalize(item: str) -> str:
    """Normalize a finding for deduplication."""
    s = item.strip()
    s = re.sub(r"\s+", " ", s)
    s = s.lower()
    return s


def supervisor_node(state: AgentState) -> dict:
    """Create a final PR review from accumulated agent comments.

    Args:
            state: Shared AgentState with `logic_comments`, `style_comments`, and `pr_diff`.

    Returns:
            Dict containing `final_report` as a Markdown string.
    """
    try:
        logic_comments = state.get("logic_comments", []) or []
        style_comments = state.get("style_comments", []) or []
        pr_diff = state.get("pr_diff", "") or ""

        # Extract individual findings from agent outputs
        findings: List[str] = []
        for blob in logic_comments + style_comments:
            findings.extend(_split_findings(blob))

        # Deduplicate while preserving readable order
        seen: Set[str] = set()
        deduped: List[str] = []
        for f in findings:
            key = _normalize(f)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(f)

        # If nothing to report, short-circuit with an empty but helpful message
        if not deduped:
            empty_md = (
                "## Automated PR Review\n\n"
                "No issues were identified by the agents. If you expected results, "
                "please ensure the PR diff is provided and agents ran successfully."
            )
            logger.info("supervisor_node: No findings to summarize")
            return {"final_report": empty_md}

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
            "PR DIFF:\n" + pr_diff + "\n\n"
            "AGENT FINDINGS (deduplicated):\n"
            + "\n".join(f"- {f}" for f in deduped)
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
        final_report = getattr(response, "content", "") or response

        if not isinstance(final_report, str):
            final_report = str(final_report)

        # Basic sanity: ensure both required sections exist; if model omitted them,
        # create a safe fallback structure using the deduped lists.
        if "Security/Logic" not in final_report and "Style" not in final_report:
            logger.warning(
                "supervisor_node: Model output missing expected sections; applying fallback format"
            )
            security_items = [
                f
                for f in deduped
                if any(
                    w in f.lower()
                    for w in (
                        "security",
                        "vulner",
                        "bug",
                        "null",
                        "crash",
                        "race",
                        "leak",
                        "inject",
                    )
                )
            ]
            style_items = [f for f in deduped if f not in security_items]

            parts = [
                "# Automated PR Review\n",
                "## Security/Logic Issues\n",
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
