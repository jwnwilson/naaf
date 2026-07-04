import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";

export type Attachment = {
  id: string;
  filename: string;
  contentType: string;
  size: number;
  url: string;
  createdAt: string;
};

export function useAttachments(workItemId: string) {
  return useQuery({
    queryKey: queryKeys.attachments(workItemId),
    queryFn: () => apiFetch<Attachment[]>(`/work-items/${workItemId}/attachments`),
    enabled: Boolean(workItemId),
  });
}
