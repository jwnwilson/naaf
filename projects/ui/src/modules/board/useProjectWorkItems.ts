import { useQuery } from "@tanstack/react-query";
import { apiList } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";

export type WorkItem = components["schemas"]["WorkItem"];

export function useProjectWorkItems(projectId: string, pollMs?: number) {
  return useQuery({
    queryKey: ["work-items", "project", projectId],
    queryFn: () => apiList<WorkItem>("/work-items", { project: projectId }),
    enabled: Boolean(projectId),
    refetchInterval: pollMs,
  });
}
