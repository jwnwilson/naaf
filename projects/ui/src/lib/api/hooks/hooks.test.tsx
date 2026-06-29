import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../queryClient";
import { useProjects } from "./useProjects";
import { useBudget } from "./useBudget";

function wrapper() {
  const client = createQueryClient();
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe("resource hooks", () => {
  it("useProjects loads the mock project list", async () => {
    const { result } = renderHook(() => useProjects(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data!.results.length).toBeGreaterThan(0);
  });

  it("useBudget loads the budget", async () => {
    const { result } = renderHook(() => useBudget(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveProperty("limit");
  });
});
