import { useQuery } from "@tanstack/react-query";
import { apiList } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type Message = components["schemas"]["Message"];

// Agents write messages into a thread server-side, which never invalidates
// client queries. Poll while the thread is open so replies appear live —
// faster while an agent is actively working, slower when idle. Paused
// automatically when the tab is hidden (refetchIntervalInBackground default).
export const THREAD_ACTIVE_POLL_MS = 1500;
export const THREAD_IDLE_POLL_MS = 5000;

export function threadMessagesPollMs(active: boolean): number {
  return active ? THREAD_ACTIVE_POLL_MS : THREAD_IDLE_POLL_MS;
}

export function useThreadMessages(workItemId?: string, active = false) {
  return useQuery({
    queryKey: queryKeys.threadMessages(workItemId),
    queryFn: () => apiList<Message>(`/threads/${workItemId!}/messages`),
    enabled: Boolean(workItemId),
    select: (page) => page.results,
    refetchInterval: threadMessagesPollMs(active),
  });
}
