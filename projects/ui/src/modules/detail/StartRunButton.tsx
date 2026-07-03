import { useState } from "react";
import { Button, Modal } from "../../components/ui";
import { useStartRun } from "../../lib/api/hooks";
import type { components } from "../../lib/api/schema";

type WorkItem = components["schemas"]["WorkItem"];
type RunOut = components["schemas"]["RunOut"];

// Agents develop tasks (and small features), not epics.
const RUNNABLE_TYPES = new Set(["task", "feature"]);
// A run transitions the item to in_progress; only these statuses allow that.
const STARTABLE_STATUSES = new Set(["todo", "in_review"]);
const ACTIVE_RUN_STATUSES = new Set(["queued", "running", "awaiting_gate"]);

export function StartRunButton({ item, run }: { item: WorkItem; run: RunOut | null }) {
  const [confirming, setConfirming] = useState(false);
  const mutation = useStartRun(item.id, item.projectId);

  if (!RUNNABLE_TYPES.has(item.type)) return null;

  const runActive = run != null && ACTIVE_RUN_STATUSES.has(run.status);
  const startable = STARTABLE_STATUSES.has(item.status);
  const disabled = !startable || runActive || mutation.isPending;
  const reason = runActive
    ? "A run is already in progress"
    : !startable
      ? "Move the item to To Do to start a run"
      : undefined;

  async function confirmStart() {
    try {
      await mutation.mutateAsync();
    } catch {
      return; // error surfaced in the dialog; keep it open
    }
    setConfirming(false);
  }

  return (
    <>
      <Button
        variant="primary"
        disabled={disabled}
        title={reason}
        onClick={() => setConfirming(true)}
      >
        {mutation.isPending ? "Starting…" : "Start run"}
      </Button>

      {confirming && (
        <Modal
          title="Start agent run"
          onClose={() => setConfirming(false)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setConfirming(false)}>Cancel</Button>
              <Button variant="primary" disabled={mutation.isPending} onClick={() => { void confirmStart(); }}>
                {mutation.isPending ? "Starting…" : "Start run"}
              </Button>
            </>
          }
        >
          <p className="text-[12px] text-text-3">
            Start an agent run on <span className="text-text-1">{item.title}</span>? This uses the
            model and opens a pull request.
          </p>
          {mutation.isError && (
            <p className="mt-2 text-[10.5px] text-[#e5686b]">
              {mutation.error instanceof Error ? mutation.error.message : String(mutation.error)}
            </p>
          )}
        </Modal>
      )}
    </>
  );
}
