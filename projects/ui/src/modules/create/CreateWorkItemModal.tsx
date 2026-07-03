// src/modules/create/CreateWorkItemModal.tsx
import { useState } from "react";
import { Button, Chip, FormField, Modal, Select, Textarea, TextInput } from "../../components/ui";
import { useCreateWorkItem, type WorkItemCreate } from "../../lib/api/hooks";
import { useProjectWorkItems } from "../board/useProjectWorkItems";

type Kind = "epic" | "feature" | "task";
type Status = WorkItemCreate["status"];
type Priority = WorkItemCreate["priority"];

const KIND_LABELS: Record<Kind, string> = { epic: "Epic", feature: "Feature", task: "Task" };
const STATUSES: Status[] = ["backlog", "todo", "in_progress", "in_review", "done"];
const PRIORITIES: Priority[] = ["low", "medium", "high", "urgent"];

interface Props {
  projectId: string;
  initialStatus?: Status;
  onClose: () => void;
}

interface FormState {
  type: Kind;
  title: string;
  status: Status;
  priority: Priority;
  epicId: string;
  featureId: string;
  spec: string;
}

function buildBody(form: FormState): WorkItemCreate {
  const body: WorkItemCreate = {
    type: form.type,
    title: form.title.trim(),
    status: form.status,
    priority: form.priority,
  };
  if (form.spec.trim()) body.spec = form.spec.trim();
  if (form.type !== "epic" && form.epicId) body.epicId = form.epicId;
  if (form.type === "task" && form.featureId) body.featureId = form.featureId;
  return body;
}

export function CreateWorkItemModal({ projectId, initialStatus, onClose }: Props) {
  const [form, setForm] = useState<FormState>({
    type: "task",
    title: "",
    status: initialStatus ?? "todo",
    priority: "medium",
    epicId: "",
    featureId: "",
    spec: "",
  });
  const mutation = useCreateWorkItem(projectId);
  const { data } = useProjectWorkItems(projectId);
  const items = data?.results ?? [];
  const epics = items.filter((i) => i.type === "epic");
  const features = items.filter((i) => i.type === "feature");
  const canSubmit = form.title.trim().length > 0 && !mutation.isPending;

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(addAnother: boolean) {
    await mutation.mutateAsync(buildBody(form));
    if (addAnother) {
      setForm((f) => ({ ...f, title: "", spec: "" }));
    } else {
      onClose();
    }
  }

  return (
    <Modal
      title="Create Work Item"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="secondary" disabled={!canSubmit} onClick={() => { void submit(true); }}>
            Create &amp; add another
          </Button>
          <Button variant="primary" disabled={!canSubmit} onClick={() => { void submit(false); }}>
            {mutation.isPending ? "Creating…" : `Create ${KIND_LABELS[form.type]}`}
          </Button>
        </>
      }
    >
      <div className="mb-3 flex gap-1">
        {(Object.keys(KIND_LABELS) as Kind[]).map((k) => (
          <Chip key={k} active={form.type === k} onClick={() => set("type", k)}>
            {KIND_LABELS[k]}
          </Chip>
        ))}
      </div>

      <FormField label="Title">
        <TextInput
          aria-label="Title"
          value={form.title}
          onChange={(e) => set("title", e.target.value)}
          autoFocus
        />
      </FormField>

      <div className="flex gap-3">
        <div className="flex-1">
          <FormField label="Status">
            <Select aria-label="Status" value={form.status} onChange={(e) => set("status", e.target.value as Status)}>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </Select>
          </FormField>
        </div>
        <div className="flex-1">
          <FormField label="Priority">
            <Select aria-label="Priority" value={form.priority} onChange={(e) => set("priority", e.target.value as Priority)}>
              {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
            </Select>
          </FormField>
        </div>
      </div>

      {form.type !== "epic" && (
        <FormField label="Parent Epic">
          <Select aria-label="Parent Epic" value={form.epicId} onChange={(e) => set("epicId", e.target.value)}>
            <option value="">None</option>
            {epics.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}
          </Select>
        </FormField>
      )}

      {form.type === "task" && (
        <FormField label="Parent Feature">
          <Select aria-label="Parent Feature" value={form.featureId} onChange={(e) => set("featureId", e.target.value)}>
            <option value="">None</option>
            {features.map((f) => <option key={f.id} value={f.id}>{f.title}</option>)}
          </Select>
        </FormField>
      )}

      <FormField label="Spec / Description">
        <Textarea aria-label="Spec / Description" value={form.spec} onChange={(e) => set("spec", e.target.value)} />
      </FormField>

      {mutation.isError && (
        <p className="text-[10.5px] text-[#e5686b]">{(mutation.error as Error).message}</p>
      )}
    </Modal>
  );
}
