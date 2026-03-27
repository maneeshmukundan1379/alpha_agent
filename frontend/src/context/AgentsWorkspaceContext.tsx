import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  type ReactNode,
} from "react";

import { fetchAgents } from "../lib/api";
import type { AgentMetadata } from "../types";

export type AgentsWorkspaceValue = {
  agents: AgentMetadata[];
  setAgents: React.Dispatch<React.SetStateAction<AgentMetadata[]>>;
  selectedAgentId: string;
  setSelectedAgentId: React.Dispatch<React.SetStateAction<string>>;
  refreshAgents: () => Promise<void>;
};

const AgentsWorkspaceContext = createContext<AgentsWorkspaceValue | null>(null);

export function AgentsWorkspaceProvider({
  children,
  agents,
  setAgents,
  selectedAgentId,
  setSelectedAgentId,
}: {
  children: ReactNode;
  agents: AgentMetadata[];
  setAgents: React.Dispatch<React.SetStateAction<AgentMetadata[]>>;
  selectedAgentId: string;
  setSelectedAgentId: React.Dispatch<React.SetStateAction<string>>;
}) {
  const refreshAgents = useCallback(async () => {
    const next = await fetchAgents();
    setAgents(next);
    setSelectedAgentId((current) => {
      if (next.length === 0) {
        return "";
      }
      if (current && next.some((a) => a.agent_id === current)) {
        return current;
      }
      return next[0].agent_id;
    });
  }, [setAgents, setSelectedAgentId]);

  // If the list no longer contains the selected id (e.g. delete + stale fetch), fix selection.
  useEffect(() => {
    if (!selectedAgentId) {
      return;
    }
    if (agents.some((a) => a.agent_id === selectedAgentId)) {
      return;
    }
    setSelectedAgentId(agents[0]?.agent_id ?? "");
  }, [agents, selectedAgentId, setSelectedAgentId]);

  const value = useMemo(
    () => ({
      agents,
      setAgents,
      selectedAgentId,
      setSelectedAgentId,
      refreshAgents,
    }),
    [agents, setAgents, selectedAgentId, setSelectedAgentId, refreshAgents],
  );

  return <AgentsWorkspaceContext.Provider value={value}>{children}</AgentsWorkspaceContext.Provider>;
}

export function useAgentsWorkspace(): AgentsWorkspaceValue {
  const ctx = useContext(AgentsWorkspaceContext);
  if (!ctx) {
    throw new Error("useAgentsWorkspace must be used within AgentsWorkspaceProvider");
  }
  return ctx;
}
