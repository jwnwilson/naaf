import { describe, expect, it } from "vitest";
import { threadMessagesPollMs, THREAD_ACTIVE_POLL_MS, THREAD_IDLE_POLL_MS } from "./useThreadMessages";

describe("threadMessagesPollMs", () => {
  it("polls faster while an agent is working", () => {
    expect(threadMessagesPollMs(true)).toBe(THREAD_ACTIVE_POLL_MS);
  });

  it("polls slower when the thread is idle", () => {
    expect(threadMessagesPollMs(false)).toBe(THREAD_IDLE_POLL_MS);
  });

  it("active interval is faster than idle", () => {
    expect(THREAD_ACTIVE_POLL_MS).toBeLessThan(THREAD_IDLE_POLL_MS);
  });
});
