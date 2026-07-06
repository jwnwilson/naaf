import type { PointerEvent as ReactPointerEvent } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { ChevronRightIcon } from "../components/ui";
import { PulseDot } from "../components/ui/PulseDot";
import { Thread } from "../components/thread";
import { useThreads } from "../lib/api/hooks";
import { useLocalStorage } from "../lib/hooks/useLocalStorage";
import { useResizableWidth } from "../lib/hooks/useResizableWidth";
import { projectThreadId } from "../lib/threadScope";

// Panel width bounds (px). Default keeps the original compact panel; the max
// leaves room for the board, the min keeps the thread readable.
const DEFAULT_WIDTH = 292;
const MIN_WIDTH = 240;
const MAX_WIDTH = 720;

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

// ── Resize handle ────────────────────────────────────────────────────────────

function ResizeHandle({
  onResizeStart,
  isResizing,
}: {
  onResizeStart: (event: ReactPointerEvent) => void;
  isResizing: boolean;
}) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize chat panel"
      onPointerDown={onResizeStart}
      className={`absolute inset-y-0 -left-1 z-10 w-2 cursor-col-resize touch-none transition-colors hover:bg-[rgba(186,183,246,0.35)] ${
        isResizing ? "bg-[rgba(186,183,246,0.55)]" : ""
      }`}
    />
  );
}

// ── ChatPanel ──────────────────────────────────────────────────────────────────

export function ChatPanel() {
  const [open, setOpen] = useLocalStorage("naaf.chat.open", true);
  const { width, isResizing, onResizeStart } = useResizableWidth(
    "naaf.chat.width",
    DEFAULT_WIDTH,
    MIN_WIDTH,
    MAX_WIDTH,
  );
  const { data: threads = [] } = useThreads();
  const params = useParams<{ itemId?: string }>();
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get("project");
  // Inside a work item → that thread; on a project board → the project lead
  // thread; otherwise fall back to the first thread.
  const workItemId =
    params.itemId ?? (projectId ? projectThreadId(projectId) : threads[0]?.workItemId);
  const isLeadThread = !params.itemId && Boolean(projectId);

  if (!open) {
    return <CollapsedStrip onExpand={() => setOpen(true)} />;
  }

  return (
    <aside
      style={{ width }}
      className="relative flex h-full shrink-0 flex-col border-l border-[rgba(255,255,255,0.055)] bg-[#09090c]"
    >
      <ResizeHandle onResizeStart={onResizeStart} isResizing={isResizing} />
      {/* Header */}
      <div className="flex h-[44px] shrink-0 items-stretch border-b border-[rgba(255,255,255,0.055)]">
        <div className="flex h-full flex-1 items-center gap-1.5 px-3">
          <PulseDot size={6} />
          <span className="text-[11.5px] font-medium text-[#bab7f6]">
            {isLeadThread ? "Chat with lead" : "Chat"}
          </span>
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
