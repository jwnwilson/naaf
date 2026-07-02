import { useQuery } from "@tanstack/react-query";
import { apiList } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type Message = components["schemas"]["Message"];

export function useThreadMessages(threadId?: string) {
  return useQuery({
    queryKey: queryKeys.threadMessages(threadId),
    queryFn: () => apiList<Message>(`/threads/${threadId!}/messages`),
    enabled: Boolean(threadId),
    select: (page) => page.results,
  });
}
