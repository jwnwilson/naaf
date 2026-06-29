import { describe, expect, it } from "vitest";
import { groupByStatus, STATUS_ORDER } from "./groupByStatus";
import type { components } from "../../lib/api/schema";
type WorkItem = components["schemas"]["WorkItem"];

const item = (id: string, status: WorkItem["status"]): WorkItem =>
  ({ id, status, type: "task", title: id, priority: "medium", projectId: "p1",
     createdAt: "", updatedAt: "" } as WorkItem);

describe("groupByStatus", () => {
  it("buckets items and always has all five status keys", () => {
    const g = groupByStatus([item("a", "todo"), item("b", "todo"), item("c", "done")]);
    expect(STATUS_ORDER).toEqual(["backlog", "todo", "in_progress", "in_review", "done"]);
    expect(g.todo.map((i) => i.id)).toEqual(["a", "b"]);
    expect(g.done).toHaveLength(1);
    expect(g.backlog).toEqual([]);
  });
});
