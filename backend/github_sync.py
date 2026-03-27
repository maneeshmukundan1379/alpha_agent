"""
GitHub repo sync utilities for generated agent projects.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse


REPO_CACHE_DIR = Path(__file__).resolve().parent.parent / "repo_workdirs"


# Build a stable local directory name for a GitHub repo URL.
def _repo_slug(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    path = parsed.path.strip("/").removesuffix(".git") or repo_url.strip().replace("/", "__")
    return path.replace("/", "__") or "repo"


# Return whether the repo URL points to GitHub and needs token auth.
def _is_github_repo(repo_url: str) -> bool:
    parsed = urlparse(repo_url)
    return "github.com" in (parsed.netloc or "")


def _push_error_with_hint(message: str) -> str:
    """Append guidance when GitHub rejects HTTPS push (common: read-only token)."""
    text = (message or "").strip()
    lower = text.lower()
    if "403" in text or ("permission" in lower and "denied" in lower) or "access denied" in lower:
        text += (
            "\n\nYour token can reach GitHub but cannot push to this repo. Fix:\n"
            "• Classic PAT: enable the **repo** scope (full control of private repositories).\n"
            "• Fine-grained PAT: add this repository and set **Contents** to **Read and write**.\n"
            "• If the repo is under an **organization**, authorize SSO for the token (GitHub → Settings → "
            "Applications → Personal access tokens).\n"
            "Then paste the new token into Alpha Agent Builder → Settings → GitHub token and save."
        )
    return text


# Build a git extraheader argument for token-authenticated GitHub HTTPS requests.
def _git_auth_args(github_token: str) -> list[str]:
    token = github_token.strip()
    if not token:
        raise ValueError("Save a GitHub token in Settings before using a GitHub repo.")
    # GitHub recommends username `git` and the PAT as password for HTTPS Git.
    token_bytes = f"git:{token}".encode("utf-8")
    encoded = base64.b64encode(token_bytes).decode("utf-8")
    return ["-c", f"http.extraheader=AUTHORIZATION: basic {encoded}"]


# Run a git command with optional GitHub token authentication.
def _run_git(args: list[str], *, cwd: Path, github_token: str, use_auth: bool) -> str:
    auth_args = _git_auth_args(github_token) if use_auth else []
    command = ["git", *auth_args, *args]
    result = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError((result.stderr or result.stdout or "Git command failed.").strip())
    return result.stdout.strip()


def _run_git_allow_fail(
    args: list[str], *, cwd: Path, github_token: str, use_auth: bool
) -> tuple[int, str, str]:
    auth_args = _git_auth_args(github_token) if use_auth else []
    command = ["git", *auth_args, *args]
    result = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
    return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()


# List non-cache files under a directory (for sanity checks).
def _count_agent_files(agent_root: Path) -> int:
    n = 0
    for p in agent_root.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(".pyc"):
            n += 1
    return n


# Clone or refresh the target GitHub repository into the local cache.
def _prepare_repo(repo_url: str, github_token: str) -> Path:
    REPO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    repo_dir = REPO_CACHE_DIR / _repo_slug(repo_url)
    if not repo_dir.exists():
        clone_parent = repo_dir.parent
        auth_args = _git_auth_args(github_token) if _is_github_repo(repo_url) else []
        result = subprocess.run(
            ["git", *auth_args, "clone", repo_url, str(repo_dir)],
            cwd=clone_parent,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ValueError((result.stderr or result.stdout or "Git clone failed.").strip())
        return repo_dir

    use_auth = _is_github_repo(repo_url)
    auth_args = _git_auth_args(github_token) if use_auth else []

    fetch = subprocess.run(
        ["git", *auth_args, "fetch", "origin"],
        cwd=repo_dir,
        check=False,
        capture_output=True,
        text=True,
    )
    if fetch.returncode != 0:
        raise ValueError((fetch.stderr or fetch.stdout or "Git fetch failed.").strip())

    # New empty repos have no remote branches — `pull origin HEAD` fails with "couldn't find remote ref HEAD".
    ls_remote = subprocess.run(
        ["git", *auth_args, "ls-remote", "--heads", "origin"],
        cwd=repo_dir,
        check=False,
        capture_output=True,
        text=True,
    )
    if ls_remote.returncode != 0:
        raise ValueError((ls_remote.stderr or ls_remote.stdout or "Git ls-remote failed.").strip())
    if not (ls_remote.stdout or "").strip():
        return repo_dir

    last_err = ""
    for pull_ref in ("HEAD", "main", "master"):
        pull = subprocess.run(
            ["git", *auth_args, "pull", "--rebase", "origin", pull_ref],
            cwd=repo_dir,
            check=False,
            capture_output=True,
            text=True,
        )
        if pull.returncode == 0:
            break
        last_err = (pull.stderr or pull.stdout or "").strip()
    else:
        raise ValueError(last_err or "Git pull --rebase failed.")
    return repo_dir


# Copy the generated project into the target repository and push a commit.
def sync_generated_project_to_github(
    *,
    agent_dir: Path,
    agent_id: str,
    repo_url: str,
    github_token: str,
    commit_author_name: str,
    commit_author_email: str,
) -> dict[str, str]:
    use_auth = _is_github_repo(repo_url)
    repo_dir = _prepare_repo(repo_url, github_token)
    target_dir = repo_dir / agent_id
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(agent_dir, target_dir)

    file_count = _count_agent_files(target_dir)
    if file_count == 0:
        raise ValueError(
            f"No files to check in under '{agent_id}' (folder is empty or only __pycache__). "
            "Fix the agent project locally, then try again."
        )

    _run_git(["add", agent_id], cwd=repo_dir, github_token=github_token, use_auth=use_auth)
    staged = _run_git(
        ["diff", "--cached", "--name-only"],
        cwd=repo_dir,
        github_token=github_token,
        use_auth=use_auth,
    )
    staged_lines = [ln for ln in staged.splitlines() if ln.strip()]

    if not staged_lines:
        # Everything on disk is ignored, or Git thinks there is nothing new — diagnose.
        ignored_listing = _run_git(
            ["ls-files", "-o", "-i", "--exclude-standard", "--", agent_id],
            cwd=repo_dir,
            github_token=github_token,
            use_auth=use_auth,
        )
        ignored_paths = [ln for ln in ignored_listing.splitlines() if ln.strip()]
        if ignored_paths:
            sample = "\n".join(ignored_paths[:12])
            more = f"\n… and {len(ignored_paths) - 12} more." if len(ignored_paths) > 12 else ""
            raise ValueError(
                "Git did not stage any files: everything under this agent folder is ignored by "
                f".gitignore (or a global ignore). Update the repository's .gitignore so paths like "
                f"'{agent_id}/' or '*.py' under it are not excluded, then check in again.\n"
                f"Ignored paths (sample):\n{sample}{more}"
            )

        # Tracked files match the index — no new commit. Still try to push in case a prior commit never pushed.
        push_code, push_out, push_err = _run_git_allow_fail(
            ["push", "origin", "HEAD"],
            cwd=repo_dir,
            github_token=github_token,
            use_auth=_is_github_repo(repo_url),
        )
        commit_sha = _run_git(["rev-parse", "HEAD"], cwd=repo_dir, github_token=github_token, use_auth=use_auth)
        push_msg = (push_err or push_out or "").strip()
        if push_code != 0 and "Everything up-to-date" not in push_msg and "up to date" not in push_msg.lower():
            raise ValueError(
                _push_error_with_hint(
                    f"No new changes to commit under '{agent_id}' (GitHub may already have this exact tree). "
                    f"Push also failed: {push_msg or 'unknown error'}"
                )
            )
        return {
            "repo_path": str(target_dir),
            "commit_sha": commit_sha,
            "summary": (
                f"No new changes to commit for folder '{agent_id}' — the clone already matched your agent files. "
                f"If you do not see them on github.com, open the correct repo/branch and look under '{agent_id}/'. "
                f"Push status: {push_msg or 'ok / already up to date'}."
            ),
        }

    _run_git(
        [
            "-c",
            f"user.name={commit_author_name}",
            "-c",
            f"user.email={commit_author_email}",
            "commit",
            "-m",
            f"Update generated agent {agent_id}",
        ],
        cwd=repo_dir,
        github_token="",
        use_auth=False,
    )
    push_auth = _git_auth_args(github_token) if _is_github_repo(repo_url) else []
    result = subprocess.run(
        ["git", *push_auth, "push", "origin", "HEAD"],
        cwd=repo_dir,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(
            _push_error_with_hint((result.stderr or result.stdout or "Git push failed.").strip())
        )
    commit_sha = _run_git(["rev-parse", "HEAD"], cwd=repo_dir, github_token=github_token, use_auth=use_auth)
    n = len(staged_lines)
    return {
        "repo_path": str(target_dir),
        "commit_sha": commit_sha,
        "summary": (
            f"Committed and pushed {n} path(s) to the configured repo under '{agent_id}/' "
            f"(commit {commit_sha[:7]}). Refresh github.com to see the update."
        ),
    }
