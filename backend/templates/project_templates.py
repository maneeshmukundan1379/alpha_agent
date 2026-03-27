"""
Template-driven file generation for Alpha Agent Builder outputs.
"""

from __future__ import annotations

import json
from html import escape
from textwrap import dedent

from ..schemas import AgentConfigRequest

# Injected into every generated agent's system prompt (generic; no domain-specific APIs).
GENERIC_RUNTIME_HINT = (
    "RUNTIME ROLE: You are the model behind this specific application. The description and instructions above "
    "are the product specification—follow them on every turn. Do not reply with generic refusals that you "
    "cannot browse the web, access external sites, build UIs, or create files when the user is asking this app "
    "to do its job. Deliver the closest useful outcome in chat: structured answers, clear formatting, labeled "
    "illustrative examples when live data is unavailable, runnable code or steps the user can apply, or ask "
    "concisely for missing inputs (e.g. pasted content or credentials). If something requires live data not "
    "present in the message or uploads, state that briefly and continue with what you can produce now."
)


TEMPLATE_HINTS = {
    "default_agent": (
        "Complete the user's task clearly and directly. When it helps readability, use headings and bullet points. "
        "For analysis or research-style requests, include findings, caveats, and suggested next steps. "
        "Keep multi-turn conversation natural and concise. "
        "When external data, HTTP APIs, or tools are involved, state assumptions clearly; implement fetching in "
        "Python in logic.py when the user expects live or structured data."
    ),
}

TOOL_HINTS = {
    "document_context": (
        "When the user message includes a section 'Uploaded file context', that text was extracted from files "
        "the user attached in the UI—use it as the primary document. If that section is missing or empty, say no "
        "file content was received."
    ),
    "structured_output": "Use clear headings, bullet points, and compact structure when it improves readability.",
    "citation_notes": "When using uploaded file content, cite the relevant file name in the response where practical.",
    "checklist_planner": "End with a short action checklist when a task or plan is requested.",
}


# Render all files for a generated agent project from a validated config.
def render_project_files(
    *,
    config: AgentConfigRequest,
    provider: dict,
    requirements: list[str],
    secret_names: list[str],
) -> dict[str, str]:
    files = {
        "logic.py": _render_logic(config, provider),
        "run_agent.py": _render_run_agent(config),
        "requirements.txt": _render_requirements(requirements),
        "README.md": _render_readme(config, provider),
        "agent_config.json": _render_agent_config(config, provider, requirements, secret_names),
        ".gitignore": _render_root_gitignore(),
    }

    if config.frontend_type == "cli":
        files["main.py"] = _render_cli_main(config)
    elif config.frontend_type == "gradio":
        files["app.py"] = _render_gradio_app(config)
    elif config.frontend_type == "react":
        files["main.py"] = _render_react_backend(config)
        files.update(_render_react_ui_files(config))
    else:
        raise ValueError(f"Unsupported frontend_type: {config.frontend_type!r}")

    return files


