# LangGraph definicija: Nodes (čvorovi) i Edges (veze)

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition
from core.state import AgentState
from agents.logic_agent import logic_node
from agents.style_agent import style_node
from agents.supervisor import supervisor_node
from utils import post_comment


def build_graph():
    """
    Creates and compiles the LangGraph workflow for the multi-agent PR review system.

    Adds logic, style, and supervisor nodes, sets parallel entry,
    connects to supervisor and END, and returns the compiled app.

    To draw the graph you can use: `app.get_graph().draw_ascii()`

    Returns:
            app: Compiled LangGraph workflow ready for execution.

    Example:
            >>> app = build_graph()
            >>> app.get_graph().draw_ascii()
    """

    # Initialize the state graph
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("logic", logic_node)
    graph.add_node("style", style_node)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("tools", ToolNode([post_comment]))

    # Add edges
    graph.add_edge("__start__", "logic")
    graph.add_edge("__start__", "style")
    graph.add_edge("logic", "supervisor")
    graph.add_edge("style", "supervisor")
    # Add conditional edge based on supervisor output
    graph.add_conditional_edges(
        "supervisor", tools_condition, {"tools": "tools", END: END}
    )
    graph.add_edge("tools", END)

    app = graph.compile()
    return app
