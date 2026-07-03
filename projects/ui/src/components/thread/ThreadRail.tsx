import { Avatar } from "../ui/Avatar";
import { useThread } from "../../lib/api/hooks";

interface ThreadRailProps {
  workItemId: string;
}

export function ThreadRail({ workItemId }: ThreadRailProps) {
  const { data: thread } = useThread(workItemId);

  return (
    <div
      className="shrink-0 flex flex-col gap-4 overflow-y-auto px-3 py-4"
      style={{
        width: 252,
        borderLeft: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      <div>
        <p className="text-[10px] font-medium uppercase tracking-wide mb-2 text-[#42454e]">
          Participants
        </p>
        <div className="flex flex-col gap-1.5">
          {(thread?.participants ?? []).map((p) => (
            <div key={p} className="flex items-center gap-1.5">
              <Avatar
                initials={p.slice(0, 2).toUpperCase()}
                variant={p === "user" ? "user" : "agent"}
                size={18}
              />
              <span className="text-[11.5px] text-[#6b6e78]">{p}</span>
            </div>
          ))}
        </div>
      </div>

      {thread?.filesWritten && thread.filesWritten.length > 0 && (
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wide mb-2 text-[#42454e]">
            Files
          </p>
          <div className="flex flex-col gap-1">
            {thread.filesWritten.map((f, i) => {
              const label =
                typeof f["path"] === "string" ? f["path"] : JSON.stringify(f);
              return (
                <p key={i} className="text-[11px] font-mono text-[#52555e] truncate">
                  {label}
                </p>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
