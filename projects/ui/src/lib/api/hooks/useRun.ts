import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiList } from "../client";
import { queryKeys } from "../queryKeys";
import { useEventSource } from "../../hooks/useEventSource";
import type { components } from "../schema";

export type RunOut = components["schemas"]["RunOut"];
export type RunEventOut = components["schemas"]["RunEventOut"];

export function useRun(runId: string): {
  run: RunOut | undefined;
  events: RunEventOut[];
  isStreaming: boolean;
} {
  const runQuery = useQuery({
    queryKey: queryKeys.run(runId),
    queryFn: () => apiFetch<RunOut>(`/runs/${runId}`),
  });
  const historyQuery = useQuery({
    queryKey: queryKeys.runEvents(runId),
    queryFn: () => apiList<RunEventOut>(`/runs/${runId}/events`),
    select: (page) => page.results,
  });

  const history = historyQuery.data ?? [];
  const [streamed, setStreamed] = useState<RunEventOut[]>([]);
  const lastSeq = history.length ? history[history.length - 1].seq : 0;

  useEventSource<RunEventOut>(
    runQuery.data ? `/api/runs/${runId}/events/stream?after=${lastSeq}` : null,
    (ev) => setStreamed((prev) => [...prev, ev]),
  );

  const events = [...history, ...streamed];
  return {
    run: runQuery.data,
    events,
    isStreaming: !!runQuery.data && runQuery.data.status === "running",
  };
}
