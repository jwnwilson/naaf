import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { LogStream } from "./LogStream";

test("renders a log event and a stage_passed token line", () => {
  render(
    <LogStream
      events={[
        {
          id: "e1",
          runId: "r1",
          seq: 1,
          stage: "plan",
          role: "lead",
          type: "log",
          payload: { message: "Reading ticket" },
          createdAt: "2026-07-02T00:00:00Z",
        },
        {
          id: "e2",
          runId: "r1",
          seq: 2,
          stage: "plan",
          role: "lead",
          type: "stage_passed",
          payload: { summary: "ok", tokens: 1050 },
          createdAt: "2026-07-02T00:00:01Z",
        },
      ]}
    />,
  );
  expect(screen.getByText(/Reading ticket/)).toBeInTheDocument();
  expect(screen.getByText(/1050 tok/)).toBeInTheDocument();
});
