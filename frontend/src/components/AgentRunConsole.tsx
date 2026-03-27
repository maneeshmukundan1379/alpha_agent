import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { useAgentsWorkspace } from "../context/AgentsWorkspaceContext";
import { fetchAgentLogs, fetchUploads, runAgent, uploadFiles } from "../lib/api";
import type { RunRecord, UploadedFileInfo } from "../types";

const DEFAULT_CLI_PROMPT = "Briefly introduce yourself and what you can help with.";

interface AgentRunConsoleProps {
  onBanner: (banner: { kind: "success" | "error"; text: string } | null) => void;
}

export function AgentRunConsole({ onBanner }: AgentRunConsoleProps) {
  const { agents, selectedAgentId, setSelectedAgentId } = useAgentsWorkspace();
  const [runPrompt, setRunPrompt] = useState("");
  const [isExecuting, setIsExecuting] = useState(false);
  const [logs, setLogs] = useState("");
  const [runRecord, setRunRecord] = useState<RunRecord | null>(null);
  const [uploads, setUploads] = useState<UploadedFileInfo[]>([]);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [embeddedUiUrl, setEmbeddedUiUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selected = agents.find((a) => a.agent_id === selectedAgentId);
  const isWebUi = selected?.frontend_type === "gradio" || selected?.frontend_type === "react";

  const refreshLogs = useCallback(async () => {
    if (!selectedAgentId) {
      setLogs("");
      setRunRecord(null);
      return;
    }
    try {
      const data = await fetchAgentLogs(selectedAgentId);
      setRunRecord(data.run);
      setLogs(data.logs);
    } catch {
      setLogs("");
      setRunRecord(null);
    }
  }, [selectedAgentId]);

  const refreshUploads = useCallback(async () => {
    if (!selectedAgentId) {
      setUploads([]);
      return;
    }
    try {
      const list = await fetchUploads(selectedAgentId);
      setUploads(list);
    } catch {
      setUploads([]);
    }
  }, [selectedAgentId]);

  useEffect(() => {
    void refreshLogs();
    if (!isWebUi) {
      void refreshUploads();
    }
  }, [refreshLogs, refreshUploads, isWebUi]);

  useEffect(() => {
    if (!selectedAgentId) {
      return;
    }
    const tick = () => void refreshLogs();
    const id = window.setInterval(tick, 2000);
    return () => window.clearInterval(id);
  }, [selectedAgentId, refreshLogs]);

  useEffect(() => {
    setEmbeddedUiUrl(null);
  }, [selectedAgentId]);

  const promptForRun = (): string => {
    const trimmed = runPrompt.trim();
    if (selected?.frontend_type === "cli") {
      return trimmed || DEFAULT_CLI_PROMPT;
    }
    return trimmed;
  };

  const handleExecute = async () => {
    if (!selectedAgentId) {
      return;
    }
    setIsExecuting(true);
    onBanner(null);
    try {
      const result = await runAgent(selectedAgentId, isWebUi ? "" : promptForRun());
      await refreshLogs();
      if (result.local_url) {
        setEmbeddedUiUrl(result.local_url);
        onBanner({
          kind: "success",
          text: "UI is ready below. Use the built-in chat and uploads inside the agent—nothing else to run here.",
        });
      } else {
        onBanner({
          kind: "success",
          text: result.message,
        });
      }
    } catch (e) {
      setEmbeddedUiUrl(null);
      onBanner({
        kind: "error",
        text: e instanceof Error ? e.message : "Failed to execute the agent.",
      });
    } finally {
      setIsExecuting(false);
    }
  };

  const handlePickFiles = () => fileInputRef.current?.click();

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!selectedAgentId || !files?.length) {
      e.target.value = "";
      return;
    }
    setUploadBusy(true);
    onBanner(null);
    try {
      await uploadFiles(selectedAgentId, Array.from(files));
      await refreshUploads();
      onBanner({ kind: "success", text: "Files uploaded." });
    } catch (err) {
      onBanner({
        kind: "error",
        text: err instanceof Error ? err.message : "Upload failed.",
      });
    } finally {
      setUploadBusy(false);
      e.target.value = "";
    }
  };

  const acceptExtensions = selected?.supported_upload_types?.length
    ? selected.supported_upload_types.map((t) => `.${t}`).join(",")
    : undefined;

  if (agents.length === 0) {
    return (
      <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 text-center text-sm text-slate-400 shadow-xl shadow-slate-950/30">
        <p>Generate an agent on the builder page first.</p>
        <Link className="mt-4 inline-block text-cyan-300 underline hover:text-cyan-200" to="/">
          Back to builder
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <Link
          className="text-sm font-medium text-cyan-300 underline-offset-4 hover:text-cyan-200 hover:underline"
          to="/"
        >
          ← Back to builder
        </Link>
      </div>

      <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-2xl shadow-cyan-950/20">
        <div className="mb-2 inline-flex rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-emerald-100">
          {isWebUi ? "Web agent" : "CLI"}
        </div>
        <h2 className="text-lg font-semibold text-white">
          {isWebUi ? "Start the generated UI" : "CLI run, uploads &amp; logs"}
        </h2>
        <p className="mt-1 text-sm text-slate-300">
          {isWebUi ? (
            <>
              Gradio and React agents open their own page—one click starts the server (React also runs Vite). Chat and uploads happen{" "}
              <strong className="text-slate-200">inside that UI</strong>, not on this screen.
            </>
          ) : (
            <>
              One-shot runs use the prompt below. Optional uploads are passed to the CLI runner on the server—separate
              from any web UI.
            </>
          )}
        </p>

        <div className="mt-5 flex flex-col gap-4 lg:flex-row lg:items-end">
          <label className="block min-w-[240px] flex-1 space-y-2">
            <span className="text-sm font-medium text-slate-200">Agent</span>
            <select
              className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white focus:border-cyan-400/60 focus:outline-none"
              onChange={(e) => setSelectedAgentId(e.target.value)}
              value={selectedAgentId}
            >
              {agents.map((agent) => (
                <option key={agent.agent_id} value={agent.agent_id}>
                  {agent.agent_name}
                </option>
              ))}
            </select>
          </label>
          <button
            className="rounded-full bg-gradient-to-r from-emerald-400 via-cyan-400 to-violet-500 px-8 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-500/20 transition hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!selectedAgentId || isExecuting}
            onClick={() => void handleExecute()}
            type="button"
          >
            {isExecuting ? "Starting…" : isWebUi ? "Start agent UI" : "Execute CLI run"}
          </button>
        </div>

        {!isWebUi ? (
          <label className="mt-6 block space-y-2">
            <span className="text-sm font-medium text-slate-200">
              Run prompt (empty uses a short default)
            </span>
            <textarea
              className="min-h-[100px] w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none"
              onChange={(e) => setRunPrompt(e.target.value)}
              placeholder="Ask the CLI agent something…"
              value={runPrompt}
            />
          </label>
        ) : null}
      </div>

      {isWebUi && embeddedUiUrl ? (
        <div className="space-y-3 rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-xl shadow-slate-950/20">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-medium text-slate-200">Agent UI</span>
            <a
              className="text-sm font-medium text-cyan-300 underline-offset-4 hover:text-cyan-200 hover:underline"
              href={embeddedUiUrl}
              rel="noopener noreferrer"
              target="_blank"
            >
              Open in new tab
            </a>
          </div>
          <iframe
            className="h-[min(720px,78vh)] w-full rounded-2xl border border-white/15 bg-slate-950"
            referrerPolicy="no-referrer-when-downgrade"
            src={embeddedUiUrl}
            title={`Agent UI: ${selected?.agent_name ?? selectedAgentId}`}
          />
        </div>
      ) : null}

      {!isWebUi && selected?.allow_file_uploads ? (
        <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-xl shadow-slate-950/20">
          <h3 className="text-base font-semibold text-white">Uploads (CLI only)</h3>
          <p className="mt-1 text-sm text-slate-400">
            These files are sent to the server-side CLI run. Types: {selected.supported_upload_types.join(", ") || "any"}
          </p>
          <input
            accept={acceptExtensions}
            className="hidden"
            multiple
            onChange={(e) => void handleFileChange(e)}
            ref={fileInputRef}
            type="file"
          />
          <button
            className="mt-4 rounded-full border border-white/15 bg-white/10 px-5 py-2 text-sm font-semibold text-white hover:bg-white/15 disabled:opacity-50"
            disabled={uploadBusy}
            onClick={handlePickFiles}
            type="button"
          >
            {uploadBusy ? "Uploading…" : "Choose files"}
          </button>
          {uploads.length > 0 ? (
            <ul className="mt-4 space-y-1 text-sm text-slate-300">
              {uploads.map((u) => (
                <li key={u.stored_path}>
                  {u.name}{" "}
                  <span className="text-slate-500">({Math.round(u.size_bytes / 1024)} KB)</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-slate-500">No files uploaded yet.</p>
          )}
        </div>
      ) : !isWebUi ? (
        <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 text-sm text-slate-500">
          This agent was generated without CLI file uploads.
        </div>
      ) : null}

      <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-xl shadow-slate-950/20">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-base font-semibold text-white">Server logs</h3>
          {runRecord ? (
            <span className="text-xs text-slate-400">
              Status: <span className="text-slate-200">{runRecord.status}</span>
              {runRecord.prompt && !isWebUi ? (
                <>
                  {" "}
                  · Prompt: <span className="text-slate-300">{runRecord.prompt.slice(0, 80)}</span>
                  {runRecord.prompt.length > 80 ? "…" : ""}
                </>
              ) : null}
            </span>
          ) : (
            <span className="text-xs text-slate-500">No runs yet</span>
          )}
        </div>
        <pre className="mt-4 max-h-[min(480px,55vh)] overflow-auto whitespace-pre-wrap rounded-2xl border border-white/10 bg-slate-950/70 p-4 font-mono text-xs text-slate-200">
          {logs || "—"}
        </pre>
      </div>
    </div>
  );
}
