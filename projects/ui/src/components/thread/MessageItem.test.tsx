import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MessageItem } from "./MessageItem";
import type { Message } from "../../lib/api/hooks";

function msg(overrides: Partial<Message>): Message {
  return {
    id: "m1",
    threadId: "wi1",
    authorKind: "agent",
    authorRole: "backend",
    model: null,
    kind: "text",
    content: "hello",
    mentions: [],
    payload: null,
    runId: null,
    createdAt: "2026-07-03T10:38:04Z",
    ...overrides,
  };
}

describe("MessageItem", () => {
  it("shows the agent display name and model badge in the header", () => {
    render(<MessageItem message={msg({ authorRole: "backend", model: "claude-opus-4" })} />);
    expect(screen.getByText("Backend Engineer")).toBeInTheDocument();
    expect(screen.getByText("claude-opus-4")).toBeInTheDocument();
  });

  it("labels the lead agent and omits a model badge when unknown", () => {
    render(<MessageItem message={msg({ authorRole: "lead", model: null })} />);
    expect(screen.getByText("Lead Agent")).toBeInTheDocument();
    expect(screen.queryByText(/claude/)).not.toBeInTheDocument();
  });

  it("renders a user message as You", () => {
    render(<MessageItem message={msg({ authorKind: "user", authorRole: null, content: "hi" })} />);
    expect(screen.getByText("You")).toBeInTheDocument();
  });

  it("highlights an @mention in the body", () => {
    render(
      <MessageItem
        message={msg({ content: "@lead please review", mentions: ["lead"] })}
      />,
    );
    const mention = screen.getByText("@lead");
    expect(mention.tagName).toBe("SPAN");
    expect(mention.className).toContain("font-mono");
  });
});
