"""
One-shot runner for the generated agent.
"""

from __future__ import annotations

import sys

from logic import run_agent_task


# Read a prompt from argv or stdin and print the generated response.
def main() -> int:
    prompt = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    uploaded_paths: list[str] = []
    is_interactive = sys.stdin.isatty()
    if not prompt and is_interactive:
        prompt = input("Prompt: ").strip()
    if not prompt:
        print("A prompt is required.")
        return 1

    print(run_agent_task(prompt, uploaded_paths=uploaded_paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
