import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiList } from "../client";
import { queryKeys } from "../queryKeys";
import { useEventSource } from "../../hooks/useEventSource";
import type { components } from "../schema";

export type ActivityEvent = components["schemas"]["ActivityEventOut"];

export interface ActivityState {
  isWorking: boolean;
  textBlocks: string[];
  toolCalls: { name: string; result?: string }[];
  error?: string;
  done: boolean;
}

export function reduceActivity(events: ActivityEvent[]): ActivityState {
  const textBlocks: string[] = [];
  const toolCalls: { name: string; result?: string }[] = [];
  let error: string | undefined;
  let done = false;
  let sawStatus = false;
  for (const ev of events) {
    const p = (ev.payload ?? {}) as Record<string, unknown>;
    if (ev.kind === "status") sawStatus = true;
    else if (ev.kind === "text_block") textBlocks.push(String(p.text ?? ""));
    else if (ev.kind === "tool_call") toolCalls.push({ name: String(p.name ?? "") });
    else if (ev.kind === "tool_result" && toolCalls.length)
      toolCalls[toolCalls.length - 1] = { ...toolCalls[toolCalls.length - 1], result: String(p.result ?? "") };
    else if (ev.kind === "final") done = true;
    else if (ev.kind === "error") { error = String(p.message ?? "error"); done = true; }
  }
  const isWorking = (sawStatus || textBlocks.length > 0 || toolCalls.length > 0) && !done;
  return { isWorking, textBlocks, toolCalls, error, done };
}

function scopePath(scope: { threadId?: string; runId?: string }): string {
  return scope.threadId ? `/threads/${scope.threadId}` : `/runs/${scope.runId}`;
}

export function useAgentActivity(scope: { threadId?: string; runId?: string } | null) {
  const base = scope ? scopePath(scope) : null;
  const key = scope?.threadId
    ? queryKeys.threadActivity(scope.threadId)
    : queryKeys.runActivity(scope?.runId);

  const history = useQuery({
    queryKey: key,
    queryFn: () => apiList<ActivityEvent>(`${base}/activity`),
    enabled: Boolean(base),
    select: (page) => page.results,
  });

  const [streamed, setStreamed] = useState<ActivityEvent[]>([]);
  useEffect(() => { setStreamed([]); }, [base]);

  const hist = history.data ?? [];
  const lastSeq = hist.length ? hist[hist.length - 1].seq : 0;
  useEventSource<ActivityEvent>(
    base ? `/api${base}/activity/stream?after=${lastSeq}` : null,
    (ev) => setStreamed((prev) => [...prev, ev]),
  );

  const bySeq = new Map<number, ActivityEvent>();
  for (const e of [...hist, ...streamed]) bySeq.set(e.seq, e);
  const events = Array.from(bySeq.values()).sort((a, b) => a.seq - b.seq);
  return { events, ...reduceActivity(events) };
}
