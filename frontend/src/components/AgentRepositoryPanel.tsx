import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { AgentEditChatModal } from "./AgentEditChatModal";
import { useAgentsWorkspace } from "../context/AgentsWorkspaceContext";
import { checkInAgent, deleteAgent, fetchAgentTree, runAgent } from "../lib/api";
import type { AgentTreeNode } from "../types";

function TreeRows({
  node,
  depth,
  defaultOpenDepth,
}: {
  node: AgentTreeNode;
  depth: number;
  defaultOpenDepth: number;
}) {
  const [open, setOpen] = useState(depth < defaultOpenDepth);

  if (node.node_type === "file") {
    return (
      <div
        className="rounded-lg py-0.5 font-mono text-xs text-slate-300"
        style={{ paddingLeft: depth * 14 }}
      >
        <span className="text-slate-500">📄</span> {node.name}
      </div>
    );
  }

  return (
    <div>
      <button
        className="flex w-full items-center gap-1 rounded-lg py-0.5 text-left font-mono text-xs text-slate-200 transition hover:bg-white/5"
        onClick={() => setOpen((o) => !o)}
        style={{ paddingLeft: depth * 14 }}
        type="button"
      >
        <span>{open ? "📂" : "📁"}</span>
        <span>{node.name}</span>
      </button>
      {open ? (
        <div>
          {node.children.map((child) => (
            <TreeRows
              defaultOpenDepth={defaultOpenDepth}
              depth={depth + 1}
              key={child.path}
              node={child}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

interface AgentRepositoryPanelProps {
  onBanner: (banner: { kind: "success" | "error"; text: string } | null) => void;
}

export function AgentRepositoryPanel({ onBanner }: AgentRepositoryPanelProps) {
  const navigate = useNavigate();
  const { agents, setAgents, selectedAgentId, setSelectedAgentId, refreshAgents } = useAgentsWorkspace();
  const [tree, setTree] = useState<AgentTreeNode | null>(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [checkInBusy, setCheckInBusy] = useState(false);
  const [checkInStatus, setCheckInStatus] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [liveUiUrl, setLiveUiUrl] = useState<string | null>(null);
  const [liveUiAgentId, setLiveUiAgentId] = useState<string | null>(null);
  const [runUiBusy, setRunUiBusy] = useState(false);
  const [editChatOpen, setEditChatOpen] = useState(false);

  const loadTree = useCallback(async () => {
    if (!selectedAgentId) {
      setTree(null);
      return;
    }
    setTreeLoading(true);
    try {
      const root = await fetchAgentTree(selectedAgentId);
      setTree(root);
    } catch (e) {
      setTree(null);
      onBanner({
        kind: "error",
        text: e instanceof Error ? e.message : "Failed to load file tree.",
      });
    } finally {
      setTreeLoading(false);
    }
  }, [selectedAgentId, onBanner]);

  useEffect(() => {
    void loadTree();
  }, [loadTree]);

  useEffect(() => {
    setCheckInStatus(null);
  }, [selectedAgentId]);

  useEffect(() => {
    if (liveUiAgentId && liveUiAgentId !== selectedAgentId) {
      setLiveUiUrl(null);
      setLiveUiAgentId(null);
    }
  }, [selectedAgentId, liveUiAgentId]);

  useEffect(() => {
    if (liveUiAgentId && !agents.some((a) => a.agent_id === liveUiAgentId)) {
      setLiveUiUrl(null);
      setLiveUiAgentId(null);
    }
  }, [agents, liveUiAgentId]);

  const handleRunAgent = async () => {
    if (!selectedAgentId) {
      return;
    }
    const agent = agents.find((a) => a.agent_id === selectedAgentId);
    if (!agent) {
      return;
    }
    if (agent.frontend_type === "cli") {
      navigate("/run");
      return;
    }

    setRunUiBusy(true);
    onBanner(null);
    try {
      const result = await runAgent(selectedAgentId, "");
      if (result.local_url) {
        setLiveUiUrl(result.local_url);
        setLiveUiAgentId(selectedAgentId);
        onBanner({
          kind: "success",
          text: "The agent UI is loading below. Upload files and chat there—no second step needed.",
        });
      }
    } catch (e) {
      setLiveUiUrl(null);
      setLiveUiAgentId(null);
      onBanner({
        kind: "error",
        text: e instanceof Error ? e.message : "Failed to start the agent.",
      });
    } finally {
      setRunUiBusy(false);
    }
  };

  const handleCheckIn = async () => {
    if (!selectedAgentId) {
      return;
    }
    if (
      !window.confirm(
        "Check this agent into the configured GitHub repository? (Requires repo URL and token in settings.)",
      )
    ) {
      return;
    }
    setCheckInBusy(true);
    setCheckInStatus(null);
    onBanner(null);
    try {
      const result = await checkInAgent(selectedAgentId);
      await refreshAgents();
      setCheckInStatus({ kind: "success", text: result.message });
      onBanner({ kind: "success", text: result.message });
      await loadTree();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Check-in failed.";
      setCheckInStatus({ kind: "error", text: msg });
      onBanner({
        kind: "error",
        text: msg,
      });
    } finally {
      setCheckInBusy(false);
    }
  };

  const handleAfterAiEdit = useCallback(
    (updatedFiles: string[]) => {
      if (updatedFiles.length > 0 && liveUiAgentId === selectedAgentId) {
        setLiveUiUrl(null);
        setLiveUiAgentId(null);
      }
      void loadTree();
      if (updatedFiles.length > 0) {
        onBanner({
          kind: "success",
          text: `AI updated: ${updatedFiles.join(", ")}. Run the agent again to load changes.`,
        });
      }
    },
    [liveUiAgentId, selectedAgentId, loadTree, onBanner],
  );

  const handleDelete = async () => {
    if (!selectedAgentId) {
      return;
    }
    const agent = agents.find((a) => a.agent_id === selectedAgentId);
    const label = agent?.agent_name ?? selectedAgentId;
    if (
      !window.confirm(
        `Delete agent "${label}" and remove its files? This cannot be undone.`,
      )
    ) {
      return;
    }
    setDeleteBusy(true);
    onBanner(null);
    try {
      const idToRemove = selectedAgentId;
      const res = await deleteAgent(idToRemove);
      // Immediate UI update so the dropdown cannot show a deleted agent while refresh runs.
      const nextAgents = agents.filter((a) => a.agent_id !== idToRemove);
      setAgents(nextAgents);
      setSelectedAgentId(nextAgents[0]?.agent_id ?? "");
      setTree(null);
      await refreshAgents();
      onBanner({ kind: "success", text: res.message });
    } catch (e) {
      onBanner({
        kind: "error",
        text: e instanceof Error ? e.message : "Delete failed.",
      });
    } finally {
      setDeleteBusy(false);
    }
  };

  if (agents.length === 0) {
    return (
      <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 text-center text-sm text-slate-400 shadow-xl shadow-slate-950/30">
        Generate an agent above to manage its repository: Run, Edit agent (AI), Delete, then tree, Git check-in, and
        refresh.
      </div>
    );
  }

  const selected = agents.find((a) => a.agent_id === selectedAgentId);

  return (
    <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-2xl shadow-violet-950/20">
      <div className="mb-2 inline-flex rounded-full border border-violet-400/20 bg-violet-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-violet-100">
        Repository
      </div>
      <h3 className="text-lg font-semibold text-white">Repository</h3>
      <p className="mt-1 text-sm text-slate-300">
        For <span className="text-cyan-200">Gradio / React</span>, Run starts the app and shows it here—use the
        built-in chat (and uploads when enabled) in that UI. For <span className="text-cyan-200">CLI</span>, Run opens a
        terminal-style console. <span className="text-amber-200">Edit agent (AI)</span> sits between Run and Delete to
        change code with chat. Delete removes the agent. Check in and refresh apply to the file tree.
      </p>

      <label className="mt-5 block space-y-2">
        <span className="text-sm font-medium text-slate-200">Agent</span>
        <select
          className="w-full max-w-xl rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-white focus:border-violet-400/60 focus:outline-none"
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

      <div className="mt-4 flex flex-wrap gap-3">
        <button
          className="rounded-full bg-gradient-to-r from-emerald-400 via-cyan-400 to-violet-500 px-5 py-2.5 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-500/20 transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!selectedAgentId || runUiBusy}
          onClick={() => void handleRunAgent()}
          type="button"
        >
          {runUiBusy
            ? "Starting…"
            : selected?.frontend_type === "cli"
              ? "Run agent (CLI console)"
              : "Run agent"}
        </button>
        <button
          className="rounded-full border-2 border-amber-400/50 bg-amber-500/20 px-5 py-2.5 text-sm font-semibold text-amber-50 transition hover:bg-amber-500/30 disabled:opacity-50"
          disabled={!selectedAgentId}
          onClick={() => setEditChatOpen(true)}
          type="button"
        >
          Edit agent (AI)
        </button>
        <button
          className="rounded-full border border-rose-400/30 bg-rose-500/15 px-5 py-2.5 text-sm font-semibold text-rose-100 transition hover:bg-rose-500/25 disabled:opacity-50"
          disabled={!selectedAgentId || deleteBusy}
          onClick={() => void handleDelete()}
          type="button"
        >
          {deleteBusy ? "Deleting…" : "Delete agent"}
        </button>
      </div>

      <div className="mt-4 flex flex-wrap items-start gap-3 border-t border-white/10 pt-4">
        <div className="flex min-w-[min(100%,280px)] max-w-xl flex-col gap-2">
          <button
            className="self-start rounded-full border border-white/15 bg-white/10 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-white/15 disabled:opacity-50"
            disabled={!selectedAgentId || checkInBusy}
            onClick={() => void handleCheckIn()}
            type="button"
          >
            {checkInBusy ? "Checking in…" : "Check in to GitHub"}
          </button>
          {checkInBusy ? (
            <p className="text-xs text-slate-400">Cloning or updating the repo cache, committing, and pushing…</p>
          ) : null}
          {!checkInBusy && checkInStatus ? (
            <div
              className={`rounded-xl border px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap ${
                checkInStatus.kind === "success"
                  ? "border-emerald-400/25 bg-emerald-500/10 text-emerald-100"
                  : "border-rose-400/30 bg-rose-500/10 text-rose-100"
              }`}
              role="status"
            >
              <span className="font-semibold text-slate-200">
                {checkInStatus.kind === "success" ? "Check-in: " : "Check-in failed: "}
              </span>
              {checkInStatus.text}
            </div>
          ) : null}
        </div>
        <button
          className="rounded-full border border-cyan-400/25 bg-cyan-500/10 px-5 py-2.5 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-500/20 disabled:opacity-50"
          disabled={!selectedAgentId || treeLoading}
          onClick={() => void loadTree()}
          type="button"
        >
          {treeLoading ? "Refreshing…" : "Refresh tree"}
        </button>
      </div>

      {selected ? (
        <p className="mt-4 text-xs text-slate-500">
          Logic:{" "}
          <span className={selected.generation_source === "llm" ? "text-emerald-300/90" : "text-slate-400"}>
            {selected.generation_source === "llm" ? "LLM-generated" : "template"}
          </span>
          {" · "}
          GitHub: {selected.github_repo_path || "—"} · Commit:{" "}
          {selected.github_commit_sha ? selected.github_commit_sha.slice(0, 7) : "—"}
        </p>
      ) : null}

      {liveUiUrl && liveUiAgentId === selectedAgentId && selected?.frontend_type !== "cli" ? (
        <div className="mt-6 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-medium text-slate-200">Live agent</span>
            <a
              className="text-sm font-medium text-cyan-300 underline-offset-4 hover:text-cyan-200 hover:underline"
              href={liveUiUrl}
              rel="noopener noreferrer"
              target="_blank"
            >
              Open in new tab
            </a>
          </div>
          <p className="text-xs text-slate-500">
            If the frame stays blank, your browser may block embedding—use &quot;Open in new tab&quot;.
          </p>
          <iframe
            className="h-[min(720px,78vh)] w-full rounded-2xl border border-white/15 bg-slate-950 shadow-inner"
            referrerPolicy="no-referrer-when-downgrade"
            src={liveUiUrl}
            title={`Agent UI: ${selected?.agent_name ?? selectedAgentId}`}
          />
        </div>
      ) : null}

      <div className="mt-6 max-h-[min(420px,50vh)] overflow-auto rounded-2xl border border-white/10 bg-slate-950/40 p-4">
        {treeLoading && !tree ? (
          <p className="text-sm text-slate-400">Loading tree…</p>
        ) : tree ? (
          <TreeRows defaultOpenDepth={2} depth={0} node={tree} />
        ) : (
          <p className="text-sm text-slate-500">No tree loaded.</p>
        )}
      </div>

      {selectedAgentId && selected ? (
        <AgentEditChatModal
          agentId={selectedAgentId}
          agentName={selected.agent_name}
          frontendType={selected.frontend_type}
          onClose={() => setEditChatOpen(false)}
          onEdited={handleAfterAiEdit}
          open={editChatOpen}
        />
      ) : null}
    </div>
  );
}
