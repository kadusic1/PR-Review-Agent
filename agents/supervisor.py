"""Supervisor (Orchestrator) for the multi-agent PR review system.

Orchestrates the final reporting by:
1. Collecting findings from logic, style, and diagram agents
2. Validating and sanitizing the generated Mermaid diagram
3. Positioning the architecture diagram at the TOP of the report
4. Deduplicating findings and producing a professional GitHub PR review
5. Posting the final report as a GitHub comment

Uses llama-3.3-70b-versatile for high-quality report generation.

Behavior guarantees:
- Diagram validation: Checks for valid Mermaid syntax before including
- Diagram positioning: Always places diagram section first (📊 Architecture Visualization)
- Safe fallback: If diagram is invalid, silently omits it without breaking the report
- Produces clearly separated sections for Security/Logic, Architecture, and Style
"""

from __future__ import annotations

import logging
import os
import re
from utils import ORCHESTRATOR_PROMPT
from langchain_core.messages import AIMessage
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from core.state import AgentState

load_dotenv()

logger = logging.getLogger(__name__)


def is_valid_mermaid(diagram: str) -> bool:
    """
    Validates that a diagram string contains valid Mermaid syntax.

    Args:
        diagram: The diagram string to validate.

    Returns:
        bool: True if the diagram appears to be valid Mermaid code.

    Validation criteria:
        - Contains 'classDiagram' or 'graph' keyword
        - Has balanced braces
        - Doesn't contain error patterns
    """
    if not diagram:
        return False

    # Check for diagram type
    has_diagram_type = "classDiagram" in diagram or "graph" in diagram

    # Count braces
    open_braces = diagram.count("{")
    close_braces = diagram.count("}")

    if not has_diagram_type or open_braces != close_braces:
        return False

    # Check for error patterns
    error_patterns = [
        r"^Error:",
        r"^I apologize",
        r"^I cannot",
        r"^I don't",
    ]

    for pattern in error_patterns:
        if re.search(pattern, diagram, re.MULTILINE | re.IGNORECASE):
            return False

    return True


def format_diagram_section(diagram: str) -> str:
    """
    Formats the architecture diagram as a GitHub-friendly section.

    Args:
        diagram: The raw Mermaid diagram (may or may not be in code block).

    Returns:
        str: Formatted diagram section ready for insertion into report,
             or empty string if diagram is invalid.
    """
    if not diagram or not is_valid_mermaid(diagram):
        logger.warning(
            "supervisor_node: Diagram validation failed, omitting from report"
        )
        return ""

    # Ensure diagram is wrapped in markdown code block
    if not diagram.startswith("```"):
        diagram = f"```mermaid\n{diagram}\n```"

    section = (
        "## 📊 Architecture Visualization\n\n"
        "This diagram shows the structural changes introduced in this PR:\n\n"
        f"{diagram}\n\n"
        "---\n\n"
    )

    return section


def supervisor_node(state: AgentState) -> dict:
    """
    Orchestrates the final PR review report with architecture visualization.

    Combines findings from all agents (logic, style, diagram) into a professional
    GitHub PR review. Positions the architecture diagram at the top and validates
    all outputs before final report assembly.

    Args:
        state (AgentState): Shared state containing findings and pr_diff.

    Returns:
        dict: A dictionary with 'final_report' and 'messages' keys.

    Features:
        - Diagram validation and sanitization
        - Safety checks for PR size
        - Automatic handling of missing findings
        - Professional Markdown formatting
    """
    try:
        # 1. Extract inputs from all agents
        logic_data = state.get("logic_comments", []) or []
        style_data = state.get("style_comments", []) or []
        architecture_diagram = state.get("architecture_diagram", "") or ""
        pr_diff = state.get("pr_diff", "") or ""
        pr_url = state.get("pr_url")

        if not pr_url:
            logger.warning("supervisor_node: pr_url not found in state.")
            return {
                "final_report": "## ⚠️ PR Review Aborted\n\n**Reason:** PR URL not provided."
            }

        # 2. SAFETY CHECK: Diff Size Limit
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

        # 3. Validate and format architecture diagram
        diagram_section = format_diagram_section(architecture_diagram)

        # 4. Quick exit if no findings and no diagram
        if not logic_data and not style_data and not diagram_section:
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

        # 5. Prepare findings context for LLM
        logic_text = "\n".join(f"- {str(item)}" for item in logic_data)
        style_text = "\n".join(f"- {str(item)}" for item in style_data)

        # Truncate diff for prompt context
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
            "5. Output Markdown only (no code blocks unless showing examples)."
        )

        # 6. Generate final report content from LLM
        model_name = os.getenv("MODEL_HEAVY", "llama-3.3-70b-versatile")
        llm = ChatGroq(temperature=0, model_name=model_name)

        response = llm.invoke(
            [
                {"role": "system", "content": ORCHESTRATOR_PROMPT},
                {"role": "user", "content": user_msg},
            ]
        )

        logger.info("supervisor_node: Final report content generated successfully.")
        findings_report = response.content

        # 7. ASSEMBLE FINAL REPORT: Diagram first, then findings
        final_report = diagram_section + findings_report

        # 8. Prepare tool call for GitHub posting
        tool_call = {
            "name": "post_comment",
            "args": {"pr_url": pr_url, "comment_body": final_report},
            "id": "call_llm_generated",
        }

        # Create AI message that simulates tool call
        message = AIMessage(
            content="Generated comprehensive report with architecture visualization. Posting to GitHub...",
            tool_calls=[tool_call],
        )

        logger.info("supervisor_node: Report assembly complete. Ready for posting.")
        return {"final_report": final_report, "messages": [message]}

    except Exception as e:
        logger.error(f"supervisor_node: Critical error - {e}")
        return {"final_report": f"## ⚠️ System Error\nFailed to generate report: {e}"}
