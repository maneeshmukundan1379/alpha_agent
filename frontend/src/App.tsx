import { useEffect, useState } from "react";
import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { AuthPanel } from "./components/AuthPanel";
import { BuilderForm } from "./components/BuilderForm";
import { AgentRepositoryPanel } from "./components/AgentRepositoryPanel";
import { AgentRunConsole } from "./components/AgentRunConsole";
import { RequirementsPreview } from "./components/RequirementsPreview";
import { SettingsModal } from "./components/SettingsModal";
import { AgentsWorkspaceProvider } from "./context/AgentsWorkspaceContext";
import {
  fetchAgents,
  fetchMe,
  fetchProviders,
  generateAgent,
  getAuthToken,
  login,
  logout,
  previewRequirements,
  saveSettings,
  setAuthToken,
  signup,
  updatePassword,
  updateProfile,
} from "./lib/api";
import type {
  AgentConfigRequest,
  AgentMetadata,
  ProviderInfo,
  RequirementsPreviewResponse,
  SettingsPayload,
  UserProfile,
} from "./types";

const defaultConfig: AgentConfigRequest = {
  agent_name: "Alpha Insight Agent",
  description:
    "Analyze a business or product question, summarize the main insights, and recommend practical next steps.",
  instructions:
    "Respond in a polished professional tone. Use headings when useful, explain assumptions clearly, and end with recommended next actions.",
  provider_id: "openai",
  model: "gpt-4o-mini",
  frontend_type: "gradio",
  temperature: 0.2,
  secrets: [],
  include_settings_api_keys: true,
  extra_requirements: [],
  enabled_tools: ["document_context", "structured_output"],
  allow_file_uploads: true,
  supported_upload_types: ["txt", "md", "csv", "json", "py", "pdf", "docx"],
  github_repo_url: "",
};

function AppHeaderBar({
  user,
  onOpenSettings,
}: {
  user: UserProfile;
  onOpenSettings: () => void;
}) {
  const location = useLocation();
  const onRunPage = location.pathname === "/run";

  return (
    <div className="flex flex-col items-stretch gap-4 md:items-end">
      <div className="flex flex-wrap items-center justify-end gap-3">
        {onRunPage ? (
          <NavLink
            className="rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm font-semibold text-white transition hover:bg-white/15"
            to="/"
          >
            ← Builder
          </NavLink>
        ) : null}
        <div className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200">
          @{user.username}
        </div>
        <button
          className="flex h-12 w-12 items-center justify-center rounded-full border border-white/10 bg-white/5 text-xl text-slate-100 transition hover:bg-white/10"
          onClick={onOpenSettings}
          type="button"
        >
          ⚙
        </button>
      </div>
    </div>
  );
}

