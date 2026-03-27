"""
LLM-assisted editing of generated agent source files (whitelisted paths only).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI

from .agent_diagnostics import collect_static_diagnostics
from .generator import get_generated_agent
from .requirements_builder import REACT_UI_FILES
from .runner import stop_local_ui_server

# Whitelisted paths relative to the agent directory (forward slashes). No path traversal.
EDITABLE_ROOT_FILES = frozenset(
    {
        "logic.py",
        "app.py",
        "main.py",
        "run_agent.py",
        "requirements.txt",
    }
)
EDITABLE_REACT_UI_RELATIVE = frozenset(REACT_UI_FILES)
EDITABLE_RELATIVE_PATHS: frozenset[str] = EDITABLE_ROOT_FILES | EDITABLE_REACT_UI_RELATIVE

MAX_TOTAL_SOURCE_CHARS = 220_000


def _normalize_editable_rel(rel: str) -> str:
    s = rel.strip().replace("\\", "/")
    if not s or s.startswith("/"):
        raise ValueError(f"Invalid relative path: {rel!r}")
    parts: list[str] = []
    for p in s.split("/"):
        if p in ("", "."):
            continue
        if p == "..":
            raise ValueError("Path traversal is not allowed.")
        parts.append(p)
    return "/".join(parts)


def _safe_agent_file(agent_dir: Path, rel: str) -> Path:
    norm = _normalize_editable_rel(rel)
    if norm not in EDITABLE_RELATIVE_PATHS:
        raise ValueError(f"Editing {rel!r} is not allowed.")
    root = agent_dir.resolve()
    path = (root / norm).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("Path escapes agent directory.") from exc
    return path


def read_editable_sources(agent_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in sorted(EDITABLE_RELATIVE_PATHS):
        path = agent_dir / rel
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            out[rel] = text
    return out


def _truncate_sources(files: dict[str, str]) -> tuple[dict[str, str], bool]:
    total = sum(len(v) for v in files.values())
    if total <= MAX_TOTAL_SOURCE_CHARS:
        return files, False
    # Proportionally trim largest files first.
    remaining = MAX_TOTAL_SOURCE_CHARS
    sizes = sorted(((len(content), name, content) for name, content in files.items()), reverse=True)
    trimmed: dict[str, str] = {}
    for _size, name, content in sizes:
        budget = max(0, min(len(content), remaining // max(1, len(files) - len(trimmed))))
        if budget < len(content):
            trimmed[name] = content[:budget] + "\n\n# ... [truncated for editor context; file is longer on disk]\n"
        else:
            trimmed[name] = content
        remaining -= len(trimmed[name])
    return trimmed, True


def _build_openai_client(settings: dict[str, str]) -> tuple[OpenAI, str]:
    openai_key = (settings.get("openai_api_key") or "").strip()
    gemini_key = (settings.get("gemini_api_key") or "").strip()
    if openai_key:
        return OpenAI(api_key=openai_key), "openai"
    if gemini_key:
        return OpenAI(
            api_key=gemini_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ), "gemini"
    raise ValueError("Add an OpenAI or Gemini API key in Settings to use AI refine.")


def _parse_model_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}\s*$", raw)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError("Model did not return valid JSON.")


def _log_ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def apply_agent_edits(
    user_id: int,
    agent_id: str,
    messages: list[dict[str, str]],
    *,
    settings: dict[str, str],
    include_static_diagnostics: bool = True,
    runtime_error: str = "",
) -> tuple[str, list[str], list[str]]:
    """
    Run one chat turn: read whitelisted files, call LLM, write back any returned files.

    Returns (assistant_message, list of updated relative paths, activity_log lines).
    """
    logs: list[str] = []

    def trace(msg: str) -> None:
        logs.append(f"[{_log_ts()}] {msg}")
    if not messages:
        raise ValueError("At least one message is required.")
    if not any(m.get("role") == "user" for m in messages):
        raise ValueError("Include at least one user message.")

    metadata = get_generated_agent(user_id, agent_id)
    trace(f"Loaded agent {metadata.agent_name!r} ({agent_id}) — frontend={metadata.frontend_type}")
    agent_dir = Path(metadata.agent_dir)
    if not agent_dir.is_dir():
        raise FileNotFoundError(f"Agent directory missing: {agent_dir}")

    stop_local_ui_server(agent_id)
    trace("Stopped embedded/local UI for this agent (if it was running).")

    files = read_editable_sources(agent_dir)
    if not files:
        raise ValueError("No editable source files found for this agent.")

    for name in sorted(files.keys()):
        trace(f"Read {name} ({len(files[name]):,} chars).")
    files_for_prompt, was_truncated = _truncate_sources(files)
    if was_truncated:
        trace("Truncated large files to fit editor context budget (see system note to model).")

    client, provider_label = _build_openai_client(settings)
    model = (metadata.model or "gpt-4o-mini").strip()
    trace(f"Calling LLM ({provider_label}, model={model!r}) with JSON response…")

    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = (m.get("content") or "").strip()
            break
    if last_user:
        preview = last_user.replace("\n", " ")[:220]
        if len(last_user) > 220:
            preview += "…"
        trace(f"Latest user instruction: {preview}")

    allowed_list = sorted(EDITABLE_RELATIVE_PATHS)
    system = f"""You are a senior engineer helping refine a small generated AI agent project (Python and, when present, React/Vite).

