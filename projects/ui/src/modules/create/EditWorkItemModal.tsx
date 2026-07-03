// src/modules/create/EditWorkItemModal.tsx
import { useState } from "react";
import { Button, FormField, Modal, Select, Textarea, TextInput } from "../../components/ui";
import { useUpdateWorkItem, type WorkItem, type WorkItemUpdate } from "../../lib/api/hooks";

type Priority = WorkItem["priority"];

const PRIORITIES: Priority[] = ["low", "medium", "high", "urgent"];

interface Props {
  item: WorkItem;
  onClose: () => void;
}

export function EditWorkItemModal({ item, onClose }: Props) {
  const [form, setForm] = useState({
    title: item.title,
    priority: item.priority,
    spec: item.spec ?? "",
  });
  const mutation = useUpdateWorkItem(item.id, item.projectId);
  const canSubmit = form.title.trim().length > 0 && !mutation.isPending;

  async function submit() {
    const body: WorkItemUpdate = {
      title: form.title.trim(),
      priority: form.priority,
      spec: form.spec.trim(),
    };
    try {
      await mutation.mutateAsync(body);
    } catch {
      return; // error is surfaced via mutation.isError
    }
    onClose();
  }

  return (
    <Modal
      title="Edit Work Item"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={!canSubmit} onClick={() => { void submit(); }}>
            {mutation.isPending ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      <FormField label="Title">
        <TextInput
          aria-label="Title"
          value={form.title}
          onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
          autoFocus
        />
      </FormField>

      <FormField label="Priority">
        <Select
          aria-label="Priority"
          value={form.priority}
          onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value as Priority }))}
        >
          {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
        </Select>
      </FormField>

      <FormField label="Spec / Description">
        <Textarea
          aria-label="Spec / Description"
          value={form.spec}
          onChange={(e) => setForm((f) => ({ ...f, spec: e.target.value }))}
        />
      </FormField>

      {mutation.isError && (
        <p className="text-[10.5px] text-[#e5686b]">{mutation.error instanceof Error ? mutation.error.message : String(mutation.error)}</p>
      )}
    </Modal>
  );
}
