import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type WorkItemCreate = components["schemas"]["WorkItemCreate"];
export type WorkItem = components["schemas"]["WorkItem"];

export function useCreateWorkItem(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WorkItemCreate) =>
      apiPost<WorkItem>(`/projects/${projectId}/work-items`, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["work-items", "project", projectId] });
      void qc.invalidateQueries({ queryKey: queryKeys.board(projectId) });
      void qc.invalidateQueries({ queryKey: queryKeys.projects() });
    },
  });
}
