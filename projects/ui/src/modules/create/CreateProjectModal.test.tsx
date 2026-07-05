import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, test, vi } from "vitest";
import { server } from "../../lib/api/mocks/server";
import { CreateProjectModal } from "./CreateProjectModal";

function renderModal(onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <CreateProjectModal onClose={onClose} />
    </QueryClientProvider>,
  );
  return { onClose };
}

test("submit is disabled until a name is entered", async () => {
  renderModal();
  const submit = screen.getByRole("button", { name: /create project/i });
  expect(submit).toBeDisabled();
  await userEvent.type(screen.getByLabelText(/name/i), "Acme");
  expect(submit).toBeEnabled();
});

test("creates a project and closes", async () => {
  server.use(
    http.post("/api/projects", async () =>
      HttpResponse.json(
        { success: true, error: null, data: { id: "p9", name: "Acme", repoUrl: "", itemCount: 0, createdAt: "2026-07-03T00:00:00Z", updatedAt: "2026-07-03T00:00:00Z" } },
        { status: 201 },
      ),
    ),
  );
  const { onClose } = renderModal();
  await userEvent.type(screen.getByLabelText(/name/i), "Acme");
  await userEvent.click(screen.getByRole("button", { name: /create project/i }));
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
});

test("submits the description with the new project", async () => {
  let received: { name: string; description?: string } | null = null;
  server.use(
    http.post("/api/projects", async ({ request }) => {
      received = (await request.json()) as { name: string; description?: string };
      return HttpResponse.json(
        { success: true, error: null, data: { id: "p9", name: received.name, description: received.description ?? "", repoUrl: "", itemCount: 0, createdAt: "2026-07-03T00:00:00Z", updatedAt: "2026-07-03T00:00:00Z" } },
        { status: 201 },
      );
    }),
  );
  renderModal();
  await userEvent.type(screen.getByLabelText(/name/i), "Acme");
  await userEvent.type(screen.getByLabelText(/description/i), "our repo");
  await userEvent.click(screen.getByRole("button", { name: /create project/i }));
  await waitFor(() => expect(received?.description).toBe("our repo"));
});
