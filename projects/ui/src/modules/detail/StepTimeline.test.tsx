import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { StepTimeline } from "./StepTimeline";

test("renders one node per stage with its label", () => {
  render(
    <StepTimeline
      stages={[
        { stage: "plan", status: "passed", role: "lead", startedAt: null, endedAt: null },
        { stage: "implement", status: "running", role: "backend", startedAt: null, endedAt: null },
      ]}
    />,
  );
  expect(screen.getByText("plan")).toBeInTheDocument();
  expect(screen.getByText("implement")).toBeInTheDocument();
});
