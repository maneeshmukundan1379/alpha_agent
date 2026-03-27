# Alpha Agent Builder — architecture and call flow

This document uses **plain-text flowcharts** (box-drawing characters) so the diagrams read like a classic flowchart in any editor or viewer—no Mermaid. The React UI (`frontend/`) calls **FastAPI** in `backend/main.py` over HTTP.

**How to read import arrows:** in §1, lines like `main.py ──► generator.py` mean *main.py imports (depends on) generator.py*.

---

## 1. Module dependency flowchart (who imports whom)

```
                              ┌────────────────────────────────────────────┐
                              │              ENTRY LAYER                   │
                              │             backend/main.py              │
                              │  Exposes HTTP API; ties requests to code │
                              └──────────────────────┬───────────────────┘
                                                     │
       ┌───────────────┬────────────────────────────┼────────────────────────────┬───────────────────┐
       │               │                            │                            │                   │
       ▼               ▼                            ▼                            ▼                   ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ auth_store   │ │  schemas     │ │  providers   │ │ requirements_    │ │  generator       │
│    .py       │ │    .py       │ │    .py       │ │ builder.py       │ │    .py           │
│ User DB,     │ │ Pydantic API │ │ Pick model,  │ │ Turn UI config   │ │ Assemble full    │
│ sessions     │ │ DTOs         │ │ SDK snippets │ │ into requirements│ │ agent on disk    │
└──────────────┘ └──────────────┘ └──────────────┘ └────────┬──────────┘ └────────┬──────────┘
                                                            │                     │
                                             ┌──────────────┘                     │
                                             │  imports providers + schemas       │
                                             ▼                                  │
                                      (same leaf modules)                        │
                                                                                 │
  ┌──────────────┐   ┌───────────────────────────────────────────────────────────┘
  │              │   │
  ▼              ▼   ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐
│   codegen    │   │  templates/  │   │ secrets_store│   │ github_sync  │   │ (generator also reads │
│    .py       │──►│ project_     │   │    .py       │   │    .py       │   │  paths from disk)     │
│ Optional LLM │   │ templates.py │   │ Build .env   │   │ Push folder  │   │                       │
│ logic.py gen │   │ Jinja layouts│   │ text blobs   │   │ to Git remote│   └──────────────────────┘
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────────────┘
       │                  │                 │
       └──────────────────┼─────────────────┘
                          ▼
                   ┌──────────────┐
                   │  schemas.py  │
                   │ Shared types │
                   └──────────────┘

       ┌──────────────┐                    ┌──────────────────────────┐
       │   runner     │ ── imports ──►    │  generator + schemas     │
       │    .py       │                    │  Run/save/load agent     │
       │ Start agent  │                    │  projects                │
       │ subprocess   │                    └──────────────────────────┘
       └──────┬───────┘
              │
              │ also used by
              ▼
       ┌──────────────┐
       │ agent_       │ ── imports ──►  generator, requirements_builder,
       │ editor.py    │                  agent_diagnostics, runner
       │ LLM edits on │
       │ whitelisted  │
       │ files        │
       └──────┬───────┘
              │
              ▼
       ┌──────────────┐
       │ agent_       │
       │ diagnostics  │
       │    .py       │
       │ Static checks│
       │ (stdlib only)│
       └──────────────┘

       main.py ──► agent_editor.py ──► runner.py / generator.py / …
       main.py ──► runner.py ──► generator.py / schemas.py
```

**Thin packages:** `backend/__init__.py` and `backend/templates/__init__.py` only re-export; substantive dependencies are in the chart above.

---

## 2. Flowchart: preview requirements — `POST /api/requirements/preview`

```
   ┌─────────────────────┐
   │  Browser /          │
   │  frontend           │
   │  React UI; calls    │
   │  the API            │
   └──────────┬──────────┘
              │
              │ ① JSON: RequirementsPreviewRequest
              ▼
   ┌──────────────────────────────────────────────────┐
   │              main.py                             │
   │         route: requirements_preview              │
   │  Validates input; delegates to builder + preview │
   └──────────────────────────┬───────────────────────┘
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
   ┌─────────────────────────┐         ┌─────────────────────────┐
   │ ② build_requirements    │         │ ⑤ preview_generated     │
   │    (config)             │         │    _files(config)       │
   │  Compute dependency     │         │  Dry-run: list files    │
   │  lines from form        │         │  that would be emitted  │
   └──────────┬──────────────┘         └──────────┬──────────────┘
              │                                     │
              ▼                                     ▼
   ┌─────────────────────────┐             (uses same config +
   │ requirements_           │             provider + frontend
   │ builder.py              │             rules internally)
   │ Merge user choices with │
   │ provider defaults       │
   └──────────┬──────────────┘
              │
              ▼
   ┌─────────────────────────┐
   │ ③ get_provider(...)     │
   │    providers.py         │
   │  Resolve templates &    │
   │  rules for chosen model │
   └──────────┬──────────────┘
              │
              ▼
   ┌─────────────────────────┐
   │ ④ return requirement    │
   │    lines + file list    │
   │  What pip needs +       │
   │  manifest for UI        │
   └─────────────────────────┘
                              │
                              ▼
                              ┌──────────────────────────┐
                              │ ⑥ JSON response:         │
                              │ RequirementsPreview      │
                              │ Response                 │
                              │ Send preview payload     │
                              │ back to browser          │
                              └──────────────────────────┘
```

