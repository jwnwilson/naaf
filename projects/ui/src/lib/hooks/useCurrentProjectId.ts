// src/lib/hooks/useCurrentProjectId.ts
import { useParams, useSearchParams } from "react-router-dom";
import { useProjects } from "../api/hooks";

export function useCurrentProjectId(): string | undefined {
  const { projectId } = useParams<{ projectId?: string }>();
  const [params] = useSearchParams();
  const { data } = useProjects();
  return projectId ?? params.get("project") ?? data?.results[0]?.id;
}
