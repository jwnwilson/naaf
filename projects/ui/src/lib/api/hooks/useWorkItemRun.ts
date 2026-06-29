import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import type { components } from "../schema";

type AgentRun = components["schemas"]["AgentRun"];

export function useWorkItemRun(itemId: string) {
  return useQuery({
    queryKey: ["work-item-run", itemId],
    queryFn: () => apiFetch<AgentRun | null>(`/work-items/${itemId}/run`),
    enabled: Boolean(itemId),
  });
}
