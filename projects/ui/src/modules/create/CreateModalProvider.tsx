import { useMemo, useState, type ReactNode } from "react";
import type { WorkItem } from "../../lib/api/hooks/useCreateWorkItem";
import { CreateProjectModal } from "./CreateProjectModal";
import { CreateWorkItemModal } from "./CreateWorkItemModal";
import { EditWorkItemModal } from "./EditWorkItemModal";
import { CreateModalContext } from "./useCreateModal";

type State =
  | { kind: "none" }
  | { kind: "project" }
  | { kind: "work-item"; projectId: string; status?: WorkItem["status"] }
  | { kind: "edit-work-item"; item: WorkItem };

export function CreateModalProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ kind: "none" });

  const value = useMemo(
    () => ({
      openCreateProject: () => setState({ kind: "project" }),
      openCreateWorkItem: (o: { projectId: string; status?: WorkItem["status"] }) =>
        setState({ kind: "work-item", projectId: o.projectId, status: o.status }),
      openEditWorkItem: (item: WorkItem) => setState({ kind: "edit-work-item", item }),
      close: () => setState({ kind: "none" }),
    }),
    [],
  );

  return (
    <CreateModalContext.Provider value={value}>
      {children}
      {state.kind === "project" && <CreateProjectModal onClose={value.close} />}
      {state.kind === "work-item" && (
        <CreateWorkItemModal projectId={state.projectId} initialStatus={state.status} onClose={value.close} />
      )}
      {state.kind === "edit-work-item" && (
        <EditWorkItemModal item={state.item} onClose={value.close} />
      )}
    </CreateModalContext.Provider>
  );
}
