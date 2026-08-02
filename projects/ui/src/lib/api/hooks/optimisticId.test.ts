import { expect, test } from "vitest";
import { makeOptimisticId } from "./optimisticId";

test("makeOptimisticId returns an optimistic-prefixed id", () => {
  expect(makeOptimisticId()).toMatch(/^optimistic-/);
});

test("makeOptimisticId returns a distinct id on every call", () => {
  const a = makeOptimisticId();
  const b = makeOptimisticId();
  expect(a).not.toBe(b);
});
