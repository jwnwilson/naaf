import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type DashboardMetrics = components["schemas"]["DashboardMetrics"];
export type TokenUsagePoint = components["schemas"]["TokenUsagePoint"];

export function useDashboard() {
  return useQuery({
    queryKey: queryKeys.dashboard(),
    queryFn: () => apiFetch<DashboardMetrics>("/dashboard/metrics"),
  });
}

export function useTokenUsage() {
  return useQuery({
    queryKey: [...queryKeys.dashboard(), "token-usage"],
    queryFn: () => apiFetch<TokenUsagePoint[]>("/dashboard/token-usage"),
  });
}
