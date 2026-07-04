import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "../../lib/api/mocks/server";
import { AttachmentsPanel } from "./AttachmentsPanel";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const att = (filename: string) => ({
  id: `id-${filename}`,
  filename,
  contentType: "text/markdown",
  size: 3,
  url: `/work-items/wi1/attachments/id-${filename}`,
  createdAt: "2026-07-04T00:00:00Z",
});

describe("AttachmentsPanel", () => {
  it("renders the attachment list", async () => {
    server.use(
      http.get("/api/work-items/wi1/attachments", () =>
        HttpResponse.json({ success: true, data: [att("notes.md")], error: null }),
      ),
    );
    render(<AttachmentsPanel workItemId="wi1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("notes.md")).toBeInTheDocument());
  });

  it("warns before overwriting and does NOT upload when the user declines", async () => {
    const uploadSpy = vi.fn();
    server.use(
      http.get("/api/work-items/wi1/attachments", () =>
        HttpResponse.json({ success: true, data: [att("notes.md")], error: null }),
      ),
      http.post("/api/work-items/wi1/attachments", () => {
        uploadSpy();
        return HttpResponse.json({ success: true, data: att("notes.md"), error: null });
      }),
    );
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<AttachmentsPanel workItemId="wi1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("notes.md")).toBeInTheDocument());

    const input = screen.getByTestId("attachment-input") as HTMLInputElement;
    const file = new File(["new"], "notes.md", { type: "text/markdown" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() =>
      expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining("notes.md")),
    );
    // Declined confirm ⇒ no upload POST should ever fire.
    expect(uploadSpy).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
