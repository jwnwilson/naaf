import type { Message } from "../../lib/api/hooks";

export interface DayGroup {
  key: string; // YYYY-MM-DD (local)
  label: string; // e.g. "Today · Jul 3"
  messages: Message[];
}

function dayKey(d: Date): string {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function monthDay(d: Date): string {
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function dayLabel(d: Date, now: Date): string {
  const md = monthDay(d);
  const today = dayKey(now);
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (dayKey(d) === today) return `Today · ${md}`;
  if (dayKey(d) === dayKey(yesterday)) return `Yesterday · ${md}`;
  return md;
}

/** Split messages (assumed oldest-first) into consecutive same-day groups. */
export function groupMessagesByDay(messages: Message[], now: Date = new Date()): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const m of messages) {
    const d = new Date(m.createdAt);
    const key = Number.isNaN(d.getTime()) ? "" : dayKey(d);
    const last = groups[groups.length - 1];
    if (last && last.key === key) {
      last.messages.push(m);
    } else {
      groups.push({ key, label: Number.isNaN(d.getTime()) ? "" : dayLabel(d, now), messages: [m] });
    }
  }
  return groups;
}