function App() {
  const [config, setConfig] = useState<AgentConfigRequest>(defaultConfig);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [preview, setPreview] = useState<RequirementsPreviewResponse | null>(null);
  const [agents, setAgents] = useState<AgentMetadata[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [banner, setBanner] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [settings, setSettings] = useState<SettingsPayload | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    const initialize = async () => {
      try {
        if (!getAuthToken()) {
          return;
        }
        const me = await fetchMe();
        setUser(me.user);
        setSettings(me.settings);

        const [providerList, existingAgents] = await Promise.all([fetchProviders(), fetchAgents()]);
        setProviders(providerList);

        if (providerList.length > 0) {
          const provider = providerList[0];
          setConfig((current) => ({
            ...current,
            provider_id: provider.id,
            model: provider.default_model,
            github_repo_url: me.settings.default_repo_url || current.github_repo_url,
          }));
        }

        setAgents(existingAgents);
        if (existingAgents.length > 0) {
          setSelectedAgentId(existingAgents[0].agent_id);
        }
      } catch (error) {
        setAuthToken("");
        setBanner({
          kind: "error",
          text: error instanceof Error ? error.message : "Failed to load the application.",
        });
      }
    };

    void initialize();
  }, []);

  useEffect(() => {
    if (!user) {
      return;
    }
    const syncPreview = async () => {
      try {
        const result = await previewRequirements(config);
        setPreview(result);
      } catch (error) {
        setPreview(null);
        setBanner({
          kind: "error",
          text: error instanceof Error ? error.message : "Failed to preview requirements.",
        });
      }
    };

    void syncPreview();
  }, [config, user]);

  const handleAuthenticated = async (
    token: string,
    nextUser: UserProfile,
    nextSettings: SettingsPayload,
    rememberMe: boolean,
  ) => {
    setAuthToken(token, rememberMe);
    setUser(nextUser);
    setSettings(nextSettings);
    setConfig((current) => ({
      ...current,
      github_repo_url: nextSettings.default_repo_url || current.github_repo_url,
    }));
    const [providerList, existingAgents] = await Promise.all([fetchProviders(), fetchAgents()]);
    setProviders(providerList);
    setAgents(existingAgents);
    if (existingAgents.length > 0) {
      setSelectedAgentId(existingAgents[0].agent_id);
    }
  };

  const handleLogin = async (payload: {
    identifier: string;
    password: string;
    rememberMe: boolean;
  }) => {
    try {
      const auth = await login({
        identifier: payload.identifier,
        password: payload.password,
      });
      await handleAuthenticated(auth.token, auth.user, auth.settings, payload.rememberMe);
      setBanner(null);
    } catch (error) {
      setBanner({
        kind: "error",
        text: error instanceof Error ? error.message : "Login failed.",
      });
    }
  };

  const handleSignup = async (payload: {
    name: string;
    username: string;
    email: string;
    password: string;
    rememberMe: boolean;
  }) => {
    try {
      const { rememberMe, ...signupBody } = payload;
      const auth = await signup(signupBody);
      await handleAuthenticated(auth.token, auth.user, auth.settings, rememberMe);
      setBanner(null);
    } catch (error) {
      setBanner({
        kind: "error",
        text: error instanceof Error ? error.message : "Signup failed.",
      });
    }
  };

  const handleGenerate = async () => {
    setIsGenerating(true);
    setBanner(null);
    try {
      const result = await generateAgent(config);
      const nextAgents = await fetchAgents();
      setAgents(nextAgents);
      setSelectedAgentId(result.agent.agent_id);
      setBanner({ kind: "success", text: result.message });
    } catch (error) {
      setBanner({
        kind: "error",
        text: error instanceof Error ? error.message : "Failed to generate the agent.",
      });
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSaveProfile = async (payload: { name: string; username: string; email: string }) => {
    const nextUser = await updateProfile(payload);
    setUser(nextUser);
    setBanner({ kind: "success", text: "Profile updated." });
  };

  const handleSavePassword = async (payload: {
    current_password: string;
    new_password: string;
  }) => {
    await updatePassword(payload);
    setBanner({ kind: "success", text: "Password updated." });
  };

  const handleSaveSettings = async (payload: {
    openai_api_key?: string;
    gemini_api_key?: string;
    github_token?: string;
    default_repo_url?: string;
  }) => {
    const nextSettings = await saveSettings(payload);
    setSettings(nextSettings);
    setConfig((current) => ({
      ...current,
      github_repo_url: current.github_repo_url || nextSettings.default_repo_url,
    }));
    setBanner({ kind: "success", text: "Settings saved." });
  };

  const handleLogout = async () => {
    await logout();
    setUser(null);
    setSettings(null);
    setAgents([]);
    setProviders([]);
    setSelectedAgentId("");
    setSettingsOpen(false);
  };

  if (!user) {
    return (
      <div className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(56,189,248,0.12),transparent_35%),radial-gradient(circle_at_right,rgba(168,85,247,0.16),transparent_25%),linear-gradient(180deg,#020617,#0f172a)] text-white">
        {banner ? (
          <div className="mx-auto max-w-5xl px-6 pt-6 lg:px-8">
            <div
              className={`rounded-2xl border px-4 py-3 text-sm ${
                banner.kind === "success"
                  ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-100"
                  : "border-rose-400/20 bg-rose-400/10 text-rose-100"
              }`}
            >
              {banner.text}
            </div>
          </div>
        ) : null}
        <AuthPanel onLogin={handleLogin} onSignup={handleSignup} />
      </div>
    );
  }

  return (
    <AgentsWorkspaceProvider
      agents={agents}
      selectedAgentId={selectedAgentId}
      setAgents={setAgents}
      setSelectedAgentId={setSelectedAgentId}
    >
      <BrowserRouter>
        <div className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(56,189,248,0.12),transparent_35%),radial-gradient(circle_at_right,rgba(168,85,247,0.16),transparent_25%),linear-gradient(180deg,#020617,#0f172a)] text-white">
          <div className="mx-auto max-w-7xl px-6 py-10 lg:px-8">
            <div className="mb-10 rounded-[2.5rem] border border-white/10 bg-white/5 p-8 shadow-2xl shadow-slate-950/50 backdrop-blur">
              <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
                <div className="flex-1">
                  <div className="mb-3 inline-flex rounded-full border border-cyan-400/20 bg-cyan-400/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.25em] text-cyan-100">
                    Alpha Agent Builder
                  </div>
                  <h1 className="max-w-4xl text-4xl font-semibold tracking-tight text-white md:text-5xl">
                    Create and run your own agents
                  </h1>
                  <p className="mt-5 max-w-4xl text-2xl font-semibold leading-snug tracking-tight md:text-3xl">
                    <span
                      className="bg-gradient-to-r from-cyan-200 via-white to-violet-200 bg-clip-text text-transparent"
                      style={{ filter: "drop-shadow(0 0 28px rgba(34,211,238,0.35))" }}
                    >
                      Build any agent in under 10 mins
                    </span>
                  </p>
                  <ol className="mt-6 max-w-3xl list-decimal space-y-2 pl-5 text-base leading-7 text-slate-300">
                    <li>Define what your agent should do.</li>
                    <li>Select the LLM provider and model.</li>
                    <li>Choose the generated frontend.</li>
                    <li>Preview requirements and generated files.</li>
                    <li>
                      In <span className="text-cyan-200">Repository</span>: Run loads Gradio or React in-page; chat and
                      uploads are in that UI. CLI runs open a separate console. Then check in or refresh the tree.
                    </li>
                  </ol>
                </div>
                <AppHeaderBar onOpenSettings={() => setSettingsOpen(true)} user={user} />
              </div>
            </div>

            {banner ? (
              <div
                className={`mb-6 rounded-2xl border px-4 py-3 text-sm ${
                  banner.kind === "success"
                    ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-100"
                    : "border-rose-400/20 bg-rose-400/10 text-rose-100"
                }`}
              >
                {banner.text}
              </div>
            ) : null}

            <Routes>
              <Route
                element={
                  <>
                    <div className="grid gap-6 xl:grid-cols-[1.4fr_0.9fr]">
                      <div className="space-y-6">
                        <BuilderForm
                          config={config}
                          isGenerating={isGenerating}
                          onChange={setConfig}
                          onGenerate={handleGenerate}
                          providers={providers}
                        />
                      </div>
                      <RequirementsPreview preview={preview} />
                    </div>
                    <div className="mt-8">
                      <AgentRepositoryPanel onBanner={setBanner} />
                    </div>
                  </>
                }
                path="/"
              />
              <Route
                element={
                  <div>
                    <div className="mb-8 rounded-2xl border border-white/10 bg-white/5 px-6 py-5">
                      <h2 className="text-2xl font-semibold text-white">Run agent</h2>
                      <p className="mt-1 text-sm text-slate-400">
                        Execute the agent (opens a new tab for Gradio/React), attach uploads, and watch logs.
                      </p>
                    </div>
                    <AgentRunConsole onBanner={setBanner} />
                  </div>
                }
                path="/run"
              />
              <Route element={<Navigate replace to="/" />} path="*" />
            </Routes>
          </div>
          <SettingsModal
            onClose={() => setSettingsOpen(false)}
            onLogout={handleLogout}
            onSavePassword={handleSavePassword}
            onSaveProfile={handleSaveProfile}
            onSaveSettings={handleSaveSettings}
            open={settingsOpen}
            settings={settings}
            user={user}
          />
        </div>
      </BrowserRouter>
    </AgentsWorkspaceProvider>
  );
}

export default App;
