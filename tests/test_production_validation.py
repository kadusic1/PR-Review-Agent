#!/usr/bin/env python
"""
Comprehensive validation test for production deployment.
Ensures all components work seamlessly together.
"""

import sys
from core.state import AgentState, make_initial_state
from core.graph import build_graph
from agents.diagram_agent import (
    diagram_node,
    is_valid_mermaid_diagram,
    sanitize_diagram,
)
from agents.supervisor import supervisor_node, is_valid_mermaid, format_diagram_section


def test_imports():
    """Test all imports are clean."""
    print("TEST: Imports and Module Loads")
    try:
        from agents.logic_agent import logic_node
        from agents.style_agent import style_node
        from agents.diagram_agent import diagram_node
        from agents.supervisor import supervisor_node

        print("All agent imports successful")
        return True
    except Exception as e:
        print(f"Import failed: {e}")
        return False


def test_state_structure():
    """Test AgentState has all required fields."""
    print("\nTEST: AgentState Structure")
    required_fields = [
        "pr_diff",
        "logic_comments",
        "style_comments",
        "architecture_diagram",  # NEW FIELD
        "final_report",
        "pr_url",
        "messages",
    ]

    state = make_initial_state("test diff", "https://test.com")

    for field in required_fields:
        if field in state:
            print(f"Field '{field}' present")
        else:
            print(f"Field '{field}' missing")
            return False

    # Check types
    if isinstance(state["logic_comments"], list):
        print("logic_comments is list")
    else:
        print("logic_comments is not list")
        return False

    if isinstance(state["architecture_diagram"], str):
        print("architecture_diagram is str")
    else:
        print("architecture_diagram is not str")
        return False

    return True


def test_mermaid_validation():
    """Test Mermaid diagram validation."""
    print("\nTEST: Mermaid Validation")

    test_cases = [
        ("classDiagram\n    class User {}", True, "Valid classDiagram"),
        ("graph LR\n    A --> B", True, "Valid graph"),
        ("", False, "Empty string"),
        ("classDiagram { }", True, "Unbalanced braces still passes basic check"),
        ("Error: Invalid", False, "Error pattern detected"),
        ("I apologize, but I cannot", False, "Refusal pattern"),
    ]

    for diagram, expected, description in test_cases:
        result = is_valid_mermaid(diagram)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {description}: {result}")
        if result != expected:
            return False

    return True


def test_diagram_node_structure():
    """Test diagram node returns correct structure."""
    print("\nTEST: Diagram Node Output Structure")

    state = make_initial_state("test diff", "https://test.com")
    result = diagram_node(state)

    if "architecture_diagram" not in result:
        print("Missing 'architecture_diagram' key in output")
        return False
    print("Returns 'architecture_diagram' key")

    if isinstance(result["architecture_diagram"], str):
        print("architecture_diagram value is string")
    else:
        print("architecture_diagram value is not string")
        return False

    return True


def test_graph_compilation():
    """Test graph compiles without errors."""
    print("\nTEST: Graph Compilation")

    try:
        app = build_graph()
        print("Graph compiles successfully")

        # Check it's a compiled graph
        if hasattr(app, "invoke"):
            print("Graph has invoke method")
        else:
            print("Graph missing invoke method")
            return False

        return True
    except Exception as e:
        print(f"Graph compilation failed: {e}")
        return False


def test_supervisor_diagram_formatting():
    """Test supervisor formats diagrams correctly."""
    print("\nTEST: Supervisor Diagram Formatting")

    valid_diagram = "```mermaid\nclassDiagram\n    class User {}\n```"
    formatted = format_diagram_section(valid_diagram)

    checks = [
        ("Architecture Visualization" in formatted, "Header present"),
        ("```mermaid" in formatted, "Code block preserved"),
        ("---" in formatted, "Separator present"),
        (formatted.startswith("## 📊"), "Header at start"),
    ]

    for check, desc in checks:
        status = "✓" if check else "✗"
        print(f"  {status} {desc}")
        if not check:
            return False

    return True


def test_supervisor_with_diagram():
    """Test supervisor handles diagram in state."""
    print("\nTEST: Supervisor With Diagram in State")

    from unittest.mock import patch, MagicMock

    state = make_initial_state("test diff", "https://test.com")
    state["architecture_diagram"] = "```mermaid\nclassDiagram\n    class Test {}\n```"
    state["logic_comments"] = ["Sample finding"]

    mock_response = MagicMock()
    mock_response.content = "Test findings"

    with patch("agents.supervisor.ChatGroq") as mock_groq:
        mock_groq.return_value.invoke.return_value = mock_response
        result = supervisor_node(state)

    final_report = result.get("final_report", "")

    if "Architecture Visualization" in final_report:
        print("  ✓ Diagram section appears in final report")
    else:
        print("  ✗ Diagram section missing from final report")
        return False

    if final_report.find("📊") < final_report.find("Test findings"):
        print("  ✓ Diagram positioned before findings")
    else:
        print("  ✗ Diagram not positioned at top")
        return False

    return True


def test_circular_imports():
    """Test no circular import issues."""
    print("\nTEST: Circular Import Prevention")

    try:
        # This should work without circular import errors
        from agents.diagram_agent import diagram_node
        from core.graph import build_graph
        from agents.supervisor import supervisor_node

        print("  ✓ No circular imports detected")
        return True
    except ImportError as e:
        if "circular" in str(e).lower():
            print(f"  ✗ Circular import detected: {e}")
            return False
        raise


def main():
    """Run all tests."""
    print("=" * 70)
    print("COMPREHENSIVE PRODUCTION VALIDATION TEST")
    print("=" * 70)

    tests = [
        test_imports,
        test_state_structure,
        test_mermaid_validation,
        test_diagram_node_structure,
        test_graph_compilation,
        test_supervisor_diagram_formatting,
        test_supervisor_with_diagram,
        test_circular_imports,
    ]

    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append((test_func.__name__, result))
        except Exception as e:
            print(f"  ✗ Test raised exception: {e}")
            results.append((test_func.__name__, False))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        test_name = name.replace("test_", "").replace("_", " ").title()
        print(f"  {status}  {test_name}")

    print("=" * 70)
    print(f"Result: {passed}/{total} tests passed")
    print("=" * 70)

    if passed == total:
        print("\n🎉 ALL TESTS PASSED - READY FOR PRODUCTION 🚀\n")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
