import type { ChangeEvent } from "react";

import type { AgentConfigRequest, ProviderInfo } from "../types";
import { SecretsEditor } from "./SecretsEditor";

interface BuilderFormProps {
  config: AgentConfigRequest;
  providers: ProviderInfo[];
  isGenerating: boolean;
  onChange: (nextConfig: AgentConfigRequest) => void;
  onGenerate: () => void;
}

const FRONTEND_OPTIONS = [
  {
    id: "cli",
    label: "CLI",
    description: "Terminal-based interactive agent (Python only).",
  },
  {
    id: "gradio",
    label: "Gradio",
    description: "Python web UI — quick to run, no Node.js.",
  },
  {
    id: "react",
    label: "React",
    description: "Vite + React chat UI with a FastAPI backend (needs Node.js for dev).",
  },
] as const;

const TOOL_OPTIONS = [
  {
    id: "document_context",
    label: "Document Context",
    description: "Ground the generated agent with uploaded file content when available.",
  },
  {
    id: "structured_output",
    label: "Structured Output",
    description: "Push the generated agent toward headings, bullets, and cleaner response structure.",
  },
  {
    id: "citation_notes",
    label: "Citation Notes",
    description: "Encourage the generated agent to mention the source file when using uploaded context.",
  },
  {
    id: "checklist_planner",
    label: "Checklist Planner",
    description: "End planning or recommendation responses with a concise action checklist.",
  },
] as const;

