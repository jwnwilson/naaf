import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ListRow } from "./ListRow";
import type { components } from "../../lib/api/schema";
type WorkItem = components["schemas"]["WorkItem"];

const item = { id: "NAAF-2", status: "todo", type: "task", title: "Write tests",
  priority: "low", projectId: "p1", createdAt: "", updatedAt: "" } as WorkItem;

describe("ListRow", () => {
  it("shows the title and links to the item", () => {
    render(<MemoryRouter><ListRow item={item} /></MemoryRouter>);
    expect(screen.getByText("Write tests")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/projects/p1/items/NAAF-2");
  });
});
