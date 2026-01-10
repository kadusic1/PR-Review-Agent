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
<<<<<<< HEAD
import re
from typing import List, Set

from dotenv import load_dotenv

from langchain_groq import ChatGroq

=======
from utils import ORCHESTRATOR_PROMPT
from langchain_core.messages import AIMessage
from dotenv import load_dotenv
from langchain_groq import ChatGroq
>>>>>>> 886b8f2d42f9adcea5a6180eff32a839f434c92e
from core.state import AgentState

load_dotenv()

logger = logging.getLogger(__name__)


<<<<<<< HEAD
def _split_findings(text: str) -> List[str]:
    """Split an agent output into individual findings.
    Heuristic-based splitting: splits on common bullet characters. Trims and
    ignores very short/empty items. Preserves multi-line findings by splitting
    on bullet separators rather than raw newlines.
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
    """Normalize a finding for deduplication."""
    s = item.strip()
    s = re.sub(r"\s+", " ", s)
    s = s.lower()
    # Remove punctuation to improve deduplication
    s = re.sub(r"[^\w\s]", "", s)
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
=======
def supervisor_node(state: AgentState) -> dict:
    """
    Summarizes agent findings into a professional GitHub PR review.

    Orchestrates the final reporting. Includes a safety check to abort
    analysis if the PR size exceeds the token limit constraints.

    Args:
        state (AgentState): Shared state containing findings and pr_diff.

    Returns:
        dict: A dictionary with the 'final_report' key.

    Example:
        >>> state = {"pr_diff": "huge string..."}
        >>> result = supervisor_node(state)
        >>> "PR Too Large" in result["final_report"]
        True
    """
    try:
        # 1. Extract inputs
        logic_data = state.get("logic_comments", []) or []
        style_data = state.get("style_comments", []) or []
        pr_diff = state.get("pr_diff", "") or ""
        pr_url = state.get("pr_url")

        if not pr_url:
            logger.warning("supervisor_node: pr_url not found in state.")
            return {
                "final_report": "## ⚠️ PR Review Aborted\n\n**Reason:** PR URL not provided."
            }

        # 2. SAFETY CHECK: Diff Size Limit
        # Default to 60,000 chars (approx 15k tokens), adjustable via env
        max_chars = int(os.getenv("PR_MAX_CHARS", "60000"))
        curr_len = len(pr_diff)

        if curr_len > max_chars:
            logger.warning(
                f"supervisor_node: PR size ({curr_len}) exceeds limit "
                f"({max_chars}). Aborting."
            )
            error_msg = (
                "## ⚠️ PR Review Aborted\n\n"
                "**Reason:** The Pull Request is too large for automated "
                f"analysis.\n\n"
                f"- **Size Detected:** {curr_len} characters\n"
                f"- **Limit:** {max_chars} characters\n\n"
                "Please reduce the PR scope or review critical files manually."
            )
            return {"final_report": error_msg}

        # 3. Quick exit if no findings
        if not logic_data and not style_data:
            logger.info("supervisor_node: No findings to report.")
            final_report = (
                "## ✅ Automated PR Review\n\n"
                "No critical issues or style suggestions detected."
            )
            tool_call = {
                "name": "post_comment",
                "args": {"pr_url": pr_url, "comment_body": final_report},
                "id": "call_fast_exit",
            }

            message = AIMessage(
                content="No issues found. Posting positive review.",
                tool_calls=[tool_call],
            )

            return {"final_report": final_report, "messages": [message]}

        # 4. Prepare Context
        logic_text = "\n".join(f"- {str(item)}" for item in logic_data)
        style_text = "\n".join(f"- {str(item)}" for item in style_data)

        # Truncate diff for prompt context (keep it focused)
        # We checked safety above; this truncate is just for the prompt context
        diff_context = (
            pr_diff[:10000] + "...(truncated for context)"
            if len(pr_diff) > 10000
            else pr_diff
        )

        user_msg = (
            f"PR CONTEXT:\n{diff_context}\n\n"
            f"LOGIC FINDINGS:\n{logic_text}\n\n"
            f"STYLE FINDINGS:\n{style_text}\n\n"
            "INSTRUCTIONS:\n"
            "1. Group into '🚨 Security & Logic' and '🎨 Style'.\n"
            "2. Deduplicate findings intelligently.\n"
            "3. If a section is empty, mark it 'No issues found'.\n"
            "4. Be concise and professional.\n"
            "5. Output Markdown only."
        )

        # 6. Call LLM
        model_name = os.getenv("MODEL_HEAVY", "llama-3.3-70b-versatile")
        llm = ChatGroq(temperature=0, model_name=model_name)

        response = llm.invoke(
            [
                {"role": "system", "content": ORCHESTRATOR_PROMPT},
                {"role": "user", "content": user_msg},
            ]
        )

        logger.info("supervisor_node: Final report generated successfully.")
        final_report = response.content
        tool_call = {
            "name": "post_comment",
            "args": {"pr_url": pr_url, "comment_body": final_report},
            "id": "call_llm_generated",
        }

        # Kreiramo poruku koja simulira da je LLM pozvao alat
        message = AIMessage(
            content="Generated report. Posting to GitHub...", tool_calls=[tool_call]
        )

        return {"final_report": final_report, "messages": [message]}

    except Exception as e:
        logger.error(f"supervisor_node: Critical error - {e}")
        return {"final_report": f"## ⚠️ System Error\nFailed to generate report: {e}"}
>>>>>>> 886b8f2d42f9adcea5a6180eff32a839f434c92e
