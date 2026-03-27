"""
Lightweight static checks for generated agent projects (used by edit-chat).

Runs `python -m py_compile` on whitelisted .py files and tries `import logic`
in the agent directory. Does not start Gradio/FastAPI servers.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Only compile these; avoid executing app.py / main.py beyond compile.
_COMPILE_NAMES = ("logic.py", "app.py", "main.py", "run_agent.py")

_MAX_DIAG_OUTPUT = 12_000
_SUBPROCESS_TIMEOUT = 45


def collect_static_diagnostics(agent_dir: Path) -> tuple[str, list[str]]:
    """
    Return (multiline block for the LLM, human-readable log lines for activity).
    """
    agent_dir = agent_dir.resolve()
    if not agent_dir.is_dir():
        return "", [f"[diagnostics] skip — not a directory: {agent_dir}"]

    logs: list[str] = []
    lines: list[str] = ["=== AUTOMATED_STATIC_DIAGNOSTICS ===", f"Agent directory: {agent_dir}", ""]

    for name in _COMPILE_NAMES:
        path = agent_dir / name
        if not path.is_file():
            continue
        logs.append(f"[diagnostics] py_compile {name}…")
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "py_compile", str(path)],
                cwd=str(agent_dir),
                capture_output=True,
                text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            msg = f"TIMEOUT after {_SUBPROCESS_TIMEOUT}s"
            lines.append(f"--- py_compile {name} ---\n{msg}\n")
            logs.append(f"[diagnostics] {name}: {msg}")
            continue
        except OSError as exc:
            msg = f"OS error: {exc}"
            lines.append(f"--- py_compile {name} ---\n{msg}\n")
            logs.append(f"[diagnostics] {name}: {msg}")
            continue

        if proc.returncode == 0:
            lines.append(f"--- py_compile {name} ---\nOK\n")
            logs.append(f"[diagnostics] {name}: OK (py_compile)")
        else:
            err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
            if len(err) > 4000:
                err = err[:4000] + "\n... [truncated]"
            lines.append(f"--- py_compile {name} ---\n{err}\n")
            logs.append(f"[diagnostics] {name}: FAILED py_compile")

    logic_py = agent_dir / "logic.py"
    if logic_py.is_file():
        logs.append("[diagnostics] import logic…")
        try:
            proc = subprocess.run(
                [sys.executable, "-c", "import logic"],
                cwd=str(agent_dir),
                capture_output=True,
                text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            msg = f"TIMEOUT after {_SUBPROCESS_TIMEOUT}s"
            lines.append("--- import logic ---\n" + msg + "\n")
            logs.append("[diagnostics] import logic: TIMEOUT")
        except OSError as exc:
            msg = f"OS error: {exc}"
            lines.append("--- import logic ---\n" + msg + "\n")
            logs.append(f"[diagnostics] import logic: {msg}")
        else:
            if proc.returncode == 0:
                lines.append("--- import logic ---\nOK\n")
                logs.append("[diagnostics] import logic: OK")
            else:
                err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
                if len(err) > 6000:
                    err = err[:6000] + "\n... [truncated]"
                lines.append("--- import logic ---\n" + err + "\n")
                logs.append("[diagnostics] import logic: FAILED")

    block = "\n".join(lines).strip()
    if len(block) > _MAX_DIAG_OUTPUT:
        block = block[:_MAX_DIAG_OUTPUT] + "\n... [diagnostics truncated]\n"

    return block, logs
