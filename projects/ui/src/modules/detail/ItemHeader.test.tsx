import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ItemHeader } from "./ItemHeader";
import type { components } from "../../lib/api/schema";
type WorkItem = components["schemas"]["WorkItem"];

const item = { id: "NAAF-1", status: "in_progress", type: "task", title: "Add token auth",
  priority: "high", projectId: "p1", epicId: "AUTH", createdAt: "", updatedAt: "" } as WorkItem;

describe("ItemHeader", () => {
  it("renders the title and the status/priority metadata", () => {
    render(<ItemHeader item={item} />);
    expect(screen.getByText("Add token auth")).toBeInTheDocument();
    expect(screen.getByText(/in_progress|in progress/i)).toBeInTheDocument();
    expect(screen.getByText(/high/i)).toBeInTheDocument();
  });

  it("does not render an Edit button when onEdit is omitted", () => {
    render(<ItemHeader item={item} />);
    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
  });

  it("calls onEdit when the Edit button is clicked", async () => {
    const onEdit = vi.fn();
    render(<ItemHeader item={item} onEdit={onEdit} />);
    await userEvent.click(screen.getByRole("button", { name: /edit/i }));
    expect(onEdit).toHaveBeenCalledOnce();
  });
});
