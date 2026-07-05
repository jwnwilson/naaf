import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ItemHeader } from "./ItemHeader";
import type { components } from "../../lib/api/schema";
type WorkItem = components["schemas"]["WorkItem"];

const baseItem = { id: "NAAF-1", key: "NAAF-1", status: "in_progress", type: "task", title: "Add token auth",
  priority: "high", projectId: "p1", epicId: "AUTH", createdAt: "", updatedAt: "" } as WorkItem;
const item = baseItem;

describe("ItemHeader", () => {
  it("renders the title and the status/priority metadata", () => {
    render(<ItemHeader item={item} />);
    expect(screen.getByText("Add token auth")).toBeInTheDocument();
    expect(screen.getByText(/in_progress|in progress/i)).toBeInTheDocument();
    expect(screen.getByText(/high/i)).toBeInTheDocument();
  });

  it("shows the key and lineage names", () => {
    render(<ItemHeader item={{ ...baseItem, key: "NAAF-3", epicName: "Auth", featureName: "Login flow" }} />);
    expect(screen.getByText("NAAF-3")).toBeInTheDocument();
    expect(screen.getByText("Auth")).toBeInTheDocument();
    expect(screen.getByText("Login flow")).toBeInTheDocument();
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
