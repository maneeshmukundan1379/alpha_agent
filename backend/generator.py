"""
Project generation and metadata management for Alpha Agent Builder.
"""

from __future__ import annotations

import json
import re
import shutil
from typing import Literal
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .providers import get_provider
from .requirements_builder import build_requirements, preview_generated_files
from .schemas import AgentConfigRequest, AgentMetadata, AgentTreeNode, UploadedFileInfo
from .codegen import try_generate_logic_py
from .secrets_store import has_saved_secrets, write_agent_environment
from .templates import render_project_files
from .github_sync import sync_generated_project_to_github

APP_DIR = Path(__file__).resolve().parent.parent
GENERATED_AGENTS_DIR = APP_DIR / "generated_agents"


# Build a filesystem-safe slug for generated agent directory names.
def slugify(value: str) -> str:
    collapsed = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return collapsed.strip("-") or "agent"


# Return the metadata file path for a generated agent directory.
def _metadata_path(agent_dir: Path) -> Path:
    return agent_dir / "metadata.json"


# Return the uploads directory for a generated agent.
def _uploads_dir(agent_dir: Path) -> Path:
    return agent_dir / "uploads"


# Return the per-user generated agents directory.
def _user_agents_dir(user_id: int) -> Path:
    return GENERATED_AGENTS_DIR / f"user_{user_id}"


# Convert a metadata JSON payload into the API model.
def _metadata_from_payload(payload: dict) -> AgentMetadata:
    payload = dict(payload)
    payload["created_at"] = datetime.fromisoformat(payload["created_at"])
    payload.setdefault("user_id", 0)
    payload.setdefault("enabled_tools", [])
    payload.setdefault("allow_file_uploads", False)
    payload.setdefault("supported_upload_types", [])
    payload.setdefault("github_repo_url", "")
    payload.setdefault("github_repo_path", "")
    payload.setdefault("github_commit_sha", "")
    payload.setdefault("generation_source", "template")
    payload.setdefault("include_settings_api_keys", True)
    payload.setdefault("extra_secret_key_names", [])
    return AgentMetadata(**payload)


