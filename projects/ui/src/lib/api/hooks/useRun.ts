import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiList } from "../client";
import { queryKeys } from "../queryKeys";
import { useEventSource } from "../../hooks/useEventSource";
import type { components } from "../schema";

export type RunOut = components["schemas"]["RunOut"];
export type RunEventOut = components["schemas"]["RunEventOut"];

/** Merge history and streamed events, deduplicating by seq, in ascending seq order. */
export function mergeEventsBySeq(
  history: RunEventOut[],
  streamed: RunEventOut[],
): RunEventOut[] {
  const bySeq = new Map<number, RunEventOut>();
  for (const ev of history) bySeq.set(ev.seq, ev);
  for (const ev of streamed) bySeq.set(ev.seq, ev);
  return Array.from(bySeq.values()).sort((a, b) => a.seq - b.seq);
}

export function useRun(runId: string): {
  run: RunOut | undefined;
  events: RunEventOut[];
  isStreaming: boolean;
} {
  const TERMINAL_STATUSES = ["succeeded", "failed", "cancelled"] as const;

  const runQuery = useQuery({
    queryKey: queryKeys.run(runId),
    queryFn: () => apiFetch<RunOut>(`/runs/${runId}`),
    refetchInterval: (query) => {
      const run = query.state.data as RunOut | undefined;
      return run && TERMINAL_STATUSES.includes(run.status as typeof TERMINAL_STATUSES[number])
        ? false
        : 2_000;
    },
  });
  const historyQuery = useQuery({
    queryKey: queryKeys.runEvents(runId),
    queryFn: () => apiList<RunEventOut>(`/runs/${runId}/events`),
    select: (page) => page.results,
  });

  const history = historyQuery.data ?? [];
  const [streamed, setStreamed] = useState<RunEventOut[]>([]);

  useEffect(() => {
    setStreamed([]);
  }, [runId]);

  const lastSeq = history.length ? history[history.length - 1].seq : 0;

  useEventSource<RunEventOut>(
    runQuery.data ? `/api/runs/${runId}/events/stream?after=${lastSeq}` : null,
    (ev) => setStreamed((prev) => [...prev, ev]),
  );

  const events = mergeEventsBySeq(history, streamed);
  return {
    run: runQuery.data,
    events,
    isStreaming: !!runQuery.data && runQuery.data.status === "running",
  };
}
