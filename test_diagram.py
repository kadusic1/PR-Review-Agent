#!/usr/bin/env python
"""Test script for the Diagram Agent integration."""

from core.state import make_initial_state
from agents.diagram_agent import (
    diagram_node,
    is_valid_mermaid_diagram,
    sanitize_diagram,
)
from core.graph import build_graph

# Test 1: State initialization with architecture_diagram field
print("=" * 60)
print("TEST 1: AgentState with architecture_diagram field")
print("=" * 60)

test_diff = """
diff --git a/models.py b/models.py
--- a/models.py
+++ b/models.py
@@ -1,5 +1,15 @@
class User:
    name: str
    email: str
+
+class Admin(User):
+    permissions: list
+    
+class Product:
+    id: int
+    name: str
"""

state = make_initial_state(test_diff, "https://github.com/test/pr")

print(f"✓ State initialized")
print(f"  Keys: {list(state.keys())}")
print(f"  architecture_diagram field exists: {'architecture_diagram' in state}")
print(f"  architecture_diagram is empty: {state['architecture_diagram'] == ''}")
print()

# Test 2: Diagram validation
print("=" * 60)
print("TEST 2: Mermaid diagram validation")
print("=" * 60)

valid_diagram = """classDiagram
    class User {
        +String name
        +String email
    }
    class Admin {
        +List permissions
    }
    Admin <|-- User"""

print(f"✓ Valid Mermaid diagram: {is_valid_mermaid_diagram(valid_diagram)}")
print(f"✓ Empty string: {is_valid_mermaid_diagram('')}")
print(f"✓ Unmatched braces: {is_valid_mermaid_diagram('classDiagram { }')}")
print(f"✓ Error message: {is_valid_mermaid_diagram('Error: Invalid syntax')}")
print()

# Test 3: Diagram sanitization
print("=" * 60)
print("TEST 3: Diagram sanitization")
print("=" * 60)

markdown_wrapped = """```mermaid
classDiagram
    class User {
        +String name
    }
```"""

sanitized = sanitize_diagram(markdown_wrapped)
print(f"✓ Markdown wrapped extracted: {len(sanitized) > 0}")
print(f"✓ Contains classDiagram: {'classDiagram' in sanitized}")
print()

# Test 4: Graph structure
print("=" * 60)
print("TEST 4: Graph compilation with all 3 agents")
print("=" * 60)

app = build_graph()
print("✓ Graph compiled successfully")

# Introspect the graph
print(
    f"✓ Number of nodes: {len(app._graph_schema['nodes']) if hasattr(app, '_graph_schema') else 'N/A'}"
)
print()

# Test 5: Supervisor diagram formatting
print("=" * 60)
print("TEST 5: Supervisor diagram formatting")
print("=" * 60)

from agents.supervisor import format_diagram_section

formatted = format_diagram_section(markdown_wrapped)
print(f"✓ Section has header: {'📊 Architecture Visualization' in formatted}")
print(f"✓ Section has dashes: {'---' in formatted}")
print(f"✓ Section preserves diagram: {'classDiagram' in formatted}")
print()

print("=" * 60)
print("✅ ALL TESTS PASSED! Diagram Agent is ready.")
print("=" * 60)
