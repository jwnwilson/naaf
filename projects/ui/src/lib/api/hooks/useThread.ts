import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type ThreadDetail = components["schemas"]["ThreadDetail"];

export function useThread(workItemId?: string) {
  return useQuery({
    queryKey: queryKeys.thread(workItemId),
    queryFn: () => apiFetch<ThreadDetail>(`/threads/${workItemId!}`),
    enabled: Boolean(workItemId),
  });
}