# Build the provider-aware logic module for the generated agent.
def _render_logic(config: AgentConfigRequest, provider: dict) -> str:
    provider_id = json.dumps(provider["id"])
    model_name = json.dumps(config.model)
    agent_name = json.dumps(config.agent_name)
    description = json.dumps(config.description)
    instructions = json.dumps(config.instructions)
    template_hint = json.dumps(TEMPLATE_HINTS[config.template_id])
    tool_hints = json.dumps([TOOL_HINTS[tool_id] for tool_id in config.enabled_tools])
    enabled_tools = json.dumps(config.enabled_tools)
    allow_file_uploads = "True" if config.allow_file_uploads else "False"
    supported_upload_types = json.dumps(config.supported_upload_types)

    return dedent(
        f'''\
        """
        Core logic for the generated agent.
        """

        from __future__ import annotations

        import os
        from pathlib import Path

        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass

        from openai import OpenAI

        PROVIDER_ID = {provider_id}
        DEFAULT_MODEL_NAME = {model_name}
        MODEL_NAME = (os.getenv("ALPHA_AGENT_MODEL") or DEFAULT_MODEL_NAME).strip()
        AGENT_NAME = {agent_name}
        AGENT_DESCRIPTION = {description}
        AGENT_INSTRUCTIONS = {instructions}
        TEMPLATE_HINT = {template_hint}
        TOOL_HINTS = {tool_hints}
        ENABLED_TOOLS = {enabled_tools}
        ALLOW_FILE_UPLOADS = {allow_file_uploads}
        SUPPORTED_UPLOAD_TYPES = {supported_upload_types}
        TEMPERATURE = {config.temperature}


        # Return the client configuration needed for the selected provider.
        def _client_settings() -> dict:
            if PROVIDER_ID == "openai":
                api_key = os.getenv("OPENAI_API_KEY", "").strip()
                if not api_key:
                    raise ValueError("Set OPENAI_API_KEY before running this agent.")
                return {{"api_key": api_key}}

            api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
            if not api_key:
                raise ValueError("Set GEMINI_API_KEY or GOOGLE_API_KEY before running this agent.")
            return {{
                "api_key": api_key,
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            }}


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
                    return "\\n".join(parts).strip()
                except Exception:
                    return ""

            if suffix == "docx" and "docx" in allowed_suffixes:
                try:
                    from docx import Document

                    doc = Document(str(path))
                    return "\\n".join(p.text for p in doc.paragraphs if p.text).strip()
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

            allowed_suffixes = {{str(t).lower().lstrip(".") for t in SUPPORTED_UPLOAD_TYPES}}
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
                    "\\n".join(
                        [
                            f"File: {{path.name}}",
                            "Content:",
                            content[:12000],
                        ]
                    )
                )
            return "\\n\\n".join(blocks)


        # Build the system prompt that defines the generated agent's behavior.
        def build_system_prompt() -> str:
            parts = [
                f"You are {{AGENT_NAME}}.",
                AGENT_DESCRIPTION,
                AGENT_INSTRUCTIONS,
                {json.dumps(GENERIC_RUNTIME_HINT)},
                TEMPLATE_HINT,
                "If the user request is ambiguous, state the assumptions you are making.",
            ]
            parts.extend(TOOL_HINTS)
            if ALLOW_FILE_UPLOADS:
                parts.append(
                    "If uploaded files are provided, use them as grounded context and clearly say when the answer depends on file content."
                )
            return "\\n\\n".join(parts)


        def _gradio_history_to_messages(history: list | None) -> list[dict]:
            \"\"\"Normalize Gradio chat history: type='messages' dicts or legacy [user, assistant] pairs.\"\"\"
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
                        out.append({{"role": "user", "content": str(u)}})
                    if a:
                        out.append({{"role": "assistant", "content": str(a)}})
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
                    f"User request:\\n{{clean_input}}\\n\\n"
                    "Uploaded file context:\\n"
                    f"{{file_context}}"
                )

            msgs: list[dict] = [{{"role": "system", "content": build_system_prompt()}}]
            msgs.extend(_gradio_history_to_messages(history))
            msgs.append({{"role": "user", "content": final_input}})

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
        '''
    )


# Build the common one-shot CLI runner used by Alpha Agent Builder.
def _render_run_agent(config: AgentConfigRequest) -> str:
    file_path_help = ""
    if config.allow_file_uploads:
        file_path_help = dedent(
            """\
                uploaded_paths = sys.argv[2:]
                is_interactive = sys.stdin.isatty()
                if not prompt and is_interactive:
                    prompt = input("Prompt: ").strip()
                if not uploaded_paths and is_interactive:
                    raw_paths = input("Optional file paths (comma-separated): ").strip()
                    uploaded_paths = [item.strip() for item in raw_paths.split(",") if item.strip()]
            """
        )
    else:
        file_path_help = (
            'uploaded_paths: list[str] = []\n'
            "            is_interactive = sys.stdin.isatty()\n"
            "            if not prompt and is_interactive:\n"
            '                prompt = input("Prompt: ").strip()'
        )

    return dedent(
        f'''\
        """
        One-shot runner for the generated agent.
        """

        from __future__ import annotations

        import sys

        from logic import run_agent_task


        # Read a prompt from argv or stdin and print the generated response.
        def main() -> int:
            prompt = sys.argv[1].strip() if len(sys.argv) > 1 else ""
{_indent_block(file_path_help, 3)}
            if not prompt:
                print("A prompt is required.")
                return 1

            print(run_agent_task(prompt, uploaded_paths=uploaded_paths))
            return 0


        if __name__ == "__main__":
            raise SystemExit(main())
        '''
    )


