// src/modules/create/EditWorkItemModal.tsx
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button, FormField, Modal, Select, Textarea, TextInput } from "../../components/ui";
import {
  useDeleteWorkItem,
  useUpdateWorkItem,
  type WorkItem,
  type WorkItemUpdate,
} from "../../lib/api/hooks";

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
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const update = useUpdateWorkItem(item.id, item.projectId);
  const remove = useDeleteWorkItem(item.id, item.projectId);
  const navigate = useNavigate();
  const { itemId } = useParams<{ itemId?: string }>();
  const canSubmit = form.title.trim().length > 0 && !update.isPending;
  const err = update.error ?? remove.error;

  async function submit() {
    const body: WorkItemUpdate = {
      title: form.title.trim(),
      priority: form.priority,
      spec: form.spec.trim(),
    };
    try {
      await update.mutateAsync(body);
    } catch {
      return; // error is surfaced via `err`
    }
    onClose();
  }

  async function confirmDelete() {
    try {
      await remove.mutateAsync();
    } catch {
      return; // error is surfaced via `err`
    }
    // If we're on this item's detail page, leave it — the item no longer exists.
    if (itemId === item.id) navigate(`/projects?project=${item.projectId}`);
    onClose();
  }

  return (
    <Modal
      title="Edit Work Item"
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
            <Button variant="primary" disabled={!canSubmit} onClick={() => { void submit(); }}>
              {update.isPending ? "Saving…" : "Save"}
            </Button>
          </>
        )
      }
    >
      {confirmingDelete ? (
        <p className="text-[12px] text-text-1">
          Delete <strong>{item.title}</strong> and all its runs, threads, and attachments? This can't be undone.
        </p>
      ) : (
        <>
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
        </>
      )}

      {err && (
        <p className="text-[10.5px] text-[#e5686b]">{err instanceof Error ? err.message : String(err)}</p>
      )}
    </Modal>
  );
}
