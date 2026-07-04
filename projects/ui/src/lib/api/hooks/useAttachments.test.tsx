import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../mocks/server";
import { useAttachments } from "./useAttachments";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useAttachments", () => {
  it("lists attachments for a work item", async () => {
    server.use(
      http.get("/api/work-items/wi1/attachments", () =>
        HttpResponse.json({
          success: true,
          data: [
            {
              id: "a1",
              filename: "notes.md",
              contentType: "text/markdown",
              size: 4,
              url: "/x",
              createdAt: "2026-07-04T00:00:00Z",
            },
          ],
          error: null,
        }),
      ),
    );
    const { result } = renderHook(() => useAttachments("wi1"), { wrapper });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(result.current.data?.[0].filename).toBe("notes.md");
  });
});
