import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type Agent = components["schemas"]["Agent"];

export function useAgents() {
  return useQuery({
    queryKey: queryKeys.agents(),
    queryFn: () => apiFetch<Agent[]>("/agents"),
  });
}
