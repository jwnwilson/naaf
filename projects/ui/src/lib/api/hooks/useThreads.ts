import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type Thread = components["schemas"]["Thread"];

export function useThreads() {
  return useQuery({
    queryKey: queryKeys.threads(),
    queryFn: () => apiFetch<Thread[]>("/threads"),
  });
}
