import { ProgressBar } from "../../components/ui/ProgressBar";
import type { components } from "../../lib/api/schema";

type WorkItem = components["schemas"]["WorkItem"];
type Attachment = components["schemas"]["Attachment"];

const SECTION_LABEL = "text-[9.5px] font-mono text-[#2e3038] tracking-widest uppercase mb-[10px]";
const KEY_CLASS = "w-[80px] shrink-0 text-[12px] text-[#42454e]";
const VAL_CLASS = "text-[12px] text-[#8a8d96]";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function RailSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-[rgba(255,255,255,0.055)] px-[14px] py-[14px]">
      <p className={SECTION_LABEL}>{label}</p>
      {children}
    </div>
  );
}

function Properties({ item }: { item: WorkItem }) {
  const rows: Array<{ key: string; value: string }> = [
    { key: "Status", value: item.status },
    { key: "Priority", value: item.priority },
    { key: "Type", value: item.type },
    { key: "Agent", value: item.assignedAgent?.id ?? "—" },
  ];

  return (
    <RailSection label="PROPERTIES">
      <div className="flex flex-col gap-[6px]">
        {rows.map(({ key, value }) => (
          <div key={key} className="flex items-center gap-[8px]">
            <span className={KEY_CLASS}>{key}</span>
            <span className={key === "Status" ? "text-[12px] text-[#bab7f6]" : VAL_CLASS}>
              {value}
            </span>
          </div>
        ))}
      </div>
    </RailSection>
  );
}

function TokenUsage({ item }: { item: WorkItem }) {
  const limit = item.tokenLimit ?? 200000;
  const thisRun = (item.tokenUsageThisRun ?? 0) / limit;
  const allRuns = (item.tokenUsageAllRuns ?? 0) / limit;

  return (
    <RailSection label="TOKEN USAGE">
      <div className="flex flex-col gap-[10px]">
        <div>
          <p className="mb-[5px] text-[11px] text-[#42454e]">This run</p>
          <ProgressBar value={thisRun} tone="accent" height={3} />
        </div>
        <div>
          <p className="mb-[5px] text-[11px] text-[#42454e]">All runs</p>
          <ProgressBar value={allRuns} tone="muted" height={3} />
        </div>
      </div>
    </RailSection>
  );
}

function RecentActivity() {
  return (
    <RailSection label="RECENT ACTIVITY">
      <div className="relative pl-[12px]">
        <div className="absolute left-[5px] top-0 h-full w-[1px] bg-[#1e2028]" />
        <p className="text-[11px] text-[#42454e]">No activity yet</p>
      </div>
    </RailSection>
  );
}

function AttachmentRow({ attachment }: { attachment: Attachment }) {
  return (
    <div className="flex items-center gap-[8px]">
      <svg
        width="12"
        height="14"
        viewBox="0 0 12 14"
        fill="none"
        aria-hidden="true"
        className="shrink-0"
      >
        <rect x="0.5" y="0.5" width="11" height="13" rx="1.5" stroke="#52555e" />
        <line x1="3" y1="4" x2="9" y2="4" stroke="#52555e" />
        <line x1="3" y1="7" x2="9" y2="7" stroke="#52555e" />
        <line x1="3" y1="10" x2="7" y2="10" stroke="#52555e" />
      </svg>
      <span className="truncate text-[11px] text-[#52555e]">{attachment.name}</span>
      <span className="ml-auto shrink-0 font-mono text-[9px] text-[#25272e]">
        {formatBytes(attachment.size)}
      </span>
    </div>
  );
}

function Attachments({ item }: { item: WorkItem }) {
  const files = item.attachments ?? [];

  return (
    <RailSection label="ATTACHMENTS">
      {files.length === 0 ? (
        <p className="text-[11px] text-[#42454e]">No attachments</p>
      ) : (
        <div className="flex flex-col gap-[8px]">
          {files.map((att) => (
            <AttachmentRow key={att.id} attachment={att} />
          ))}
        </div>
      )}
    </RailSection>
  );
}

export function DetailRail({ item }: { item: WorkItem }) {
  return (
    <div className="w-[252px] shrink-0 border-l border-[rgba(255,255,255,0.055)]">
      <Properties item={item} />
      <TokenUsage item={item} />
      <RecentActivity />
      <Attachments item={item} />
    </div>
  );
}
