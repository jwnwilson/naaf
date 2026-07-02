import { useState } from "react";
import { Avatar } from "../../components/ui/Avatar";
import { Button } from "../../components/ui/Button";
import { useThreadMessages, useSendMessage } from "../../lib/api/hooks";
import type { Message } from "../../lib/api/hooks";

const AGENT_BUBBLE_STYLE: React.CSSProperties = {
  background: "#131618",
  border: "1px solid rgba(255,255,255,0.07)",
  borderRadius: "4px 12px 12px 12px",
  color: "#b0b2b8",
};

const USER_BUBBLE_STYLE: React.CSSProperties = {
  background: "rgba(124,108,240,0.11)",
  border: "1px solid rgba(124,108,240,0.16)",
  borderRadius: "12px 4px 12px 12px",
  color: "#bab7f6",
};

function agentInitials(agentId: string): string {
  return agentId.replace("agent-", "A").toUpperCase();
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "gap-2"} mb-3`}>
      {!isUser && message.agentId && (
        <Avatar
          initials={agentInitials(message.agentId)}
          variant="agent"
          size={22}
        />
      )}
      <div
        className="max-w-[80%] px-3 py-2 text-[12.5px] leading-[1.65]"
        style={isUser ? USER_BUBBLE_STYLE : AGENT_BUBBLE_STYLE}
      >
        {message.content}
      </div>
    </div>
  );
}

export function ConversationPane({ threadId }: { threadId: string }) {
  const { data: messages = [], isLoading } = useThreadMessages(threadId);
  const send = useSendMessage(threadId);
  const [value, setValue] = useState("");
  const disabled = value.trim().length === 0;

  function submit() {
    if (disabled) return;
    send.mutate({ content: value.trim() });
    setValue("");
  }

  return (
    <div className="flex flex-col h-full flex-1 overflow-hidden">
      <div
        className="flex items-center gap-2 shrink-0 px-4"
        style={{ height: 44, borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <Avatar initials="LEAD" variant="agent" size={22} />
        <span className="text-[12.5px] font-medium text-[#c4c5cb]">lead</span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {isLoading && <p className="text-[11px] text-[#30333c]">Loading…</p>}
        {!isLoading && messages.length === 0 && (
          <p className="text-[11px] text-[#30333c]">No messages yet</p>
        )}
        {messages.map((msg: Message) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
      </div>

      <div
        className="shrink-0 px-4 py-3"
        style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
          className="rounded-[6px] px-3 py-2"
          style={{ background: "#0e0f11", border: "1px solid rgba(255,255,255,0.09)" }}
        >
          <div className="flex items-center justify-between gap-2">
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="Reply to agent…"
              className="bg-transparent text-[12px] flex-1 outline-none"
              style={{ color: "#c4c5cb" }}
            />
            <Button type="submit" variant="primary" disabled={disabled}>
              Send ↑
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
