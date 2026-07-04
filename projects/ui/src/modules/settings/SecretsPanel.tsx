import { useState } from "react";
import { Button, TextInput } from "../../components/ui";
import { useDeleteSecret, useSecrets, useSetSecret, type Secret } from "../../lib/api/hooks/useSecrets";

interface Field {
  name: string;
  label: string;
  placeholder: string;
}

const FIELDS: Field[] = [
  { name: "anthropic_api_key", label: "Anthropic API key", placeholder: "sk-ant-…" },
  { name: "github_token", label: "GitHub token", placeholder: "ghp_…" },
];

function SecretRow({ field, secret }: { field: Field; secret: Secret | undefined }) {
  const [value, setValue] = useState("");
  const set = useSetSecret(field.name);
  const del = useDeleteSecret(field.name);
  const isSet = secret?.isSet ?? false;
  const canSave = value.trim().length > 0 && !set.isPending;

  async function save() {
    if (!value.trim()) return;
    try {
      await set.mutateAsync(value);
    } catch {
      return; // error surfaced below
    }
    setValue(""); // never keep the raw value around
  }

  return (
    <div className="flex flex-col gap-1 border-b border-[rgba(255,255,255,0.06)] pb-4">
      <div className="flex items-center gap-2">
        <label className="text-[12px] text-text-1">{field.label}</label>
        <span className="font-mono text-[10.5px]" style={{ color: isSet ? "#7c8" : "#52555e" }}>
          {isSet ? `Set ••••${secret?.hint}` : "Not set"}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <TextInput
          type="password"
          aria-label={field.label}
          value={value}
          placeholder={field.placeholder}
          onChange={(e) => setValue(e.target.value)}
        />
        <Button variant="primary" disabled={!canSave} onClick={() => { void save(); }}>
          {set.isPending ? "Saving…" : "Save"}
        </Button>
        {isSet && (
          <Button variant="secondary" disabled={del.isPending} onClick={() => del.mutate()}>
            Clear
          </Button>
        )}
      </div>
      {set.isError && (
        <p className="text-[10.5px] text-[#e5686b]">
          {set.error instanceof Error ? set.error.message : String(set.error)}
        </p>
      )}
    </div>
  );
}

export function SecretsPanel() {
  const { data: secrets = [], isLoading } = useSecrets();
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 style={{ fontSize: 15, fontWeight: 600, color: "var(--text-1)", marginBottom: 4 }}>
          Secrets
        </h2>
        <p className="text-[11px] text-text-3">
          Stored encrypted and injected into agent runs. Values are write-only — never shown after saving.
        </p>
      </div>
      {isLoading && <p className="text-[12px] text-text-3">Loading…</p>}
      <div className="flex flex-col gap-4 max-w-[520px]">
        {FIELDS.map((f) => (
          <SecretRow key={f.name} field={f} secret={secrets.find((s) => s.name === f.name)} />
        ))}
      </div>
    </div>
  );
}
