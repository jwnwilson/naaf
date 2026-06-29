import { Avatar } from "../../components/ui/Avatar";
import { Button } from "../../components/ui/Button";
import { StatusBadge } from "../../components/ui/StatusBadge";
import type { components } from "../../lib/api/schema";
import { useInboxConversation } from "./useInboxConversation";

type InboxItem = components["schemas"]["InboxItem"];
type Message = components["schemas"]["Message"];

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

export function ConversationPane({ item }: { item: InboxItem }) {
  const { data, isLoading } = useInboxConversation(item.conversationId);
  const messages = data?.results ?? [];

  return (
    <div className="flex flex-col h-full flex-1 overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center gap-2 shrink-0 px-4"
        style={{
          height: 44,
          borderBottom: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <Avatar
          initials={agentInitials(item.agentId)}
          variant="agent"
          size={22}
        />
        <span className="text-[12.5px] font-medium text-[#c4c5cb]">
          {item.agentId}
        </span>
        <span className="font-mono text-[11px] text-[#7c6cf0]">
          {item.workItemId}
        </span>
        <StatusBadge kind={item.type} />
        <div className="flex-1" />
        <Button variant="secondary">View PR</Button>
        <Button variant="tertiary">Dismiss</Button>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {isLoading && (
          <p className="text-[11px] text-[#30333c]">Loading…</p>
        )}
        {!isLoading && messages.length === 0 && (
          <p className="text-[11px] text-[#30333c]">No messages yet</p>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {/* Quick actions shown when there are messages */}
        {messages.length > 0 && (
          <div className="flex gap-2 mt-2">
            <Button variant="primary">Approve PR</Button>
            <Button variant="secondary">Request changes</Button>
            <Button variant="tertiary">Skip</Button>
          </div>
        )}
      </div>

      {/* Reply input (display-only for A2) */}
      <div
        className="shrink-0 px-4 py-3"
        style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}
      >
        <div
          className="rounded-[6px] px-3 py-2"
          style={{
            background: "#0e0f11",
            border: "1px solid rgba(255,255,255,0.09)",
          }}
        >
          {/* Context chips */}
          <div className="flex gap-2 mb-2">
            <span
              className="text-[10.5px] font-mono px-[6px] py-[2px] rounded"
              style={{
                background: "rgba(124,108,240,0.10)",
                color: "#bab7f6",
              }}
            >
              @{item.agentId}
            </span>
            <span className="text-[10.5px] text-[#30333c] cursor-pointer">
              + attach
            </span>
          </div>

          {/* Input row */}
          <div className="flex items-center justify-between gap-2">
            <input
              readOnly
              placeholder="Reply to agent…"
              className="bg-transparent text-[12px] flex-1 outline-none"
              style={{ color: "#8a8d96" }}
            />
            <Button variant="primary" disabled>
              Send ↑
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
