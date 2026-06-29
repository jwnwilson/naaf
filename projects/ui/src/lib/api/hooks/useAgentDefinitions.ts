import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type AgentDefinition = components["schemas"]["AgentDefinition"];

export function useAgentDefinitions() {
  return useQuery({
    queryKey: queryKeys.agentDefinitions(),
    queryFn: () => apiFetch<AgentDefinition[]>("/agent-definitions"),
  });
}
