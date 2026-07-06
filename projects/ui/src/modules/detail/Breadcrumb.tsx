import type { components } from "../../lib/api/schema";

type WorkItem = components["schemas"]["WorkItem"];

function Chevron() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
      <path d="M3.5 2.5L6 5l-2.5 2.5" stroke="#25272e" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Breadcrumb({ item }: { item: WorkItem }) {
  const segments: { label: string; emphasized?: boolean }[] = [];

  if (item.epicName) {
    segments.push({ label: item.epicName });
  }
  if (item.featureName) {
    segments.push({ label: item.featureName });
  }
  segments.push({ label: item.key, emphasized: true });

  return (
    <div className="flex h-[34px] items-center gap-[6px] px-[16px] text-[11px] text-text-5">
      {segments.map((seg, i) => (
        <span key={seg.label} className="flex items-center gap-[6px]">
          {i > 0 && <Chevron />}
          <span className={seg.emphasized ? "text-text-3" : undefined}>
            {seg.label}
          </span>
        </span>
      ))}
    </div>
  );
}
