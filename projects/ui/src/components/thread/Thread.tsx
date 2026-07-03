import type { ReactNode } from "react";
import { useThreadMessages } from "../../lib/api/hooks";
import { MessageItem } from "./MessageItem";
import { ThreadComposer } from "./ThreadComposer";
import { ThreadRail } from "./ThreadRail";

interface ThreadProps {
  workItemId: string;
  showRail?: boolean;
  /** Documented no-op / tight-padding hint */
  compact?: boolean;
  header?: ReactNode;
  banner?: ReactNode;
  composerPlaceholder?: string;
}

export function Thread({
  workItemId,
  showRail,
  banner,
  composerPlaceholder,
}: ThreadProps) {
  const { data: messages = [], isLoading } = useThreadMessages(workItemId);

  return (
    <div className="flex flex-col h-full flex-1 overflow-hidden">
      {banner}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <div className="flex flex-col flex-1 overflow-hidden">
          <div className="flex-1 overflow-y-auto px-4 py-4">
            {isLoading && (
              <p className="text-[11px] text-[#30333c]">Loading…</p>
            )}
            {!isLoading && messages.length === 0 && (
              <p className="text-[11px] text-[#30333c]">No messages yet</p>
            )}
            {messages.map((msg) => (
              <MessageItem key={msg.id} message={msg} />
            ))}
          </div>
          <ThreadComposer
            workItemId={workItemId}
            placeholder={composerPlaceholder}
          />
        </div>
        {showRail && <ThreadRail workItemId={workItemId} />}
      </div>
    </div>
  );
}
