# Alpha Agent Builder — Python modules

This list covers **authored Python for the builder service** under `backend/`. It does **not** include:

- `generated_agents/` (output of the builder)
- `repo_workdirs/` (cloned or synced remote repos)
- `frontend/` (TypeScript/React)

| File | One-line summary |
|------|------------------|
| `backend/main.py` | The API the browser talks to; hands real work to other files. |
| `backend/schemas.py` | Shared “forms” for data so every part of the app agrees on fields and rules. |
| `backend/auth_store.py` | Saves users, logins, and your saved keys/settings on disk (SQLite). |
| `backend/providers.py` | Built-in list of AI vendors (names, models, which env vars they need). |
| `backend/requirements_builder.py` | Figures out pip packages and which files a new agent will get before you build it. |
| `backend/codegen.py` | Asks the AI to write `logic.py` when possible; checks the code; can give up cleanly. |
| `backend/templates/__init__.py` | Tiny pass-through so other code can import templates from one place. |
| `backend/templates/project_templates.py` | The boilerplate text that becomes your generated project files and LLM hints. |
| `backend/secrets_store.py` | Writes each agent’s `.env` from what you typed (and saved keys if allowed). |
| `backend/generator.py` | Builds and updates the agent folder on disk; wires templates, codegen, env, GitHub. |
| `backend/github_sync.py` | Copies your agent into a Git repo, commits, and pushes for you. |
| `backend/runner.py` | Starts and stops the generated app, remembers if it’s running, keeps logs. |
| `backend/agent_editor.py` | Lets you chat to change allowed files; applies edits; can stop the running UI. |
| `backend/agent_diagnostics.py` | Quick “does this Python even load?” checks before/while editing. |
| `backend/__init__.py` | Tells Python this folder is the `backend` package; not a feature on its own. |

---

## Plain-language guide

Each module below uses the same idea as **`main.py`**: a short **plain explanation**, then **in one line**, then **who uses it**. The website (React) only talks to the server through **`main.py`** unless noted.

### `backend/main.py`

This is the **front door** of the server. When you click things in the app, the browser sends requests here. **`main.py`** receives them and **sends them to the right helper**—it does not try to pack every feature into one file.

**In one line:** The **web API** the UI calls; it connects URLs to the rest of the backend.

**Who uses it:** The **browser / React app** (every HTTP request).

---

### `backend/schemas.py`

Think of this as the **shared checklist and shape of every message** between the UI and the server. “An agent has these fields,” “a run record looks like this,” and simple validation live here so you do not get mismatched JSON in random places.

**In one line:** **Shared data shapes** and rules for requests and responses.

**Who uses it:** **`main.py`** and almost every module that reads or writes agent-related data (`generator`, `runner`, `codegen`, `templates`, `requirements_builder`, `secrets_store`, and more).

---

### `backend/auth_store.py`

This is the **notebook** where the server remembers **who signed up**, **who is logged in** (sessions), and **your saved settings** (API keys, GitHub token, default repo). It is a small **SQLite** file on the server, not something the React code touches directly—only through **`main.py`**.

**In one line:** **Account and settings storage** for logged-in users.

**Who uses it:** **`main.py`** for auth and settings routes.

---

### `backend/providers.py`

This is a **menu of AI providers** baked into the app: names you see in the UI, default models, and **which environment variable names** each provider expects. It does not call the APIs; it just **describes** what is supported.

**In one line:** **Static catalog** of LLM providers and their defaults.

**Who uses it:** **`main.py`** (show the list), **`requirements_builder`**, **`generator`**, **`codegen`**.

---

### `backend/requirements_builder.py`

When you pick options in the form, this module answers two simple questions: **what should `requirements.txt` list?** and **which files will exist** in the new project (CLI vs a small web UI vs React, etc.). The UI can show a **preview** before anything is written to disk.

**In one line:** **Turns your choices into pip lines + a file manifest.**

**Who uses it:** **`main.py`** (preview), **`generator`** (real build), **`agent_editor`** (know which React paths are safe to edit).

---

### `backend/codegen.py`

After the scaffold exists, this module can ask **your chosen LLM** to draft the main **`logic.py`** file. It **checks** that the answer looks like real Python; if not, or if keys are missing, it **backs off** without breaking the whole flow. It reads **hint text** from the template module so the model knows the intended shape.