---

## 3. Flowchart: generate agent — `POST /api/agents/generate`

```
   ┌─────────────────────┐
   │  Browser /          │
   │  frontend           │
   │  User submits agent │
   │  configuration      │
   └──────────┬──────────┘
              │
              │ ① config + Bearer token
              ▼
   ┌──────────────────────────────────────────────────┐
   │              main.py                             │
   │         route: generate_agent                    │
   │  Auth check; pass secrets + config to generator  │
   └──────────────────────────┬───────────────────────┘
                              │
                              │ ② get_user_secret_values(user_id)
                              ▼
                  ┌───────────────────┐
                  │ auth_store.py     │
                  │ Load saved API    │
                  │ keys for user     │
                  └─────────┬─────────┘
                            │
                            │ ③ settings dict (keys, tokens)
                            ▼
   ┌──────────────────────────────────────────────────┐
   │           generator.py                           │
   │     generate_agent_project(...)                  │
   │  Orchestrate template, deps, secrets, optional  │
   │  LLM, and output paths                           │
   └──────────────────────────┬───────────────────────┘
                              │
          ┌───────────────────┼───────────────────┬──────────────────┐
          ▼                   ▼                   ▼                  ▼
   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐       ┌─────────────┐
   │④ provider   │   │⑤ build +   │   │⑥ render    │       │⑦ optional   │
   │  metadata    │   │  preview    │   │ project_   │       │ LLM path    │
   │ Vendor name, │   │  reqs       │   │ files      │       │ Refine      │
   │ model ids    │   │ Same as     │   │ Jinja fill │       │ logic.py    │
   │              │   │ preview API │   │ disk tree  │       │ if enabled  │
   └─────────────┘   └─────────────┘   └──────┬──────┘       └──────┬──────┘
                                              │                     │
                                              │                     ▼
                                              │              ┌──────────────┐
                                              │              │ codegen.py   │
                                              │              │ try_gen      │
                                              │              │ logic.py     │
                                              │              │ AST-safe     │
                                              │              │ code assist  │
                                              │              └──────┬───────┘
                                              │                     │
                                              └──────────┬──────────┘
                                                         │
                                                         ▼
                                                 ┌──────────────┐
                                                 │⑧ secrets_    │
                                                 │  store:      │
                                                 │  .env        │
                                                 │ Write key    │
                                                 │ file for app │
                                                 └──────┬───────┘
                                                        │
                                                        ▼
                                                 ┌──────────────┐
                                                 │⑨ write tree  │
                                                 │ metadata     │
                                                 │ .json        │
                                                 │ Persist full │
                                                 │ project under│
                                                 │ generated_   │
                                                 │ agents/…     │
                                                 └──────┬───────┘
                                                        │
                                                        ▼
   ┌──────────────────────────────────────────────────┐
   │ ⑩ HTTP 200 + GenerateAgentResponse                │
   │ Ack + paths / ids for new agent                   │
   └──────────────────────────────────────────────────┘
```

---

## 4. Flowchart: run agent — `POST /api/agents/run`

```
   ┌─────────────────────┐
   │  Browser /          │
   │  frontend           │
   │  "Run" from UI      │
   └──────────┬──────────┘
              │
              │ ① RunAgentRequest
              ▼
   ┌──────────────────────────────────────────────────┐
   │              main.py                             │
   │         route: execute_agent                     │
   │  Resolve user; hand off to runner                │
   └──────────────────────────┬───────────────────────┘
                              │
                              │ ② get_user_secret_values
                              ▼
                  ┌───────────────────┐
                  │ auth_store.py     │
                  │ Keys env for      │
                  │ child process     │
                  └─────────┬─────────┘
                            │
                            ▼
   ┌──────────────────────────────────────────────────┐
   │              runner.py                           │
   │           run_agent(...)                       │
   │  Prepare command, cwd, env; capture output     │
   └──────────────────────────┬───────────────────────┘
                              │
                              │ ③ get_generated_agent,
                              │   list_uploaded_files
                              ▼
                  ┌───────────────────┐
                  │ generator.py      │
                  │ Locate on-disk    │
                  │ agent + uploads   │
                  └─────────┬─────────┘
                            │
                            │ ④ paths + metadata
                            ▼
   ┌──────────────────────────────────────────────────┐
   │ ⑤ subprocess: CLI / Gradio / FastAPI+Vite       │
   │    (per agent frontend_type)                     │
   │  Launch the generated app in the right mode      │
   └──────────────────────────┬───────────────────────┘
                              │
                              ▼
   ┌──────────────────────────────────────────────────┐
   │ ⑥ RunAgentResponse (run record, local_url?)     │
   │ Status + logs + optional local preview URL       │
   └──────────────────────────────────────────────────┘
```

