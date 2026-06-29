import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SpecTab } from "./SpecTab";
import type { components } from "../../lib/api/schema";
type WorkItem = components["schemas"]["WorkItem"];

const item = { id: "NAAF-1", status: "todo", type: "task", title: "x", priority: "low",
  projectId: "p1", spec: "# Goal\n\nDo the thing.", tokenUsageThisRun: 12400,
  tokenLimit: 200000, createdAt: "", updatedAt: "" } as WorkItem;

describe("SpecTab", () => {
  it("renders the markdown spec heading and the properties rail", () => {
    render(<SpecTab item={item} />);
    expect(screen.getByRole("heading", { name: /Goal/ })).toBeInTheDocument();
    expect(screen.getByText(/PROPERTIES/i)).toBeInTheDocument();
  });
});
