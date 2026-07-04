import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";

export function useDeleteAttachment(workItemId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (attachmentId: string) =>
      apiFetch<{ deleted: string }>(
        `/work-items/${workItemId}/attachments/${attachmentId}`,
        { method: "DELETE" },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.attachments(workItemId) });
      void qc.invalidateQueries({ queryKey: queryKeys.workItem(workItemId) });
    },
  });
}