export function BuilderForm({
  config,
  providers,
  isGenerating,
  onChange,
  onGenerate,
}: BuilderFormProps) {
  const selectedProvider =
    providers.find((provider) => provider.id === config.provider_id) ?? providers[0];

  const update = <K extends keyof AgentConfigRequest>(key: K, value: AgentConfigRequest[K]) => {
    onChange({ ...config, [key]: value });
  };

  const updateConfig = (nextFields: Partial<AgentConfigRequest>) => {
    onChange({ ...config, ...nextFields });
  };

  const updateText =
    (key: "agent_name" | "description" | "instructions") =>
    (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      update(key, event.target.value);
    };

  return (
    <div className="space-y-6 rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-2xl shadow-slate-950/40">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-2 inline-flex rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-cyan-100">
            Agent Blueprint
          </div>
          <h2 className="text-2xl font-semibold text-white">Design a Python agent in minutes</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
            Describe the use case, choose the model provider, add optional third-party API keys, pick a
            generated frontend, and export a ready-to-run Python project.
          </p>
        </div>

        <button
          className="rounded-full bg-gradient-to-r from-cyan-400 via-sky-400 to-violet-500 px-5 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
          disabled={isGenerating}
          onClick={onGenerate}
          type="button"
        >
          {isGenerating ? "Generating..." : "Generate Agent"}
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <label className="space-y-2">
          <span className="text-sm font-medium text-slate-200">Agent name</span>
          <input
            className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none"
            onChange={updateText("agent_name")}
            placeholder="Customer Insight Agent"
            value={config.agent_name}
          />
        </label>

        <label className="space-y-2">
          <span className="text-sm font-medium text-slate-200">Model provider</span>
          <select
            className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white focus:border-cyan-400/60 focus:outline-none"
            onChange={(event) => {
              const provider = providers.find((item) => item.id === event.target.value);
              updateConfig({
                provider_id: event.target.value as AgentConfigRequest["provider_id"],
                model: provider?.default_model ?? config.model,
              });
            }}
            value={config.provider_id}
          >
            {providers.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="space-y-2">
        <span className="text-sm font-medium text-slate-200">What should this agent be used for?</span>
        <textarea
          className="min-h-[110px] w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none"
          onChange={updateText("description")}
          placeholder="Example: analyze customer feedback, detect the top themes, and suggest practical follow-up actions."
          value={config.description}
        />
      </label>

      <label className="space-y-2">
        <span className="text-sm font-medium text-slate-200">Agent instructions</span>
        <textarea
          className="min-h-[160px] w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none"
          onChange={updateText("instructions")}
          placeholder="Tell the agent how to respond, structure output, and handle ambiguity."
          value={config.instructions}
        />
      </label>

      <label className="space-y-2">
        <span className="text-sm font-medium text-slate-200">Model</span>
        <select
          className="w-full max-w-xl rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white focus:border-cyan-400/60 focus:outline-none"
          onChange={(event) => update("model", event.target.value)}
          value={config.model}
        >
          {selectedProvider?.models.map((model) => (
            <option key={model} value={model}>
              {model}
            </option>
          ))}
        </select>
        <p className="text-xs text-slate-400">{selectedProvider?.description}</p>
      </label>

      <div className="space-y-3 rounded-2xl border border-white/10 bg-slate-950/30 p-4">
        <label className="flex items-start gap-3">
          <input
            checked={config.include_settings_api_keys}
            className="mt-1 h-4 w-4 accent-cyan-400"
            onChange={(event) => update("include_settings_api_keys", event.target.checked)}
            type="checkbox"
          />
          <span>
            <span className="text-sm font-medium text-slate-200">
              Include Settings API keys in the agent <code className="text-cyan-200/90">.env</code>
            </span>
            <p className="mt-1 text-xs leading-5 text-slate-400">
              When enabled, keys you saved under Settings (OpenAI, Gemini, GitHub token) are written into this
              agent&apos;s local <code className="text-slate-300">.env</code> at generate time so the project runs
              standalone. The file is gitignored. Uncheck if you only want custom keys below or will inject keys
              another way.
            </p>
          </span>
        </label>
      </div>

      <SecretsEditor
        description="Names and values are merged into this agent’s .env (additional keys override Settings if the name matches). Use UPPER_SNAKE_CASE names your logic.py can read with os.getenv."
        heading="Additional secret APIs"
        onChange={(secrets) => updateConfig({ secrets })}
        secrets={config.secrets}
        suggestedKeys={["NEWS_API_KEY", "SERPAPI_API_KEY", "TAVILY_API_KEY"]}
      />

      <div className="grid gap-4 md:grid-cols-2">
        <label className="space-y-2">
          <span className="text-sm font-medium text-slate-200">Generated frontend</span>
          <select
            className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white focus:border-cyan-400/60 focus:outline-none"
            onChange={(event) =>
              update("frontend_type", event.target.value as AgentConfigRequest["frontend_type"])
            }
            value={config.frontend_type}
          >
            {FRONTEND_OPTIONS.map((frontend) => (
              <option key={frontend.id} value={frontend.id}>
                {frontend.label}
              </option>
            ))}
          </select>
          <p className="text-xs text-slate-400">
            {FRONTEND_OPTIONS.find((frontend) => frontend.id === config.frontend_type)?.description}
          </p>
        </label>

        <label className="space-y-2">
          <span className="text-sm font-medium text-slate-200">Temperature</span>
          <input
            className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white focus:border-cyan-400/60 focus:outline-none"
            max={2}
            min={0}
            onChange={(event) => update("temperature", Number(event.target.value))}
            step={0.1}
            type="number"
            value={config.temperature}
          />
        </label>
      </div>

      <label className="space-y-2">
        <span className="text-sm font-medium text-slate-200">Optional GitHub repository</span>
        <input
          className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none"
          onChange={(event) => update("github_repo_url", event.target.value)}
          placeholder="https://github.com/your-org/your-repo.git"
          value={config.github_repo_url}
        />
        <p className="text-xs text-slate-400">
          If provided, the generated agent will also be checked into this GitHub repo using the token saved in Settings.
        </p>
      </label>

      <label className="space-y-2">
        <span className="text-sm font-medium text-slate-200">Additional Python requirements</span>
        <input
          className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none"
          onChange={(event) =>
            update(
              "extra_requirements",
              event.target.value
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean),
            )
          }
          placeholder="Example: pandas, numpy"
          value={config.extra_requirements.join(", ")}
        />
        <p className="text-xs text-slate-400">
          Add any extra Python packages you want included in the generated `requirements.txt`.
        </p>
      </label>

      <div className="space-y-3">
        <div>
          <span className="text-sm font-medium text-slate-200">Tools and capabilities</span>
          <p className="mt-1 text-xs text-slate-400">
            Choose optional behaviors baked into the generated agent&apos;s system prompt and tooling hints.
          </p>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          {TOOL_OPTIONS.map((tool) => {
            const enabled = config.enabled_tools.includes(tool.id);
            return (
              <button
                key={tool.id}
                className={`rounded-2xl border p-4 text-left transition ${
                  enabled
                    ? "border-cyan-400/40 bg-cyan-400/10"
                    : "border-white/10 bg-slate-950/40 hover:bg-white/5"
                }`}
                onClick={() =>
                  update(
                    "enabled_tools",
                    enabled
                      ? config.enabled_tools.filter((toolId) => toolId !== tool.id)
                      : [...config.enabled_tools, tool.id],
                  )
                }
                type="button"
              >
                <div className="text-sm font-semibold text-white">{tool.label}</div>
                <div className="mt-1 text-xs leading-5 text-slate-400">{tool.description}</div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-3 rounded-2xl border border-white/10 bg-slate-950/30 p-4">
        <label className="flex items-center gap-3">
          <input
            checked={config.allow_file_uploads}
            className="h-4 w-4 accent-cyan-400"
            onChange={(event) => update("allow_file_uploads", event.target.checked)}
            type="checkbox"
          />
          <span className="text-sm font-medium text-slate-200">
            Enable file upload support in the generated agent
          </span>
        </label>

        <label className="space-y-2">
          <span className="text-sm font-medium text-slate-200">Supported upload types</span>
          <input
            className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!config.allow_file_uploads}
            onChange={(event) =>
              update(
                "supported_upload_types",
                event.target.value
                  .split(",")
                  .map((item) => item.trim().replace(/^\./, "").toLowerCase())
                  .filter(Boolean),
              )
            }
            placeholder="txt, md, csv, json, py"
            value={config.supported_upload_types.join(", ")}
          />
          <p className="text-xs text-slate-400">
            These file types can be uploaded through the generated agent and the builder runner.
          </p>
        </label>
      </div>
    </div>
  );
}
