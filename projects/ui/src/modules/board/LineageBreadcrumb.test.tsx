import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LineageBreadcrumb } from "./LineageBreadcrumb";

describe("LineageBreadcrumb", () => {
  it("renders epic › feature when both present", () => {
    render(<LineageBreadcrumb item={{ epicName: "Auth", featureName: "Login flow" }} />);
    expect(screen.getByText("Auth › Login flow")).toBeInTheDocument();
  });

  it("renders only the epic when feature is absent", () => {
    render(<LineageBreadcrumb item={{ epicName: "Auth", featureName: null }} />);
    expect(screen.getByText("Auth")).toBeInTheDocument();
  });

  it("renders nothing when there is no lineage", () => {
    const { container } = render(
      <LineageBreadcrumb item={{ epicName: null, featureName: null }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
