import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPatch } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type WorkItemUpdate = components["schemas"]["WorkItemUpdate"];
export type WorkItem = components["schemas"]["WorkItem"];

export function useUpdateWorkItem(id: string, projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WorkItemUpdate) => apiPatch<WorkItem>(`/work-items/${id}`, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.workItem(id) });
      void qc.invalidateQueries({ queryKey: ["work-items", "project", projectId] });
      void qc.invalidateQueries({ queryKey: queryKeys.board(projectId) });
      void qc.invalidateQueries({ queryKey: queryKeys.projects() });
    },
  });
}
