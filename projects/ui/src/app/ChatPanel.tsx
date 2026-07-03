import { useParams } from "react-router-dom";
import { ChevronRightIcon } from "../components/ui";
import { PulseDot } from "../components/ui/PulseDot";
import { Thread } from "../components/thread";
import { useThreads } from "../lib/api/hooks";
import { useLocalStorage } from "../lib/hooks/useLocalStorage";

// ── Collapsed strip ────────────────────────────────────────────────────────────

function CollapsedStrip({ onExpand }: { onExpand: () => void }) {
  return (
    <button
      aria-label="expand chat"
      onClick={onExpand}
      className="flex h-full w-[34px] shrink-0 cursor-pointer flex-col items-center justify-center gap-2 border-l border-[rgba(255,255,255,0.055)] bg-[#080a0d] text-[#52555e] hover:text-[#8a8d96]"
    >
      <ChevronRightIcon />
      <span
        className="font-mono text-[8.5px] text-[#1e2028]"
        style={{ writingMode: "vertical-rl", transform: "rotate(180deg)", letterSpacing: "0.09em" }}
      >
        CHAT ⌘J
      </span>
    </button>
  );
}

// ── ChatPanel ──────────────────────────────────────────────────────────────────

export function ChatPanel() {
  const [open, setOpen] = useLocalStorage("naaf.chat.open", true);
  const { data: threads = [] } = useThreads();
  const params = useParams<{ itemId?: string }>();
  const workItemId = params.itemId ?? threads[0]?.workItemId;

  if (!open) {
    return <CollapsedStrip onExpand={() => setOpen(true)} />;
  }

  return (
    <aside className="flex h-full w-[292px] shrink-0 flex-col border-l border-[rgba(255,255,255,0.055)] bg-[#09090c]">
      {/* Header */}
      <div className="flex h-[44px] shrink-0 items-stretch border-b border-[rgba(255,255,255,0.055)]">
        <div className="flex h-full flex-1 items-center gap-1.5 px-3">
          <PulseDot size={6} />
          <span className="text-[11.5px] font-medium text-[#bab7f6]">Chat</span>
        </div>
        <button
          aria-label="collapse"
          onClick={() => setOpen(false)}
          className="flex w-[34px] items-center justify-center border-l border-[rgba(255,255,255,0.055)] text-[#52555e] hover:text-[#8a8d96]"
        >
          <ChevronRightIcon className="rotate-180" />
        </button>
      </div>

      {/* Thread or empty state */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {workItemId ? (
          <Thread workItemId={workItemId} compact composerPlaceholder="Message…" />
        ) : (
          <p className="text-center text-[11.5px] text-[#52555e] p-4">No conversations</p>
        )}
      </div>
    </aside>
  );
}
