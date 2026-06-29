export const queryKeys = {
  projects: () => ["projects"] as const,
  board: (projectId: string) => ["board", projectId] as const,
  workItem: (id: string) => ["work-item", id] as const,
  inbox: (filter?: string) => ["inbox", filter ?? "all"] as const,
  threads: () => ["threads"] as const,
  dashboard: () => ["dashboard"] as const,
  agents: () => ["agents"] as const,
  budget: () => ["budget"] as const,
  agentDefinitions: () => ["agent-definitions"] as const,
  run: (id: string) => ["run", id] as const,
};
