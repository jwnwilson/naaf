import { useRef } from "react";
import { useAttachments } from "../../lib/api/hooks/useAttachments";
import { useUploadAttachment } from "../../lib/api/hooks/useUploadAttachment";
import { useDeleteAttachment } from "../../lib/api/hooks/useDeleteAttachment";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AttachmentsPanel({ workItemId }: { workItemId: string }) {
  const { data: attachments = [], isLoading } = useAttachments(workItemId);
  const upload = useUploadAttachment(workItemId);
  const remove = useDeleteAttachment(workItemId);
  const inputRef = useRef<HTMLInputElement>(null);

  const onPick = (file: File | undefined) => {
    if (!file) return;
    const exists = attachments.some((a) => a.filename === file.name);
    if (exists && !window.confirm(`${file.name} already exists — overwrite it?`)) return;
    upload.mutate({ file, overwrite: exists });
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-auto p-4">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[11px] text-[#8b8f9a]">Attachments</span>
        <label className="cursor-pointer font-mono text-[11px] text-[#bab7f6]">
          + Upload
          <input
            ref={inputRef}
            data-testid="attachment-input"
            type="file"
            className="hidden"
            onChange={(e) => onPick(e.target.files?.[0])}
          />
        </label>
      </div>

      {isLoading && (
        <span className="font-mono text-[11px] text-[#42454e]">Loading…</span>
      )}
      {!isLoading && attachments.length === 0 && (
        <span className="font-mono text-[11px] text-[#42454e]">No attachments</span>
      )}

      <ul className="flex flex-col gap-1">
        {attachments.map((a) => (
          <li
            key={a.id}
            className="flex items-center justify-between rounded px-2 py-1 hover:bg-white/5"
          >
            <a
              href={`/api${a.url}`}
              target="_blank"
              rel="noreferrer"
              className="font-mono text-[11.5px] text-[#d6d3f0]"
            >
              {a.filename}
            </a>
            <span className="flex items-center gap-3">
              <span className="font-mono text-[10px] text-[#42454e]">
                {a.contentType}
              </span>
              <span className="font-mono text-[10px] text-[#42454e]">
                {formatSize(a.size)}
              </span>
              <button
                type="button"
                onClick={() => remove.mutate(a.id)}
                className="font-mono text-[10px] text-[#e06c75]"
              >
                delete
              </button>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
