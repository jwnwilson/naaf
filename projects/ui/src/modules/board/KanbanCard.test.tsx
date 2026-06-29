import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { KanbanCard } from "./KanbanCard";
import type { components } from "../../lib/api/schema";
type WorkItem = components["schemas"]["WorkItem"];

const item = { id: "NAAF-1", status: "in_progress", type: "task", title: "Add auth",
  priority: "high", projectId: "p1", epicId: "e1", createdAt: "", updatedAt: "" } as WorkItem;

describe("KanbanCard", () => {
  it("shows the id and title and links to the item", () => {
    render(<MemoryRouter><KanbanCard item={item} /></MemoryRouter>);
    expect(screen.getByText("Add auth")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/projects/p1/items/NAAF-1");
  });
});