---

## 5. Flowchart: edit chat — `POST /api/agents/{agent_id}/edit-chat`

```
   ┌─────────────────────┐
   │  Browser /          │
   │  frontend           │
   │  Chat to change     │
   │  generated code     │
   └──────────┬──────────┘
              │
              │ ① messages + flags
              ▼
   ┌──────────────────────────────────────────────────┐
   │              main.py                             │
   │         route: agent_edit_chat                   │
   │  Route to editor with agent id + conversation    │
   └──────────────────────────┬───────────────────────┘
                              │
                              ▼
   ┌──────────────────────────────────────────────────┐
   │           agent_editor.py                        │
   │        apply_agent_edits(...)                    │
   │  LLM loop over allowed files only                │
   └──────────────────────────┬───────────────────────┘
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
   ┌─────────────────────────┐         ┌─────────────────────────┐
   │ ② get_generated_        │         │ ③ optional:             │
   │    agent                │         │ agent_diagnostics       │
   │    (generator)          │         │ collect_static_…        │
   │ Load current tree       │         │ Sanity-check before/    │
   │ paths + settings        │         │ after edits             │
   └──────────┬──────────────┘         └──────────┬──────────────┘
              │                                    │
              └───────────────────┬────────────────┘
                                  │
                                  ▼
                   ┌──────────────────────────┐
                   │ ④ LLM proposes           │
                   │    patches (paths        │
                   │    on whitelist)         │
                   │ Model returns diffs for  │
                   │ permitted files only     │
                   └──────────┬───────────────┘
                              │
                              ▼
                   ┌──────────────────────────┐
                   │ ⑤ write files under      │
                   │    agent directory       │
                   │ Apply patches atomically │
                   └──────────┬───────────────┘
                              │
                              ▼
                   ┌──────────────────────────┐
                   │ ⑥ stop_local_ui_         │
                   │    server (runner)       │
                   │ Restart requires stop if  │
                   │ dev server was running   │
                   └──────────┬───────────────┘
                              │
                              ▼
   ┌──────────────────────────────────────────────────┐
   │ ⑦ AgentEditChatResponse                           │
   │ Summary + any diagnostics for the UI              │
   └──────────────────────────────────────────────────┘
```

---

## 6. Flowchart: GitHub check-in — `POST /api/agents/{agent_id}/checkin`

```
   ┌─────────────────────┐
   │  Browser /          │
   │  frontend           │
   │  Push project to    │
   │  remote repo        │
   └──────────┬──────────┘
              │
              │ ① agent_id + auth
              ▼
   ┌──────────────────────────────────────────────────┐
   │              main.py                             │
   │         route: checkin_agent                     │
   │  Auth; load tokens for Git operations            │
   └──────────────────────────┬───────────────────────┘
                              │
                              │ ② get_user_secret_values
                              ▼
                  ┌───────────────────┐
                  │ auth_store.py     │
                  │ Git PAT / creds   │
                  └─────────┬─────────┘
                            │
                            ▼
   ┌──────────────────────────────────────────────────┐
   │           generator.py                         │
   │     checkin_generated_agent(...)               │
   │  Resolve agent folder + metadata for sync       │
   └──────────────────────────┬───────────────────────┘
                              │
                              │ ③ get_generated_agent
                              ▼
   ┌──────────────────────────────────────────────────┐
   │           github_sync.py                         │
   │   sync_generated_project_to_github(...)        │
   │  High-level: clone or update, copy tree         │
   └──────────────────────────┬───────────────────────┘
                              │
                              ▼
   ┌──────────────────────────────────────────────────┐
   │ ④ git: ensure repo / copy tree / commit /       │
   │    push → summary string                        │
   │  Make commit with generated files; push upstream │
   └──────────────────────────┬───────────────────────┘
                              │
                              ▼
   ┌──────────────────────────────────────────────────┐
   │ ⑤ CheckInAgentResponse                          │
   │ Human-readable result / link for UI              │
   └──────────────────────────────────────────────────┘
```

---

## Legend (roles)

| Module | Role |
|--------|------|
| **main.py** | FastAPI routes, auth dependency, maps HTTP ↔ services |
| **generator.py** | Creates/updates `generated_agents/user_*`, `metadata.json`, uploads folder |
| **runner.py** | Subprocess runner for generated agents; optional local UI URL |
| **agent_editor.py** | LLM edits to whitelisted agent files |
| **codegen.py** | Optional LLM `logic.py` with AST validation |
| **github_sync.py** | Push generated project to configured Git remote |
| **auth_store.py** | SQLite users, sessions, saved settings |
| **schemas.py** | Pydantic models for API and metadata |
