import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../../lib/api/mocks/server";
import type { components } from "../../lib/api/schema";
import { StartRunButton } from "./StartRunButton";

type WorkItem = components["schemas"]["WorkItem"];
type RunOut = components["schemas"]["RunOut"];

const task = {
  id: "w1", type: "task", title: "Add auth", status: "todo", priority: "medium",
  projectId: "p1", createdAt: "", updatedAt: "",
} as WorkItem;

function renderBtn(item: WorkItem, run: RunOut | null = null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <StartRunButton item={item} run={run} />
    </QueryClientProvider>,
  );
}

test("renders an enabled Start run button for a startable task", () => {
  renderBtn(task);
  expect(screen.getByRole("button", { name: /start run/i })).toBeEnabled();
});

test("renders nothing for an epic (not a runnable unit)", () => {
  renderBtn({ ...task, type: "epic" });
  expect(screen.queryByRole("button", { name: /start run/i })).not.toBeInTheDocument();
});

test("is disabled for a non-startable status", () => {
  renderBtn({ ...task, status: "backlog" });
  expect(screen.getByRole("button", { name: /start run/i })).toBeDisabled();
});

test("is disabled when a run is already active", () => {
  const run = { id: "r1", status: "running" } as RunOut;
  renderBtn({ ...task, status: "in_progress" }, run);
  expect(screen.getByRole("button", { name: /start run/i })).toBeDisabled();
});

test("confirms then POSTs and closes the dialog on success", async () => {
  let called = false;
  server.use(
    http.post("/api/work-items/w1/runs", () => {
      called = true;
      return HttpResponse.json(
        { success: true, error: null, data: { id: "r1", workItemId: "w1", projectId: "p1", autonomyLevel: "gated_all", status: "queued", currentStage: null, stages: [], createdAt: "", updatedAt: "", startedAt: null, tokenUsage: 0, cost: 0, prUrl: null } },
        { status: 201 },
      );
    }),
  );
  renderBtn(task);
  await userEvent.click(screen.getByRole("button", { name: /start run/i }));
  const dialog = screen.getByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: /^start run$/i }));
  await waitFor(() => expect(called).toBe(true));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("surfaces an error and keeps the dialog open when start fails", async () => {
  server.use(
    http.post("/api/work-items/w1/runs", () =>
      HttpResponse.json({ success: false, data: null, error: "cannot transition" }, { status: 409 }),
    ),
  );
  renderBtn(task);
  await userEvent.click(screen.getByRole("button", { name: /start run/i }));
  const dialog = screen.getByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: /^start run$/i }));
  await waitFor(() => expect(screen.getByText(/cannot transition/i)).toBeInTheDocument());
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});
