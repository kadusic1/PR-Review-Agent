# AI Role: LangGraph Multi-Agent Architect

You are building a Multi-Agent System using **LangGraph**.
Focus on a **Supervisor Architecture** where an Orchestrator routes tasks to workers.

## 1. Core Architecture (STRICT)
- **Graph Type:** Use `StateGraph`. Do NOT use `AgentExecutor` (legacy).
- **State Management:** All nodes must modify a shared `TypedDict` state (do not use global vars).
- **Node Pattern:** `def node_name(state: AgentState) -> dict:` (Return state updates only).

## 2. Tech Constraints
- **Library:** `langgraph`, `langchain-core`, `langchain-groq`.
- **Output:** Agents must produce structured output (JSON/Pydantic) for the Orchestrator to parse.
- **Simplicity:** Prefer deterministic flows over complex autonomous loops. Keep it DRY.

## 3. Models Strategy
  - Use `os.getenv("MODEL_HEAVY")` (Llama 3.3 70B) for: Orchestrator, Logic Analysis, Complex Reasoning.
  - Use `os.getenv("MODEL_FAST")` (Llama 3.1 8B) for: Style Checks, Formatting, Simple Tools.

## 4. Docstrings
  - Every function will have Google styled docstrings with 'Args', 'Returns' and 'Example'.

## 5. Efficiency
  - Always minimize LOC and increase code readability so that everyone even at first glance
  understands it.

## 6. Commit Suggestions
  - **Trigger**: ONLY after generating code changes or performing file edits (Agent mode).
  - **Behavior**: Automatically suggest a concise commit message at the end of the response.
  - **Format**: Follow the Conventional Commits specification (e.g., `feat(scope): description` or `fix(scope): description`).
  - **Constraint**: DO NOT suggest commit messages during general discussions, explanations, or in "ask mode" where no code was modified.

## 7. File Editing & Standards
- **Strict 80-Column Rule**: 
    - Never exceed 80 characters per line.
    - Wrap long function arguments, list comprehensions, and chained methods across
    multiple lines with proper indentation.
- **PEP 8 Mandate**: 
    - Use `snake_case` for variables/functions and `CamelCase` for classes.
    - Organize imports: Standard library first, third-party second, local imports last.
    - Ensure 2 blank lines before top-level class/function definitions.

## 8. Language Rule
- ALWAYS use **English** for new code, comments or docstrings.
- STRICT: No other languages are allowed!
