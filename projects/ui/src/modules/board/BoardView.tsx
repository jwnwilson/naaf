import { Button } from "../../components/ui";
import { StatusCircle } from "../../components/ui/StatusCircle";
import { KanbanCard } from "./KanbanCard";
import { LiveAgentsRibbon } from "./LiveAgentsRibbon";
import { STATUS_ORDER, groupByStatus } from "./groupByStatus";
import { useProjectWorkItems } from "./useProjectWorkItems";
import { useCreateModal } from "../create/useCreateModal";
import type { WorkItemStatus } from "./groupByStatus";

const STATUS_LABELS: Record<WorkItemStatus, string> = {
  backlog: "Backlog",
  todo: "Todo",
  in_progress: "In Progress",
  in_review: "In Review",
  done: "Done",
};

interface ColumnHeaderProps {
  status: WorkItemStatus;
  count: number;
  onAdd: () => void;
}

function ColumnHeader({ status, count, onAdd }: ColumnHeaderProps) {
  return (
    <div className="flex items-center gap-[6px] px-[12px] py-[10px]">
      <StatusCircle status={status} size={12} />
      <span className="text-[11.5px] font-semibold text-text-1 flex-1">
        {STATUS_LABELS[status]}
      </span>
      <span className="font-mono text-[9.5px] text-text-6">{count}</span>
      <button
        type="button"
        onClick={onAdd}
        aria-label={`Add ${STATUS_LABELS[status]} item`}
        className="ml-[4px] text-text-4 hover:text-text-3 text-[14px] leading-none"
      >
        +
      </button>
    </div>
  );
}

export function BoardView({ projectId }: { projectId: string }) {
  const { data, isLoading } = useProjectWorkItems(projectId);
  const results = data?.results ?? [];
  const grouped = groupByStatus(results);
  const { openCreateWorkItem } = useCreateModal();

  if (!isLoading && results.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-text-4">
        <p className="text-[12px]">No work items yet.</p>
        <Button variant="primary" onClick={() => openCreateWorkItem({ projectId })}>
          Create your first item
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <LiveAgentsRibbon />
      <div className="flex flex-1 overflow-x-auto overflow-y-hidden">
        {STATUS_ORDER.map((status) => {
          const items = grouped[status];
          const isInProgress = status === "in_progress";
          return (
            <div
              key={status}
              className={`flex flex-col flex-1 border-r border-[rgba(255,255,255,0.05)] overflow-y-auto${isInProgress ? " bg-[#0c0d10]" : ""}`}
            >
              <ColumnHeader
                status={status}
                count={items.length}
                onAdd={() => openCreateWorkItem({ projectId, status })}
              />
              <div className="flex flex-col gap-[8px] px-[10px] pb-[10px]">
                {items.map((item) => (
                  <KanbanCard key={item.id} item={item} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
