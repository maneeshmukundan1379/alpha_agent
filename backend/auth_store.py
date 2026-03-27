"""
SQLite-backed auth, settings, and session utilities for Alpha Agent Builder.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any

DB_FILE = os.path.join(os.path.dirname(__file__), "alpha_agent_builder.db")


# Open a SQLite connection for auth and settings operations.
def _connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


# Initialize the database tables used by the builder app.
def init_db() -> None:
    with _connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                openai_api_key TEXT NOT NULL DEFAULT '',
                gemini_api_key TEXT NOT NULL DEFAULT '',
                github_token TEXT NOT NULL DEFAULT '',
                default_repo_url TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )


# Hash passwords before storing them in the database.
def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# Normalize username or email identifiers for lookups.
def _normalize_identifier(identifier: str) -> str:
    return (identifier or "").strip().lower()


# Convert a user row into a JSON-friendly dictionary.
def _user_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "username": str(row["username"]),
        "email": str(row["email"]),
        "created_at": str(row["created_at"]),
    }


# Return the settings row for a given user, creating a default one if needed.
def _ensure_settings_row(user_id: int) -> None:
    with _connect_db() as conn:
        conn.execute(
            """
            INSERT INTO user_settings (user_id)
            VALUES (?)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (user_id,),
        )


# Return one user by username or email.
def get_user_record(identifier: str) -> dict[str, Any] | None:
    clean_identifier = _normalize_identifier(identifier)
    if not clean_identifier:
        return None

    with _connect_db() as conn:
        row = conn.execute(
            """
            SELECT id, name, username, email, password_hash, created_at
            FROM users
            WHERE username = ? OR email = ?
            LIMIT 1
            """,
            (clean_identifier, clean_identifier),
        ).fetchone()

    if not row:
        return None

    payload = _user_row_to_dict(row)
    payload["password_hash"] = str(row["password_hash"])
    return payload


# Create a user account and a matching default settings row.
def create_user(name: str, username: str, email: str, password: str) -> tuple[bool, str, dict[str, Any] | None]:
    clean_name = (name or "").strip()
    clean_username = _normalize_identifier(username)
    clean_email = _normalize_identifier(email)
    clean_password = password or ""
    if not all([clean_name, clean_username, clean_email, clean_password]):
        return False, "Please fill in all signup fields.", None

    try:
        with _connect_db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (name, username, email, password_hash)
                VALUES (?, ?, ?, ?)
                """,
                (clean_name, clean_username, clean_email, _hash_password(clean_password)),
            )
            user_id = int(cursor.lastrowid)
        _ensure_settings_row(user_id)
        return True, "Signup successful.", get_user_by_id(user_id)
    except sqlite3.IntegrityError:
        return False, "Username or email already exists.", None


# Look up a user record by numeric id.
def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with _connect_db() as conn:
        row = conn.execute(
            """
            SELECT id, name, username, email, created_at
            FROM users
            WHERE id = ?
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    return _user_row_to_dict(row) if row else None


# Create a new session token for an authenticated user.
def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with _connect_db() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id) VALUES (?, ?)",
            (token, user_id),
        )
    return token


# Authenticate a user and return a new session token.
def login_user(identifier: str, password: str) -> tuple[bool, str, dict[str, Any] | None, str | None]:
    clean_identifier = _normalize_identifier(identifier)
    clean_password = password or ""
    if not clean_identifier or not clean_password:
        return False, "Please enter username/email and password.", None, None

    user_record = get_user_record(clean_identifier)
    if not user_record:
        return False, "User not found.", None, None
    if user_record["password_hash"] != _hash_password(clean_password):
        return False, "Invalid password.", None, None

    token = create_session(int(user_record["id"]))
    return True, "Login successful.", get_user_by_id(int(user_record["id"])), token


