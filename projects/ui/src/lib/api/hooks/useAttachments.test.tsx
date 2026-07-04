import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { server } from "../mocks/server";
import * as client from "../client";
import { queryKeys } from "../queryKeys";
import { useAttachments } from "./useAttachments";
import type { Attachment } from "./useAttachments";
import { useUploadAttachment } from "./useUploadAttachment";
import { useDeleteAttachment } from "./useDeleteAttachment";

afterEach(() => vi.restoreAllMocks());

// Each mutation test needs a handle on the QueryClient to assert cache
// invalidation, so build the wrapper + client together.
function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

const sampleAttachment: Attachment = {
  id: "a2",
  filename: "a.txt",
  contentType: "text/plain",
  size: 1,
  url: "/y",
  createdAt: "2026-07-04T00:00:00Z",
};

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
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useAttachments("wi1"), { wrapper });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(result.current.data?.[0].filename).toBe("notes.md");
  });
});

describe("useUploadAttachment", () => {
  // NOTE: jsdom's FormData is not recognized by undici's global fetch, so it
  // serializes to "[object FormData]" and MSW's request.formData() cannot parse
  // it. We therefore assert the FormData the hook builds by spying on apiUpload
  // (the real multipart client helper is covered separately below).
  it("posts file + overwrite to the work-item path, resolves, and invalidates caches", async () => {
    const spy = vi
      .spyOn(client, "apiUpload")
      .mockResolvedValue(sampleAttachment);
    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useUploadAttachment("wi1"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        file: new File(["x"], "a.txt", { type: "text/plain" }),
        overwrite: false,
      });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(spy).toHaveBeenCalledTimes(1);
    const [path, form] = spy.mock.calls[0];
    expect(path).toBe("/work-items/wi1/attachments");
    expect((form.get("file") as File).name).toBe("a.txt");
    expect(form.get("overwrite")).toBe("false");
    expect(result.current.data).toEqual(sampleAttachment);
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: queryKeys.attachments("wi1"),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: queryKeys.workItem("wi1"),
    });
  });
});

describe("useDeleteAttachment", () => {
  it("deletes at the work-item-scoped path, resolves, and invalidates caches", async () => {
    server.use(
      http.delete("/api/work-items/wi1/attachments/att1", () =>
        HttpResponse.json({ success: true, data: { deleted: "att1" }, error: null }),
      ),
    );
    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useDeleteAttachment("wi1"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync("att1");
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.deleted).toBe("att1");
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: queryKeys.attachments("wi1"),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: queryKeys.workItem("wi1"),
    });
  });
});

describe("apiUpload", () => {
  it("unwraps the envelope data on success", async () => {
    server.use(
      http.post("/api/up", () =>
        HttpResponse.json({ success: true, data: { ok: 1 }, error: null }),
      ),
    );
    const res = await client.apiUpload<{ ok: number }>("/up", new FormData());
    expect(res).toEqual({ ok: 1 });
  });

  it("throws ApiError carrying the envelope error on failure", async () => {
    server.use(
      http.post("/api/up", () =>
        HttpResponse.json({ success: false, data: null, error: "boom" }, { status: 400 }),
      ),
    );
    await expect(client.apiUpload("/up", new FormData())).rejects.toThrow("boom");
  });

  it("throws ApiError when the response body is not JSON", async () => {
    server.use(
      http.post("/api/up", () => new HttpResponse("<html>502</html>", { status: 502 })),
    );
    await expect(client.apiUpload("/up", new FormData())).rejects.toThrow(
      client.ApiError,
    );
  });
});
