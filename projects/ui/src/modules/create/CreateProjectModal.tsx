import { useState } from "react";
import { Button, Modal } from "../../components/ui";
import { useCreateProject } from "../../lib/api/hooks";
import { ProjectFormFields, type ProjectFormValues } from "./ProjectFormFields";

export function CreateProjectModal({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState<ProjectFormValues>({ name: "", repoUrl: "", description: "" });
  const mutation = useCreateProject();
  const canSubmit = form.name.trim().length > 0 && !mutation.isPending;

  async function submit() {
    try {
      await mutation.mutateAsync({
        name: form.name.trim(),
        repoUrl: form.repoUrl.trim(),
        description: form.description.trim(),
      });
    } catch {
      return; // error is surfaced via mutation.isError
    }
    onClose();
  }

  return (
    <Modal
      title="Create Project"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={!canSubmit} onClick={() => { void submit(); }}>
            {mutation.isPending ? "Creating…" : "Create Project"}
          </Button>
        </>
      }
    >
      <ProjectFormFields values={form} onChange={(patch) => setForm((f) => ({ ...f, ...patch }))} />
      {mutation.isError && (
        <p className="text-[10.5px] text-[#e5686b]">{mutation.error instanceof Error ? mutation.error.message : String(mutation.error)}</p>
      )}
    </Modal>
  );
}
