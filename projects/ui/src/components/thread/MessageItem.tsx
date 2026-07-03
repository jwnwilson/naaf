import { Avatar } from "../ui/Avatar";
import type { Message } from "../../lib/api/hooks";

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

interface MessageItemProps {
  message: Message;
  onAnswer?: (msgId: string, option: string) => void;
  answering?: boolean;
}

export function MessageItem({ message, onAnswer, answering }: MessageItemProps) {
  const isUser = message.authorKind === "user";

  if (message.kind === "file_write" && isFileWritePayload(message.payload)) {
    return (
      <div className="mb-3">
        <div
          className="rounded-[6px] px-3 py-2 text-[11.5px]"
          style={{
            background: "#0d1117",
            border: "1px solid rgba(255,255,255,0.08)",
            color: "#7c6cf0",
          }}
        >
          <p className="font-mono text-[10.5px] text-[#52555e] mb-0.5">file_write</p>
          <p className="font-mono truncate">{message.payload.path}</p>
          {message.payload.lines !== undefined && (
            <p className="text-[10.5px] text-[#30333c] mt-0.5">
              {message.payload.lines} lines
            </p>
          )}
        </div>
      </div>
    );
  }

  if (message.kind === "question" && isQuestionPayload(message.payload)) {
    const payload = message.payload;
    return (
      <div className="mb-3">
        <div
          className="px-3 py-2 text-[12.5px]"
          style={{
            background: "#131618",
            border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: "3px 10px 10px 10px",
            color: "#b0b2b8",
          }}
        >
          <p className="mb-2">{message.content}</p>
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
                    background: isResolved
                      ? "rgba(124,108,240,0.30)"
                      : "rgba(124,108,240,0.12)",
                    border: isResolved
                      ? "1px solid rgba(124,108,240,0.60)"
                      : "1px solid rgba(124,108,240,0.24)",
                    color: "#bab7f6",
                  }}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  // text / event — default bubble
  return (
    <div className={`flex ${isUser ? "justify-end" : "gap-2"} mb-3`}>
      {!isUser && (
        <Avatar
          initials={(message.authorRole ?? "ag").slice(0, 2).toUpperCase()}
          variant="agent"
          size={22}
        />
      )}
      <div
        className="max-w-[80%] px-3 py-2 text-[12.5px] leading-[1.65]"
        style={
          isUser
            ? {
                background: "rgba(124,108,240,0.11)",
                border: "1px solid rgba(124,108,240,0.16)",
                borderRadius: "10px 3px 10px 10px",
                color: "#bab7f6",
              }
            : {
                background: "#131618",
                border: "1px solid rgba(255,255,255,0.07)",
                borderRadius: "3px 10px 10px 10px",
                color: "#b0b2b8",
              }
        }
      >
        {message.content}
        {message.authorKind === "agent" && message.model && (
          <p className="mt-1 text-[9.5px] font-mono text-[#30333c]">
            {message.model}
          </p>
        )}
      </div>
    </div>
  );
}
