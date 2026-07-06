import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Breadcrumb } from "./Breadcrumb";
import type { components } from "../../lib/api/schema";
type WorkItem = components["schemas"]["WorkItem"];

const baseItem = { id: "NAAF-1", key: "NAAF-1", status: "todo", type: "task", title: "x", priority: "low",
  projectId: "api-service", epicId: "AUTH", createdAt: "", updatedAt: "" } as WorkItem;

describe("Breadcrumb", () => {
  it("renders epic/feature names and the key", () => {
    render(<Breadcrumb item={{ ...baseItem, key: "NAAF-3", epicName: "Auth", featureName: "Login flow" }} />);
    expect(screen.getByText("Auth")).toBeInTheDocument();
    expect(screen.getByText("Login flow")).toBeInTheDocument();
    expect(screen.getByText("NAAF-3")).toBeInTheDocument();
  });
});
