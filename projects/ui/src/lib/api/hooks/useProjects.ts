import { useQuery } from "@tanstack/react-query";
import { apiList, type Meta } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type Project = components["schemas"]["Project"];

export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects(),
    queryFn: () => apiList<Project>("/projects"),
  });
}

export type { Meta };
