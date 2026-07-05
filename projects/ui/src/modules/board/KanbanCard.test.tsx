import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { KanbanCard } from "./KanbanCard";
import type { components } from "../../lib/api/schema";
type WorkItem = components["schemas"]["WorkItem"];

const item = { id: "id-1", key: "NAAF-3", status: "in_progress", type: "task", title: "Add auth",
  priority: "high", projectId: "p1", epicId: "e1", epicName: "Auth", featureId: "f1",
  featureName: "Login flow", createdAt: "", updatedAt: "" } as WorkItem;

describe("KanbanCard", () => {
  it("shows the key, title, and lineage breadcrumb, and links to the item", () => {
    render(<MemoryRouter><KanbanCard item={item} /></MemoryRouter>);
    expect(screen.getByText("NAAF-3")).toBeInTheDocument();
    expect(screen.getByText("Add auth")).toBeInTheDocument();
    expect(screen.getByText("Auth › Login flow")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/projects/p1/items/id-1");
  });
});
