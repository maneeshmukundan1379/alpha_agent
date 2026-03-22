"""
Core logic for the generated agent.
"""

from __future__ import annotations

import os
from pathlib import Path

from openai import OpenAI

PROVIDER_ID = "gemini"
DEFAULT_MODEL_NAME = "gemini-2.5-flash"
MODEL_NAME = (os.getenv("ALPHA_AGENT_MODEL") or DEFAULT_MODEL_NAME).strip()
AGENT_NAME = "Document Summarizer"
AGENT_DESCRIPTION = "Summarize the document uploaded and answers user questions related to the document"
AGENT_INSTRUCTIONS = "The user should be able to upload a document or a pdf. The uagent should read the uploaded document and be able to answer any questions related to the document. Create a very professional and beautiful chat style front end for user input"
TEMPLATE_HINT = "Complete the user's task clearly and directly. When it helps readability, use headings and bullet points. For analysis or research-style requests, include findings, caveats, and suggested next steps. Keep multi-turn conversation natural and concise. When external data, HTTP APIs, or tools are involved, state assumptions clearly; implement fetching in Python in logic.py when the user expects live or structured data."
TOOL_HINTS = ["When the user message includes a section 'Uploaded file context', that text was extracted from files the user attached in the UI\u2014use it as the primary document. If that section is missing or empty, say no file content was received.", "Use clear headings, bullet points, and compact structure when it improves readability."]
ENABLED_TOOLS = ["document_context", "structured_output"]
ALLOW_FILE_UPLOADS = True
SUPPORTED_UPLOAD_TYPES = ["csv", "docx", "json", "md", "pdf", "py", "txt"]
TEMPERATURE = 0.2


# Return the client configuration needed for the selected provider.
def _client_settings() -> dict:
    if PROVIDER_ID == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("Set OPENAI_API_KEY before running this agent.")
        return {"api_key": api_key}

    api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY or GOOGLE_API_KEY before running this agent.")
    return {
        "api_key": api_key,
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    }


# Turn Gradio File/FileData, nested lists, and path strings into real filesystem paths.
def normalize_upload_paths(uploaded: object) -> list[str]:
    if uploaded is None:
        return []
    if isinstance(uploaded, (str, Path)):
        s = str(uploaded).strip()
        return [s] if s else []
    if isinstance(uploaded, dict):
        p = uploaded.get("path") or uploaded.get("name")
        if isinstance(p, str) and p.strip():
            return [p.strip()]
        return []
    path_attr = getattr(uploaded, "path", None)
    if isinstance(path_attr, str) and path_attr.strip():
        return [path_attr.strip()]
    name_attr = getattr(uploaded, "name", None)
    if isinstance(name_attr, str) and name_attr.strip():
        return [name_attr.strip()]
    if isinstance(uploaded, (list, tuple)):
        combined: list[str] = []
        for item in uploaded:
            combined.extend(normalize_upload_paths(item))
        return combined
    return []


# Load plain text from one file; uses optional parsers only for extensions in SUPPORTED_UPLOAD_TYPES.
def _extract_file_text(path: Path, allowed_suffixes: set[str]) -> str:
    suffix = path.suffix.lower().lstrip(".")
    if allowed_suffixes and suffix and suffix not in allowed_suffixes:
        return ""

    if suffix == "pdf" and "pdf" in allowed_suffixes:
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            parts: list[str] = []
            for page in reader.pages:
                parts.append(page.extract_text() or "")
            return "\n".join(parts).strip()
        except Exception:
            return ""

    if suffix == "docx" and "docx" in allowed_suffixes:
        try:
            from docx import Document

            doc = Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs if p.text).strip()
        except Exception:
            return ""

    try:
        return path.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return ""


# Build structured text from uploaded files (after path normalization).
def _read_uploaded_files(paths: list[str]) -> str:
    if not ALLOW_FILE_UPLOADS or not paths:
        return ""

    allowed_suffixes = {str(t).lower().lstrip(".") for t in SUPPORTED_UPLOAD_TYPES}
    blocks: list[str] = []
    for raw_path in paths:
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue

        suffix = path.suffix.lower().lstrip(".")
        content = _extract_file_text(path, allowed_suffixes)
        if not content:
            continue

        blocks.append(
            "\n".join(
                [
                    f"File: {path.name}",
                    "Content:",
                    content[:12000],
                ]
            )
        )
    return "\n\n".join(blocks)


# Build the system prompt that defines the generated agent's behavior.
def build_system_prompt() -> str:
    parts = [
        f"You are {AGENT_NAME}.",
        AGENT_DESCRIPTION,
        AGENT_INSTRUCTIONS,
        "RUNTIME ROLE: You are the model behind this specific application. The description and instructions above are the product specification\u2014follow them on every turn. Do not reply with generic refusals that you cannot browse the web, access external sites, build UIs, or create files when the user is asking this app to do its job. Deliver the closest useful outcome in chat: structured answers, clear formatting, labeled illustrative examples when live data is unavailable, runnable code or steps the user can apply, or ask concisely for missing inputs (e.g. pasted content or credentials). If something requires live data not present in the message or uploads, state that briefly and continue with what you can produce now.",
        TEMPLATE_HINT,
        "If the user request is ambiguous, state the assumptions you are making.",
    ]
    parts.extend(TOOL_HINTS)
    if ALLOW_FILE_UPLOADS:
        parts.append(
            "If uploaded files are provided, use them as grounded context and clearly say when the answer depends on file content."
        )
    return "\n\n".join(parts)


def _gradio_history_to_messages(history: list | None) -> list[dict]:
    """Normalize Gradio chat history: type='messages' dicts or legacy [user, assistant] pairs."""
    out: list[dict] = []
    for item in history or []:
        if isinstance(item, dict):
            role = item.get("role")
            if role not in ("user", "assistant"):
                continue
            raw = item.get("content", "")
            content = raw if isinstance(raw, str) else str(raw)
            out.append(dict(role=role, content=content))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            u, a = item[0], item[1]
            if u:
                out.append({"role": "user", "content": str(u)})
            if a:
                out.append({"role": "assistant", "content": str(a)})
    return out


# Run one conversational turn using prior chat turns (Gradio messages or legacy pairs).
def run_agent_chat(
    user_input: str,
    history: list | None,
    uploaded_paths: object = None,
) -> str:
    clean_input = (user_input or "").strip()
    if not clean_input:
        raise ValueError("A prompt is required to run the agent.")

    resolved_paths = normalize_upload_paths(uploaded_paths)
    file_context = _read_uploaded_files(resolved_paths)
    final_input = clean_input
    if file_context:
        final_input = (
            f"User request:\n{clean_input}\n\n"
            "Uploaded file context:\n"
            f"{file_context}"
        )

    msgs: list[dict] = [{"role": "system", "content": build_system_prompt()}]
    msgs.extend(_gradio_history_to_messages(history))
    msgs.append({"role": "user", "content": final_input})

    client = OpenAI(**_client_settings())
    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=TEMPERATURE,
        messages=msgs,
    )
    return (response.choices[0].message.content or "").strip()


# Single-shot entry (CLI, FastAPI, scripts): no prior turns.
def run_agent_task(user_input: str, uploaded_paths: object = None) -> str:
    return run_agent_chat(user_input, None, uploaded_paths)
