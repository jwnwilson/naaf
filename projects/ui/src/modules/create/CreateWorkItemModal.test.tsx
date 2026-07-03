// src/modules/create/CreateWorkItemModal.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, test, vi } from "vitest";
import { server } from "../../lib/api/mocks/server";
import { CreateWorkItemModal } from "./CreateWorkItemModal";

function renderModal(props: Partial<{ initialStatus: "todo"; onClose: () => void }> = {}) {
  const onClose = props.onClose ?? vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // no work items in the project by default
  server.use(
    http.get("/api/work-items", () =>
      HttpResponse.json({ success: true, error: null, data: [], meta: { total: 0, page_size: 50, page_number: 1 } }),
    ),
  );
  render(
    <QueryClientProvider client={qc}>
      <CreateWorkItemModal projectId="p1" initialStatus={props.initialStatus} onClose={onClose} />
    </QueryClientProvider>,
  );
  return { onClose };
}

test("defaults to Task and shows parent feature + epic selects", async () => {
  renderModal();
  expect(screen.getByRole("button", { name: /^create task$/i })).toBeInTheDocument();
  expect(screen.getByLabelText(/parent epic/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/parent feature/i)).toBeInTheDocument();
});

test("switching to Epic hides parent selects", async () => {
  renderModal();
  await userEvent.click(screen.getByRole("button", { name: /^epic$/i }));
  expect(screen.queryByLabelText(/parent epic/i)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^create epic$/i })).toBeInTheDocument();
});

test("title is required before submit", async () => {
  renderModal();
  expect(screen.getByRole("button", { name: /^create task$/i })).toBeDisabled();
  await userEvent.type(screen.getByLabelText(/title/i), "Do it");
  expect(screen.getByRole("button", { name: /^create task$/i })).toBeEnabled();
});

test("creates a work item and closes", async () => {
  server.use(
    http.post("/api/projects/p1/work-items", async ({ request }) => {
      const body = (await request.json()) as { type: string; title: string; status: string };
      expect(body.type).toBe("epic");
      expect(body.status).toBe("todo");
      return HttpResponse.json(
        { success: true, error: null, data: { id: "w9", type: "epic", title: body.title, status: "todo", priority: "medium", projectId: "p1", createdAt: "2026-07-03T00:00:00Z", updatedAt: "2026-07-03T00:00:00Z" } },
        { status: 201 },
      );
    }),
  );
  const { onClose } = renderModal({ initialStatus: "todo" });
  await userEvent.click(screen.getByRole("button", { name: /^epic$/i }));
  await userEvent.type(screen.getByLabelText(/title/i), "Big epic");
  await userEvent.click(screen.getByRole("button", { name: /^create epic$/i }));
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
});

test("Create & add another keeps the modal open and clears the title", async () => {
  server.use(
    http.post("/api/projects/p1/work-items", async () =>
      HttpResponse.json(
        { success: true, error: null, data: { id: "w9", type: "task", title: "t", status: "todo", priority: "medium", projectId: "p1", createdAt: "2026-07-03T00:00:00Z", updatedAt: "2026-07-03T00:00:00Z" } },
        { status: 201 },
      ),
    ),
  );
  const { onClose } = renderModal();
  await userEvent.type(screen.getByLabelText(/title/i), "First");
  await userEvent.click(screen.getByRole("button", { name: /create & add another/i }));
  await waitFor(() => expect((screen.getByLabelText(/title/i) as HTMLInputElement).value).toBe(""));
  expect(onClose).not.toHaveBeenCalled();
});
