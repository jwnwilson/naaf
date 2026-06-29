import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type Budget = components["schemas"]["Budget"];

export function useBudget() {
  return useQuery({
    queryKey: queryKeys.budget(),
    queryFn: () => apiFetch<Budget>("/budget"),
  });
}