# Build the interactive CLI entrypoint for a terminal-based generated agent.
def _render_cli_main(config: AgentConfigRequest) -> str:
    upload_prompt = ""
    if config.allow_file_uploads:
        upload_prompt = dedent(
            """\
                    raw_paths = input("Optional file paths (comma-separated): ").strip()
                    uploaded_paths = [item.strip() for item in raw_paths.split(",") if item.strip()]
            """
        )
    else:
        upload_prompt = "                uploaded_paths = []\n"

    return dedent(
        f'''\
        """
        Interactive CLI frontend for the generated agent.
        """

        from __future__ import annotations

        from logic import ALLOW_FILE_UPLOADS, run_agent_task


        # Run the generated agent in a simple terminal loop.
        def main() -> int:
            print("Type a prompt for the agent. Type 'exit' to stop.")
            while True:
                prompt = input("\\nYou: ").strip()
                if prompt.lower() in {"exit", "quit"}:
                    print("Goodbye.")
                    return 0
                if not prompt:
                    continue
{_indent_block(upload_prompt, 4)}
                if not ALLOW_FILE_UPLOADS:
                    uploaded_paths = []
                print(f"\\nAgent: {{run_agent_task(prompt, uploaded_paths=uploaded_paths)}}")


        if __name__ == "__main__":
            raise SystemExit(main())
        '''
    )


