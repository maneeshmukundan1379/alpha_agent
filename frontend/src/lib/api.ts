import type {
  AgentConfigRequest,
  AgentEditChatMessage,
  AgentEditChatRequestBody,
  AgentEditChatResponse,
  AgentLogsResponse,
  AgentMetadata,
  AgentTreeNode,
  AuthResponse,
  CheckInAgentResponse,
  GenerateAgentResponse,
  MeResponse,
  ProviderInfo,
  RequirementsPreviewResponse,
  RunAgentResponse,
  SettingsPayload,
  UpdateSettingsRequest,
  UploadedFileInfo,
  UserProfile,
} from "../types";

const API_BASE = "http://127.0.0.1:8000";

/** Short-lived sign-in (this browser tab / session). */
const TOKEN_SESSION_KEY = "alpha-agent-builder-token-session";
/** Only set when the user checks "Keep me signed in". */
const TOKEN_PERSISTENT_KEY = "alpha-agent-builder-token-persistent";
/** Pre–split-behavior key (always localStorage). Removed on load so old tokens cannot skip login. */
const LEGACY_TOKEN_KEY = "alpha-agent-builder-token";

function evictLegacyAuthToken(): void {
  try {
    localStorage.removeItem(LEGACY_TOKEN_KEY);
    sessionStorage.removeItem(LEGACY_TOKEN_KEY);
  } catch {
    /* storage unavailable */
  }
}

evictLegacyAuthToken();

function readStoredToken(): string {
  return (
    sessionStorage.getItem(TOKEN_SESSION_KEY) ?? localStorage.getItem(TOKEN_PERSISTENT_KEY) ?? ""
  );
}

let authToken = readStoredToken();

const FIELD_LABELS: Record<string, string> = {
  name: "Name",
  username: "Username",
  email: "Email",
  password: "Password",
  identifier: "Login",
  agent_name: "Agent name",
  description: "Agent purpose",
  instructions: "Agent instructions",
  provider_id: "Model provider",
  model: "Model",
  frontend_type: "Generated frontend",
  github_repo_url: "Optional GitHub repository",
  current_password: "Current password",
  new_password: "New password",
  openai_api_key: "OpenAI API key",
  gemini_api_key: "Gemini API key",
  github_token: "GitHub token",
};

function formatFieldName(location: unknown): string {
  if (!Array.isArray(location)) {
    return "";
  }

  const filtered = location
    .filter((part): part is string => typeof part === "string")
    .filter((part) => part !== "body" && part !== "config");

  const fieldKey = filtered[filtered.length - 1] ?? "";
  return FIELD_LABELS[fieldKey] ?? fieldKey.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatValidationMessage(record: Record<string, unknown>): string {
  const fieldName = formatFieldName(record.loc);
  const type = typeof record.type === "string" ? record.type : "";
  const input = typeof record.input === "string" ? record.input.trim() : "";
  const ctx = record.ctx && typeof record.ctx === "object" ? (record.ctx as Record<string, unknown>) : {};

  if (type === "string_too_short") {
    if (!input) {
      return fieldName ? `${fieldName} cannot be blank.` : "This field cannot be blank.";
    }
    const minLength = typeof ctx.min_length === "number" ? ctx.min_length : null;
    return fieldName && minLength
      ? `${fieldName} must be at least ${minLength} characters.`
      : `${fieldName || "This field"} is too short.`;
  }

  if (type === "missing") {
    return fieldName ? `${fieldName} is required.` : "A required field is missing.";
  }

  if (type === "string_too_long") {
    const maxLength = typeof ctx.max_length === "number" ? ctx.max_length : null;
    return fieldName && maxLength
      ? `${fieldName} must be at most ${maxLength} characters.`
      : `${fieldName || "This field"} is too long.`;
  }

  const message = typeof record.msg === "string" && record.msg.trim() ? record.msg : "Request failed.";
  return fieldName ? `${fieldName}: ${message}` : message;
}


function formatErrorDetail(detail: unknown): string {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => formatErrorDetail(item))
      .filter((message) => message && message !== "Request failed.");
    return messages.length > 0 ? messages.join(" | ") : "Request failed.";
  }

  if (detail && typeof detail === "object") {
    const record = detail as Record<string, unknown>;

    if (typeof record.msg === "string" && record.msg.trim()) {
      return formatValidationMessage(record);
    }

    if (typeof record.detail === "string" && record.detail.trim()) {
      return record.detail;
    }

    try {
      return JSON.stringify(detail);
    } catch {
      return "Request failed.";
    }
  }

  return "Request failed.";
}


/**
 * Store the JWT. Default: session-only key (new tab / new browser session → login again).
 * rememberMe=true writes the persistent key only (not the legacy single-key localStorage behavior).
 */
export function setAuthToken(token: string, rememberMe = false) {
  authToken = token;
  localStorage.removeItem(TOKEN_PERSISTENT_KEY);
  sessionStorage.removeItem(TOKEN_SESSION_KEY);
  localStorage.removeItem(LEGACY_TOKEN_KEY);
  sessionStorage.removeItem(LEGACY_TOKEN_KEY);
  if (!token) {
    return;
  }
  if (rememberMe) {
    localStorage.setItem(TOKEN_PERSISTENT_KEY, token);
  } else {
    sessionStorage.setItem(TOKEN_SESSION_KEY, token);
  }
}


