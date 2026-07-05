import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";
import { DASHBOARD_POLL_MS } from "./useDashboard";

export type Budget = components["schemas"]["Budget"];

export function useBudget() {
  return useQuery({
    queryKey: queryKeys.budget(),
    queryFn: () => apiFetch<Budget>("/budget"),
    refetchInterval: DASHBOARD_POLL_MS,
  });
}
