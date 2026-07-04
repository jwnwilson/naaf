import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiUpload } from "../client";
import { queryKeys } from "../queryKeys";
import type { Attachment } from "./useAttachments";

export function useUploadAttachment(workItemId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, overwrite }: { file: File; overwrite: boolean }) => {
      const form = new FormData();
      form.append("file", file);
      form.append("overwrite", String(overwrite));
      return apiUpload<Attachment>(`/work-items/${workItemId}/attachments`, form);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.attachments(workItemId) });
      void qc.invalidateQueries({ queryKey: queryKeys.workItem(workItemId) });
    },
  });
}
