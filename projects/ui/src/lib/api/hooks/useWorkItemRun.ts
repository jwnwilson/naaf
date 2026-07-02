import { useQuery } from "@tanstack/react-query";
import { apiList } from "../client";
import type { components } from "../schema";

export type RunOut = components["schemas"]["RunOut"];

export function useWorkItemRun(itemId: string) {
  return useQuery({
    queryKey: ["work-item-run", itemId],
    queryFn: async (): Promise<RunOut | null> => {
      const { results } = await apiList<RunOut>("/runs", { work_item: itemId });
      return results[0] ?? null;
    },
    enabled: Boolean(itemId),
  });
}
