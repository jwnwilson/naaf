import type { ReactNode } from "react";
import { useAnswerQuestion, useThreadMessages } from "../../lib/api/hooks";
import { MessageItem } from "./MessageItem";
import { ThreadComposer } from "./ThreadComposer";
import { ThreadRail } from "./ThreadRail";
import { groupMessagesByDay } from "./groupByDay";
import { TypingIndicator } from "../ui/TypingIndicator";

interface ThreadProps {
  workItemId: string;
  showRail?: boolean;
  /** Documented no-op / tight-padding hint */
  compact?: boolean;
  banner?: ReactNode;
  composerPlaceholder?: string;
  /** Show the agent typing indicator (a run is active on this item). */
  showTyping?: boolean;
}

function DayDivider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2.5 py-1.5">
      <div className="flex-1 h-px bg-[rgba(255,255,255,0.05)]" />
      <span className="font-mono text-[10px] text-[#2e3038]">{label}</span>
      <div className="flex-1 h-px bg-[rgba(255,255,255,0.05)]" />
    </div>
  );
}

function TypingRow() {
  return (
    <div className="flex gap-2.5 items-start mb-3.5" data-testid="typing-indicator">
      <div className="w-[26px] h-[26px] flex-none" />
      <div
        className="flex items-center px-3.5 py-2.5"
        style={{ background: "#131618", border: "1px solid rgba(255,255,255,0.07)", borderRadius: "3px 10px 10px 10px" }}
      >
        <TypingIndicator />
      </div>
    </div>
  );
}

export function Thread({
  workItemId,
  showRail,
  banner,
  composerPlaceholder,
  showTyping,
}: ThreadProps) {
  const { data: messages = [], isLoading } = useThreadMessages(workItemId);
  const answer = useAnswerQuestion(workItemId);
  const handleAnswer = (msgId: string, option: string) => { answer.mutate({ msgId, option }); };
  const groups = groupMessagesByDay(messages);

  return (
    <div className="flex flex-col h-full flex-1 overflow-hidden">
      {banner}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <div className="flex flex-col flex-1 overflow-hidden">
          <div className="flex-1 overflow-y-auto px-4 py-4">
            {isLoading && (
              <p className="text-[11px] text-[#30333c]">Loading…</p>
            )}
            {!isLoading && messages.length === 0 && !showTyping && (
              <p className="text-[11px] text-[#30333c]">No messages yet</p>
            )}
            {groups.map((group) => (
              <div key={group.key}>
                {group.label && <DayDivider label={group.label} />}
                {group.messages.map((msg) => (
                  <MessageItem key={msg.id} message={msg} onAnswer={handleAnswer} answering={answer.isPending} />
                ))}
              </div>
            ))}
            {showTyping && <TypingRow />}
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
