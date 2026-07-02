import { describe, expect, it } from "vitest";
import * as api from "./index";

describe("api barrel", () => {
  it("re-exports the client, query wiring, and hooks", () => {
    for (const name of ["apiFetch", "apiList", "ApiError", "createQueryClient", "QueryProvider",
      "queryKeys", "useProjects", "useBoard", "useWorkItem", "useDashboard",
      "useAgents", "useBudget", "useAgentDefinitions", "useRun"]) {
      expect(api[name as keyof typeof api]).toBeDefined();
    }
  });
});
