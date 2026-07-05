import { createContext, useContext } from "react";
import type { Project } from "../../lib/api/hooks/useProjects";
import type { WorkItem } from "../../lib/api/hooks/useCreateWorkItem";

export interface CreateModalContextValue {
  openCreateProject: () => void;
  openCreateWorkItem: (o: { projectId: string; status?: WorkItem["status"] }) => void;
  openEditWorkItem: (item: WorkItem) => void;
  openEditProject: (project: Project) => void;
  close: () => void;
}

export const CreateModalContext = createContext<CreateModalContextValue | null>(null);

export function useCreateModal(): CreateModalContextValue {
  const ctx = useContext(CreateModalContext);
  if (!ctx) throw new Error("useCreateModal must be used within CreateModalProvider");
  return ctx;
}
