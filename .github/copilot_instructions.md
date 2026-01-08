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