# Resolve a session token back to its authenticated user.
def get_user_by_session(token: str) -> dict[str, Any] | None:
    clean_token = (token or "").strip()
    if not clean_token:
        return None

    with _connect_db() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.name, u.username, u.email, u.created_at
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            LIMIT 1
            """,
            (clean_token,),
        ).fetchone()
    return _user_row_to_dict(row) if row else None


# Delete a session token when the user logs out.
def delete_session(token: str) -> None:
    with _connect_db() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", ((token or "").strip(),))


# Return the saved integration settings for a user.
def get_user_settings(user_id: int) -> dict[str, Any]:
    _ensure_settings_row(user_id)
    with _connect_db() as conn:
        row = conn.execute(
            """
            SELECT openai_api_key, gemini_api_key, github_token, default_repo_url, updated_at
            FROM user_settings
            WHERE user_id = ?
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    assert row is not None
    return {
        "has_openai_api_key": bool(str(row["openai_api_key"] or "").strip()),
        "has_gemini_api_key": bool(str(row["gemini_api_key"] or "").strip()),
        "has_github_token": bool(str(row["github_token"] or "").strip()),
        "default_repo_url": str(row["default_repo_url"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


# Return the raw stored secrets for backend-only usage.
def get_user_secret_values(user_id: int) -> dict[str, str]:
    _ensure_settings_row(user_id)
    with _connect_db() as conn:
        row = conn.execute(
            """
            SELECT openai_api_key, gemini_api_key, github_token, default_repo_url
            FROM user_settings
            WHERE user_id = ?
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    assert row is not None
    return {
        "openai_api_key": str(row["openai_api_key"] or ""),
        "gemini_api_key": str(row["gemini_api_key"] or ""),
        "github_token": str(row["github_token"] or ""),
        "default_repo_url": str(row["default_repo_url"] or ""),
    }


# Save integration settings and API keys for a user.
def update_user_settings(
    user_id: int,
    *,
    openai_api_key: str | None = None,
    gemini_api_key: str | None = None,
    github_token: str | None = None,
    default_repo_url: str | None = None,
) -> dict[str, Any]:
    _ensure_settings_row(user_id)
    current = get_user_secret_values(user_id)
    next_values = {
        "openai_api_key": current["openai_api_key"] if openai_api_key is None else openai_api_key.strip(),
        "gemini_api_key": current["gemini_api_key"] if gemini_api_key is None else gemini_api_key.strip(),
        "github_token": current["github_token"] if github_token is None else github_token.strip(),
        "default_repo_url": current["default_repo_url"] if default_repo_url is None else default_repo_url.strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with _connect_db() as conn:
        conn.execute(
            """
            UPDATE user_settings
            SET openai_api_key = ?, gemini_api_key = ?, github_token = ?, default_repo_url = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (
                next_values["openai_api_key"],
                next_values["gemini_api_key"],
                next_values["github_token"],
                next_values["default_repo_url"],
                next_values["updated_at"],
                user_id,
            ),
        )
    return get_user_settings(user_id)


# Update the current user's basic profile fields.
def update_user_profile(user_id: int, *, name: str, username: str, email: str) -> tuple[bool, str, dict[str, Any] | None]:
    clean_name = (name or "").strip()
    clean_username = _normalize_identifier(username)
    clean_email = _normalize_identifier(email)
    if not all([clean_name, clean_username, clean_email]):
        return False, "Name, username, and email are required.", None

    try:
        with _connect_db() as conn:
            conn.execute(
                """
                UPDATE users
                SET name = ?, username = ?, email = ?
                WHERE id = ?
                """,
                (clean_name, clean_username, clean_email, user_id),
            )
        return True, "Profile updated.", get_user_by_id(user_id)
    except sqlite3.IntegrityError:
        return False, "Username or email already exists.", None


# Change the current user's password after verifying the old password.
def change_user_password(user_id: int, current_password: str, new_password: str) -> tuple[bool, str]:
    clean_current = current_password or ""
    clean_new = new_password or ""
    if not clean_current or not clean_new:
        return False, "Current password and new password are required."

    user_record = get_user_by_id(user_id)
    if not user_record:
        return False, "User not found."

    with _connect_db() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ? LIMIT 1",
            (user_id,),
        ).fetchone()
        if not row or str(row["password_hash"]) != _hash_password(clean_current):
            return False, "Current password is incorrect."
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (_hash_password(clean_new), user_id),
        )
    return True, "Password updated."
