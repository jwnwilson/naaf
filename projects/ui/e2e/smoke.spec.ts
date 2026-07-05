import { expect, test } from "@playwright/test";

test("the UI shell loads against the live stack", async ({ page }) => {
  await page.goto("/");
  // The app shell renders a sidebar with PROJECTS; assert something stable is visible.
  await expect(page.getByText(/projects/i).first()).toBeVisible();
});
