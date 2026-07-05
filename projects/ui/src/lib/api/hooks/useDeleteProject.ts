import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiDelete } from "../client";
import { queryKeys } from "../queryKeys";

export function useDeleteProject(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiDelete(`/projects/${id}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.projects() });
    },
  });
}
