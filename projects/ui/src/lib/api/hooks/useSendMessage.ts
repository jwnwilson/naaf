import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost } from "../client";
import { queryKeys } from "../queryKeys";
import { invalidateBoardForThread } from "./invalidateBoard";
import type { Message } from "./useThreadMessages";

type SendVars = { content: string };

export function useSendMessage(workItemId: string) {
  const qc = useQueryClient();
  const key = queryKeys.threadMessages(workItemId);
  return useMutation<Message, Error, SendVars, { previous?: { results: Message[] } }>({
    mutationFn: (vars) =>
      apiPost<Message>(`/threads/${workItemId}/messages`, { content: vars.content }),
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<{ results: Message[] }>(key);
      const optimistic: Message = {
        id: `optimistic-${vars.content}`,
        threadId: workItemId,
        authorKind: "user",
        authorRole: null,
        model: null,
        kind: "text",
        content: vars.content,
        mentions: [],
        payload: null,
        runId: null,
        createdAt: new Date().toISOString(),
      };
      qc.setQueryData<{ results: Message[]; meta?: unknown }>(key, (old) =>
        old
          ? { ...old, results: [...old.results, optimistic] }
          : { results: [optimistic], meta: { total: 1, page_size: 50, page_number: 1 } },
      );
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(key, ctx.previous);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: key });
      void qc.invalidateQueries({ queryKey: queryKeys.thread(workItemId) });
      void qc.invalidateQueries({ queryKey: queryKeys.threads() });
      // Lead (project) thread: created work items should appear on the board.
      invalidateBoardForThread(qc, workItemId);
    },
  });
}
