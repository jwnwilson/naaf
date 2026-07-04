import type { ReactNode } from "react";
import { Avatar } from "../ui/Avatar";
import { useThread } from "../../lib/api/hooks";
import { avatarVariant, participantInitials } from "../../lib/agentIdentity";
import type { components } from "../../lib/api/schema";

type Participant = components["schemas"]["ThreadParticipant"];

interface ThreadRailProps {
  workItemId: string;
}

const RAIL_LABEL = "font-mono text-[9.5px] tracking-[0.07em] text-[#28292e]";

function formatTime(iso: string | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

function Subtitle({ p }: { p: Participant }) {
  if (p.role === "user") return <span className="text-[10px] text-[#42454e]">Owner</span>;
  if (p.role === "lead") return <span className="text-[10px] text-[#42454e]">Orchestrator</span>;
  if (p.status === "running") {
    return (
      <span className="flex items-center gap-1 mt-px">
        <span
          className="w-[5px] h-[5px] rounded-full bg-[#7c6cf0] flex-none"
          style={{ animation: "pulse 2s infinite" }}
        />
        <span className="text-[10px] text-[#7c6cf0]">Running</span>
      </span>
    );
  }
  return <span className="text-[10px] text-[#42454e]">Idle</span>;
}

function ParticipantRow({ p }: { p: Participant }) {
  return (
    <div className="flex items-center gap-2.5">
      <Avatar initials={participantInitials(p)} variant={avatarVariant(p)} size={22} />
      <div className="min-w-0">
        <div className="text-[12px] text-[#c4c5cb] truncate">{p.name}</div>
        <Subtitle p={p} />
      </div>
    </div>
  );
}

function InfoRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center text-[12px]">
      <span className="text-[#42454e] w-20 flex-none">{label}</span>
      {children}
    </div>
  );
}

function FileRow({ path }: { path: string }) {
  return (
    <div
      className="flex items-center gap-1.5 rounded-[5px] px-2 py-1.5"
      style={{ border: "1px solid rgba(255,255,255,0.06)" }}
    >
      <svg width="12" height="14" viewBox="0 0 12 14" fill="none" style={{ flex: "none", color: "#3a3d44" }}>
        <rect x=".75" y=".75" width="10.5" height="12.5" rx="1.5" stroke="currentColor" strokeWidth="1" />
        <path d="M3 5h6M3 7.5h6M3 10h4" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
      </svg>
      <span className="font-mono text-[10.5px] text-[#7c6cf0] truncate">{path}</span>
    </div>
  );
}

export function ThreadRail({ workItemId }: ThreadRailProps) {
  const { data: thread } = useThread(workItemId);
  const participants = thread?.participantDetails ?? [];
  const files = (thread?.filesWritten ?? [])
    .map((f) => (typeof f["path"] === "string" ? (f["path"] as string) : null))
    .filter((p): p is string => p !== null);

  return (
    <div
      className="shrink-0 flex flex-col gap-4 overflow-y-auto px-3.5 py-4"
      style={{ width: 252, borderLeft: "1px solid rgba(255,255,255,0.055)" }}
    >
      <div>
        <p className={`${RAIL_LABEL} mb-2.5`}>PARTICIPANTS</p>
        <div className="flex flex-col gap-2.5">
          {participants.map((p) => (
            <ParticipantRow key={p.role} p={p} />
          ))}
        </div>
      </div>

      <div className="h-px bg-[rgba(255,255,255,0.05)]" />

      <div>
        <p className={`${RAIL_LABEL} mb-2.5`}>THREAD INFO</p>
        <div className="flex flex-col gap-2">
          <InfoRow label="Messages">
            <span className="text-[#8a8d96]">{thread?.messageCount ?? 0}</span>
          </InfoRow>
          <InfoRow label="Started">
            <span className="text-[#8a8d96]">{formatTime(thread?.createdAt)}</span>
          </InfoRow>
          <InfoRow label="Task">
            <span className="font-mono text-[11px] text-[#7c6cf0]">{workItemId}</span>
          </InfoRow>
        </div>
      </div>

      {files.length > 0 && (
        <>
          <div className="h-px bg-[rgba(255,255,255,0.05)]" />
          <div>
            <p className={`${RAIL_LABEL} mb-2`}>FILES WRITTEN</p>
            <div className="flex flex-col gap-1.5">
              {files.map((path, i) => (
                <FileRow key={i} path={path} />
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
