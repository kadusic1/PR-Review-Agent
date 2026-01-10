"""Core agent state definitions for the PR review system.

This module defines the shared state structure that flows through
the multi-agent LangGraph workflow.
"""

from typing import Annotated, List, TypedDict
import operator
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """Shared state passed between agents in the PR review workflow.

    This TypedDict defines the data structure that all agents read from
    and write to. The `operator.add` annotation ensures that list fields
    accumulate comments from multiple agents rather than overwriting them.

    Fields:
        pr_diff: The pull-request diff or code under review.
        logic_comments: Accumulated logic/security/bug comments from agents.
            Uses operator.add to append rather than replace.
        style_comments: Accumulated style/formatting comments from agents.
            Uses operator.add to append rather than replace.
        final_report: Aggregated final report produced by the orchestrator.

    Example:
        >>> state: AgentState = {
        ...     "pr_diff": "diff --git a/file.py b/file.py...",
        ...     "logic_comments": [],
        ...     "style_comments": [],
        ...     "final_report": "",
        ... }
        >>> # Within the LangGraph framework, if Agent 1 returns:
        >>> # {"logic_comments": ["Bug: SQL injection"]}
        >>> # and Agent 2 returns:
        >>> # {"logic_comments": ["Bug: Missing validation"]}
        >>> # The state will be automatically merged, resulting in:
        >>> # state["logic_comments"] == ["Bug: SQL injection", "Bug: Missing validation"]
    """

    pr_diff: str
    logic_comments: Annotated[List[str], operator.add]
    style_comments: Annotated[List[str], operator.add]
    final_report: str
    pr_url: str
    messages: Annotated[List[BaseMessage], operator.add]


def make_initial_state(pr_diff: str = "", pr_url: str = "") -> AgentState:
    """Create a minimal AgentState with empty comment lists.

    This helper function initializes a clean state object with
    empty lists for comments and an empty final report.

    Args:
        pr_diff: The pull-request diff or code snapshot to seed the state.
            Defaults to empty string if not provided.

    Returns:
        An AgentState instance with empty comment lists and empty final report.

    Example:
        >>> s = make_initial_state("diff --git a/main.py...")
        >>> s["pr_diff"]
        'diff --git a/main.py...'
        >>> s["logic_comments"]
        []
        >>> s["style_comments"]
        []
    """
    if pr_diff is None or pr_url is None:
        raise ValueError('pr_diff and pr_url cannot be None')          

    return {
        "pr_diff": pr_diff,
        "logic_comments": [],
        "style_comments": [],
        "final_report": "",
        "pr_url": pr_url,
        "messages": [],
    }
