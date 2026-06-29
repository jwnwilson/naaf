import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parse } from "yaml";
import { describe, expect, it } from "vitest";

const doc = parse(readFileSync(resolve(__dirname, "naaf-api.yaml"), "utf8"));

describe("OpenAPI contract", () => {
  it("is OpenAPI 3.1 with an envelope-based schema set", () => {
    expect(doc.openapi).toMatch(/^3\.1/);
    expect(doc.components.schemas).toHaveProperty("Envelope");
    expect(doc.components.schemas).toHaveProperty("WorkItem");
    expect(doc.components.schemas).toHaveProperty("Project");
    expect(doc.components.schemas).toHaveProperty("AgentRun");
    expect(doc.components.schemas).toHaveProperty("InboxItem");
  });

  it("defines the core paths every screen needs", () => {
    for (const path of [
      "/projects", "/projects/{id}", "/projects/{id}/board", "/work-items",
      "/work-items/{id}", "/work-items/{id}/transition", "/projects/{id}/work-items",
      "/agents", "/runs/{id}", "/runs/{id}/stream", "/inbox", "/threads",
      "/dashboard/metrics", "/dashboard/token-usage", "/budget",
      "/agent-definitions",
    ]) {
      expect(doc.paths, `missing path ${path}`).toHaveProperty([path]);
    }
  });

  it("uses the UI-canonical work-item status enum", () => {
    expect(doc.components.schemas.WorkItem.properties.status.enum).toEqual(
      ["backlog", "todo", "in_progress", "in_review", "done"],
    );
  });
});