# Build the Gradio frontend entrypoint for a generated agent project.
def _render_gradio_app(config: AgentConfigRequest) -> str:
    if config.allow_file_uploads:
        lines = [
            '"""',
            "Gradio frontend for the generated agent (generic multi-turn chat).",
            "",
            "Chatbot: use _gradio_chatbot() only — do not pass type= or render_as= directly.",
            "Gradio 6+ removed Chatbot(type=...); Gradio 4/5 need type='messages' for dict history.",
            "chat_fn returns OpenAI-style message dicts (role + content), matching template logic.py.",
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "import inspect",
            "import os",
            "",
            "import gradio as gr",
            "",
            "from logic import AGENT_NAME, run_agent_chat",
            "",
            "",
            "def _gradio_chatbot(height: int = 440) -> gr.Chatbot:",
            "    \"\"\"Pass type='messages' only if Chatbot supports it (Gradio 4/5). Gradio 6+ removed that kwarg.\"\"\"",
            "    if \"type\" in inspect.signature(gr.Chatbot.__init__).parameters:",
            "        return gr.Chatbot(height=height, type=\"messages\")",
            "    return gr.Chatbot(height=height)",
            "",
            "",
            "# Message-style history (dicts with role/content); see _gradio_chatbot for Gradio version differences.",
            "# Append one user message and the model reply to the chat history.",
            "def chat_fn(message: str, history: list, uploaded_files: object) -> list:",
            "    text = (message or '').strip()",
            "    if not text:",
            "        return history or []",
            "    reply = run_agent_chat(text, history or [], uploaded_paths=uploaded_files)",
            "    h = list(history or [])",
            '    h.append({\"role\": \"user\", \"content\": text})',
            '    h.append({\"role\": \"assistant\", \"content\": reply})',
            "    return h",
            "",
            "",
            "# Build the Gradio UI used to chat with the generated agent.",
            "def build_ui() -> gr.Blocks:",
            "    with gr.Blocks(title=AGENT_NAME) as demo:",
            "        gr.Markdown(f'# {AGENT_NAME}')",
            '        gr.Markdown("Multi-turn chat. Optional uploads apply to each send (same as the builder).")',
            "        chat = _gradio_chatbot(440)",
            '        uploads = gr.File(label="Context files (optional)", file_count="multiple", type="filepath")',
            '        msg = gr.Textbox(show_label=False, lines=2, placeholder="Message…")',
            '        with gr.Row():',
            '            send = gr.Button("Send", variant="primary")',
            '            clear = gr.Button("Clear")',
            "        send.click(chat_fn, [msg, chat, uploads], [chat]).then(lambda: '', outputs=[msg])",
            "        msg.submit(chat_fn, [msg, chat, uploads], [chat]).then(lambda: '', outputs=[msg])",
            "        clear.click(lambda: [], outputs=[chat])",
            "    return demo",
            "",
            "",
            "demo = build_ui()",
            "",
            'if __name__ == "__main__":',
            "    _port = int(os.environ.get('ALPHA_AGENT_PORT', '7860'))",
            '    demo.launch(server_name="127.0.0.1", server_port=_port, inbrowser=False, show_error=True, theme=gr.themes.Soft(primary_hue="cyan", neutral_hue="slate"))',
            "",
        ]
    else:
        lines = [
            '"""',
            "Gradio frontend for the generated agent (generic multi-turn chat).",
            "",
            "Chatbot: use _gradio_chatbot() only — do not pass type= or render_as= directly.",
            "Gradio 6+ removed Chatbot(type=...); Gradio 4/5 need type='messages' for dict history.",
            "chat_fn returns OpenAI-style message dicts (role + content), matching template logic.py.",
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "import inspect",
            "import os",
            "",
            "import gradio as gr",
            "",
            "from logic import AGENT_NAME, run_agent_chat",
            "",
            "",
            "def _gradio_chatbot(height: int = 440) -> gr.Chatbot:",
            "    \"\"\"Pass type='messages' only if Chatbot supports it (Gradio 4/5). Gradio 6+ removed that kwarg.\"\"\"",
            "    if \"type\" in inspect.signature(gr.Chatbot.__init__).parameters:",
            "        return gr.Chatbot(height=height, type=\"messages\")",
            "    return gr.Chatbot(height=height)",
            "",
            "",
            "# Message-style history (dicts with role/content); see _gradio_chatbot for Gradio version differences.",
            "# Append one user message and the model reply to the chat history.",
            "def chat_fn(message: str, history: list) -> list:",
            "    text = (message or '').strip()",
            "    if not text:",
            "        return history or []",
            "    reply = run_agent_chat(text, history or [])",
            "    h = list(history or [])",
            '    h.append({\"role\": \"user\", \"content\": text})',
            '    h.append({\"role\": \"assistant\", \"content\": reply})',
            "    return h",
            "",
            "",
            "# Build the Gradio UI used to chat with the generated agent.",
            "def build_ui() -> gr.Blocks:",
            "    with gr.Blocks(title=AGENT_NAME) as demo:",
            "        gr.Markdown(f'# {AGENT_NAME}')",
            '        gr.Markdown("Multi-turn chat: earlier messages stay in context for the model.")',
            "        chat = _gradio_chatbot(440)",
            '        msg = gr.Textbox(show_label=False, lines=2, placeholder="Message…")',
            '        with gr.Row():',
            '            send = gr.Button("Send", variant="primary")',
            '            clear = gr.Button("Clear")',
            "        send.click(chat_fn, [msg, chat], [chat]).then(lambda: '', outputs=[msg])",
            "        msg.submit(chat_fn, [msg, chat], [chat]).then(lambda: '', outputs=[msg])",
            "        clear.click(lambda: [], outputs=[chat])",
            "    return demo",
            "",
            "",
            "demo = build_ui()",
            "",
            'if __name__ == "__main__":',
            "    _port = int(os.environ.get('ALPHA_AGENT_PORT', '7860'))",
            '    demo.launch(server_name="127.0.0.1", server_port=_port, inbrowser=False, show_error=True, theme=gr.themes.Soft(primary_hue="cyan", neutral_hue="slate"))',
            "",
        ]

    return "\n".join(lines)


