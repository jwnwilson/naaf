import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Message } from "../../lib/api/hooks";
import { MessageItem } from "./MessageItem";
import { Thread } from "./Thread";

vi.mock("../../lib/api/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api/hooks")>();
  return {
    ...actual,
    useThreadMessages: vi.fn(),
    useAnswerQuestion: vi.fn(),
  };
});

vi.mock("../../lib/api/hooks/useAgentActivity", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api/hooks/useAgentActivity")>();
  return {
    ...actual,
    useAgentActivity: vi.fn(),
  };
});

vi.mock("./ThreadComposer", () => ({
  ThreadComposer: () => <div data-testid="thread-composer" />,
}));

vi.mock("./ThreadRail", () => ({
  ThreadRail: () => <div data-testid="thread-rail" />,
}));

import * as apiHooks from "../../lib/api/hooks";
import * as activityHook from "../../lib/api/hooks/useAgentActivity";

const IDLE = { isWorking: false, textBlocks: [], toolCalls: [], done: false, events: [] };
const WORKING = { isWorking: true, textBlocks: [], toolCalls: [], done: false, events: [] };

describe("Thread empty-state gate", () => {
  beforeEach(() => {
    vi.mocked(apiHooks.useAnswerQuestion).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as never);
  });

  it("shows 'No messages yet' when idle and no messages", () => {
    vi.mocked(apiHooks.useThreadMessages).mockReturnValue({ data: [], isLoading: false } as never);
    vi.mocked(activityHook.useAgentActivity).mockReturnValue(IDLE as never);
    render(<Thread workItemId="wi-1" />);
    expect(screen.getByText("No messages yet")).toBeInTheDocument();
  });

  it("does NOT show 'No messages yet' when agent is working and no messages yet", () => {
    vi.mocked(apiHooks.useThreadMessages).mockReturnValue({ data: [], isLoading: false } as never);
    vi.mocked(activityHook.useAgentActivity).mockReturnValue(WORKING as never);
    render(<Thread workItemId="wi-1" />);
    expect(screen.queryByText("No messages yet")).not.toBeInTheDocument();
  });
});

function msg(overrides: Partial<Message>): Message {
  return {
    id: "m1",
    threadId: "wi-1",
    authorKind: "agent",
    authorRole: "engineer",
    model: null,
    kind: "text",
    content: "hello",
    mentions: [],
    payload: null,
    runId: null,
    createdAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("MessageItem", () => {
  it("file_write card shows path", () => {
    render(
      <MessageItem
        message={msg({
          kind: "file_write",
          content: "Wrote file",
          payload: { path: "src/foo.ts", lines: 42 },
        })}
      />,
    );
    expect(screen.getByText("src/foo.ts")).toBeInTheDocument();
  });

  it("question renders option buttons", () => {
    render(
      <MessageItem
        message={msg({
          kind: "question",
          content: "Which approach?",
          payload: {
            options: [
              { id: "a", label: "Option A" },
              { id: "b", label: "Option B" },
            ],
          },
        })}
      />,
    );
    expect(screen.getByRole("button", { name: "Option A" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Option B" })).toBeInTheDocument();
  });

  it("marks the chosen option resolved", () => {
    render(
      <MessageItem
        message={msg({
          kind: "question",
          content: "Plan gate",
          payload: {
            options: [
              { id: "approve", label: "Approve" },
              { id: "reject", label: "Reject" },
            ],
            resolved_option: "approve",
          },
        })}
      />,
    );
    const approve = screen.getByRole("button", { name: /Approve/ });
    expect(approve).toBeDisabled();
    expect(screen.getByRole("button", { name: /Reject/ })).toBeDisabled();
  });

  it("calls onAnswer when an option is clicked", () => {
    const onAnswer = vi.fn();
    render(
      <MessageItem
        message={msg({
          id: "q1",
          kind: "question",
          payload: {
            options: [
              { id: "approve", label: "Approve" },
              { id: "reject", label: "Reject" },
            ],
            resolved_option: null,
          },
        })}
        onAnswer={onAnswer}
      />,
    );
    screen.getByRole("button", { name: /Approve/ }).click();
    expect(onAnswer).toHaveBeenCalledWith("q1", "approve");
  });

  it("model badge appears for agent messages", () => {
    render(
      <MessageItem
        message={msg({
          authorKind: "agent",
          model: "claude-sonnet-4-6",
          content: "I am an agent.",
        })}
      />,
    );
    expect(screen.getByText("claude-sonnet-4-6")).toBeInTheDocument();
  });
});
