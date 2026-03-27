"""
Requirement and file planning helpers for generated agents.
"""

from __future__ import annotations

from .providers import get_provider
from .schemas import AgentConfigRequest


COMMON_REQUIREMENTS = ["openai", "pydantic", "python-dotenv"]

TEMPLATE_REQUIREMENTS = {
    "default_agent": ["requests"],
}

FRONTEND_REQUIREMENTS = {
    "cli": [],
    "gradio": ["gradio"],
    "react": ["fastapi", "uvicorn"],
}

REACT_UI_FILES = [
    "react-ui/package.json",
    "react-ui/vite.config.ts",
    "react-ui/tsconfig.json",
    "react-ui/tsconfig.node.json",
    "react-ui/index.html",
    "react-ui/src/main.tsx",
    "react-ui/src/App.tsx",
    "react-ui/src/index.css",
    "react-ui/src/vite-env.d.ts",
    "react-ui/.gitignore",
]

FRONTEND_FILES = {
    "cli": ["main.py"],
    "gradio": ["app.py"],
    "react": ["main.py", *REACT_UI_FILES],
}

TOOL_REQUIREMENTS = {
    "document_context": [],
    "structured_output": [],
    "citation_notes": [],
    "checklist_planner": [],
}


# Build the final Python dependency list for a generated agent project.
def build_requirements(config: AgentConfigRequest) -> list[str]:
    provider = get_provider(config.provider_id)
    requirements = set(COMMON_REQUIREMENTS)
    requirements.update(TEMPLATE_REQUIREMENTS[config.template_id])
    requirements.update(FRONTEND_REQUIREMENTS[config.frontend_type])
    for tool_id in config.enabled_tools:
        requirements.update(TOOL_REQUIREMENTS[tool_id])

    if provider["id"] == "gemini":
        requirements.add("httpx")

    if config.frontend_type == "react" and config.allow_file_uploads:
        requirements.add("python-multipart")

    if config.allow_file_uploads:
        for raw in config.supported_upload_types:
            ext = str(raw).lower().lstrip(".")
            if ext == "pdf":
                requirements.add("pypdf")
            elif ext == "docx":
                requirements.add("python-docx")

    requirements.update(config.extra_requirements)
    return sorted(requirements)


# List the files that will be generated for the selected template and frontend.
def preview_generated_files(config: AgentConfigRequest) -> list[str]:
    files = [
        "README.md",
        "agent_config.json",
        "logic.py",
        "run_agent.py",
        "requirements.txt",
        ".gitignore",
        ".env",
    ]
    if config.allow_file_uploads:
        files.extend(["uploads/", "uploads/.gitkeep"])
    files.extend(FRONTEND_FILES[config.frontend_type])
    return sorted(set(files))
