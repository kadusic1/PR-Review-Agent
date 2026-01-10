#!/usr/bin/env python3
"""Runnable test for `agents.supervisor.supervisor_node`.

This script mocks `langchain_groq.ChatGroq` and `dotenv.load_dotenv`,
invokes `supervisor_node` with sample `state`, and prints the resulting
`final_report` as UTF-8 to preserve emoji characters.

Usage:
    python scripts/run_supervisor_test.py
"""

from types import SimpleNamespace
import types
import sys
import os

# Ensure repo root is on PYTHONPATH
ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

# Mock external dependencies used by the supervisor
fake_mod = types.ModuleType("langchain_groq")


class ChatGroq:
    def __init__(self, *args, **kwargs):
        pass

    def invoke(self, messages):
        # Return a simple formatted Markdown reply to simulate model output
        content = (
            "# Automated PR Review 🧾\n\n"
            "## ⚠️ Security/Logic Issues\n\n"
            "- Potential SQL injection in `execute_query()` — validate inputs.\n\n"
            "## 🎨 Style Suggestions\n\n"
            "- Fix PEP8 line length in `long_line_example`."
        )
        return SimpleNamespace(content=content)


fake_mod.ChatGroq = ChatGroq
sys.modules["langchain_groq"] = fake_mod

# Mock dotenv
fake_dotenv = types.ModuleType("dotenv")
fake_dotenv.load_dotenv = lambda *a, **k: None
sys.modules["dotenv"] = fake_dotenv

# Import and run the supervisor
from agents.supervisor import supervisor_node


def main():
    state = {
        "pr_diff": (
            "diff --git a/app.py b/app.py\n"
            '+ user_input = request.args.get("q")\n'
            '+ db.execute("SELECT * FROM users WHERE name = %s" % user_input)'
        ),
        "logic_comments": [
            "- SQL injection possible in `db.execute` when using string formatting",
            "Potential SQL injection in `execute_query()` — validate inputs.",
        ],
        "style_comments": [
            "* Line exceeds 120 characters in `long_line_example`",
            "* Line exceeds 120 characters in `long_line_example`",  # duplicate
        ],
        "final_report": "",
    }

    result = supervisor_node(state)
    out = result.get("final_report", "")
    # Write raw UTF-8 bytes to stdout so emojis render correctly
    sys.stdout.buffer.write(out.encode("utf-8"))


if __name__ == "__main__":
    main()
