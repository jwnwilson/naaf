import { expect, test } from "@playwright/test";
import {
  CHAT_TEXT_PLAN,
  STAGE_TEXT_DONE,
  STAGE_TEXT_SCAN,
  TASK_TITLE,
} from "./fixtures/scripted";

const REAL = process.env.NAAF_E2E_REAL === "1";

test("chat → lead creates a task → run streams multi-stage output", async ({ page }) => {
  // ── 1. Create a project with full_auto autonomy (no gates) via the API ──────
  const res = await page.request.post("http://localhost:8000/projects", {
    data: { name: "E2E Project", autonomyLevel: "full_auto" },
  });
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  const projectId: string = body.data.id;

  // ── 2. Navigate to the project board (ChatPanel shows project lead thread) ──
  await page.goto(`/projects?project=${projectId}`);
  // Ensure the board has loaded (sidebar shows the project name)
  await expect(page.getByText("E2E Project").first()).toBeVisible({ timeout: 10_000 });

  // ── 3. Send a message to the lead in the project chat panel ─────────────────
  await page.getByTestId("thread-composer-input").fill("Build a notes feature");
  await page.getByTestId("thread-composer-send").click();

  // ── 4. Lead streams its planning text (activity-feed shows while working) ───
  await expect(page.getByTestId("activity-feed")).toContainText(CHAT_TEXT_PLAN, {
    timeout: 20_000,
  });

  // ── 5. Lead creates the task — poll API until the task exists in the DB ─────
  await expect
    .poll(
      async () => {
        const r = await page.request.get(
          `http://localhost:8000/work-items?project=${projectId}`,
        );
        if (!r.ok()) return false;
        const json = await r.json();
        const items: Array<{ title: string }> = json.data?.results ?? json.data ?? [];
        return items.some((i) => i.title === TASK_TITLE);
      },
      { timeout: 40_000, intervals: [1_000] },
    )
    .toBe(true);

  // Board polls every 5s; wait for the task card to appear
  await expect(page.getByText(TASK_TITLE)).toBeVisible({ timeout: 15_000 });

  // ── 6. Open the task detail page ─────────────────────────────────────────────
  await page.getByText(TASK_TITLE).click();
  // Breadcrumb or item header confirms we are on the detail page
  await expect(page.getByText(TASK_TITLE).first()).toBeVisible({ timeout: 10_000 });

  // ── 7. Start a run (triggers modal; confirm to launch) ───────────────────────
  await page.getByTestId("start-run-button").click();
  await expect(page.getByTestId("start-run-confirm")).toBeVisible({ timeout: 5_000 });
  await page.getByTestId("start-run-confirm").click();

  // ── 8. Switch to the Agent tab to open the run monitor ───────────────────────
  await page.getByRole("button", { name: "Agent" }).click();

  // ── 9. Run streams stage texts into the agent monitor's activity feed ────────
  // The scripted adapter emits STAGE_TEXT_SCAN then STAGE_TEXT_DONE for each
  // stage (PLAN / IMPLEMENT / VERIFY). With full_auto there are no gates so the
  // pipeline advances automatically. The activity-feed accumulates all text
  // blocks across stages while isWorking=true.
  const monitor = page.getByTestId("agent-monitor");
  await expect(monitor.getByTestId("activity-feed")).toContainText(STAGE_TEXT_SCAN, {
    timeout: 30_000,
  });
  await expect(monitor.getByTestId("activity-feed")).toContainText(STAGE_TEXT_DONE, {
    timeout: 30_000,
  });

  // ── 10. Run advances through stages — assert verify (or later) is reached ────
  // run-status renders "{status} · {currentStage} · {startedAt}".
  // We match stage names only (verify/pr/learn) — never "failed", which can
  // appear in the status field even before verify, and never the dead
  // alternatives "done"/"complete" which match no real RunStatus or RunStage.
  // PR/LEARN may error without a real repo; that is expected and out of scope.
  await expect(page.getByTestId("run-status")).toContainText(
    /verify|pr|learn/i,
    { timeout: 45_000 },
  );
});

// ── @real smoke: run against a live Claude CLI subscription ──────────────────
// Guarded by NAAF_E2E_REAL=1. Assertions are deliberately loose — real LLM
// output varies, so we only verify observable side-effects: a task was created
// and the activity feed received content.
// Run with: make e2e-real  (boots with naaf_llm_provider=claude_cli)
test.describe("@real real-claude smoke", () => {
  test.skip(!REAL, "set NAAF_E2E_REAL=1 with naaf_llm_provider=claude_cli to run");

  test("a task is created and some output streams (loose assertions)", async ({
    page,
  }) => {
    // ── 1. Create a project with full_auto autonomy (no gates) ───────────────
    const res = await page.request.post("http://localhost:8000/projects", {
      data: { name: "Real E2E Project", autonomyLevel: "full_auto" },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    const projectId: string = body.data.id;

    // ── 2. Navigate to the board ─────────────────────────────────────────────
    await page.goto(`/projects?project=${projectId}`);
    await expect(page.getByText("Real E2E Project").first()).toBeVisible({
      timeout: 10_000,
    });

    // ── 3. Send a message to the lead ────────────────────────────────────────
    await page.getByTestId("thread-composer-input").fill("Build a notes feature");
    await page.getByTestId("thread-composer-send").click();

    // ── 4. Activity feed receives content (no exact-string check) ────────────
    await expect(page.getByTestId("activity-feed")).not.toBeEmpty({
      timeout: 30_000,
    });

    // ── 5. At least one work item was created ─────────────────────────────────
    await expect
      .poll(
        async () => {
          const r = await page.request.get(
            `http://localhost:8000/work-items?project=${projectId}`,
          );
          if (!r.ok()) return false;
          const json = await r.json();
          const items: Array<unknown> = json.data?.results ?? json.data ?? [];
          return items.length > 0;
        },
        { timeout: 60_000, intervals: [2_000] },
      )
      .toBe(true);
  });
});
