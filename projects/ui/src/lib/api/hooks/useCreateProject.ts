import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type ProjectCreate = components["schemas"]["ProjectCreate"];
export type Project = components["schemas"]["Project"];

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectCreate) => apiPost<Project>("/projects", body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.projects() });
    },
  });
}
