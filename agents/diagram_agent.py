"""Architecture Diagram Agent for visual representation of code changes.

This module generates Mermaid JS class diagrams that visualize architectural
changes and structural modifications detected in the PR diff.

Uses Llama 3.3 70B (MODEL_HEAVY) for high-precision Mermaid syntax generation
with built-in validation and error correction capabilities.
"""

import os
import re
import logging
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from core.state import AgentState
from utils.common import DIAGRAM_PROMPT

load_dotenv()

logger = logging.getLogger(__name__)


# DIAGRAM_PROMPT is defined in utils/common.py to keep prompts centralized


def is_valid_mermaid_diagram(diagram_text: str) -> bool:
    """
    Validates that the diagram contains proper Mermaid classDiagram syntax.

    Args:
        diagram_text: The diagram text to validate.

    Returns:
        bool: True if the diagram appears to be valid Mermaid code.

    Checks:
        - Presence of 'classDiagram' keyword
        - Proper closing of all braces
        - Absence of common error patterns
    """
    if not diagram_text:
        return False

    # Check for classDiagram or graph keyword
    has_diagram_type = "classDiagram" in diagram_text or "graph" in diagram_text

    # Count braces to ensure they're balanced
    open_braces = diagram_text.count("{")
    close_braces = diagram_text.count("}")

    # Basic validation: must have diagram type and balanced braces
    if not has_diagram_type or open_braces != close_braces:
        return False

    # Check for common error patterns
    error_patterns = [
        r"^Error:",  # Error messages
        r"^I apologize",  # Apology responses
        r"^I cannot",  # Refusal responses
        r"^I don't",  # Refusal responses
    ]

    for pattern in error_patterns:
        if re.search(pattern, diagram_text, re.MULTILINE | re.IGNORECASE):
            return False

    return True


def sanitize_diagram(diagram_text: str) -> str:
    """
    Cleans and sanitizes the diagram output by removing non-code text.

    Args:
        diagram_text: The raw diagram text from the LLM.

    Returns:
        str: Cleaned diagram code, or empty string if extraction fails.

    Attempts to:
        1. Extract code from markdown code blocks (```mermaid...```)
        2. Remove leading/trailing whitespace
        3. Validate the result
    """
    if not diagram_text:
        return ""

    # Try to extract from markdown code block
    mermaid_block = re.search(
        r"```(?:mermaid)?\s*\n?(.*?)\n?```",
        diagram_text,
        re.DOTALL | re.IGNORECASE,
    )

    if mermaid_block:
        cleaned = mermaid_block.group(1).strip()
    else:
        # If no code block, try to find the classDiagram section
        classDiagram_match = re.search(
            r"(classDiagram.*?)(?:\n```|$)",
            diagram_text,
            re.DOTALL | re.IGNORECASE,
        )
        if classDiagram_match:
            cleaned = classDiagram_match.group(1).strip()
        else:
            cleaned = diagram_text.strip()

    # Remove any explanatory text before or after
    lines = cleaned.split("\n")
    diagram_lines = []
    in_diagram = False

    for line in lines:
        # Start collecting when we see classDiagram or graph
        if re.match(r"^\s*(classDiagram|graph)", line):
            in_diagram = True

        if in_diagram:
            diagram_lines.append(line)

    result = "\n".join(diagram_lines).strip()

    # Final validation
    if is_valid_mermaid_diagram(result):
        return result
    else:
        logger.warning("diagram_agent: Sanitization failed validation")
        return ""


def diagram_node(state: AgentState) -> dict:
    """
    Generates a Mermaid JS class diagram representing architectural changes.

    This agent analyzes the PR diff for structural changes and generates
    a visual representation using Mermaid class diagram syntax.

    Args:
        state: The shared AgentState containing pr_diff to analyze.

    Returns:
        A dict with 'architecture_diagram' key containing the Mermaid code
        (or empty string if generation fails).

    Example:
        >>> state = {"pr_diff": "diff --git a/models.py...", ...}
        >>> result = diagram_node(state)
        >>> result["architecture_diagram"]
        '```mermaid\\nclassDiagram\\n    class User {...}'
    """
    try:
        pr_diff = state.get("pr_diff", "")
        if not pr_diff:
            logger.warning("diagram_node: No PR diff provided")
            return {"architecture_diagram": ""}

        # Use the heavy model (Llama 3.3 70B) for precise Mermaid syntax
        model_name = os.getenv("MODEL_HEAVY", "llama-3.3-70b-versatile")
        llm = ChatGroq(temperature=0, model_name=model_name)

        # Prepare context window (keep it focused)
        diff_context = (
            pr_diff[:8000] + "\n...(truncated for context)"
            if len(pr_diff) > 8000
            else pr_diff
        )

        user_prompt = f"""Analyze the following code changes and generate a Mermaid class diagram
that visualizes the architectural modifications:

{diff_context}

Generate ONLY valid Mermaid classDiagram code. No explanations, no comments inside the diagram."""

        messages = [
            {"role": "system", "content": DIAGRAM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        response = llm.invoke(messages)
        raw_diagram = response.content

        # Sanitize and validate
        cleaned_diagram = sanitize_diagram(raw_diagram)

        if cleaned_diagram:
            logger.info("diagram_node: Diagram generated and validated successfully")
            # Wrap in markdown code block for GitHub rendering
            final_diagram = f"```mermaid\n{cleaned_diagram}\n```"
            return {"architecture_diagram": final_diagram}
        else:
            logger.warning("diagram_node: Generated diagram failed validation")
            return {"architecture_diagram": ""}

    except Exception as e:
        logger.error(f"diagram_node: Error during diagram generation - {e}")
        return {"architecture_diagram": ""}
