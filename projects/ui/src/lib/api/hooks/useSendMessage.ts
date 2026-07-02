import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost } from "../client";
import { queryKeys } from "../queryKeys";
import type { Message } from "./useThreadMessages";

type SendVars = { content: string; agentId?: string | null };

export function useSendMessage(threadId: string) {
  const qc = useQueryClient();
  const key = queryKeys.threadMessages(threadId);
  return useMutation<Message, Error, SendVars, { previous?: { results: Message[] } }>({
    mutationFn: (vars) =>
      apiPost<Message>(`/threads/${threadId}/messages`, {
        content: vars.content,
        agentId: vars.agentId ?? null,
      }),
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<{ results: Message[] }>(key);
      const optimistic: Message = {
        id: `optimistic-${vars.content}`,
        conversationId: threadId,
        role: "user",
        agentId: vars.agentId ?? null,
        content: vars.content,
        attachments: null,
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
    },
  });
}
