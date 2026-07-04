import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";

export type Agent = {
  role: string;
  model: string;
  status: "running" | "idle";
  runId: string | null;
  workItemId: string | null;
  currentStage: string | null;
  progress: number | null;
  tokenUsage: number;
};

// The roster lights up as runs advance server-side; poll while mounted so the
// panel stays live. Paused when the tab is hidden (refetchIntervalInBackground
// defaults to false), matching useBoard/BOARD_POLL_MS.
export const AGENTS_POLL_MS = 5000;

export function useAgents(pollMs: number = AGENTS_POLL_MS) {
  return useQuery({
    queryKey: queryKeys.agents(),
    queryFn: () => apiFetch<Agent[]>("/agents"),
    refetchInterval: pollMs,
  });
}
