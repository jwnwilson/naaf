import { useState } from "react";
import { Avatar } from "../components/ui/Avatar";
import { ChevronRightIcon } from "../components/ui";
import { PulseDot } from "../components/ui/PulseDot";
import { TypingIndicator } from "../components/ui/TypingIndicator";
import { useThreads, useThreadMessages, useSendMessage } from "../lib/api/hooks";
import type { Thread, Message } from "../lib/api/hooks";
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

// ── Message bubble ─────────────────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex gap-2 ${isUser ? "flex-row-reverse" : ""}`}>
      {!isUser && <Avatar initials="LA" variant="agent" size={20} />}
      <div
        className={`max-w-[80%] px-3 py-2 text-[12px] leading-[1.5] ${
          isUser
            ? "rounded-[9px_3px_9px_9px] border border-[rgba(124,108,240,0.16)] bg-[rgba(124,108,240,0.11)] text-[#bab7f6]"
            : "rounded-[3px_9px_9px_9px] border border-[rgba(255,255,255,0.07)] bg-[#131618] text-[#b0b2b8]"
        }`}
      >
        {msg.content}
      </div>
    </div>
  );
}

// ── Thread tab ─────────────────────────────────────────────────────────────────

function ThreadTab({ thread }: { thread: Thread | undefined }) {
  const label = thread ? `agent-${thread.agentId.replace("agent-", "")}` : "Chat";
  return (
    <div className="flex h-full flex-1 items-center gap-1.5 border-b-2 border-accent px-3">
      <PulseDot size={6} />
      <span className="text-[11.5px] font-medium text-[#bab7f6]">{label}</span>
    </div>
  );
}

// ── Input area ─────────────────────────────────────────────────────────────────

function ChatInput({ threadId }: { threadId: string | undefined }) {
  const [value, setValue] = useState("");
  const send = useSendMessage(threadId ?? "");
  const disabled = !threadId || value.trim().length === 0;

  function submit() {
    if (disabled) return;
    send.mutate({ content: value.trim() });
    setValue("");
  }

  return (
    <div className="p-[13px]">
      <form
        onSubmit={(e) => { e.preventDefault(); submit(); }}
        className="rounded-[7px] border border-[rgba(255,255,255,0.09)] bg-[#101316] p-2"
      >
        <div className="flex items-center gap-1 pb-2">
          <span className="rounded-[3px] border border-[rgba(255,255,255,0.08)] px-1.5 py-0.5 font-mono text-[9.5px] text-[#3a3d44]">
            @agent
          </span>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Message…"
            className="flex-1 bg-transparent text-[11.5px] text-[#c4c5cb] placeholder-[#20222a] outline-none"
          />
          <button
            type="submit"
            aria-label="send"
            disabled={disabled}
            className="flex h-[22px] w-[22px] items-center justify-center rounded-[5px] bg-[rgba(124,108,240,0.18)] text-accent disabled:opacity-40"
          >
            ↑
          </button>
        </div>
      </form>
    </div>
  );
}

// ── ChatPanel ──────────────────────────────────────────────────────────────────

export function ChatPanel() {
  const [open, setOpen] = useLocalStorage("naaf.chat.open", true);
  const { data: threads = [] } = useThreads();
  const firstThread: Thread | undefined = threads[0];
  const { data: messages = [], isLoading } = useThreadMessages(firstThread?.id);

  if (!open) {
    return <CollapsedStrip onExpand={() => setOpen(true)} />;
  }

  return (
    <aside className="flex h-full w-[292px] shrink-0 flex-col border-l border-[rgba(255,255,255,0.055)] bg-[#09090c]">
      {/* Header */}
      <div className="flex h-[44px] shrink-0 items-stretch border-b border-[rgba(255,255,255,0.055)]">
        <ThreadTab thread={firstThread} />
        <button
          aria-label="collapse"
          onClick={() => setOpen(false)}
          className="flex w-[34px] items-center justify-center border-l border-[rgba(255,255,255,0.055)] text-[#52555e] hover:text-[#8a8d96]"
        >
          <ChevronRightIcon className="rotate-180" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-3">
        {isLoading && (
          <div className="flex justify-center py-2">
            <TypingIndicator />
          </div>
        )}
        {!isLoading && messages.length === 0 && (
          <p className="text-center text-[11.5px] text-[#52555e]">No messages yet.</p>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
      </div>

      {/* Input */}
      <ChatInput threadId={firstThread?.id} />
    </aside>
  );
}
