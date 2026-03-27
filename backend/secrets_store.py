"""
Helpers for storing generated agent secrets locally.
"""

from __future__ import annotations

from pathlib import Path

from .schemas import AgentConfigRequest, SecretInput


def _escape_env_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


# Write a generated agent's secrets into its local .env file (legacy: custom secrets only).
def write_secrets(agent_dir: Path, secrets: list[SecretInput]) -> None:
    env_path = agent_dir / ".env"
    if not secrets:
        env_path.write_text("", encoding="utf-8")
        return

    lines = [f'{secret.key}="{_escape_env_value(secret.value)}"' for secret in secrets]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# Merge Settings provider keys (optional) and per-agent secrets into `.env`.
# Per-agent `config.secrets` override Settings when the same variable name appears.
def write_agent_environment(
    agent_dir: Path,
    settings: dict[str, str],
    config: AgentConfigRequest,
) -> None:
    env_path = agent_dir / ".env"
    merged: dict[str, str] = {}

    if config.include_settings_api_keys:
        oa = (settings.get("openai_api_key") or "").strip()
        if oa:
            merged["OPENAI_API_KEY"] = oa
        gm = (settings.get("gemini_api_key") or "").strip()
        if gm:
            merged["GEMINI_API_KEY"] = gm
            merged["GOOGLE_API_KEY"] = gm
        gh = (settings.get("github_token") or "").strip()
        if gh:
            merged["GITHUB_TOKEN"] = gh

    for secret in config.secrets:
        merged[secret.key] = secret.value

    if not merged:
        env_path.write_text("", encoding="utf-8")
        return

    lines = [f'{key}="{_escape_env_value(val)}"' for key, val in sorted(merged.items())]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# Return whether an agent has a saved .env file with content.
def has_saved_secrets(agent_dir: Path) -> bool:
    env_path = agent_dir / ".env"
    return env_path.exists() and bool(env_path.read_text(encoding="utf-8").strip())


# Build a safe .env.example file based on the required secret keys.
def build_env_example(secret_names: list[str]) -> str:
    if not secret_names:
        return "# No required secrets for this template.\n"
    return "".join(f"{secret_name}=\n" for secret_name in secret_names)
