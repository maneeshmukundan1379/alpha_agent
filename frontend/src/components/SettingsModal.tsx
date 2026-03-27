import { useEffect, useState } from "react";

import type { SettingsPayload, UserProfile } from "../types";

interface SettingsModalProps {
  open: boolean;
  user: UserProfile;
  settings: SettingsPayload | null;
  onClose: () => void;
  onSaveProfile: (payload: { name: string; username: string; email: string }) => Promise<void>;
  onSavePassword: (payload: { current_password: string; new_password: string }) => Promise<void>;
  onSaveSettings: (payload: {
    openai_api_key?: string;
    gemini_api_key?: string;
    github_token?: string;
    default_repo_url?: string;
  }) => Promise<void>;
  onLogout: () => Promise<void>;
}

export function SettingsModal({
  open,
  user,
  settings,
  onClose,
  onSaveProfile,
  onSavePassword,
  onSaveSettings,
  onLogout,
}: SettingsModalProps) {
  const [profileForm, setProfileForm] = useState({
    name: user.name,
    username: user.username,
    email: user.email,
  });
  const [passwordForm, setPasswordForm] = useState({
    current_password: "",
    new_password: "",
  });
  const [secretsForm, setSecretsForm] = useState({
    openai_api_key: "",
    gemini_api_key: "",
    github_token: "",
    default_repo_url: settings?.default_repo_url ?? "",
  });

  useEffect(() => {
    setProfileForm({
      name: user.name,
      username: user.username,
      email: user.email,
    });
  }, [user]);

  useEffect(() => {
    setSecretsForm({
      openai_api_key: "",
      gemini_api_key: "",
      github_token: "",
      default_repo_url: settings?.default_repo_url ?? "",
    });
  }, [settings]);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-6 backdrop-blur-sm">
      <div className="max-h-[90vh] w-full max-w-4xl overflow-auto rounded-[2rem] border border-white/10 bg-slate-950/95 p-6 shadow-2xl shadow-slate-950/70">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <div className="mb-2 inline-flex rounded-full border border-violet-400/20 bg-violet-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-violet-100">
              Settings
            </div>
            <h2 className="text-2xl font-semibold text-white">Account and integrations</h2>
          </div>
          <button
            className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200 transition hover:bg-white/10"
            onClick={onClose}
            type="button"
          >
            Close
          </button>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-6">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
              <h3 className="text-lg font-semibold text-white">Profile</h3>
              <div className="mt-4 space-y-3">
                <input
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white"
                  onChange={(event) =>
                    setProfileForm((current) => ({ ...current, name: event.target.value }))
                  }
                  value={profileForm.name}
                />
                <input
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white"
                  onChange={(event) =>
                    setProfileForm((current) => ({ ...current, username: event.target.value }))
                  }
                  value={profileForm.username}
                />
                <input
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white"
                  onChange={(event) =>
                    setProfileForm((current) => ({ ...current, email: event.target.value }))
                  }
                  value={profileForm.email}
                />
                <button
                  className="rounded-full bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950"
                  onClick={() => void onSaveProfile(profileForm)}
                  type="button"
                >
                  Save profile
                </button>
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
              <h3 className="text-lg font-semibold text-white">Password</h3>
              <div className="mt-4 space-y-3">
                <input
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white"
                  onChange={(event) =>
                    setPasswordForm((current) => ({
                      ...current,
                      current_password: event.target.value,
                    }))
                  }
                  placeholder="Current password"
                  type="password"
                  value={passwordForm.current_password}
                />
                <input
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white"
                  onChange={(event) =>
                    setPasswordForm((current) => ({
                      ...current,
                      new_password: event.target.value,
                    }))
                  }
                  placeholder="New password"
                  type="password"
                  value={passwordForm.new_password}
                />
                <button
                  className="rounded-full bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950"
                  onClick={() => void onSavePassword(passwordForm)}
                  type="button"
                >
                  Change password
                </button>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
              <h3 className="text-lg font-semibold text-white">Integrations and API keys</h3>
              <div className="mt-4 space-y-3">
                <input
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white"
                  onChange={(event) =>
                    setSecretsForm((current) => ({
                      ...current,
                      openai_api_key: event.target.value,
                    }))
                  }
                  placeholder={`OpenAI API key${settings?.has_openai_api_key ? " (saved)" : ""}`}
                  type="password"
                  value={secretsForm.openai_api_key}
                />
                <input
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white"
                  onChange={(event) =>
                    setSecretsForm((current) => ({
                      ...current,
                      gemini_api_key: event.target.value,
                    }))
                  }
                  placeholder={`Gemini API key${settings?.has_gemini_api_key ? " (saved)" : ""}`}
                  type="password"
                  value={secretsForm.gemini_api_key}
                />
                <input
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white"
                  onChange={(event) =>
                    setSecretsForm((current) => ({
                      ...current,
                      github_token: event.target.value,
                    }))
                  }
                  placeholder={`GitHub token${settings?.has_github_token ? " (saved)" : ""}`}
                  type="password"
                  value={secretsForm.github_token}
                />
                <input
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white"
                  onChange={(event) =>
                    setSecretsForm((current) => ({
                      ...current,
                      default_repo_url: event.target.value,
                    }))
                  }
                  placeholder="Default GitHub repo URL"
                  value={secretsForm.default_repo_url}
                />
                <button
                  className="rounded-full bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950"
                  onClick={() => void onSaveSettings(secretsForm)}
                  type="button"
                >
                  Save integrations
                </button>
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
              <h3 className="text-lg font-semibold text-white">Session</h3>
              <p className="mt-2 text-sm text-slate-300">
                Logged in as <span className="font-medium text-white">@{user.username}</span>
              </p>
              <button
                className="mt-4 rounded-full border border-rose-400/30 bg-rose-400/10 px-4 py-2 text-sm font-medium text-rose-100 transition hover:bg-rose-400/20"
                onClick={() => void onLogout()}
                type="button"
              >
                Log out
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
