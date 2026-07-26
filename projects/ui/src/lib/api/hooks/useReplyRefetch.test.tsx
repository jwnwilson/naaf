import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { queryKeys } from "../queryKeys";
import { useReplyRefetch } from "./useReplyRefetch";

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { spy, wrapper };
}

test("invalidates thread messages when done goes false -> true", () => {
  const { spy, wrapper } = setup();
  const { rerender } = renderHook(({ done }) => useReplyRefetch("w1", done), {
    wrapper,
    initialProps: { done: false },
  });
  expect(spy).not.toHaveBeenCalled();

  rerender({ done: true });
  expect(spy).toHaveBeenCalledWith({ queryKey: queryKeys.threadMessages("w1") });
  expect(spy).toHaveBeenCalledTimes(1);
});

test("does not invalidate while done stays true (no repeated edge)", () => {
  const { spy, wrapper } = setup();
  const { rerender } = renderHook(({ done }) => useReplyRefetch("w1", done), {
    wrapper,
    initialProps: { done: true },
  });
  // First render with done=true is the initial mount, not a false->true edge.
  const callsAfterMount = spy.mock.calls.length;
  rerender({ done: true });
  expect(spy.mock.calls.length).toBe(callsAfterMount);
});

test("no-op when workItemId is undefined", () => {
  const { spy, wrapper } = setup();
  const { rerender } = renderHook(({ done }) => useReplyRefetch(undefined, done), {
    wrapper,
    initialProps: { done: false },
  });
  rerender({ done: true });
  expect(spy).not.toHaveBeenCalled();
});
