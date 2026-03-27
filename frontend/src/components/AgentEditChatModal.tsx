import { useEffect, useRef, useState } from "react";

import { agentEditChat } from "../lib/api";
import type { AgentEditChatMessage, FrontendType } from "../types";

interface AgentEditChatModalProps {
  open: boolean;
  onClose: () => void;
  agentId: string;
  agentName: string;
  /** Used to show which paths the edit agent can touch */
  frontendType?: FrontendType;
  onEdited: (updatedFiles: string[]) => void;
}

export function AgentEditChatModal({
  open,
  onClose,
  agentId,
  agentName,
  frontendType,
  onEdited,
}: AgentEditChatModalProps) {
  const [messages, setMessages] = useState<AgentEditChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [includeStaticDiagnostics, setIncludeStaticDiagnostics] = useState(true);
  const [runtimeError, setRuntimeError] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activityLog, setActivityLog] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const logBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      setMessages([]);
      setDraft("");
      setIncludeStaticDiagnostics(true);
      setRuntimeError("");
      setError(null);
      setBusy(false);
      setActivityLog([]);
    }
  }, [open, agentId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, open]);

  useEffect(() => {
    logBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activityLog, busy, open]);

  if (!open) {
    return null;
  }

  const send = async () => {
    const text = draft.trim();
    if (!text || busy) {
      return;
    }
    const nextThread: AgentEditChatMessage[] = [...messages, { role: "user", content: text }];
    setMessages(nextThread);
    setDraft("");
    setBusy(true);
    setError(null);
    try {
      const result = await agentEditChat(agentId, nextThread, {
        include_static_diagnostics: includeStaticDiagnostics,
        runtime_error: runtimeError,
      });
      const lines = result.activity_log ?? [];
      const stamp = new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      setActivityLog((prev) => [...prev, `── ${stamp} · your instruction ──`, ...lines]);
      setMessages((m) => [...m, { role: "assistant", content: result.assistant_message }]);
      if (result.updated_files.length > 0) {
        onEdited(result.updated_files);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Request failed.";
      setError(msg);
      setActivityLog((prev) => [...prev, `[error] ${msg}`]);
      setMessages((m) => m.slice(0, -1));
      setDraft(text);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      aria-modal="true"
      className="fixed inset-0 z-[100] flex items-end justify-center bg-slate-950/80 p-4 backdrop-blur-sm sm:items-center"
      onClick={(e) => e.target === e.currentTarget && !busy && onClose()}
      onKeyDown={(e) => e.key === "Escape" && !busy && onClose()}
      role="dialog"
    >
      <div className="flex max-h-[min(720px,92vh)] w-full max-w-5xl flex-col overflow-hidden rounded-[1.75rem] border border-white/15 bg-slate-900 shadow-2xl shadow-cyan-950/40">
        <div className="flex items-start justify-between gap-4 border-b border-white/10 px-5 py-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-widest text-cyan-300/90">Edit agent</div>
            <h2 className="mt-1 text-lg font-semibold text-white">{agentName}</h2>
            <p className="mt-1 text-xs text-slate-400">
              Uses your Settings API key. Whitelisted paths: <code className="text-slate-300">logic.py</code>,{" "}
              <code className="text-slate-300">app.py</code> (if present), <code className="text-slate-300">main.py</code>,{" "}
              <code className="text-slate-300">run_agent.py</code>, <code className="text-slate-300">requirements.txt</code>
              {frontendType === "react" ? (
                <>
                  , plus the generated <code className="text-slate-300">react-ui/</code> app (e.g.{" "}
                  <code className="text-slate-300">App.tsx</code>, <code className="text-slate-300">main.tsx</code>, Vite
                  config, styles).
                </>
              ) : null}
              . Optional <strong className="text-slate-300">static checks</strong> (Python compile +{" "}
              <code>import logic</code>) and a <strong className="text-slate-300">runtime error</strong> paste help the model
              fix broken agents. The running agent is stopped before each turn.{" "}
              <strong className="text-slate-300">Activity</strong> shows file reads, diagnostics, model call, and writes.
            </p>
          </div>
          <button
            className="rounded-full border border-white/15 px-3 py-1.5 text-sm text-slate-200 hover:bg-white/10 disabled:opacity-40"
            disabled={busy}
            onClick={onClose}
            type="button"
          >
            Close
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-0 lg:flex-row">
          <div className="min-h-0 min-w-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
            {messages.length === 0 ? (
              <div className="rounded-2xl border border-white/10 bg-slate-950/50 p-4 text-sm text-slate-400">
                {frontendType === "react" ? (
                  <>
                    Example: “Change the chat header title and primary button color in the React UI,” or “Widen the message
                    column in <code className="text-slate-300">react-ui/src/App.tsx</code>.” You can also ask to adjust{" "}
                    <code className="text-slate-300">main.py</code> or <code className="text-slate-300">logic.py</code>.
                  </>
                ) : (
                  <>
                    Example: “Fix the Gradio error” (with static checks on + traceback pasted below), or “Add a tone textbox
                    and pass it into the system prompt in logic.py.”
                  </>
                )}
              </div>
            ) : null}
            {messages.map((m, i) => (
              <div
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
                key={`${m.role}-${i}-${m.content.slice(0, 12)}`}
              >
                <div
                  className={`max-w-[90%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
                    m.role === "user"
                      ? "bg-cyan-500/20 text-cyan-50"
                      : "border border-white/10 bg-slate-950/70 text-slate-100"
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {error ? (
              <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
                {error}
              </div>
            ) : null}
            <div ref={bottomRef} />
          </div>

          <div className="flex max-h-48 min-h-0 shrink-0 flex-col border-t border-white/10 bg-slate-950/80 lg:max-h-none lg:w-[min(100%,320px)] lg:border-t-0 lg:border-l">
            <div className="border-b border-white/10 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Activity log
              {busy ? <span className="ml-2 text-cyan-300/90">· working…</span> : null}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2 font-mono text-[11px] leading-relaxed text-slate-400">
              {activityLog.length === 0 && !busy ? (
                <p className="text-slate-500">Logs appear after each send: files read, model call, disk writes.</p>
              ) : null}
              {activityLog.map((line, i) => (
                <div className="break-words border-b border-white/5 py-1 text-slate-300 last:border-0" key={`${i}-${line.slice(0, 24)}`}>
                  {line}
                </div>
              ))}
              {busy && activityLog.length === 0 ? (
                <div className="animate-pulse text-slate-500">Waiting for edit agent…</div>
              ) : null}
              <div ref={logBottomRef} />
            </div>
          </div>
        </div>

        <div className="border-t border-white/10 p-4">
          <label className="mb-2 flex cursor-pointer items-center gap-2 text-xs text-slate-400">
            <input
              checked={includeStaticDiagnostics}
              className="rounded border-white/20 bg-slate-900"
              disabled={busy}
              onChange={(e) => setIncludeStaticDiagnostics(e.target.checked)}
              type="checkbox"
            />
            Run static checks (py_compile + import logic) — results go to the model and Activity log
          </label>
          <textarea
            className="mb-3 min-h-[72px] w-full resize-y rounded-2xl border border-white/10 bg-slate-950/40 px-4 py-2 font-mono text-[11px] text-slate-200 placeholder:text-slate-600 focus:border-amber-400/40 focus:outline-none disabled:opacity-50"
            disabled={busy}
            onChange={(e) => setRuntimeError(e.target.value)}
            placeholder="Optional: paste full traceback or stderr from running the agent (terminal or browser)…"
            value={runtimeError}
          />
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <textarea
              className="min-h-[88px] flex-1 resize-y rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-cyan-400/50 focus:outline-none disabled:opacity-50"
              disabled={busy}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              placeholder="Describe changes, or say e.g. “Fix the errors from diagnostics/traceback”… (Enter to send, Shift+Enter for newline)"
              value={draft}
            />
            <button
              className="shrink-0 rounded-full bg-gradient-to-r from-cyan-400 to-violet-500 px-6 py-3 text-sm font-semibold text-slate-950 shadow-lg disabled:cursor-not-allowed disabled:opacity-50"
              disabled={busy || !draft.trim()}
              onClick={() => void send()}
              type="button"
            >
              {busy ? "Working…" : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