export function getAuthToken(): string {
  return authToken;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers ?? {});
  if (!headers.has("Content-Type") && !(init?.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (authToken) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }

  const method = (init?.method ?? "GET").toUpperCase();
  const response = await fetch(`${API_BASE}${path}`, {
    cache: method === "GET" ? "no-store" : undefined,
    headers,
    ...init,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Request failed." }));
    throw new Error(formatErrorDetail(body.detail));
  }

  return response.json() as Promise<T>;
}

export async function signup(payload: {
  name: string;
  username: string;
  email: string;
  password: string;
}): Promise<AuthResponse> {
  return request<AuthResponse>("/api/auth/signup", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function login(payload: { identifier: string; password: string }): Promise<AuthResponse> {
  return request<AuthResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchMe(): Promise<MeResponse> {
  return request<MeResponse>("/api/auth/me");
}

export async function logout(): Promise<void> {
  await request<{ message: string }>("/api/auth/logout", { method: "POST" });
  setAuthToken("");
}

export async function updateProfile(payload: {
  name: string;
  username: string;
  email: string;
}): Promise<UserProfile> {
  const data = await request<{ user: UserProfile }>("/api/settings/profile", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return data.user;
}

export async function updatePassword(payload: {
  current_password: string;
  new_password: string;
}): Promise<void> {
  await request<{ message: string }>("/api/settings/password", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function fetchSettings(): Promise<SettingsPayload> {
  const data = await request<{ settings: SettingsPayload }>("/api/settings");
  return data.settings;
}

export async function saveSettings(payload: UpdateSettingsRequest): Promise<SettingsPayload> {
  const data = await request<{ settings: SettingsPayload }>("/api/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return data.settings;
}

export async function fetchProviders(): Promise<ProviderInfo[]> {
  const data = await request<{ providers: ProviderInfo[] }>("/api/providers");
  return data.providers;
}

export async function previewRequirements(
  config: AgentConfigRequest,
): Promise<RequirementsPreviewResponse> {
  return request<RequirementsPreviewResponse>("/api/requirements/preview", {
    method: "POST",
    body: JSON.stringify({ config }),
  });
}

export async function generateAgent(
  config: AgentConfigRequest,
): Promise<GenerateAgentResponse> {
  return request<GenerateAgentResponse>("/api/agents/generate", {
    method: "POST",
    body: JSON.stringify({ config }),
  });
}

export async function fetchAgents(): Promise<AgentMetadata[]> {
  const data = await request<{ agents: AgentMetadata[] }>("/api/agents");
  return data.agents;
}

export async function fetchAgent(agent_id: string): Promise<AgentMetadata> {
  const data = await request<{ agent: AgentMetadata }>(`/api/agents/${agent_id}`);
  return data.agent;
}

export async function checkInAgent(agent_id: string): Promise<CheckInAgentResponse> {
  return request<CheckInAgentResponse>(`/api/agents/${agent_id}/checkin`, {
    method: "POST",
  });
}

export async function deleteAgent(agent_id: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/api/agents/${agent_id}`, {
    method: "DELETE",
  });
}

export async function fetchAgentTree(agent_id: string): Promise<AgentTreeNode> {
  const data = await request<{ agent_id: string; tree: AgentTreeNode }>(`/api/agents/${agent_id}/tree`);
  return data.tree;
}

export async function agentEditChat(
  agent_id: string,
  messages: AgentEditChatMessage[],
  options?: Pick<AgentEditChatRequestBody, "include_static_diagnostics" | "runtime_error">,
): Promise<AgentEditChatResponse> {
  const body: AgentEditChatRequestBody = {
    messages,
    include_static_diagnostics: options?.include_static_diagnostics ?? true,
    runtime_error: options?.runtime_error?.trim() || "",
  };
  return request<AgentEditChatResponse>(`/api/agents/${agent_id}/edit-chat`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function runAgent(agent_id: string, prompt: string): Promise<RunAgentResponse> {
  return request<RunAgentResponse>("/api/agents/run", {
    method: "POST",
    body: JSON.stringify({ agent_id, prompt }),
  });
}

export async function fetchAgentLogs(agent_id: string): Promise<AgentLogsResponse> {
  return request<AgentLogsResponse>(`/api/agents/${agent_id}/logs`);
}

export async function fetchUploads(agent_id: string): Promise<UploadedFileInfo[]> {
  const data = await request<{ agent_id: string; files: UploadedFileInfo[] }>(
    `/api/agents/${agent_id}/uploads`,
  );
  return data.files;
}

export async function uploadFiles(
  agent_id: string,
  files: File[],
): Promise<UploadedFileInfo[]> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));

  const response = await fetch(`${API_BASE}/api/agents/${agent_id}/uploads`, {
    method: "POST",
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
    body: formData,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Upload failed." }));
    throw new Error(body.detail ?? "Upload failed.");
  }

  const data = (await response.json()) as { agent_id: string; files: UploadedFileInfo[] };
  return data.files;
}
