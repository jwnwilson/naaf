import { expect, test } from "vitest";
import { hasRunFinished } from "./runFinished";

test("returns false when no run_finished event is present", () => {
  expect(hasRunFinished([{ type: "log" }, { type: "stage_passed" }])).toBe(false);
});

test("returns true when a run_finished event is present", () => {
  expect(hasRunFinished([{ type: "log" }, { type: "run_finished" }])).toBe(true);
});

test("returns false for an empty list", () => {
  expect(hasRunFinished([])).toBe(false);
});
