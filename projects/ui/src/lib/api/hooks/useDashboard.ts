import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type DashboardMetrics = components["schemas"]["DashboardMetrics"];
export type TokenUsagePoint = components["schemas"]["TokenUsagePoint"];
export type ActivityEvent = components["schemas"]["ActivityEvent"];

// The dashboard reflects server-side agent activity; poll while mounted so the
// token chart + activity feed stay live. Paused when the tab is hidden
// (refetchIntervalInBackground defaults to false).
export const DASHBOARD_POLL_MS = 10000;

export function useDashboard() {
  return useQuery({
    queryKey: queryKeys.dashboard(),
    queryFn: () => apiFetch<DashboardMetrics>("/dashboard/metrics"),
    refetchInterval: DASHBOARD_POLL_MS,
  });
}

export function useTokenUsage() {
  return useQuery({
    queryKey: [...queryKeys.dashboard(), "token-usage"],
    queryFn: () => apiFetch<TokenUsagePoint[]>("/dashboard/token-usage"),
    refetchInterval: DASHBOARD_POLL_MS,
  });
}

export function useActivity() {
  return useQuery({
    queryKey: [...queryKeys.dashboard(), "activity"],
    queryFn: () => apiFetch<ActivityEvent[]>("/activity"),
    refetchInterval: DASHBOARD_POLL_MS,
  });
}
