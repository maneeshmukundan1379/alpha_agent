"""
LLM-generated logic.py for new agents (replaces template logic when valid).

Frontends (app.py / main.py) and run_agent.py stay templated so CLI/Gradio/FastAPI wiring remains stable.
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any, Optional

from openai import OpenAI

from .providers import get_provider
from .schemas import AgentConfigRequest
from .templates.project_templates import TEMPLATE_HINTS, TOOL_HINTS


def _declared_env_var_names(config: AgentConfigRequest) -> list[str]:
    provider = get_provider(config.provider_id)
    names = set(provider["secret_names"])
    names.update(secret.key for secret in config.secrets)
    if config.include_settings_api_keys:
        names.update(
            {
                "OPENAI_API_KEY",
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
                "GITHUB_TOKEN",
            }
        )
    if "GEMINI_API_KEY" in names:
        names.add("GOOGLE_API_KEY")
    return sorted(names)


def _build_client(
    settings: dict[str, str],
    *,
    preferred_provider: str | None = None,
) -> tuple[Optional[OpenAI], str]:
    openai_key = (settings.get("openai_api_key") or "").strip()
    gemini_key = (settings.get("gemini_api_key") or "").strip()
    if preferred_provider == "gemini" and gemini_key:
        return OpenAI(
            api_key=gemini_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ), "gemini"
    if preferred_provider == "openai" and openai_key:
        return OpenAI(api_key=openai_key), "openai"
    if openai_key:
        return OpenAI(api_key=openai_key), "openai"
    if gemini_key:
        return OpenAI(
            api_key=gemini_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ), "gemini"
    return None, ""


def _parse_json_object(raw: str) -> dict[str, Any]:
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
    raise ValueError("Code generation model did not return valid JSON.")


def _validate_logic_source(source: str) -> None:
    if len(source) > 200_000:
        raise ValueError("Generated logic.py is too large.")
    compile(source, "logic.py", "exec")
    tree = ast.parse(source)
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    if "run_agent_chat" not in names:
        raise ValueError("Generated logic.py must define run_agent_chat.")
    if "run_agent_task" not in names:
        raise ValueError("Generated logic.py must define run_agent_task.")


def try_generate_logic_py(
    config: AgentConfigRequest,
    *,
    settings: dict[str, str],
) -> tuple[str | None, list[str], str]:
    """
    Ask the configured LLM to write logic.py from the user's description/instructions.

    Returns (logic_py_or_none, extra_requirements, note).
    If logic_py_or_none is None, the caller should use the template logic.py.
    """
    client, _provider_label = _build_client(settings, preferred_provider=config.provider_id)
    if client is None:
        return None, [], "no_api_key"

    tool_lines = [TOOL_HINTS[t] for t in config.enabled_tools]
    payload = {
        "agent_name": config.agent_name,
        "description": config.description,
        "instructions": config.instructions,
        "template_style": TEMPLATE_HINTS[config.template_id],
        "tool_hints": tool_lines,
        "provider_id": config.provider_id,
        "model_for_runtime": config.model,
        "temperature": config.temperature,
        "frontend_type": config.frontend_type,
        "allow_file_uploads": config.allow_file_uploads,
        "supported_upload_types": config.supported_upload_types,
        "extra_requirements_suggested_by_user": config.extra_requirements,
        "include_settings_api_keys": config.include_settings_api_keys,
        "extra_secret_key_names": sorted({s.key for s in config.secrets}),
        "declared_env_var_names": _declared_env_var_names(config),
    }

    system = """You are an expert Python engineer. You write production-ready logic for small AI agent projects.

Your ONLY output must be a single JSON object (no markdown fences) with this exact shape:
{
  "logic_py": "<full content of logic.py as a string, with newlines escaped properly in JSON>",
  "requirements_extra": ["optional", "pip", "package", "names"],
  "implementation_notes": "one short sentence"
}

File to generate: logic.py — the core brain of the agent.

Hard requirements for logic.py:
1. Use `from __future__ import annotations` at the top.
2. Define these functions with these signatures (names and params must match exactly):
   - def run_agent_chat(user_input: str, history: list | None, uploaded_paths: object = None) -> str:
   - def run_agent_task(user_input: str, uploaded_paths: object = None) -> str:
     (run_agent_task should delegate to run_agent_chat with history=None.)
3. Implement what the user's description and instructions ask for using real Python when external data or APIs are needed
   (e.g. HTTP requests to public JSON endpoints, datetime filters, parsing). Do not rely on the LLM alone to "browse" the web;
   fetch data in Python and pass summaries or structured text into the model if you use one.
4. If provider_id is "openai", use os.getenv("OPENAI_API_KEY") and the openai package (OpenAI client) with model from env ALPHA_AGENT_MODEL or a module-level default from the config the user chose.
5. If provider_id is "gemini", use GEMINI_API_KEY or GOOGLE_API_KEY and OpenAI-compatible base URL:
   https://generativelanguage.googleapis.com/v1beta/openai/
6. Expose AGENT_NAME as a string constant matching the agent name from the request.
7. If allow_file_uploads is true, accept uploaded_paths like the standard Gradio file paths; read text when reasonable.
8. Keep secrets only from environment variables — never hardcode API keys.
9. The payload includes `declared_env_var_names`: every name the user may have in `.env` (LLM provider keys from Settings when enabled, plus custom keys). Use `os.getenv` for any third-party or integration APIs the instructions require (e.g. news, maps, databases) when those names appear in `declared_env_var_names` or are implied by the task.
10. Use only standard library plus packages you list in requirements_extra (and common stack: openai, httpx, requests, etc.).
11. In run_agent_chat, normalize Gradio `history` before building API messages: it may be a list of dicts with "role" and "content" (Gradio Chatbot with type="messages") or legacy [user, assistant] pairs. Support both shapes.

Gradio/FastAPI/CLI UIs are separate files; this module is imported as `logic` — only implement logic.py.
Optional: at the top of logic.py you may call `load_dotenv()` from `python-dotenv` so a local `.env` is loaded when the process environment is empty (the template already does this when present).
Note for Gradio: Chatbot message dicts work on Gradio 6+ without a type= kwarg (it was removed). On Gradio 4/5 use type="messages" when that parameter exists. Never use render_as=."""

    user_msg = (
        "Generate logic.py from this JSON config (behavior must satisfy description + instructions):\n"
        + json.dumps(payload, indent=2)
    )

    model = (config.model or "gpt-4o-mini").strip()
    temp = min(0.45, float(config.temperature or 0.2) + 0.15)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=temp,
            messages=messages,
            response_format={"type": "json_object"},
        )
    except Exception:
        resp = client.chat.completions.create(
            model=model,
            temperature=temp,
            messages=messages,
        )

    raw = (resp.choices[0].message.content or "").strip()
    if not raw:
        return None, [], "empty_model_response"

    try:
        data = _parse_json_object(raw)
    except ValueError:
        return None, [], "invalid_json"

    logic_py = data.get("logic_py")
    if not isinstance(logic_py, str) or not logic_py.strip():
        return None, [], "missing_logic_py"

    extra = data.get("requirements_extra") or []
    if not isinstance(extra, list):
        extra = []
    extra_clean = []
    for x in extra:
        if isinstance(x, str) and x.strip():
            extra_clean.append(x.strip())

    try:
        _validate_logic_source(logic_py)
    except Exception as exc:
        return None, [], f"validation_failed:{exc}"

    notes = data.get("implementation_notes")
    note = str(notes).strip() if isinstance(notes, str) else "ok"
    return logic_py.strip(), sorted(set(extra_clean)), note
