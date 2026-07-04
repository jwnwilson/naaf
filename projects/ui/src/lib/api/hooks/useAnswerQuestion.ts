import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost } from "../client";
import { queryKeys } from "../queryKeys";
import { invalidateBoardForThread } from "./invalidateBoard";
import type { Message } from "./useThreadMessages";

export function useAnswerQuestion(workItemId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ msgId, option }: { msgId: string; option: string }) =>
      apiPost<Message>(`/threads/${workItemId}/messages/${msgId}/answer`, { option }),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.threadMessages(workItemId) });
      // Approving a lead's run proposal starts runs → statuses change; refresh the board.
      invalidateBoardForThread(qc, workItemId);
    },
  });
}
