export type TemplateId = "default_agent";

export type FrontendType = "cli" | "gradio" | "react";
export type ProviderId = "openai" | "gemini";
export type RunStatus = "idle" | "running" | "completed" | "failed";
export type ToolId =
  | "document_context"
  | "structured_output"
  | "citation_notes"
  | "checklist_planner";

export interface SecretInput {
  key: string;
  value: string;
}

export interface AgentConfigRequest {
  agent_name: string;
  description: string;
  instructions: string;
  /** Omitted on create; server always uses default_agent */
  template_id?: TemplateId;
  provider_id: ProviderId;
  model: string;
  frontend_type: FrontendType;
  temperature: number;
  secrets: SecretInput[];
  /** When true, OpenAI/Gemini/GitHub keys from Settings are written into the agent `.env` at generate time. */
  include_settings_api_keys: boolean;
  extra_requirements: string[];
  enabled_tools: ToolId[];
  allow_file_uploads: boolean;
  supported_upload_types: string[];
  github_repo_url: string;
}

export interface ProviderInfo {
  id: ProviderId;
  label: string;
  description: string;
  default_model: string;
  models: string[];
  secret_names: string[];
}

export interface RequirementsPreviewResponse {
  requirements: string[];
  generated_files: string[];
}

export interface AgentMetadata {
  agent_id: string;
  agent_name: string;
  description: string;
  instructions: string;
  template_id: TemplateId;
  provider_id: ProviderId;
  model: string;
  frontend_type: FrontendType;
  temperature: number;
  enabled_tools: ToolId[];
  allow_file_uploads: boolean;
  supported_upload_types: string[];
  github_repo_url: string;
  github_repo_path: string;
  github_commit_sha: string;
  agent_dir: string;
  created_at: string;
  has_secrets: boolean;
  requirements: string[];
  generated_files: string[];
  /** logic.py produced by LLM codegen vs template fallback */
  generation_source?: "llm" | "template";
  include_settings_api_keys?: boolean;
  /** Names only; values are never returned from the API */
  extra_secret_key_names?: string[];
}

export interface GenerateAgentResponse {
  message: string;
  agent: AgentMetadata;
}

export interface CheckInAgentResponse {
  message: string;
  agent: AgentMetadata;
}

export interface AgentTreeNode {
  name: string;
  path: string;
  node_type: "file" | "directory";
  children: AgentTreeNode[];
}

export interface RunRecord {
  run_id: string;
  agent_id: string;
  status: RunStatus;
  command: string[];
  prompt: string;
  started_at: string;
  finished_at: string | null;
  log_path: string;
}

export interface RunAgentResponse {
  message: string;
  run: RunRecord;
  local_url?: string | null;
}

export interface AgentLogsResponse {
  run: RunRecord | null;
  logs: string;
}

export interface UploadedFileInfo {
  name: string;
  stored_path: string;
  size_bytes: number;
  uploaded_at: string;
}

export interface UserProfile {
  id: number;
  name: string;
  username: string;
  email: string;
  created_at: string;
}

export interface SettingsPayload {
  has_openai_api_key: boolean;
  has_gemini_api_key: boolean;
  has_github_token: boolean;
  default_repo_url: string;
  updated_at: string;
}

export interface AuthResponse {
  token: string;
  user: UserProfile;
  settings: SettingsPayload;
}

export interface MeResponse {
  user: UserProfile;
  settings: SettingsPayload;
}

export interface UpdateSettingsRequest {
  openai_api_key?: string;
  gemini_api_key?: string;
  github_token?: string;
  default_repo_url?: string;
}

export interface AgentEditChatMessage {
  role: "user" | "assistant";
  content: string;
}

/** Body for POST /api/agents/:id/edit-chat */
export interface AgentEditChatRequestBody {
  messages: AgentEditChatMessage[];
  /** When true, backend runs py_compile + import logic and attaches results */
  include_static_diagnostics?: boolean;
  /** Paste traceback / stderr from a failed run */
  runtime_error?: string;
}

export interface AgentEditChatResponse {
  assistant_message: string;
  updated_files: string[];
  /** Backend step-by-step trace for this edit-chat turn */
  activity_log: string[];
}
