import { QueryClient } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";
import { projectThreadId } from "../../threadScope";
import { invalidateBoardForThread } from "./invalidateBoard";

test("invalidates the board + work-items + projects for a project thread", () => {
  const qc = new QueryClient();
  const spy = vi.spyOn(qc, "invalidateQueries");
  invalidateBoardForThread(qc, projectThreadId("p1"));
  const keys = spy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
  expect(keys).toContain(JSON.stringify(["board", "p1"]));
  expect(keys).toContain(JSON.stringify(["work-items", "project", "p1"]));
  expect(keys).toContain(JSON.stringify(["projects"]));
});

test("does nothing for a work-item thread", () => {
  const qc = new QueryClient();
  const spy = vi.spyOn(qc, "invalidateQueries");
  invalidateBoardForThread(qc, "wi-task-1");
  expect(spy).not.toHaveBeenCalled();
});