# Build FastAPI backend for the React + API frontend (Vite app lives in react-ui/).
def _render_react_backend(config: AgentConfigRequest) -> str:
    cors_line = (
        'app.add_middleware(CORSMiddleware, allow_origin_regex=r"http://(127\\.0\\.0\\.1|localhost):\\d+", '
        "allow_credentials=True, allow_methods=[\"*\"], allow_headers=[\"*\"])"
    )
    if config.allow_file_uploads:
        lines = [
            '"""',
            "FastAPI backend for the generated agent. Pair with the React app in react-ui/.",
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "import tempfile",
            "from pathlib import Path",
            "",
            "from fastapi import FastAPI, File, Form, UploadFile",
            "from fastapi.middleware.cors import CORSMiddleware",
            "from pydantic import BaseModel, Field",
            "",
            "from logic import run_agent_chat, run_agent_task",
            "",
            'app = FastAPI(title="Generated Agent API", version="1.0.0")',
            cors_line,
            "",
            "",
            "class RunRequest(BaseModel):",
            "    prompt: str",
            "",
            "",
            "class RunResponse(BaseModel):",
            "    response: str",
            "",
            "",
            "class ChatMessage(BaseModel):",
            "    role: str",
            "    content: str",
            "",
            "",
            "class ChatRequest(BaseModel):",
            "    message: str",
            "    history: list[ChatMessage] = Field(default_factory=list)",
            "",
            "",
            '@app.get("/health")',
            "def health() -> dict:",
            '    return {"status": "ok"}',
            "",
            "",
            "# Multi-turn JSON chat for the React UI.",
            '@app.post("/chat", response_model=RunResponse)',
            "def chat_endpoint(body: ChatRequest) -> RunResponse:",
            "    hist = [m.model_dump() for m in body.history]",
            "    return RunResponse(response=run_agent_chat(body.message, hist or None))",
            "",
            "",
            "# Single-shot multipart run (optional file uploads from any client).",
            '@app.post("/run", response_model=RunResponse)',
            "async def run(",
            "    prompt: str = Form(...),",
            "    files: list[UploadFile] | None = File(default=None),",
            ") -> RunResponse:",
            "    with tempfile.TemporaryDirectory() as tmp_dir:",
            "        uploaded_paths: list[str] = []",
            "        for upload in files or []:",
            '            temp_path = Path(tmp_dir) / (upload.filename or "upload.txt")',
            "            temp_path.write_bytes(await upload.read())",
            "            uploaded_paths.append(str(temp_path))",
            "        return RunResponse(response=run_agent_task(prompt, uploaded_paths=uploaded_paths))",
            "",
        ]
    else:
        lines = [
            '"""',
            "FastAPI backend for the generated agent. Pair with the React app in react-ui/.",
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "from fastapi import FastAPI",
            "from fastapi.middleware.cors import CORSMiddleware",
            "from pydantic import BaseModel, Field",
            "",
            "from logic import run_agent_chat, run_agent_task",
            "",
            'app = FastAPI(title="Generated Agent API", version="1.0.0")',
            cors_line,
            "",
            "",
            "class RunRequest(BaseModel):",
            "    prompt: str",
            "",
            "",
            "class RunResponse(BaseModel):",
            "    response: str",
            "",
            "",
            "class ChatMessage(BaseModel):",
            "    role: str",
            "    content: str",
            "",
            "",
            "class ChatRequest(BaseModel):",
            "    message: str",
            "    history: list[ChatMessage] = Field(default_factory=list)",
            "",
            "",
            '@app.get("/health")',
            "def health() -> dict:",
            '    return {"status": "ok"}',
            "",
            "",
            '@app.post("/chat", response_model=RunResponse)',
            "def chat_endpoint(body: ChatRequest) -> RunResponse:",
            "    hist = [m.model_dump() for m in body.history]",
            "    return RunResponse(response=run_agent_chat(body.message, hist or None))",
            "",
            "",
            '@app.post("/run", response_model=RunResponse)',
            "def run(request: RunRequest) -> RunResponse:",
            "    return RunResponse(response=run_agent_task(request.prompt))",
            "",
        ]

    return "\n".join(lines)


