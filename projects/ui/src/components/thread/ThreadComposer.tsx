import { useState } from "react";
import { Button } from "../ui/Button";
import { useSendMessage } from "../../lib/api/hooks";

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
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={placeholder}
            className="bg-transparent text-[12px] flex-1 outline-none"
            style={{ color: "#c4c5cb" }}
          />
          <Button type="submit" variant="primary" disabled={disabled}>
            Send ↑
          </Button>
        </div>
      </form>
    </div>
  );
}
