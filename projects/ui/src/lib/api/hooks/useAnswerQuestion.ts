import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost } from "../client";
import { queryKeys } from "../queryKeys";
import type { Message } from "./useThreadMessages";

export function useAnswerQuestion(workItemId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ msgId, option }: { msgId: string; option: string }) =>
      apiPost<Message>(`/threads/${workItemId}/messages/${msgId}/answer`, { option }),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.threadMessages(workItemId) });
    },
  });
}
