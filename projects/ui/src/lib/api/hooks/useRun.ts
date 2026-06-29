import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";
import { useEventSource } from "../../hooks/useEventSource";
import type { components } from "../schema";

export type AgentRun = components["schemas"]["AgentRun"];
export type LogLine = components["schemas"]["LogLine"];

export function useRun(runId: string): {
  run: AgentRun | undefined;
  logLines: LogLine[];
  isStreaming: boolean;
} {
  const query = useQuery({
    queryKey: queryKeys.run(runId),
    queryFn: () => apiFetch<AgentRun>(`/runs/${runId}`),
  });

  const [streamed, setStreamed] = useState<LogLine[]>([]);

  useEventSource<LogLine>(
    query.data ? `/api/runs/${runId}/stream` : null,
    (line) => setStreamed((prev) => [...prev, line]),
  );

  const logLines = [...(query.data?.logLines ?? []), ...streamed];

  return {
    run: query.data,
    logLines,
    isStreaming: !!query.data && query.data.status === "running",
  };
}
