import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiDelete } from "../client";
import { queryKeys } from "../queryKeys";

export function useDeleteWorkItem(id: string, projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiDelete(`/work-items/${id}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.workItem(id) });
      void qc.invalidateQueries({ queryKey: ["work-items", "project", projectId] });
      void qc.invalidateQueries({ queryKey: queryKeys.board(projectId) });
      void qc.invalidateQueries({ queryKey: queryKeys.projects() });
    },
  });
}
