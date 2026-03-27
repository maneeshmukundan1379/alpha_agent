"""
Provider catalog for Alpha Agent Builder.
"""

from __future__ import annotations

from copy import deepcopy


PROVIDERS = [
    {
        "id": "openai",
        "label": "OpenAI",
        "description": "Use OpenAI chat models through the official OpenAI Python SDK.",
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1"],
        "secret_names": ["OPENAI_API_KEY"],
    },
    {
        "id": "gemini",
        "label": "Google Gemini",
        "description": "Use Gemini through Google's OpenAI-compatible endpoint.",
        "default_model": "gemini-2.5-flash",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
        "secret_names": ["GEMINI_API_KEY"],
    },
]


# Return the supported provider catalog for UI forms and validation.
def list_providers() -> list[dict]:
    return deepcopy(PROVIDERS)


# Look up a single provider definition by its identifier.
def get_provider(provider_id: str) -> dict:
    for provider in PROVIDERS:
        if provider["id"] == provider_id:
            return deepcopy(provider)
    raise ValueError(f"Unsupported provider: {provider_id}")