The agent is named {metadata.agent_name!r}. Frontend type: {metadata.frontend_type}.
You may ONLY suggest changes by returning JSON (no markdown fences). Shape:
{{
  "assistant_message": "Clear reply to the user about what you changed or why you could not.",
  "files": {{
    "logic.py": "<full new file content>",
    "react-ui/src/App.tsx": "<full new file content>"
  }}
}}

Rules:
- Include "files" only for files you actually changed. Each value must be the COMPLETE file text.
- Only these path keys are allowed in "files" (use forward slashes exactly as listed): {allowed_list!r}
- Python: preserve working imports, env vars (OPENAI_API_KEY, ALPHA_AGENT_PORT, etc.), and valid syntax.
- React/Vite: preserve API base URL behavior (VITE_API_URL / fetch to the FastAPI backend in main.py). Keep TypeScript and JSX valid.
- If the user only needs explanation or the change is unsafe, omit "files" and explain in assistant_message.
- If new pip packages are needed, update requirements.txt in "files" and mention it in assistant_message.
- When AUTOMATED_STATIC_DIAGNOSTICS and/or USER_REPORTED_RUNTIME_ERROR sections appear, treat them as the
  highest-priority bugs to fix. Fix syntax/import errors first, then runtime/traceback issues, then the user's chat request.
- For Gradio errors (e.g. Chatbot message format), align app.py with logic.py expectations (e.g. type="messages" and dict history).
- Gradio Chatbot: Gradio 6+ removed the type= kwarg (use plain gr.Chatbot(height=...) with dict messages). Gradio 4/5 may need type="messages". Never use render_as=.
{"- NOTE: Some file contents were truncated in the prompt; read carefully and do not invent missing sections." if was_truncated else ""}
"""

    diag_block = ""
    if include_static_diagnostics:
        diag_block, diag_logs = collect_static_diagnostics(agent_dir)
        for line in diag_logs:
            trace(line)

    runtime_error = (runtime_error or "").strip()
    if len(runtime_error) > 24_000:
        runtime_error = runtime_error[:24_000] + "\n... [truncated]"

    parts: list[str] = []
    for name in sorted(files_for_prompt.keys()):
        parts.append(f"=== FILE: {name} ===\n{files_for_prompt[name]}\n")
    if diag_block:
        parts.append(diag_block + "\n")
    if runtime_error:
        parts.append("=== USER_REPORTED_RUNTIME_ERROR (traceback or stderr from running the agent) ===\n")
        parts.append(runtime_error + "\n\n")
    parts.append("=== CHAT (most recent last) ===\n")
    for m in messages[-24:]:
        role = m.get("role", "user")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        parts.append(f"{role.upper()}:\n{content}\n")
    user_block = "\n".join(parts)

    chat_kw: dict[str, Any] = {
        "model": model,
        "temperature": min(0.3, float(metadata.temperature or 0.2)),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_block},
        ],
    }
    try:
        response = client.chat.completions.create(
            **chat_kw,
            response_format={"type": "json_object"},
        )
        trace("LLM returned (json_object mode).")
    except Exception:
        trace("json_object mode failed; retrying without response_format.")
        response = client.chat.completions.create(**chat_kw)
    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        raise RuntimeError("Empty model response.")

    trace(f"Parsed model output ({len(raw):,} chars).")
    data = _parse_model_json(raw)
    trace("Extracted JSON payload (assistant_message + optional files).")
    assistant_message = str(data.get("assistant_message") or "").strip()
    if not assistant_message:
        assistant_message = "Done."

    updated: list[str] = []
    file_updates = data.get("files")
    if isinstance(file_updates, dict):
        if not file_updates:
            trace("No file changes in model JSON (empty or omitted file entries).")
        for rel_raw, content in file_updates.items():
            if not isinstance(rel_raw, str) or not isinstance(content, str):
                continue
            try:
                norm = _normalize_editable_rel(rel_raw)
            except ValueError:
                trace(f"Skipped invalid file key in model JSON: {rel_raw!r}")
                continue
            if norm not in EDITABLE_RELATIVE_PATHS:
                trace(f"Skipped disallowed file key in model JSON: {rel_raw!r}")
                continue
            path = _safe_agent_file(agent_dir, norm)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
            updated.append(norm)
            trace(f"Wrote {norm} ({len(content):,} chars).")
    elif file_updates is not None:
        trace(f"Ignored non-object 'files' in model JSON ({type(file_updates).__name__}).")
    else:
        trace("No file changes in model JSON (explanation-only turn).")

    if updated:
        trace(f"Done — updated {len(updated)} file(s): {', '.join(sorted(set(updated)))}.")
    else:
        trace("Done — disk unchanged; see assistant reply.")

    return assistant_message, sorted(set(updated)), logs
