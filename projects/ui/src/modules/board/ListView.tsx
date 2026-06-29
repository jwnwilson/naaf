import { StatusCircle } from "../../components/ui/StatusCircle";
import { ListRow } from "./ListRow";
import { STATUS_ORDER, groupByStatus } from "./groupByStatus";
import { useProjectWorkItems } from "./useProjectWorkItems";
import type { WorkItemStatus } from "./groupByStatus";

const STATUS_LABELS: Record<WorkItemStatus, string> = {
  backlog: "Backlog",
  todo: "Todo",
  in_progress: "In Progress",
  in_review: "In Review",
  done: "Done",
};

const COLUMN_HEADERS = [
  { label: "PRIORITY", width: "w-[14px]" },
  { label: "STATUS", width: "w-[13px]" },
  { label: "ID", width: "w-[62px]" },
  { label: "TITLE", width: "flex-1" },
  { label: "EPIC", width: "w-[50px]" },
  { label: "TOKENS", width: "w-[44px]" },
  { label: "AGENT", width: "w-[18px]" },
  { label: "AGE", width: "w-[24px]" },
];

function ColumnHeaderRow() {
  return (
    <div className="flex h-[28px] items-center gap-[8px] bg-[#0b0c0f] px-[14px]">
      {COLUMN_HEADERS.map(({ label, width }) => (
        <span
          key={label}
          className={`${width} shrink-0 font-mono text-[9.5px] tracking-[0.04em] text-[#2e3038]`}
        >
          {label}
        </span>
      ))}
    </div>
  );
}

interface GroupHeaderProps {
  status: WorkItemStatus;
  count: number;
}

function GroupHeader({ status, count }: GroupHeaderProps) {
  return (
    <div className="flex h-[30px] items-center gap-[6px] bg-[#0b0c0f] px-[14px]">
      <StatusCircle status={status} size={13} />
      <span className="flex-1 text-[11.5px] font-semibold text-[#c4c5cb]">
        {STATUS_LABELS[status]}
      </span>
      <span className="font-mono text-[9.5px] text-[#30333c]">{count}</span>
      <svg
        width="10"
        height="10"
        viewBox="0 0 10 10"
        fill="none"
        className="text-[#30333c]"
        aria-hidden="true"
      >
        <path
          d="M3 3.5L5 5.5L7 3.5"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

export function ListView({ projectId }: { projectId: string }) {
  const { data } = useProjectWorkItems(projectId);
  const grouped = groupByStatus(data?.results ?? []);

  return (
    <div className="flex flex-col overflow-y-auto">
      <ColumnHeaderRow />
      {STATUS_ORDER.map((status) => {
        const items = grouped[status];
        if (items.length === 0) return null;
        return (
          <div key={status}>
            <GroupHeader status={status} count={items.length} />
            {items.map((item) => (
              <ListRow key={item.id} item={item} />
            ))}
          </div>
        );
      })}
    </div>
  );
}
