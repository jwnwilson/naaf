import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ListRow } from "./ListRow";
import type { components } from "../../lib/api/schema";
type WorkItem = components["schemas"]["WorkItem"];

const item = { id: "id-2", key: "NAAF-4", status: "todo", type: "task", title: "Write tests",
  priority: "low", projectId: "p1", epicName: "Auth", featureName: "Login flow",
  createdAt: "", updatedAt: "" } as WorkItem;

describe("ListRow", () => {
  it("shows the key, title, and lineage breadcrumb, and links to the item", () => {
    render(<MemoryRouter><ListRow item={item} /></MemoryRouter>);
    expect(screen.getByText("NAAF-4")).toBeInTheDocument();
    expect(screen.getByText("Write tests")).toBeInTheDocument();
    expect(screen.getByText("Auth › Login flow")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/projects/p1/items/id-2");
  });
});
