import type { ReactNode } from "react";
import { Avatar } from "../ui/Avatar";
import type { Message } from "../../lib/api/hooks";
import { avatarVariant, participantInitials, roleLabel } from "../../lib/agentIdentity";
import { renderContent } from "./renderContent";

type FileWritePayload = { path: string; lines?: number };
type QuestionOption = { id: string; label: string };
type QuestionPayload = { options: QuestionOption[]; resolved_option?: string | null };

function isFileWritePayload(p: unknown): p is FileWritePayload {
  return typeof p === "object" && p !== null && "path" in p;
}

function isQuestionPayload(p: unknown): p is QuestionPayload {
  return (
    typeof p === "object" &&
    p !== null &&
    "options" in p &&
    Array.isArray((p as QuestionPayload).options)
  );
}

/** "10:38:04" — the time-of-day shown next to the author name (design D3). */
function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

function ModelBadge({ model }: { model: string }) {
  return (
    <span
      className="font-mono"
      style={{
        fontSize: 9,
        padding: "1px 6px",
        borderRadius: 3,
        background: "rgba(124,108,240,0.1)",
        border: "1px solid rgba(124,108,240,0.2)",
        color: "#7c6cf0",
      }}
    >
      {model}
    </span>
  );
}

function FileWriteCard({ payload }: { payload: FileWritePayload }) {
  return (
    <div
      className="flex items-center gap-2 rounded-[6px] px-2.5 py-2 max-w-[300px]"
      style={{ background: "#0e0f11", border: "1px solid rgba(255,255,255,0.06)" }}
    >
      <svg width="12" height="14" viewBox="0 0 12 14" fill="none" style={{ flex: "none", color: "#3a3d44" }}>
        <rect x=".75" y=".75" width="10.5" height="12.5" rx="1.5" stroke="currentColor" strokeWidth="1" />
        <path d="M3 5h6M3 7.5h6M3 10h4" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
      </svg>
      <div className="min-w-0">
        <div className="font-mono text-[11px] text-[#7c6cf0] truncate">{payload.path}</div>
        <div className="text-[9.5px] text-[#42454e] mt-px">
          written{payload.lines !== undefined ? ` · ${payload.lines} lines` : ""}
        </div>
      </div>
    </div>
  );
}

const AGENT_BUBBLE = {
  background: "#131618",
  border: "1px solid rgba(255,255,255,0.07)",
  borderRadius: "3px 10px 10px 10px",
  color: "#b0b2b8",
} as const;

const USER_BUBBLE = {
  background: "rgba(124,108,240,0.11)",
  border: "1px solid rgba(124,108,240,0.18)",
  borderRadius: "10px 3px 10px 10px",
  color: "#bab7f6",
} as const;

interface MessageItemProps {
  message: Message;
  onAnswer?: (msgId: string, option: string) => void;
  answering?: boolean;
}

export function MessageItem({ message, onAnswer, answering }: MessageItemProps) {
  const isUser = message.authorKind === "user";
  const name = roleLabel(message.authorKind, message.authorRole);
  const time = formatTime(message.createdAt);
  const variant = avatarVariant({ kind: message.authorKind, role: message.authorRole ?? "" });
  const initials = participantInitials({
    kind: message.authorKind,
    role: message.authorRole ?? "",
    name,
  });

  return (
    <div className={`flex gap-2.5 mb-3.5 items-start ${isUser ? "flex-row-reverse" : ""}`}>
      <Avatar initials={initials} variant={variant} size={26} />
      <div className={`min-w-0 flex flex-col ${isUser ? "items-end" : ""}`}>
        <div className="flex items-baseline gap-2 mb-1">
          {isUser && time && (
            <span className="font-mono text-[9.5px] text-[#2e3038]">{time}</span>
          )}
          <span className="text-[12.5px] font-semibold text-[#c4c5cb]">{name}</span>
          {!isUser && time && (
            <span className="font-mono text-[9.5px] text-[#2e3038]">{time}</span>
          )}
          {!isUser && message.model && <ModelBadge model={message.model} />}
        </div>
        {messageBody(message, onAnswer, answering, isUser)}
      </div>
    </div>
  );
}

function messageBody(
  message: Message,
  onAnswer: MessageItemProps["onAnswer"],
  answering: boolean | undefined,
  isUser: boolean,
): ReactNode {
  if (message.kind === "file_write" && isFileWritePayload(message.payload)) {
    return (
      <div className="flex flex-col gap-1.5 items-start">
        {message.content && (
          <div className="px-3 py-2 text-[12.5px] leading-[1.6] max-w-[600px]" style={AGENT_BUBBLE}>
            {renderContent(message.content, message.mentions)}
          </div>
        )}
        <FileWriteCard payload={message.payload} />
      </div>
    );
  }

  if (message.kind === "question" && isQuestionPayload(message.payload)) {
    const payload = message.payload;
    return (
      <div className="px-3 py-2 text-[12.5px] leading-[1.6] max-w-[600px]" style={AGENT_BUBBLE}>
        <p className="mb-2">{renderContent(message.content, message.mentions)}</p>
        <div className="flex flex-wrap gap-1.5">
          {payload.options.map((option) => {
            const isResolved = option.id === payload.resolved_option;
            return (
              <button
                key={option.id}
                type="button"
                disabled={payload.resolved_option != null || answering}
                onClick={() => onAnswer?.(message.id, option.id)}
                className="rounded-[4px] px-2.5 py-1 text-[11px] font-medium"
                style={{
                  background: isResolved ? "rgba(124,108,240,0.30)" : "rgba(124,108,240,0.12)",
                  border: isResolved ? "1px solid rgba(124,108,240,0.60)" : "1px solid rgba(124,108,240,0.24)",
                  color: "#bab7f6",
                }}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  // text / event — default bubble
  return (
    <div
      className="px-3 py-2 text-[12.5px] leading-[1.6] max-w-[600px]"
      style={isUser ? USER_BUBBLE : AGENT_BUBBLE}
    >
      {renderContent(message.content, message.mentions)}
    </div>
  );
}
