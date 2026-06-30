import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type WorkItem = components["schemas"]["WorkItem"];

export function useWorkItem(id: string) {
  return useQuery({
    queryKey: queryKeys.workItem(id),
    queryFn: () => apiFetch<WorkItem>(`/work-items/${id}`),
    enabled: Boolean(id),
  });
}
