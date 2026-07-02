import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../lib/api/mocks/server";
import { createQueryClient } from "../lib/api/queryClient";
import type { Message } from "../lib/api/hooks";
import { ChatPanel } from "./ChatPanel";

function renderPanel() {
  render(
    <QueryClientProvider client={createQueryClient()}><ChatPanel /></QueryClientProvider>,
  );
}

describe("ChatPanel", () => {
  beforeEach(() => localStorage.clear());

  it("collapses and re-expands, persisting the state", async () => {
    renderPanel();
    // open by default: the collapse control is present
    const collapse = await screen.findByRole("button", { name: /collapse/i });
    await userEvent.click(collapse);
    // collapsed strip shows the CHAT label and an expand control
    await waitFor(() => expect(screen.getByRole("button", { name: /expand|chat/i })).toBeInTheDocument());
    expect(JSON.parse(localStorage.getItem("naaf.chat.open")!)).toBe(false);
  });

  it("sends a message from the sidebar", async () => {
    // Per-test handlers: thread r1 with empty message list that persists POSTs
    const stored: Message[] = [];
    server.use(
      http.get("/api/threads", () =>
        HttpResponse.json({
          success: true,
          data: [{ id: "r1", agentId: "lead", workItemId: "w1", createdAt: "2026-01-01T00:00:00Z" }],
          error: null,
          meta: null,
        }),
      ),
      http.get("/api/threads/r1/messages", () =>
        HttpResponse.json({ success: true, data: stored, error: null, meta: null }),
      ),
      http.post("/api/threads/r1/messages", async ({ request }) => {
        const body = (await request.json()) as { content: string };
        const msg: Message = {
          id: "m1",
          conversationId: "r1",
          role: "user",
          agentId: null,
          content: body.content,
          attachments: null,
          createdAt: new Date().toISOString(),
        };
        stored.push(msg);
        return HttpResponse.json({ success: true, data: msg, error: null, meta: null }, { status: 201 });
      }),
    );

    renderPanel();
    const input = await screen.findByPlaceholderText("Message…");
    await userEvent.type(input, "ship it");
    await userEvent.click(screen.getByLabelText("send"));
    expect(await screen.findByText("ship it")).toBeInTheDocument();
  });
});
