"""
LLM-assisted editing of generated agent source files (whitelisted paths only).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import APIStatusError, OpenAI

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


def _build_openai_client(settings: dict[str, str], *, provider_id: str) -> tuple[OpenAI, str]:
    """Use the same provider the agent was generated with so model names and API match."""
    openai_key = (settings.get("openai_api_key") or "").strip()
    gemini_key = (settings.get("gemini_api_key") or "").strip()
    if provider_id == "openai":
        if not openai_key:
            raise ValueError(
                "This agent uses OpenAI. Add OPENAI_API_KEY to your Environment file to use Edit/fix agent.",
            )
        return OpenAI(api_key=openai_key), "openai"
    if provider_id == "gemini":
        if not gemini_key:
            raise ValueError(
                "This agent uses Gemini. Add GEMINI_API_KEY or GOOGLE_API_KEY to your Environment file to use Edit/fix agent.",
            )
        return OpenAI(
            api_key=gemini_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ), "gemini"
    raise ValueError(f"Unknown provider for Edit/fix agent: {provider_id!r}")


def _raise_clear_llm_error(exc: Exception, *, provider_label: str) -> None:
    """Translate opaque provider errors into actionable messages."""
    blob = str(exc)
    body = getattr(exc, "body", None)
    if body is not None:
        blob += f" {body!s}"

    if provider_label == "gemini" and (
        "API_KEY_SERVICE_BLOCKED" in blob
        or ("PERMISSION_DENIED" in blob and "generativelanguage" in blob.lower())
        or ("403" in blob and "blocked" in blob.lower() and "google" in blob.lower())
    ):
        raise ValueError(
            "Google is blocking the Generative Language API for this API key (often "
            "API_KEY_SERVICE_BLOCKED). Fix it in Google Cloud: open the project that owns the key, "
            "go to APIs & Services → Library, enable Generative Language API; under Credentials, "
            "ensure the key is not restricted away from that API. "
            "Or create a key at https://aistudio.google.com/apikey (AI Studio). "
            "Alternatively, generate a new agent with OpenAI as the LLM and set OPENAI_API_KEY in your Environment file.",
        ) from exc

    if isinstance(exc, APIStatusError):
        code = getattr(exc.response, "status_code", None) if exc.response is not None else None
        raise RuntimeError(f"LLM request failed ({code}): {exc.message}") from exc

    raise RuntimeError(f"LLM request failed: {exc}") from exc


def _fenced_json_candidates(text: str) -> list[str]:
    """Pull ``` / ```json blocks from anywhere in the reply (models often add prose before/after)."""
    out: list[str] = []
    for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE):
        inner = (m.group(1) or "").strip()
        if inner:
            out.append(inner)
    return out


def _balanced_brace_object(text: str, start: int) -> str | None:
    """Slice one balanced {...} from text[start] (must be '{'); respects JSON string rules for depth."""
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    i = start
    in_str = False
    esc = False
    while i < len(text):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    return None


def _iter_balanced_objects(text: str) -> list[str]:
    seen: set[str] = set()
    blobs: list[str] = []
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        blob = _balanced_brace_object(text, i)
        if blob and blob not in seen:
            seen.add(blob)
            blobs.append(blob)
    blobs.sort(key=len, reverse=True)
    return blobs


def _looks_like_edit_payload(d: dict[str, Any]) -> bool:
    return "assistant_message" in d or "files" in d


def _parse_model_json(raw: str) -> dict[str, Any]:
    """Parse edit-agent JSON; tolerate prose, fenced blocks, and embedded objects."""
    raw = raw.strip()
    if not raw:
        raise ValueError("Model did not return valid JSON.")

    if raw.startswith("\ufeff"):
        raw = raw[1:].strip()

    candidates: list[str] = [raw]
    fence_full = re.match(r"^```(?:json)?\s*\n?([\s\S]*?)\n?```\s*$", raw, re.IGNORECASE)
    if fence_full:
        inner = fence_full.group(1).strip()
        if inner:
            candidates.append(inner)
    for block in _fenced_json_candidates(raw):
        if block not in candidates:
            candidates.append(block)
    if raw.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", raw, count=1, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```\s*$", "", stripped, count=1).strip()
        if stripped and stripped not in candidates:
            candidates.append(stripped)

    decoder = json.JSONDecoder()

    def _parse_dict_from_string(s: str) -> dict[str, Any] | None:
        s = s.strip()
        if not s:
            return None
        try:
            data = json.loads(s)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            pass
        for blob in _iter_balanced_objects(s):
            try:
                data = json.loads(blob)
                if isinstance(data, dict) and _looks_like_edit_payload(data):
                    return data
            except json.JSONDecodeError:
                continue
        for i, ch in enumerate(s):
            if ch != "{":
                continue
            try:
                data, _end = decoder.raw_decode(s[i:])
                if isinstance(data, dict) and _looks_like_edit_payload(data):
                    return data
            except json.JSONDecodeError:
                continue
        for blob in _iter_balanced_objects(s):
            try:
                data = json.loads(blob)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
        return None

    seen_c: set[str] = set()
    for cand in candidates:
        if cand in seen_c:
            continue
        seen_c.add(cand)
        parsed = _parse_dict_from_string(cand)
        if parsed is not None:
            return parsed

    raise ValueError(
        "Model did not return valid JSON. Try one file at a time (e.g. only App.tsx), or a smaller UI change."
    )


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

    client, provider_label = _build_openai_client(settings, provider_id=str(metadata.provider_id))
    default_model = "gpt-4o-mini" if metadata.provider_id == "openai" else "gemini-2.5-flash"
    model = (metadata.model or default_model).strip()
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
- For React/UI tweaks, prefer changing ONE file per reply so the JSON stays small and valid.
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
        "max_tokens": 16384,
    }
    try:
        response = client.chat.completions.create(
            **chat_kw,
            response_format={"type": "json_object"},
        )
        trace("LLM returned (json_object mode).")
    except Exception:
        trace("json_object mode failed; retrying without response_format.")
        try:
            response = client.chat.completions.create(**chat_kw)
        except Exception as second_exc:
            _raise_clear_llm_error(second_exc, provider_label=provider_label)
    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        raise RuntimeError("Empty model response.")

    trace(f"Parsed model output ({len(raw):,} chars).")
    try:
        data = _parse_model_json(raw)
    except ValueError as parse_exc:
        trace(f"JSON parse failed ({parse_exc}); retrying once with JSON-only instruction.")
        strict_system = (
            system
            + '\n\nYour last reply could not be parsed. Respond with ONLY one JSON object with keys '
            '"assistant_message" and optional "files". No markdown fences, no text before or after the object.'
        )
        retry_kw = {
            **chat_kw,
            "messages": [
                {"role": "system", "content": strict_system},
                {"role": "user", "content": user_block},
            ],
            "temperature": 0.0,
        }
        try:
            response2 = client.chat.completions.create(
                **retry_kw,
                response_format={"type": "json_object"},
            )
            trace("Retry LLM returned (json_object mode).")
        except Exception:
            response2 = client.chat.completions.create(**retry_kw)
            trace("Retry LLM returned (no response_format).")
        raw = (response2.choices[0].message.content or "").strip()
        if not raw:
            raise parse_exc
        trace(f"Retry model output ({len(raw):,} chars).")
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
