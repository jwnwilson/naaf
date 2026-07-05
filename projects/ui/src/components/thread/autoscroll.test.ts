import { describe, expect, it } from "vitest";
import { isNearBottom } from "./autoscroll";

describe("isNearBottom", () => {
  it("is true when scrolled to the very bottom (gap 0)", () => {
    expect(isNearBottom({ scrollTop: 950, scrollHeight: 1000, clientHeight: 50 })).toBe(true);
  });

  it("is true within the default 50px threshold (gap 40)", () => {
    expect(isNearBottom({ scrollTop: 910, scrollHeight: 1000, clientHeight: 50 })).toBe(true);
  });

  it("is false when scrolled up beyond the threshold (gap 850)", () => {
    expect(isNearBottom({ scrollTop: 100, scrollHeight: 1000, clientHeight: 50 })).toBe(false);
  });

  it("is true for a short, non-overflowing list (negative gap)", () => {
    expect(isNearBottom({ scrollTop: 0, scrollHeight: 40, clientHeight: 300 })).toBe(true);
  });

  it("respects a custom threshold", () => {
    // gap = 1000 - 800 - 50 = 150
    expect(isNearBottom({ scrollTop: 800, scrollHeight: 1000, clientHeight: 50 }, 200)).toBe(true);
    expect(isNearBottom({ scrollTop: 800, scrollHeight: 1000, clientHeight: 50 })).toBe(false);
  });
});
