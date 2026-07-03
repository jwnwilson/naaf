import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type RunOut = components["schemas"]["RunOut"];

export function useStartRun(itemId: string, projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<RunOut>(`/work-items/${itemId}/runs`, {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["work-item-run", itemId] });
      void qc.invalidateQueries({ queryKey: queryKeys.workItem(itemId) });
      void qc.invalidateQueries({ queryKey: queryKeys.board(projectId) });
    },
  });
}
