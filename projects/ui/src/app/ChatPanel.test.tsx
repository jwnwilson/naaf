import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../lib/api/mocks/server";
import { createQueryClient } from "../lib/api/queryClient";
import type { Message } from "../lib/api/hooks";
import { ChatPanel } from "./ChatPanel";

function renderPanel() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <ChatPanel />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function makeMsg(overrides: Partial<Message> = {}): Message {
  return {
    id: "m0",
    threadId: "w1",
    authorKind: "user",
    authorRole: null,
    model: null,
    kind: "text",
    content: "hi",
    mentions: [],
    payload: null,
    runId: null,
    createdAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("ChatPanel", () => {
  beforeEach(() => localStorage.clear());

  it("collapses and re-expands, persisting the state", async () => {
    renderPanel();
    const collapse = await screen.findByRole("button", { name: /collapse/i });
    await userEvent.click(collapse);
    await waitFor(() => expect(screen.getByRole("button", { name: /expand|chat/i })).toBeInTheDocument());
    expect(JSON.parse(localStorage.getItem("naaf.chat.open")!)).toBe(false);
  });

  it("sends a message from the sidebar", async () => {
    const stored: Message[] = [];
    server.use(
      http.get("/api/threads", () =>
        HttpResponse.json({
          success: true,
          data: [
            {
              id: "thread-1",
              workItemId: "w1",
              title: "Test Thread",
              status: "open",
              lastMessage: null,
              messageCount: 0,
              participants: ["user"],
              createdAt: "2026-01-01T00:00:00Z",
            },
          ],
          error: null,
          meta: null,
        }),
      ),
      http.get("/api/threads/w1/messages", () =>
        HttpResponse.json({ success: true, data: stored, error: null, meta: null }),
      ),
      http.post("/api/threads/w1/messages", async ({ request }) => {
        const body = (await request.json()) as { content: string };
        const msg = makeMsg({ id: "m1", content: body.content });
        stored.push(msg);
        return HttpResponse.json({ success: true, data: msg, error: null, meta: null }, { status: 201 });
      }),
    );

    renderPanel();
    const input = await screen.findByPlaceholderText("Message…");
    await userEvent.type(input, "ship it");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(await screen.findByText("ship it")).toBeInTheDocument();
  });

  it("shows the project lead thread when a project is selected on the board", async () => {
    server.use(
      http.get("/api/threads/project:p1/messages", () =>
        HttpResponse.json({
          success: true,
          data: [makeMsg({ id: "lm1", threadId: "project:p1", authorKind: "agent", authorRole: "lead", content: "lead: planning the work" })],
          error: null,
          meta: null,
        }),
      ),
    );
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter initialEntries={["/projects?project=p1"]}>
          <Routes>
            <Route path="/projects" element={<ChatPanel />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Chat with lead")).toBeInTheDocument();
    expect(await screen.findByText("lead: planning the work")).toBeInTheDocument();
  });
});
