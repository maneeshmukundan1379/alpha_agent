"""
FastAPI backend for Alpha Agent Builder.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .auth_store import (
    change_user_password,
    create_user,
    delete_session,
    get_user_by_session,
    get_user_secret_values,
    get_user_settings,
    init_db,
    login_user,
    update_user_profile,
    update_user_settings,
)
from .agent_editor import apply_agent_edits
from .generator import (
    checkin_generated_agent,
    delete_generated_agent,
    generate_agent_project,
    get_generated_agent,
    get_generated_agent_tree,
    list_generated_agents,
    list_uploaded_files,
    save_uploaded_files,
)
from .providers import list_providers
from .requirements_builder import build_requirements, preview_generated_files
from .runner import get_agent_logs, is_agent_running, run_agent, stop_local_ui_server
from .schemas import (
    AgentDetailResponse,
    AgentEditChatRequest,
    AgentEditChatResponse,
    AgentListResponse,
    AgentLogsResponse,
    AgentTreeResponse,
    AgentUploadsResponse,
    AuthResponse,
    ChangePasswordRequest,
    CheckInAgentResponse,
    GenerateAgentResponse,
    LoginRequest,
    MeResponse,
    MessageResponse,
    ProfileResponse,
    ProvidersResponse,
    RequirementsPreviewRequest,
    RequirementsPreviewResponse,
    RunAgentRequest,
    RunAgentResponse,
    SettingsPayload,
    SettingsResponse,
    SignupRequest,
    UpdateProfileRequest,
    UpdateSettingsRequest,
    UserProfile,
)

init_db()

app = FastAPI(title="Alpha Agent Builder API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Resolve the current authenticated user from the bearer token header.
def require_user(authorization: str | None = Header(default=None)) -> dict:
    header = (authorization or "").strip()
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required.")
    token = header.split(" ", 1)[1].strip()
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    user["session_token"] = token
    return user


# Convert a raw user dict into the public profile response model.
def _user_profile(user: dict) -> UserProfile:
    return UserProfile(**user)


# Convert stored settings into the response model.
def _settings_payload(settings: dict) -> SettingsPayload:
    return SettingsPayload(**settings)


# Return the basic health status for the builder backend.
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Create a new user account and return an authenticated session.
@app.post("/api/auth/signup", response_model=AuthResponse)
def signup(request: SignupRequest) -> AuthResponse:
    ok, message, user = create_user(request.name, request.username, request.email, request.password)
    if not ok or not user:
        raise HTTPException(status_code=400, detail=message)
    login_ok, login_message, login_user_record, token = login_user(request.email, request.password)
    if not login_ok or not login_user_record or not token:
        raise HTTPException(status_code=400, detail=login_message)
    return AuthResponse(
        token=token,
        user=_user_profile(login_user_record),
        settings=_settings_payload(get_user_settings(int(login_user_record["id"]))),
    )


# Log a user in and return a fresh session token.
@app.post("/api/auth/login", response_model=AuthResponse)
def login(request: LoginRequest) -> AuthResponse:
    ok, message, user, token = login_user(request.identifier, request.password)
    if not ok or not user or not token:
        raise HTTPException(status_code=401, detail=message)
    return AuthResponse(
        token=token,
        user=_user_profile(user),
        settings=_settings_payload(get_user_settings(int(user["id"]))),
    )


# Return the current authenticated user profile and settings.
@app.get("/api/auth/me", response_model=MeResponse)
def me(user: dict = Depends(require_user)) -> MeResponse:
    return MeResponse(
        user=_user_profile(user),
        settings=_settings_payload(get_user_settings(int(user["id"]))),
    )


# Delete the current session token.
@app.post("/api/auth/logout", response_model=MessageResponse)
def logout(user: dict = Depends(require_user)) -> MessageResponse:
    delete_session(str(user["session_token"]))
    return MessageResponse(message="Logged out.")


# Update the current user's basic account profile.
@app.put("/api/settings/profile", response_model=ProfileResponse)
def update_profile(request: UpdateProfileRequest, user: dict = Depends(require_user)) -> ProfileResponse:
    ok, message, updated = update_user_profile(
        int(user["id"]),
        name=request.name,
        username=request.username,
        email=request.email,
    )
    if not ok or not updated:
        raise HTTPException(status_code=400, detail=message)
    return ProfileResponse(user=_user_profile(updated))


# Update the current user's password.
@app.put("/api/settings/password", response_model=MessageResponse)
def update_password(request: ChangePasswordRequest, user: dict = Depends(require_user)) -> MessageResponse:
    ok, message = change_user_password(int(user["id"]), request.current_password, request.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return MessageResponse(message=message)


# Return the current user's saved API and GitHub settings.
@app.get("/api/settings", response_model=SettingsResponse)
def settings(user: dict = Depends(require_user)) -> SettingsResponse:
    return SettingsResponse(settings=_settings_payload(get_user_settings(int(user["id"]))))


# Save API keys and GitHub settings for the current user.
@app.put("/api/settings", response_model=SettingsResponse)
def save_settings(request: UpdateSettingsRequest, user: dict = Depends(require_user)) -> SettingsResponse:
    updated = update_user_settings(
        int(user["id"]),
        openai_api_key=request.openai_api_key,
        gemini_api_key=request.gemini_api_key,
        github_token=request.github_token,
        default_repo_url=request.default_repo_url,
    )
    return SettingsResponse(settings=_settings_payload(updated))


# Return the supported provider options and secret requirements.
@app.get("/api/providers", response_model=ProvidersResponse)
def providers(user: dict = Depends(require_user)) -> ProvidersResponse:
    return ProvidersResponse(providers=list_providers())


# Preview the generated Python requirements and file set for a builder config.
@app.post("/api/requirements/preview", response_model=RequirementsPreviewResponse)
def requirements_preview(
    request: RequirementsPreviewRequest,
    user: dict = Depends(require_user),
) -> RequirementsPreviewResponse:
    return RequirementsPreviewResponse(
        requirements=build_requirements(request.config),
        generated_files=preview_generated_files(request.config),
    )


# Generate a new agent project on disk from the submitted builder form.
@app.post("/api/agents/generate", response_model=GenerateAgentResponse)
def generate_agent(
    request: RequirementsPreviewRequest,
    user: dict = Depends(require_user),
) -> GenerateAgentResponse:
    try:
        agent = generate_agent_project(
            request.config,
            user=user,
            settings=get_user_secret_values(int(user["id"])),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    msg = f"Generated agent '{agent.agent_name}' locally at {agent.agent_dir}."
    if agent.generation_source == "llm":
        msg += " logic.py was written by your LLM from the instructions (review and test it)."
    else:
        msg += " Template logic.py was used (no API key in Settings, or LLM codegen failed validation)."
    return GenerateAgentResponse(message=msg, agent=agent)


# Return all generated agents known to the builder app.
@app.get("/api/agents", response_model=AgentListResponse)
def list_agents(user: dict = Depends(require_user)) -> AgentListResponse:
    return AgentListResponse(agents=list_generated_agents(int(user["id"])))


# Return metadata for one generated agent.
@app.get("/api/agents/{agent_id}", response_model=AgentDetailResponse)
def get_agent(agent_id: str, user: dict = Depends(require_user)) -> AgentDetailResponse:
    try:
        return AgentDetailResponse(agent=get_generated_agent(int(user["id"]), agent_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# Check an existing generated agent into the configured Git repository.
@app.post("/api/agents/{agent_id}/checkin", response_model=CheckInAgentResponse)
def checkin_agent(agent_id: str, user: dict = Depends(require_user)) -> CheckInAgentResponse:
    try:
        agent, checkin_summary = checkin_generated_agent(
            int(user["id"]),
            user=user,
            settings=get_user_secret_values(int(user["id"])),
            agent_id=agent_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CheckInAgentResponse(
        message=f"{agent.agent_name}: {checkin_summary}",
        agent=agent,
    )


# Return the local folder tree for a generated agent.
@app.get("/api/agents/{agent_id}/tree", response_model=AgentTreeResponse)
def get_agent_tree(agent_id: str, user: dict = Depends(require_user)) -> AgentTreeResponse:
    try:
        tree = get_generated_agent_tree(int(user["id"]), agent_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AgentTreeResponse(agent_id=agent_id, tree=tree)


# Chat with an LLM to refine whitelisted source files for one generated agent.
@app.post("/api/agents/{agent_id}/edit-chat", response_model=AgentEditChatResponse)
def agent_edit_chat(
    agent_id: str,
    request: AgentEditChatRequest,
    user: dict = Depends(require_user),
) -> AgentEditChatResponse:
    try:
        assistant_message, updated_files, activity_log = apply_agent_edits(
            int(user["id"]),
            agent_id,
            [message.model_dump() for message in request.messages],
            settings=get_user_secret_values(int(user["id"])),
            include_static_diagnostics=request.include_static_diagnostics,
            runtime_error=request.runtime_error or "",
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return AgentEditChatResponse(
        assistant_message=assistant_message,
        updated_files=updated_files,
        activity_log=activity_log,
    )


# Delete one generated agent and its local folder tree.
@app.delete("/api/agents/{agent_id}", response_model=MessageResponse)
def delete_agent(agent_id: str, user: dict = Depends(require_user)) -> MessageResponse:
    if is_agent_running(agent_id):
        raise HTTPException(status_code=409, detail="Stop the running agent before deleting it.")
    stop_local_ui_server(agent_id)
    try:
        agent = delete_generated_agent(int(user["id"]), agent_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MessageResponse(message=f"Deleted '{agent.agent_name}' and removed its local folder.")


# Return the files uploaded for one generated agent.
@app.get("/api/agents/{agent_id}/uploads", response_model=AgentUploadsResponse)
def agent_uploads(agent_id: str, user: dict = Depends(require_user)) -> AgentUploadsResponse:
    try:
        files = list_uploaded_files(int(user["id"]), agent_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AgentUploadsResponse(agent_id=agent_id, files=files)


# Save uploaded files for one generated agent.
@app.post("/api/agents/{agent_id}/uploads", response_model=AgentUploadsResponse)
async def upload_agent_files(
    agent_id: str,
    files: list[UploadFile] = File(...),
    user: dict = Depends(require_user),
) -> AgentUploadsResponse:
    try:
        payloads = [(file.filename or "upload.txt", await file.read()) for file in files]
        saved = save_uploaded_files(int(user["id"]), agent_id, payloads)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AgentUploadsResponse(agent_id=agent_id, files=saved)


# Start running one generated agent with the supplied prompt.
@app.post("/api/agents/run", response_model=RunAgentResponse)
def execute_agent(request: RunAgentRequest, user: dict = Depends(require_user)) -> RunAgentResponse:
    try:
        run, local_url = run_agent(
            int(user["id"]),
            get_user_secret_values(int(user["id"])),
            request.agent_id,
            request.prompt,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if local_url:
        message = (
            f"Local agent UI is ready for '{request.agent_id}'. "
            "Open the URL in a new browser tab to use it outside this page."
        )
    else:
        message = f"Started agent '{request.agent_id}'."
    return RunAgentResponse(message=message, run=run, local_url=local_url)


# Return the latest run status and logs for one generated agent.
@app.get("/api/agents/{agent_id}/logs", response_model=AgentLogsResponse)
def agent_logs(agent_id: str, user: dict = Depends(require_user)) -> AgentLogsResponse:
    try:
        run, logs = get_agent_logs(int(user["id"]), agent_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AgentLogsResponse(run=run, logs=logs)
