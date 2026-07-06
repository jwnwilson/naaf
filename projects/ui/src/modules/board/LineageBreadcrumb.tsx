import type { components } from "../../lib/api/schema";

type WorkItem = components["schemas"]["WorkItem"];

export function LineageBreadcrumb({
  item,
}: {
  item: Pick<WorkItem, "epicName" | "featureName">;
}) {
  const parts = [item.epicName, item.featureName].filter(Boolean) as string[];
  if (parts.length === 0) return null;
  const label = parts.join(" › ");
  return (
    <span className="min-w-0 truncate font-mono text-[9px] text-text-6" title={label}>
      {label}
    </span>
  );
}
