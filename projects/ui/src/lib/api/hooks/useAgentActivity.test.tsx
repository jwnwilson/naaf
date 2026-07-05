import { describe, expect, it } from "vitest";
import { reduceActivity } from "./useAgentActivity";

describe("reduceActivity", () => {
  it("marks working after a status event with no content yet", () => {
    const s = reduceActivity([{ seq: 1, kind: "status", payload: { state: "working" }, createdAt: "" }]);
    expect(s.isWorking).toBe(true);
    expect(s.textBlocks).toEqual([]);
    expect(s.done).toBe(false);
  });

  it("collects text blocks and tool calls in order", () => {
    const s = reduceActivity([
      { seq: 1, kind: "status", payload: {}, createdAt: "" },
      { seq: 2, kind: "text_block", payload: { text: "Hi" }, createdAt: "" },
      { seq: 3, kind: "tool_call", payload: { name: "list_board" }, createdAt: "" },
    ]);
    expect(s.textBlocks).toEqual(["Hi"]);
    expect(s.toolCalls).toEqual([{ name: "list_board" }]);
  });

  it("clears working and marks done on final", () => {
    const s = reduceActivity([
      { seq: 1, kind: "status", payload: {}, createdAt: "" },
      { seq: 2, kind: "final", payload: { text: "done" }, createdAt: "" },
    ]);
    expect(s.isWorking).toBe(false);
    expect(s.done).toBe(true);
  });

  it("surfaces error kind", () => {
    const s = reduceActivity([{ seq: 1, kind: "error", payload: { message: "boom" }, createdAt: "" }]);
    expect(s.error).toBe("boom");
    expect(s.done).toBe(true);
  });

  it("re-activates isWorking on a new stage's status after a prior final", () => {
    const s = reduceActivity([
      { seq: 1, kind: "status", payload: { state: "working", stage: "plan" }, createdAt: "" },
      { seq: 2, kind: "final", payload: { stage: "plan" }, createdAt: "" },
      { seq: 3, kind: "status", payload: { state: "working", stage: "implement" }, createdAt: "" },
    ]);
    expect(s.isWorking).toBe(true);
    expect(s.done).toBe(false);
  });

  it("attaches tool_result to the last tool call immutably", () => {
    const s = reduceActivity([
      { seq: 1, kind: "tool_call", payload: { name: "search" }, createdAt: "" },
      { seq: 2, kind: "tool_result", payload: { result: "42" }, createdAt: "" },
    ]);
    expect(s.toolCalls).toEqual([{ name: "search", result: "42" }]);
  });
});
