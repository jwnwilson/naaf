import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type WorkItem = components["schemas"]["WorkItem"];

export function useBoard(projectId: string) {
  return useQuery({
    queryKey: queryKeys.board(projectId),
    queryFn: () => apiFetch<WorkItem[]>(`/projects/${projectId}/board`),
    enabled: Boolean(projectId),
  });
}