**In one line:** **Optional AI-written `logic.py`** with a safety check.

**Who uses it:** **`generator`**, when generating or regenerating an agent.

---

### `backend/templates/__init__.py`

Other code wants to say **“import from `templates`”** instead of reaching deep into `project_templates`. This file is a **one-line forwarding address**—no behavior of its own.

**In one line:** **Re-export** so imports stay tidy.

**Who uses it:** **`generator`** (and anything that imports the `templates` package the same way).

---

### `backend/templates/project_templates.py`

This is the **big box of starter text**: the Python/React files that become a new agent, plus README chunks and **hints** fed to the LLM when writing `logic.py`. **`generator`** calls **`render_project_files`** here to **fill in** blanks from your form.

**In one line:** **Boilerplate strings** that become real files on disk.

**Who uses it:** **`generator`** (render), **`codegen`** (read hint constants), **`templates/__init__.py`** (expose the render function).

---

### `backend/secrets_store.py`

Each generated agent needs its own **`.env`** file with API keys and similar secrets. This module **writes that file** from what you entered for that agent, and can **reuse keys** you saved in Settings when that is allowed.

**In one line:** **Writes per-agent `.env`** from secrets (and saved keys when OK).

**Who uses it:** **`generator`** when building or updating an agent folder.

---

### `backend/generator.py`

This is the **factory floor**. It **creates or updates** the folder under `generated_agents/user_{id}/`, **pulls in** template output, **merges in** optional LLM `logic.py`, writes **`metadata.json`**, handles **uploads** listing, and can ask **`github_sync`** to push. **`main.py`** uses it for “make / list / delete / sync” style operations.

**In one line:** **Builds and manages** the on-disk agent project.

**Who uses it:** **`main.py`**, **`runner`** (find paths and metadata), **`agent_editor`** (load project for edits).

---

### `backend/github_sync.py`

When you want the agent **in a GitHub repo**, this module does the **git** work: refresh or clone a cache of the repo, **copy** your generated tree in, **commit**, **push**, and surface **clear errors** if the URL or token is wrong.

**In one line:** **Commits and pushes** the generated agent into a remote repo.

**Who uses it:** **`generator`**, when the user triggers GitHub check-in (via **`main.py`**).

---

### `backend/runner.py`

This module **actually runs** the program you generated—as a **separate process** on the machine. It picks **ports** if needed, remembers **whether it is running**, saves **logs**, and can **stop** background servers (for example before or after edits).

**In one line:** **Start/stop/status/logs** for the generated agent process.

**Who uses it:** **`main.py`** (run and logs UI), **`agent_editor`** (stop UI for a clean restart).

---

### `backend/agent_editor.py`

This powers **“chat to change the code.”** It only opens **allowed** files, can run **quick checks** (`agent_diagnostics`), asks the **LLM** for updates, **writes files back**, and may **stop** the running UI so you can start again without stale state.

**In one line:** **Chat-driven edits** to whitelisted files in the generated project.

**Who uses it:** **`main.py`** only (edit-chat API route).

---

### `backend/agent_diagnostics.py`

Before trusting new edits, the app can run **cheap checks**: “does this Python **compile**?” and sometimes “does **`logic`** **import**?” It gives **human-readable** output for you and **short notes** for the model.

**In one line:** **Lightweight “does this code basically work?”** checks.

**Who uses it:** **`agent_editor`** only.

---

### `backend/__init__.py`

Python needs a signal that **`backend`** is a **package**. This file is that signal—a **label**, not a feature users trigger.

**In one line:** **Package marker** for the `backend` folder.

**Who uses it:** **Python** when you `import backend` (not a normal “call” from your app logic).

---

### Big picture

You use the **website** → it calls **`main.py`** → **`main.py`** reaches for **`auth_store`** (accounts), **`generator`** (build sync), **`runner`** (run/stop), **`agent_editor`** (chat edits), or **`requirements_builder`** / **`providers`** (previews and catalogs). Inside **`generator`**, you get **`templates`**, **`codegen`**, **`secrets_store`**, **`github_sync`**, plus **`schemas`** almost everywhere as the shared vocabulary.
