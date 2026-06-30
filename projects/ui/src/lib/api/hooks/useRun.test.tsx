import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../queryClient";
import { useRun } from "./useRun";

function wrapper() {
  const client = createQueryClient();
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe("useRun", () => {
  it("loads the run snapshot from the mock", async () => {
    const { result } = renderHook(() => useRun("run-1"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.run).toBeTruthy());
    expect(result.current.run!.steps.length).toBeGreaterThan(0);
  });
});
