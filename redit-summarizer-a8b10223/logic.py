from __future__ import annotations

import os
from pathlib import Path

from openai import OpenAI

PROVIDER_ID = "gemini"
DEFAULT_MODEL_NAME = "gemini-2.5-flash"
MODEL_NAME = (os.getenv("ALPHA_AGENT_MODEL") or DEFAULT_MODEL_NAME).strip()
AGENT_NAME = "Redit Summarizer"
AGENT_DESCRIPTION = "An chat agent that scans reditt for messages"
AGENT_INSTRUCTIONS = "Create a chat agent that accepts a keyword as input. On pressing the run agent, it should scroll reditt for the keyword for the past 1 week and display matching messages. Give only messages that have the matching keyword"
TEMPLATE_HINT = "Keep the conversation natural, helpful, and concise while preserving useful detail."
TOOL_HINTS = ["When the user message includes a section 'Uploaded file context', that text was extracted from files the user attached in the UI—use it as the primary document. If that section is missing or empty, say no file content was received.", "Use clear headings, bullet points, and compact structure when it improves readability."]
ENABLED_TOOLS = ["document_context", "structured_output"]
ALLOW_FILE_UPLOADS = False
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
        "RUNTIME ROLE: You are the model behind this specific application. The description and instructions above are the product specification—follow them on every turn. Do not reply with generic refusals that you cannot browse the web, access external sites, build UIs, or create files when the user is asking this app to do its job. Deliver the closest useful outcome in chat: structured answers, clear formatting, labeled illustrative examples when live data is unavailable, runnable code or steps the user can apply, or ask concisely for missing inputs (e.g. pasted content or credentials). If something requires live data not present in the message or uploads, state that briefly and continue with what you can produce now.",
        TEMPLATE_HINT,
        "If the user request is ambiguous, state the assumptions you are making.",
    ]
    parts.extend(TOOL_HINTS)
    if ALLOW_FILE_UPLOADS:
        parts.append(
            "If uploaded files are provided, use them as grounded context and clearly say when the answer depends on file content."
        )
    return "\n\n".join(parts)


# Run one conversational turn using prior chat turns (Gradio: list of [user, assistant] pairs).
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

    msgs: list[dict] = []
    
    # Process history
    for pair in history or []:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        u, a = pair[0], pair[1]
        
        user_content = str(u).strip() if u is not None else ""
        assistant_content = str(a).strip() if a is not None else ""

        # Always add user and assistant messages to maintain turn structure,
        # even if content is empty. Empty content is generally valid.
        msgs.append({"role": "user", "content": user_content})
        msgs.append({"role": "assistant", "content": assistant_content})
    
    final_user_message_content = final_input.strip()
    if not final_user_message_content:
        raise ValueError("Final user input content cannot be empty.")

    # Add the current user message
    msgs.append({"role": "user", "content": final_user_message_content})

    # Handle system prompt based on provider
    system_prompt_content = build_system_prompt().strip()
    if system_prompt_content:
        if PROVIDER_ID == "gemini":
            # For Gemini via OpenAI compatibility, prepend system prompt to the first user message.
            # The msgs list will always contain at least one user message (the current turn).
            for msg in msgs:
                if msg.get("role") == "user":
                    msg["content"] = f"{system_prompt_content}\n\n{msg['content']}"
                    break
        else: # For OpenAI or other providers that support 'system' role directly
            # Insert system prompt at the beginning of the messages list
            msgs.insert(0, {"role": "system", "content": system_prompt_content})

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
