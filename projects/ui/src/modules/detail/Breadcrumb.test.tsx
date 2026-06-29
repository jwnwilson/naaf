import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Breadcrumb } from "./Breadcrumb";
import type { components } from "../../lib/api/schema";
type WorkItem = components["schemas"]["WorkItem"];

const item = { id: "NAAF-1", status: "todo", type: "task", title: "x", priority: "low",
  projectId: "api-service", epicId: "AUTH", createdAt: "", updatedAt: "" } as WorkItem;

describe("Breadcrumb", () => {
  it("renders the project and the item id", () => {
    render(<Breadcrumb item={item} />);
    expect(screen.getByText(/api-service/)).toBeInTheDocument();
    expect(screen.getByText(/NAAF-1/)).toBeInTheDocument();
  });
});
