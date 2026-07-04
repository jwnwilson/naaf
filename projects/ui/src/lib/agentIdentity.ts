import type { components } from "./api/schema";

type Participant = components["schemas"]["ThreadParticipant"];
/** The identity fields we need — accepts a full participant or a message-derived shape. */
type Identity = Pick<Participant, "kind" | "role"> & { name?: string };

export type AvatarVariant = "user" | "agent" | "subagent";

// Mirrors the backend ROLE_LABELS (domain/messaging/thread.py) so a message —
// which carries only a role, not the enriched participant name — can render the
// same display name as the participants rail.
const ROLE_LABELS: Record<string, string> = {
  user: "You",
  lead: "Lead Agent",
  architect: "Architect",
  backend: "Backend Engineer",
  frontend: "Frontend Engineer",
  qa: "QA Engineer",
  devops: "DevOps Engineer",
};

export function roleLabel(kind: string, role: string | null | undefined): string {
  if (kind === "user") return ROLE_LABELS.user;
  const key = role ?? "";
  return ROLE_LABELS[key] ?? (key ? key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "Agent");
}

/**
 * Avatar styling for a thread participant. The lead agent is the violet
 * "agent" avatar; other agent roles use the muted "subagent" avatar so the
 * orchestrator is visually distinct from its subagents (design frame D3).
 */
export function avatarVariant(identity: Identity): AvatarVariant {
  if (identity.kind === "user") return "user";
  return identity.role === "lead" ? "agent" : "subagent";
}

/**
 * Two-letter avatar initials. The user shows the owner's initials to match the
 * sidebar avatar; agents use the initials of their display name (e.g.
 * "Lead Agent" → "LA", "Backend Engineer" → "BE").
 */
export function participantInitials(identity: Identity): string {
  if (identity.kind === "user") return "JW";
  const name = identity.name ?? identity.role;
  const words = name.trim().split(/\s+/);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}
