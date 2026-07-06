import { useState } from "react";
import { Button } from "../ui/Button";
import { useSendMessage } from "../../lib/api/hooks";

const ROLES = ["lead", "architect", "backend", "frontend", "qa", "devops"] as const;
type Role = (typeof ROLES)[number];

interface ThreadComposerProps {
  workItemId: string;
  placeholder?: string;
}

export function ThreadComposer({
  workItemId,
  placeholder = "Reply…",
}: ThreadComposerProps) {
  const [value, setValue] = useState("");
  const send = useSendMessage(workItemId);
  const disabled = value.trim().length === 0;

  function submit() {
    if (disabled) return;
    send.mutate({ content: value.trim() });
    setValue("");
  }

  function insertMention(role: Role) {
    const separator = value.length > 0 && !value.endsWith(" ") ? " " : "";
    setValue(`${value}${separator}@${role} `);
  }

  return (
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
            data-testid="thread-composer-input"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={placeholder}
            className="bg-transparent text-[12px] flex-1 outline-none"
            style={{ color: "#c4c5cb" }}
          />
          <Button data-testid="thread-composer-send" type="submit" variant="primary" disabled={disabled}>
            Send ↑
          </Button>
        </div>
        <div className="flex flex-wrap gap-1 mt-2">
          {ROLES.map((role) => (
            <button
              key={role}
              type="button"
              onClick={() => insertMention(role)}
              className="inline-flex items-center h-[20px] px-[7px] rounded-[4px] border border-[rgba(255,255,255,0.09)] font-mono text-[10px] text-[rgba(255,255,255,0.35)] hover:text-[rgba(255,255,255,0.6)] hover:border-[rgba(255,255,255,0.18)] transition-colors"
            >
              @{role}
            </button>
          ))}
        </div>
      </form>
    </div>
  );
}
