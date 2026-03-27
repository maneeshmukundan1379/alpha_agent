"""
Local process runner for generated agents.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .generator import get_generated_agent, list_uploaded_files
from .schemas import AgentMetadata, RunRecord

_run_lock = threading.Lock()
_active_run_id: str | None = None
_run_records: dict[str, RunRecord] = {}
_prepared_agents: dict[str, str] = {}
_ui_servers: dict[str, subprocess.Popen] = {}
_ui_server_lock = threading.Lock()


# Stop a background Gradio, API, or API+Vite server for one agent, if any.
def stop_local_ui_server(agent_id: str) -> None:
    with _ui_server_lock:
        raw = _ui_servers.pop(agent_id, None)
    procs: list[subprocess.Popen] = raw if isinstance(raw, list) else ([raw] if raw is not None else [])
    for proc in procs:
        if proc is None or proc.poll() is not None:
            continue
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


# Pick a free TCP port on localhost for spawned agent UIs.
def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# Start Gradio, FastAPI, or FastAPI + Vite (React) for the agent and return (run_record, browser_url).
def _start_local_ui_server(
    settings: dict[str, str],
    metadata: AgentMetadata,
) -> tuple[RunRecord, str]:
    agent_id = metadata.agent_id
    agent_dir = Path(metadata.agent_dir)
    agent_dir.mkdir(parents=True, exist_ok=True)
    _ensure_agent_dependencies(agent_dir)
    stop_local_ui_server(agent_id)

    port = _find_free_port()
    runs_dir = _runs_dir(agent_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    serve_log = runs_dir / f"serve_{uuid4().hex[:8]}.log"

    env = {
        **dict(os.environ),
        "OPENAI_API_KEY": settings.get("openai_api_key", ""),
        "GEMINI_API_KEY": settings.get("gemini_api_key", ""),
        "GOOGLE_API_KEY": settings.get("gemini_api_key", ""),
        "GITHUB_TOKEN": settings.get("github_token", ""),
        "ALPHA_AGENT_MODEL": metadata.model,
        "ALPHA_AGENT_PORT": str(port),
    }

    if metadata.frontend_type == "gradio":
        command = [sys.executable, "app.py"]
        local_url = f"http://127.0.0.1:{port}/"
        ready_url = local_url
    elif metadata.frontend_type == "react":
        react_dir = agent_dir / "react-ui"
        if not react_dir.is_dir():
            raise RuntimeError("react-ui/ missing — regenerate this agent with the React frontend.")
        npm = shutil.which("npm")
        if not npm:
            raise RuntimeError(
                "Node.js/npm is required to run React agents. Install from https://nodejs.org/ and retry."
            )
        (react_dir / ".env.development.local").write_text(
            f"VITE_API_URL=http://127.0.0.1:{port}\n",
            encoding="utf-8",
        )
        npm_install = subprocess.run(
            [npm, "install"],
            cwd=str(react_dir),
            env={**dict(os.environ), **env},
            capture_output=True,
            text=True,
            timeout=300,
        )
        if npm_install.returncode != 0:
            tail = (npm_install.stdout + "\n" + npm_install.stderr).strip()[-4000:]
            raise RuntimeError(f"npm install failed in react-ui/.\n{tail}")

        api_port = port
        vite_port = _find_free_port()
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
        ]
        local_url = f"http://127.0.0.1:{vite_port}/"
        ready_url = f"http://127.0.0.1:{api_port}/health"
    else:
        raise ValueError("Unsupported frontend for local UI server.")

    log_handle = serve_log.open("w", encoding="utf-8")
    if metadata.frontend_type == "react":
        log_handle.write(f"Starting API: {' '.join(command)}\nAPI port: {port}\n\n")
    else:
        log_handle.write(f"Starting local UI: {' '.join(command)}\nPort: {port}\n\n")
    log_handle.flush()

    process = subprocess.Popen(
        command,
        cwd=agent_dir,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    procs: list[subprocess.Popen] = [process]

    try:
        deadline = time.time() + 50.0
        started = False
        while time.time() < deadline:
            if process.poll() is not None:
                try:
                    log_handle.flush()
                except OSError:
                    pass
                tail = serve_log.read_text(encoding="utf-8")[-4000:] if serve_log.exists() else ""
                raise RuntimeError(
                    f"Local UI process exited early (code {process.returncode}).\n{tail}"
                )
            try:
                urllib.request.urlopen(ready_url, timeout=2)
                started = True
                break
            except (urllib.error.URLError, OSError):
                time.sleep(0.35)
        if not started:
            raise RuntimeError(f"Timed out waiting for server at {ready_url}")

        if metadata.frontend_type == "react":
            vite_cmd = [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", str(vite_port)]
            log_handle.write(f"\nStarting Vite: {' '.join(vite_cmd)}\nVite port: {vite_port}\n\n")
            log_handle.flush()
            vite_proc = subprocess.Popen(
                vite_cmd,
                cwd=str(agent_dir / "react-ui"),
                env={**dict(os.environ), **env},
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
            procs.append(vite_proc)
            deadline_v = time.time() + 90.0
            vite_ok = False
            vite_url = f"http://127.0.0.1:{vite_port}/"
            while time.time() < deadline_v:
                if vite_proc.poll() is not None:
                    try:
                        log_handle.flush()
                    except OSError:
                        pass
                    tail = serve_log.read_text(encoding="utf-8")[-4000:] if serve_log.exists() else ""
                    raise RuntimeError(
                        f"Vite dev server exited early (code {vite_proc.returncode}).\n{tail}"
                    )
                try:
                    urllib.request.urlopen(vite_url, timeout=2)
                    vite_ok = True
                    break
                except (urllib.error.URLError, OSError):
                    time.sleep(0.4)
            if not vite_ok:
                raise RuntimeError(f"Timed out waiting for Vite at {vite_url}")
    except Exception:
        stop_local_ui_server(agent_id)
        try:
            log_handle.write("\n--- Server failed to start ---\n")
            log_handle.flush()
        except OSError:
            pass
        log_handle.close()
        raise

    with _ui_server_lock:
        _ui_servers[agent_id] = procs

    log_handle.write(f"\n--- Local UI ready ---\nOpen in browser: {local_url}\n")
    log_handle.flush()
    log_handle.close()

    now = datetime.now(timezone.utc)
    run = RunRecord(
        run_id=uuid4().hex[:10],
        agent_id=agent_id,
        status="completed",
        command=command,
        prompt="(local web UI)",
        started_at=now,
        finished_at=now,
        log_path=str(serve_log),
    )
    _write_latest_run(agent_dir, run)
    return run, local_url


# Return whether the given agent currently has the active running subprocess.
def is_agent_running(agent_id: str) -> bool:
    with _run_lock:
        if not _active_run_id:
            return False
        active = _run_records.get(_active_run_id)
        return bool(active and active.status == "running" and active.agent_id == agent_id)


# Install the generated agent dependencies into the backend runtime when needed.
def _ensure_agent_dependencies(agent_dir: Path) -> None:
    requirements_path = agent_dir / "requirements.txt"
    if not requirements_path.exists():
        return

    requirements_hash = hashlib.sha256(requirements_path.read_bytes()).hexdigest()
    cache_key = str(agent_dir)
    if _prepared_agents.get(cache_key) == requirements_hash:
        return

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            str(requirements_path),
        ],
        cwd=agent_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        output = (result.stdout + "\n" + result.stderr).strip()
        raise RuntimeError(f"Failed to install generated agent requirements.\n{output}")

    _prepared_agents[cache_key] = requirements_hash


# Return the runs directory for a generated agent.
def _runs_dir(agent_dir: Path) -> Path:
    return agent_dir / "runs"


# Return the metadata file that stores the latest run summary.
def _latest_run_path(agent_dir: Path) -> Path:
    return _runs_dir(agent_dir) / "latest_run.json"


# Persist the latest run state to disk for later retrieval.
def _write_latest_run(agent_dir: Path, run: RunRecord) -> None:
    _runs_dir(agent_dir).mkdir(parents=True, exist_ok=True)
    _latest_run_path(agent_dir).write_text(
        json.dumps(
            {
                **run.model_dump(),
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


# Mark a run as completed or failed once its subprocess exits.
def _watch_process(process: subprocess.Popen[str], run_id: str, agent_dir: Path) -> None:
    global _active_run_id

    assert process.stdout is not None
    log_chunks: list[str] = []
    for line in process.stdout:
        log_chunks.append(line)
        log_path = Path(_run_records[run_id].log_path)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    return_code = process.wait()
    with _run_lock:
        current = _run_records[run_id]
        status = "completed" if return_code == 0 else "failed"
        updated = current.model_copy(
            update={
                "status": status,
                "finished_at": datetime.now(timezone.utc),
            }
        )
        _run_records[run_id] = updated
        _active_run_id = None
        _write_latest_run(agent_dir, updated)


# Start a generated agent: local web UI for Gradio/FastAPI, else one-shot CLI run.
def run_agent(user_id: int, settings: dict[str, str], agent_id: str, prompt: str) -> tuple[RunRecord, str | None]:
    global _active_run_id

    metadata = get_generated_agent(user_id, agent_id)
    agent_dir = Path(metadata.agent_dir)
    agent_dir.mkdir(parents=True, exist_ok=True)
    _ensure_agent_dependencies(agent_dir)

    if metadata.frontend_type in ("gradio", "react"):
        run, url = _start_local_ui_server(settings, metadata)
        return run, url

    clean_prompt = (prompt or "").strip()
    if not clean_prompt:
        raise ValueError("A prompt is required to run CLI agents.")

    with _run_lock:
        if _active_run_id:
            active = _run_records[_active_run_id]
            if active.status == "running":
                raise RuntimeError(
                    f"Another agent is already running: {active.agent_id}. Wait for it to finish first."
                )

        runs_dir = _runs_dir(agent_dir)
        runs_dir.mkdir(parents=True, exist_ok=True)
        run_id = uuid4().hex[:10]
        log_path = runs_dir / f"{run_id}.log"
        command = [sys.executable, "run_agent.py", clean_prompt]
        if metadata.allow_file_uploads:
            uploaded_files = list_uploaded_files(user_id, agent_id)
            command.extend(file.stored_path for file in uploaded_files)
        env = {
            **dict(os.environ),
            "OPENAI_API_KEY": settings.get("openai_api_key", ""),
            "GEMINI_API_KEY": settings.get("gemini_api_key", ""),
            "GOOGLE_API_KEY": settings.get("gemini_api_key", ""),
            "GITHUB_TOKEN": settings.get("github_token", ""),
            "ALPHA_AGENT_MODEL": metadata.model,
        }
        process = subprocess.Popen(
            command,
            cwd=agent_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        run = RunRecord(
            run_id=run_id,
            agent_id=agent_id,
            status="running",
            command=command,
            prompt=clean_prompt,
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            log_path=str(log_path),
        )
        _run_records[run_id] = run
        _active_run_id = run_id
        _write_latest_run(agent_dir, run)

    watcher = threading.Thread(
        target=_watch_process,
        args=(process, run_id, agent_dir),
        daemon=True,
    )
    watcher.start()
    return run, None


# Return the latest run record and current logs for a generated agent.
def get_agent_logs(user_id: int, agent_id: str) -> tuple[RunRecord | None, str]:
    metadata = get_generated_agent(user_id, agent_id)
    agent_dir = Path(metadata.agent_dir)
    latest_run_file = _latest_run_path(agent_dir)
    if not latest_run_file.exists():
        return None, ""

    payload = json.loads(latest_run_file.read_text(encoding="utf-8"))
    run = RunRecord(
        **{
            **payload,
            "started_at": datetime.fromisoformat(payload["started_at"]),
            "finished_at": datetime.fromisoformat(payload["finished_at"])
            if payload.get("finished_at")
            else None,
        }
    )
    log_path = Path(run.log_path)
    logs = log_path.read_text(encoding="utf-8") if log_path.exists() else ""

    with _run_lock:
        current = _run_records.get(run.run_id)
        if current:
            run = current
    return run, logs
