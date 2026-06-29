import { useQuery } from "@tanstack/react-query";
import { apiList } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type InboxItem = components["schemas"]["InboxItem"];

export function useInbox(filter?: string) {
  return useQuery({
    queryKey: queryKeys.inbox(filter),
    queryFn: () => apiList<InboxItem>("/inbox", filter ? { type: filter } : undefined),
  });
}
