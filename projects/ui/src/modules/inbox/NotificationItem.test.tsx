import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { NotificationItem } from "./NotificationItem";
import type { Thread } from "../../lib/api/hooks";

const thread: Thread = {
  id: "t1",
  workItemId: "w1",
  projectId: "proj-1",
  title: "My Task",
  status: "open",
  lastMessage: "Agent is working on it.",
  messageCount: 2,
  participants: ["agent-1", "user"],
  createdAt: "2026-01-01T00:00:00Z",
};

describe("NotificationItem", () => {
  it("renders title and lastMessage, fires onSelect", async () => {
    const onSelect = vi.fn();
    render(<NotificationItem item={thread} selected={false} onSelect={onSelect} />);
    expect(screen.getByText("My Task")).toBeInTheDocument();
    expect(screen.getByText("Agent is working on it.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button"));
    expect(onSelect).toHaveBeenCalledWith("t1");
  });
});
