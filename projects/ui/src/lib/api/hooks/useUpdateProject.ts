import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPatch } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type ProjectUpdate = components["schemas"]["ProjectUpdate"];
export type Project = components["schemas"]["Project"];

export function useUpdateProject(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectUpdate) => apiPatch<Project>(`/projects/${id}`, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.projects() });
    },
  });
}