def _render_react_ui_files(config: AgentConfigRequest) -> dict[str, str]:
    """Minimal Vite + React chat UI calling POST /chat on the FastAPI backend."""
    _agent_json = json.dumps(config.agent_name)
    package = {
        "name": "agent-react-ui",
        "private": True,
        "version": "0.0.0",
        "type": "module",
        "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
        "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
        "devDependencies": {
            "@types/react": "^18.3.3",
            "@types/react-dom": "^18.3.0",
            "@vitejs/plugin-react": "^4.3.1",
            "typescript": "~5.6.2",
            "vite": "^5.4.2",
        },
    }
    app_tsx = dedent(
        f"""
        import {{ useCallback, useState }} from "react";

        type Msg = {{ role: "user" | "assistant"; content: string }};

        const AGENT_NAME = {_agent_json} as const;

        const apiBase = () =>
          (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\\/$/, "") ||
          "http://127.0.0.1:7860";

        export default function App() {{
          const [input, setInput] = useState("");
          const [history, setHistory] = useState<Msg[]>([]);
          const [pending, setPending] = useState(false);
          const [error, setError] = useState<string | null>(null);

          const send = useCallback(async () => {{
            const text = input.trim();
            if (!text || pending) return;
            setPending(true);
            setError(null);
            setInput("");
            const nextHist: Msg[] = [...history, {{ role: "user", content: text }}];
            setHistory(nextHist);
            try {{
              const r = await fetch(`${{apiBase()}}/chat`, {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify({{
                  message: text,
                  history: history.map((m) => ({{ role: m.role, content: m.content }})),
                }}),
              }});
              if (!r.ok) {{
                const t = await r.text();
                throw new Error(t || r.statusText);
              }}
              const data = (await r.json()) as {{ response: string }};
              setHistory([...nextHist, {{ role: "assistant", content: data.response }}]);
            }} catch (e) {{
              setError(e instanceof Error ? e.message : "Request failed");
              setHistory(history);
            }} finally {{
              setPending(false);
            }}
          }}, [history, input, pending]);

          return (
            <div className="app">
              <header className="header">
                <h1>{{AGENT_NAME}}</h1>
                <p className="sub">React UI · API base: {{apiBase()}}</p>
              </header>
              <div className="chat">
                {{history.map((m, i) => (
                  <div key={{i}} className={{`bubble ${{m.role}}`}}>
                    <span className="role">{{m.role}}</span>
                    <pre className="text">{{m.content}}</pre>
                  </div>
                ))}}
              </div>
              {{error ? <div className="err">{{error}}</div> : null}}
              <div className="row">
                <textarea
                  rows={{3}}
                  value={{input}}
                  onChange={{(e) => setInput(e.target.value)}}
                  placeholder="Message…"
                  disabled={{pending}}
                />
                <button type="button" disabled={{pending}} onClick={{() => void send()}}>
                  {{pending ? "…" : "Send"}}
                </button>
              </div>
            </div>
          );
        }}
        """
    )

    css = dedent(
        """
        * { box-sizing: border-box; }
        body { margin: 0; font-family: ui-sans-serif, system-ui, sans-serif; background: #0f172a; color: #e2e8f0; }
        .app { max-width: 720px; margin: 0 auto; padding: 1.5rem; }
        .header h1 { margin: 0 0 0.25rem; font-size: 1.35rem; }
        .sub { margin: 0; font-size: 0.8rem; color: #94a3b8; }
        .chat { display: flex; flex-direction: column; gap: 0.75rem; margin: 1rem 0; min-height: 200px; }
        .bubble { border-radius: 12px; padding: 0.75rem 1rem; }
        .bubble.user { background: #164e63; align-self: flex-end; max-width: 90%; }
        .bubble.assistant { background: #1e293b; align-self: flex-start; max-width: 100%; }
        .role { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.08em; color: #94a3b8; }
        .text { margin: 0.35rem 0 0; white-space: pre-wrap; font-family: inherit; font-size: 0.9rem; }
        .row { display: flex; gap: 0.5rem; align-items: flex-end; }
        textarea {
          flex: 1; resize: vertical; border-radius: 12px; border: 1px solid #334155; background: #020617; color: #f8fafc; padding: 0.6rem 0.75rem;
        }
        button {
          border: none; border-radius: 999px; padding: 0.6rem 1.2rem; font-weight: 600; cursor: pointer;
          background: linear-gradient(90deg, #22d3ee, #a78bfa); color: #0f172a;
        }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        .err { color: #fca5a5; font-size: 0.85rem; margin-bottom: 0.5rem; }
        """
    )

    vite_config = dedent(
        """
        import { defineConfig } from "vite";
        import react from "@vitejs/plugin-react";

        export default defineConfig({
          plugins: [react()],
          server: { host: "127.0.0.1", port: 5173, strictPort: false },
        });
        """
    )

    tsconfig = dedent(
        """
        {
          "compilerOptions": {
            "target": "ES2022",
            "useDefineForClassFields": true,
            "lib": ["ES2022", "DOM", "DOM.Iterable"],
            "module": "ESNext",
            "skipLibCheck": true,
            "moduleResolution": "bundler",
            "isolatedModules": true,
            "moduleDetection": "force",
            "jsx": "react-jsx",
            "strict": true,
            "noUnusedLocals": true,
            "noUnusedParameters": true,
            "noFallthroughCasesInSwitch": true,
            "noEmit": true
          },
          "include": ["src"]
        }
        """
    )

    tsconfig_node = dedent(
        """
        {
          "compilerOptions": {
            "target": "ES2022",
            "lib": ["ES2023"],
            "module": "ESNext",
            "skipLibCheck": true,
            "moduleResolution": "bundler"
          },
          "include": ["vite.config.ts"]
        }
        """
    )

    index_html = dedent(
        f"""
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <title>{escape(config.agent_name)}</title>
          </head>
          <body>
            <div id="root"></div>
            <script type="module" src="/src/main.tsx"></script>
          </body>
        </html>
        """
    )

    main_tsx = dedent(
        """
        import { StrictMode } from "react";
        import { createRoot } from "react-dom/client";
        import App from "./App";
        import "./index.css";

        createRoot(document.getElementById("root")!).render(
          <StrictMode>
            <App />
          </StrictMode>,
        );
        """
    )

    vite_env = dedent(
        """
        /// <reference types="vite/client" />

        interface ImportMetaEnv {
          readonly VITE_API_URL: string;
        }

        interface ImportMeta {
          readonly env: ImportMetaEnv;
        }
        """
    )

    gitignore = "node_modules/\ndist/\n.env.development.local\n.env.local\n"

    return {
        "react-ui/package.json": json.dumps(package, indent=2) + "\n",
        "react-ui/vite.config.ts": vite_config,
        "react-ui/tsconfig.json": tsconfig,
        "react-ui/tsconfig.node.json": tsconfig_node,
        "react-ui/index.html": index_html,
        "react-ui/src/main.tsx": main_tsx,
        "react-ui/src/App.tsx": app_tsx,
        "react-ui/src/index.css": css,
        "react-ui/src/vite-env.d.ts": vite_env,
        "react-ui/.gitignore": gitignore,
    }


