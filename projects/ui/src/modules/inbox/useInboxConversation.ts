import { useQuery } from "@tanstack/react-query";
import { apiList } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";

type Message = components["schemas"]["Message"];

export function useInboxConversation(conversationId?: string) {
  return useQuery({
    queryKey: ["threads", conversationId, "messages"],
    queryFn: () => apiList<Message>(`/threads/${conversationId}/messages`),
    enabled: Boolean(conversationId),
  });
}
