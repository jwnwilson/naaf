import type { QueryClient } from "@tanstack/react-query";
import { isProjectThread, projectIdFromThread } from "../../threadScope";
import { queryKeys } from "../queryKeys";

/**
 * When a project-level (lead) thread mutates, the lead may have created or
 * changed work items. Refresh the board + work-item + project queries so those
 * appear, since server-side (agent) creates don't invalidate client queries.
 * No-op for work-item threads.
 */
export function invalidateBoardForThread(qc: QueryClient, threadId: string): void {
  if (!isProjectThread(threadId)) return;
  const projectId = projectIdFromThread(threadId);
  void qc.invalidateQueries({ queryKey: queryKeys.board(projectId) });
  void qc.invalidateQueries({ queryKey: ["work-items", "project", projectId] });
  void qc.invalidateQueries({ queryKey: queryKeys.projects() });
}