# Render the generated requirements file for the output project.
def _render_requirements(requirements: list[str]) -> str:
    return "".join(f"{requirement}\n" for requirement in requirements)


# Root ignore rules so `.env` is not committed by mistake.
def _render_root_gitignore() -> str:
    return (
        ".env\n"
        ".venv/\n"
        "__pycache__/\n"
        "*.pyc\n"
        ".DS_Store\n"
    )


# Render a JSON snapshot of the generated configuration for later inspection.
def _render_agent_config(config: AgentConfigRequest, provider: dict, requirements: list[str], secret_names: list[str]) -> str:
    declared = set(secret_names)
    declared.update(secret.key for secret in config.secrets)
    if config.include_settings_api_keys:
        declared.update(
            {
                "OPENAI_API_KEY",
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
                "GITHUB_TOKEN",
            }
        )
    if "GEMINI_API_KEY" in declared:
        declared.add("GOOGLE_API_KEY")

    payload = {
        "agent_name": config.agent_name,
        "description": config.description,
        "instructions": config.instructions,
        "template_id": config.template_id,
        "provider_id": provider["id"],
        "provider_label": provider["label"],
        "model": config.model,
        "frontend_type": config.frontend_type,
        "temperature": config.temperature,
        "enabled_tools": config.enabled_tools,
        "allow_file_uploads": config.allow_file_uploads,
        "supported_upload_types": config.supported_upload_types,
        "requirements": requirements,
        "secret_names": secret_names,
        "include_settings_api_keys": config.include_settings_api_keys,
        "extra_secret_key_names": sorted({secret.key for secret in config.secrets}),
        "declared_env_var_names": sorted(declared),
    }
    return json.dumps(payload, indent=2) + "\n"


