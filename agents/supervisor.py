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
from utils import ORCHESTRATOR_PROMPT

from dotenv import load_dotenv

from langchain_groq import ChatGroq

from core.state import AgentState

load_dotenv()

logger = logging.getLogger(__name__)


import os
import logging
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from core.state import AgentState

load_dotenv()

logger = logging.getLogger(__name__)


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
            return {
                "final_report": (
                    "## ✅ Automated PR Review\n\n"
                    "No critical issues or style suggestions detected."
                )
            }

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
        return {"final_report": response.content}

    except Exception as e:
        logger.error(f"supervisor_node: Critical error - {e}")
        return {"final_report": f"## ⚠️ System Error\nFailed to generate report: {e}"}
