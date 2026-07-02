import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, test } from "vitest";
import { server } from "../mocks/server";
import { createQueryClient } from "../queryClient";
import { mergeEventsBySeq, useRun } from "./useRun";
import type { RunEventOut } from "./useRun";

function wrapper() {
  const client = createQueryClient();
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe("useRun", () => {
  it("loads the run snapshot and returns run with events shape", async () => {
    server.use(
      http.get("/api/runs/run-1", () =>
        HttpResponse.json({
          success: true,
          error: null,
          data: {
            id: "run-1",
            workItemId: "wi-task-3",
            projectId: "p1",
            autonomyLevel: "full_auto",
            status: "running",
            currentStage: "plan",
            stages: [],
            pendingGate: null,
            createdAt: "2026-07-02T00:00:00Z",
            updatedAt: "2026-07-02T00:00:00Z",
            startedAt: null,
            endedAt: null,
            tokenUsage: 500,
            cost: 0.0015,
          },
        }),
      ),
      http.get("/api/runs/run-1/events", () =>
        HttpResponse.json({ success: true, error: null, data: [] }),
      ),
    );
    const { result } = renderHook(() => useRun("run-1"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.run).toBeTruthy());
    expect(result.current.run!.tokenUsage).toBe(500);
    expect(result.current.events).toEqual([]);
    expect(result.current.isStreaming).toBe(true);
  });
});

describe("mergeEventsBySeq", () => {
  function makeEvent(seq: number): RunEventOut {
    return {
      id: `e${seq}`,
      runId: "r1",
      seq,
      stage: "plan",
      role: "lead",
      type: "log",
      payload: { message: `event ${seq}` },
      createdAt: "2026-07-02T00:00:00Z",
    };
  }

  it("deduplicates overlapping seq values and returns ascending order", () => {
    // Arrange: history has seq 1 and 2; streamed overlaps seq 2 and adds seq 3
    const history = [makeEvent(1), makeEvent(2)];
    const streamed = [makeEvent(2), makeEvent(3)];

    // Act
    const result = mergeEventsBySeq(history, streamed);

    // Assert: exactly 3 entries, no duplicate seq 2, ascending order
    expect(result).toHaveLength(3);
    expect(result.map((e) => e.seq)).toEqual([1, 2, 3]);
  });

  it("returns history-only events when streamed is empty", () => {
    const history = [makeEvent(1), makeEvent(2)];
    const result = mergeEventsBySeq(history, []);
    expect(result).toHaveLength(2);
    expect(result.map((e) => e.seq)).toEqual([1, 2]);
  });

  it("returns streamed-only events when history is empty", () => {
    const streamed = [makeEvent(3), makeEvent(1), makeEvent(2)];
    const result = mergeEventsBySeq([], streamed);
    expect(result).toHaveLength(3);
    expect(result.map((e) => e.seq)).toEqual([1, 2, 3]);
  });
});

test("useRun returns the run and its event history", async () => {
  server.use(
    http.get("/api/runs/r1", () =>
      HttpResponse.json({
        success: true,
        error: null,
        data: {
          id: "r1",
          workItemId: "w1",
          projectId: "p1",
          autonomyLevel: "full_auto",
          status: "running",
          currentStage: "plan",
          stages: [],
          pendingGate: null,
          createdAt: "2026-07-02T00:00:00Z",
          updatedAt: "2026-07-02T00:00:00Z",
          startedAt: null,
          endedAt: null,
          tokenUsage: 700,
          cost: 0.0021,
        },
      }),
    ),
    http.get("/api/runs/r1/events", () =>
      HttpResponse.json({
        success: true,
        error: null,
        data: [
          {
            id: "e1",
            runId: "r1",
            seq: 1,
            stage: "plan",
            role: "lead",
            type: "log",
            payload: { message: "hi" },
            createdAt: "2026-07-02T00:00:00Z",
          },
        ],
      }),
    ),
  );
  const { result } = renderHook(() => useRun("r1"), { wrapper: wrapper() });
  await waitFor(() => expect(result.current.run?.tokenUsage).toBe(700));
  await waitFor(() => expect(result.current.events).toHaveLength(1));
});
