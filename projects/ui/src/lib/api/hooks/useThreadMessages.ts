import { useQuery } from "@tanstack/react-query";
import { apiList } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type Message = components["schemas"]["Message"];

export function useThreadMessages(workItemId?: string) {
  return useQuery({
    queryKey: queryKeys.threadMessages(workItemId),
    queryFn: () => apiList<Message>(`/threads/${workItemId!}/messages`),
    enabled: Boolean(workItemId),
    select: (page) => page.results,
  });
}
