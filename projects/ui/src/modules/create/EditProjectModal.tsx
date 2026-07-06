import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button, Modal } from "../../components/ui";
import { useDeleteProject, useUpdateProject, type Project } from "../../lib/api/hooks";
import { ProjectFormFields, type ProjectFormValues } from "./ProjectFormFields";

export function EditProjectModal({ project, onClose }: { project: Project; onClose: () => void }) {
  const [form, setForm] = useState<ProjectFormValues>({
    name: project.name,
    repoUrl: project.repoUrl,
    description: project.description ?? "",
  });
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const update = useUpdateProject(project.id);
  const remove = useDeleteProject(project.id);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const canSubmit = form.name.trim().length > 0 && !update.isPending;
  const err = update.error ?? remove.error;

  async function save() {
    try {
      await update.mutateAsync({
        name: form.name.trim(),
        repoUrl: form.repoUrl.trim(),
        description: form.description.trim(),
      });
    } catch {
      return;
    }
    onClose();
  }

  async function confirmDelete() {
    try {
      await remove.mutateAsync();
    } catch {
      return;
    }
    if (searchParams.get("project") === project.id) navigate("/projects");
    onClose();
  }

  return (
    <Modal
      title="Edit Project"
      onClose={onClose}
      footer={
        confirmingDelete ? (
          <>
            <Button variant="secondary" onClick={() => setConfirmingDelete(false)}>Cancel</Button>
            <Button variant="danger" disabled={remove.isPending} onClick={() => { void confirmDelete(); }}>
              {remove.isPending ? "Deleting…" : "Confirm delete"}
            </Button>
          </>
        ) : (
          <>
            <Button variant="danger" onClick={() => setConfirmingDelete(true)}>Delete</Button>
            <div className="flex-1" />
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button variant="primary" disabled={!canSubmit} onClick={() => { void save(); }}>
              {update.isPending ? "Saving…" : "Save"}
            </Button>
          </>
        )
      }
    >
      {confirmingDelete ? (
        <p className="text-[12px] text-text-1">
          Delete <strong>{project.name}</strong> and all its work items, runs, and threads? This can't be undone.
        </p>
      ) : (
        <ProjectFormFields values={form} onChange={(patch) => setForm((f) => ({ ...f, ...patch }))} />
      )}
      {err && (
        <p className="text-[10.5px] text-[#e5686b]">{err instanceof Error ? err.message : String(err)}</p>
      )}
    </Modal>
  );
}
