import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { NotificationItem } from "./NotificationItem";
import type { Thread } from "../../lib/api/hooks";

const thread: Thread = {
  id: "t1",
  agentId: "lead",
  workItemId: "w1",
  createdAt: "2026-01-01T00:00:00Z",
};

describe("NotificationItem", () => {
  it("renders agentId as title and workItemId as sub-label, fires onSelect", async () => {
    const onSelect = vi.fn();
    render(<NotificationItem item={thread} selected={false} onSelect={onSelect} />);
    expect(screen.getByText("lead")).toBeInTheDocument();
    expect(screen.getByText("w1")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button"));
    expect(onSelect).toHaveBeenCalledWith("t1");
  });
});
