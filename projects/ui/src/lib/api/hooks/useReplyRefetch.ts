import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../queryKeys";

/**
 * Refetch a thread's messages the instant an agent turn finishes.
 *
 * `done` comes from `useAgentActivity` (true after a `final`/`error` event).
 * The activity stream reports completion ~immediately, but the agent's reply
 * message only appears on the next `useThreadMessages` poll. Invalidating on
 * the false->true edge surfaces the reply in one round-trip instead of ~2s.
 */
export function useReplyRefetch(workItemId: string | undefined, done: boolean): void {
  const qc = useQueryClient();
  const prevDone = useRef(done);
  useEffect(() => {
    if (done && !prevDone.current && workItemId) {
      void qc.invalidateQueries({ queryKey: queryKeys.threadMessages(workItemId) });
    }
    prevDone.current = done;
  }, [done, workItemId, qc]);
}
