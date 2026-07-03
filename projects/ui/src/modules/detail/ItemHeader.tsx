import type { ReactNode } from "react";
import { Button } from "../../components/ui/Button";
import { StatusCircle } from "../../components/ui/StatusCircle";
import { Tag } from "../../components/ui/Tag";
import type { components } from "../../lib/api/schema";

type WorkItem = components["schemas"]["WorkItem"];

const CHIP_CLASS =
  "inline-flex h-[28px] items-center rounded-[5px] border border-border-strong px-[9px] text-[11px] text-text-3";

export function ItemHeader({ item, onEdit, actions }: { item: WorkItem; onEdit?: () => void; actions?: ReactNode }) {
  return (
    <div className="flex flex-col gap-[10px] px-[16px] pt-[16px]">
      {/* Status circle + title + actions */}
      <div className="flex items-center gap-[8px]">
        <StatusCircle status={item.status} size={14} />
        <h1 className="text-[17px] font-semibold text-text-1">{item.title}</h1>
        {(actions || onEdit) && (
          <div className="ml-auto flex items-center gap-[8px]">
            {actions}
            {onEdit && <Button variant="secondary" onClick={onEdit}>Edit</Button>}
          </div>
        )}
      </div>

      {/* Metadata row */}
      <div className="flex flex-wrap items-center gap-[6px]">
        <span className={CHIP_CLASS}>{item.status}</span>
        <span className={CHIP_CLASS}>{item.priority}</span>
        {item.assignedAgent && (
          <span className={CHIP_CLASS}>{item.assignedAgent.id}</span>
        )}
        {item.epicId && (
          <Tag tone="accent">{item.epicId}</Tag>
        )}
      </div>
    </div>
  );
}