# Render the README bundled with each generated agent project.
def _render_readme(config: AgentConfigRequest, provider: dict) -> str:
    entrypoint = "app.py" if config.frontend_type == "gradio" else "main.py"
    tools_summary = ", ".join(config.enabled_tools) if config.enabled_tools else "none"
    uploads_summary = (
        f"enabled for: {', '.join(config.supported_upload_types)}"
        if config.allow_file_uploads
        else "disabled"
    )
    if config.frontend_type == "react":
        run_section = dedent(
            """\

            ## Run (React + API)

            **Terminal 1 — FastAPI** (example port `7860`):

            ```bash
            export ALPHA_AGENT_PORT=7860
            python -m uvicorn main:app --host 127.0.0.1 --port "$ALPHA_AGENT_PORT"
            ```

            **Terminal 2 — React** (requires [Node.js](https://nodejs.org/)):

            ```bash
            cd react-ui
            printf 'VITE_API_URL=http://127.0.0.1:7860\\n' > .env.development.local
            npm install
            npm run dev
            ```

            Open the URL Vite prints (often `http://127.0.0.1:5173`). Adjust `VITE_API_URL` if your API port differs.
            """
        )
    else:
        run_section = dedent(
            f"""\

            ## Run
            ```bash
            python {entrypoint}
            ```
            """
        )

    return dedent(
        f"""\
        # {config.agent_name}

        This project was generated by Alpha Agent Builder.

        ## Summary
        - Template: `{config.template_id}`
        - Provider: `{provider["label"]}`
        - Model: `{config.model}`
        - Frontend: `{config.frontend_type}`
        - Tools: `{tools_summary}`
        - File uploads: `{uploads_summary}`

        ## Setup
        ```bash
        python3 -m venv .venv
        source .venv/bin/activate
        pip install -r requirements.txt
        ```

        At generate time, Alpha Agent Builder can write a local `.env` with your Settings provider keys (optional)
        and any extra secrets you added in the builder. That file is gitignored. If you run the project manually,
        either keep `.env` in the project root or export the same variables in your shell.
        When using the builder Run tab, Settings keys are still injected into the process environment as well.
        {run_section.strip()}

        ## One-shot execution
        ```bash
        python run_agent.py "Summarize the latest developer updates."
        ```
        """
    )


# Indent a multi-line block so it can be embedded safely in generated Python.
def _indent_block(text: str, level: int) -> str:
    prefix = " " * (level * 4)
    return "\n".join(f"{prefix}{line}" if line else "" for line in text.rstrip("\n").splitlines())


# Normalize inline block content for placement inside generated code.
def _indent_inline(text: str, level: int) -> str:
    if not text:
        return ""
    return _indent_block(text.rstrip("\n"), level)
