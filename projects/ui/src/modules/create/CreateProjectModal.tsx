import { useState } from "react";
import { Button, FormField, Modal, TextInput } from "../../components/ui";
import { useCreateProject } from "../../lib/api/hooks";

export function CreateProjectModal({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({ name: "", repoUrl: "" });
  const mutation = useCreateProject();
  const canSubmit = form.name.trim().length > 0 && !mutation.isPending;

  async function submit() {
    await mutation.mutateAsync({ name: form.name.trim(), repoUrl: form.repoUrl.trim() });
    onClose();
  }

  return (
    <Modal
      title="Create Project"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!canSubmit}
            onClick={() => { void submit(); }}
          >
            {mutation.isPending ? "Creating…" : "Create Project"}
          </Button>
        </>
      }
    >
      <FormField label="Name">
        <TextInput
          aria-label="Name"
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          autoFocus
        />
      </FormField>
      <FormField label="Repo URL">
        <TextInput
          aria-label="Repo URL"
          value={form.repoUrl}
          placeholder="https://github.com/org/repo"
          onChange={(e) => setForm((f) => ({ ...f, repoUrl: e.target.value }))}
        />
      </FormField>
      {mutation.isError && (
        <p className="text-[10.5px] text-[#e5686b]">{(mutation.error as Error).message}</p>
      )}
    </Modal>
  );
}
