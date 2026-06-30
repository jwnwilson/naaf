import type { components } from "../../lib/api/schema";

export type WorkItem = components["schemas"]["WorkItem"];
export type WorkItemStatus = WorkItem["status"];

export const STATUS_ORDER: WorkItemStatus[] = ["backlog", "todo", "in_progress", "in_review", "done"];

export function groupByStatus(items: WorkItem[]): Record<WorkItemStatus, WorkItem[]> {
  const out = Object.fromEntries(STATUS_ORDER.map((s) => [s, [] as WorkItem[]])) as Record<WorkItemStatus, WorkItem[]>;
  for (const it of items) (out[it.status] ??= []).push(it);
  return out;
}
