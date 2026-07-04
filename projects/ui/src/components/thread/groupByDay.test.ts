import { describe, expect, it } from "vitest";
import { groupMessagesByDay } from "./groupByDay";
import type { Message } from "../../lib/api/hooks";

function msg(id: string, createdAt: string): Message {
  return {
    id, threadId: "wi1", authorKind: "agent", authorRole: "lead", model: null,
    kind: "text", content: id, mentions: [], payload: null, runId: null, createdAt,
  };
}

const now = new Date("2026-07-04T09:00:00Z");

describe("groupMessagesByDay", () => {
  it("groups consecutive messages from the same calendar day", () => {
    const groups = groupMessagesByDay(
      [msg("a", "2026-07-03T10:00:00Z"), msg("b", "2026-07-03T18:00:00Z"), msg("c", "2026-07-04T08:00:00Z")],
      now,
    );
    expect(groups).toHaveLength(2);
    expect(groups[0].messages.map((m) => m.id)).toEqual(["a", "b"]);
    expect(groups[1].messages.map((m) => m.id)).toEqual(["c"]);
  });

  it("labels today and yesterday relative to now", () => {
    const groups = groupMessagesByDay(
      [msg("a", "2026-07-03T10:00:00Z"), msg("b", "2026-07-04T08:00:00Z")],
      now,
    );
    expect(groups[0].label).toMatch(/^Yesterday · /);
    expect(groups[1].label).toMatch(/^Today · /);
  });

  it("returns an empty array for no messages", () => {
    expect(groupMessagesByDay([], now)).toEqual([]);
  });
});
