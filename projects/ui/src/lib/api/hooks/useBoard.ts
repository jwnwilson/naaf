import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type WorkItem = components["schemas"]["WorkItem"];

// Agents (runs, and the conversational lead) create and move work items
// server-side, which never invalidates client queries. Poll the board while it
// is mounted so those changes appear live. Paused automatically when the tab is
// hidden (refetchIntervalInBackground defaults to false).
export const BOARD_POLL_MS = 5000;

export function useBoard(projectId: string, pollMs: number = BOARD_POLL_MS) {
  return useQuery({
    queryKey: queryKeys.board(projectId),
    queryFn: () => apiFetch<WorkItem[]>(`/projects/${projectId}/board`),
    enabled: Boolean(projectId),
    refetchInterval: pollMs,
  });
}