# Persist updated metadata back to disk.
def _write_metadata(agent_dir: Path, metadata: AgentMetadata) -> None:
    _metadata_path(agent_dir).write_text(
        json.dumps(
            {
                **metadata.model_dump(),
                "created_at": metadata.created_at.isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


# Load one generated agent's metadata from disk.
def load_agent_metadata(user_id: int, agent_id: str) -> AgentMetadata:
    agent_dir = _user_agents_dir(user_id) / agent_id
    metadata_file = _metadata_path(agent_dir)
    if not metadata_file.exists():
        raise FileNotFoundError(f"Unknown agent: {agent_id}")
    return _metadata_from_payload(json.loads(metadata_file.read_text(encoding="utf-8")))


# Load all generated agent metadata records from disk.
def list_generated_agents(user_id: int) -> list[AgentMetadata]:
    user_dir = _user_agents_dir(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    agents: list[AgentMetadata] = []
    for metadata_file in user_dir.glob("*/metadata.json"):
        payload = json.loads(metadata_file.read_text(encoding="utf-8"))
        agents.append(_metadata_from_payload(payload))
    return sorted(agents, key=lambda item: item.created_at, reverse=True)


# Generate a new agent project on disk from the builder configuration.
def generate_agent_project(
    config: AgentConfigRequest,
    *,
    user: dict,
    settings: dict,
) -> AgentMetadata:
    GENERATED_AGENTS_DIR.mkdir(parents=True, exist_ok=True)

    provider = get_provider(config.provider_id)
    requirements = build_requirements(config)
    generated_files = preview_generated_files(config)
    agent_id = f"{slugify(config.agent_name)}-{uuid4().hex[:8]}"
    user_dir = _user_agents_dir(int(user["id"]))
    user_dir.mkdir(parents=True, exist_ok=True)
    agent_dir = user_dir / agent_id
    agent_dir.mkdir(parents=True, exist_ok=False)

    rendered_files = render_project_files(
        config=config,
        provider=provider,
        requirements=requirements,
        secret_names=provider["secret_names"],
    )

    generation_source: Literal["llm", "template"] = "template"
    logic_llm, extra_reqs, _gen_note = try_generate_logic_py(config, settings=settings)
    if logic_llm is not None:
        rendered_files["logic.py"] = logic_llm
        generation_source = "llm"
        requirements = sorted(set(requirements) | set(extra_reqs))
        rendered_files["requirements.txt"] = "".join(f"{line}\n" for line in requirements)

    for relative_path, content in rendered_files.items():
        file_path = agent_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    write_agent_environment(agent_dir, settings, config)

    if config.allow_file_uploads:
        uploads_dir = _uploads_dir(agent_dir)
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / ".gitkeep").write_text("", encoding="utf-8")

    repo_url = config.github_repo_url or settings.get("default_repo_url", "")

    metadata = AgentMetadata(
        user_id=int(user["id"]),
        agent_id=agent_id,
        agent_name=config.agent_name,
        description=config.description,
        instructions=config.instructions,
        template_id=config.template_id,
        provider_id=config.provider_id,
        model=config.model,
        frontend_type=config.frontend_type,
        temperature=config.temperature,
        enabled_tools=config.enabled_tools,
        allow_file_uploads=config.allow_file_uploads,
        supported_upload_types=config.supported_upload_types,
        github_repo_url=repo_url,
        github_repo_path="",
        github_commit_sha="",
        agent_dir=str(agent_dir),
        created_at=datetime.now(timezone.utc),
        has_secrets=has_saved_secrets(agent_dir),
        requirements=requirements,
        generated_files=generated_files,
        generation_source=generation_source,
        include_settings_api_keys=config.include_settings_api_keys,
        extra_secret_key_names=[s.key for s in config.secrets],
    )
    _write_metadata(agent_dir, metadata)
    return metadata


# Return a generated agent and refresh its secret presence from disk.
def get_generated_agent(user_id: int, agent_id: str) -> AgentMetadata:
    return load_agent_metadata(user_id, agent_id)


# Delete one generated agent and its local folder tree.
def delete_generated_agent(user_id: int, agent_id: str) -> AgentMetadata:
    metadata = get_generated_agent(user_id, agent_id)
    agent_dir = Path(metadata.agent_dir)
    if not agent_dir.exists():
        raise FileNotFoundError(f"Unknown agent: {agent_id}")
    shutil.rmtree(agent_dir)
    return metadata


# Build a recursive folder tree for a generated agent directory.
def get_generated_agent_tree(user_id: int, agent_id: str) -> AgentTreeNode:
    metadata = get_generated_agent(user_id, agent_id)
    root = Path(metadata.agent_dir)

    def build_tree(path: Path) -> AgentTreeNode:
        if path.is_dir():
            children = [
                build_tree(child)
                for child in sorted(
                    path.iterdir(),
                    key=lambda item: (not item.is_dir(), item.name.lower()),
                )
                if child.name != "__pycache__"
            ]
            return AgentTreeNode(
                name=path.name,
                path=str(path),
                node_type="directory",
                children=children,
            )

        return AgentTreeNode(
            name=path.name,
            path=str(path),
            node_type="file",
            children=[],
        )

    return build_tree(root)


# Check an existing generated agent into the configured repository on demand.
def checkin_generated_agent(
    user_id: int,
    *,
    user: dict,
    settings: dict,
    agent_id: str,
) -> tuple[AgentMetadata, str]:
    metadata = get_generated_agent(user_id, agent_id)
    repo_url = metadata.github_repo_url or settings.get("default_repo_url", "")
    if not repo_url:
        raise ValueError("Save a GitHub repo URL in Settings or on the agent before checking in.")

    repo_result = sync_generated_project_to_github(
        agent_dir=Path(metadata.agent_dir),
        agent_id=metadata.agent_id,
        repo_url=repo_url,
        github_token=settings.get("github_token", ""),
        commit_author_name=str(user["name"]),
        commit_author_email=str(user["email"]),
    )
    updated = metadata.model_copy(
        update={
            "github_repo_url": repo_url,
            "github_repo_path": repo_result["repo_path"],
            "github_commit_sha": repo_result["commit_sha"],
        }
    )
    _write_metadata(Path(updated.agent_dir), updated)
    summary = str(repo_result.get("summary") or "Check-in finished.")
    return updated, summary


# Save uploaded files for a generated agent and return their stored metadata.
def save_uploaded_files(user_id: int, agent_id: str, files: list[tuple[str, bytes]]) -> list[UploadedFileInfo]:
    metadata = get_generated_agent(user_id, agent_id)
    if not metadata.allow_file_uploads:
        raise ValueError("This generated agent does not allow file uploads.")

    agent_dir = Path(metadata.agent_dir)
    uploads_dir = _uploads_dir(agent_dir)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    saved: list[UploadedFileInfo] = []
    allowed_types = set(metadata.supported_upload_types)
    for original_name, payload in files:
        suffix = Path(original_name).suffix.lower().lstrip(".")
        if allowed_types and suffix and suffix not in allowed_types:
            raise ValueError(
                f"Unsupported upload type '{suffix}'. Allowed types: {', '.join(sorted(allowed_types))}"
            )

        stored_name = f"{uuid4().hex[:8]}-{Path(original_name).name}"
        stored_path = uploads_dir / stored_name
        stored_path.write_bytes(payload)
        saved.append(
            UploadedFileInfo(
                name=Path(original_name).name,
                stored_path=str(stored_path),
                size_bytes=len(payload),
                uploaded_at=datetime.now(timezone.utc),
            )
        )
    return list_uploaded_files(user_id, agent_id)


# Return the files previously uploaded for a generated agent.
def list_uploaded_files(user_id: int, agent_id: str) -> list[UploadedFileInfo]:
    metadata = get_generated_agent(user_id, agent_id)
    agent_dir = Path(metadata.agent_dir)
    uploads_dir = _uploads_dir(agent_dir)
    if not uploads_dir.exists():
        return []

    files: list[UploadedFileInfo] = []
    for file_path in sorted(uploads_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if file_path.name == ".gitkeep" or not file_path.is_file():
            continue
        stats = file_path.stat()
        files.append(
            UploadedFileInfo(
                name=file_path.name.split("-", 1)[1] if "-" in file_path.name else file_path.name,
                stored_path=str(file_path),
                size_bytes=stats.st_size,
                uploaded_at=datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc),
            )
        )
    return files
