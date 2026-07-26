type Subscriber = (raw: string) => void;
type UrlGetter = () => string | null;

interface Entry {
  es: EventSource | null;
  subscribers: Set<Subscriber>;
  urlGetters: Set<UrlGetter>;
  attempt: number;
  timer: ReturnType<typeof setTimeout> | undefined;
  stopped: boolean;
}

// Keyed by connection *path* (url without query). Duplicate subscribers to the
// same stream (e.g. a chat panel + a detail tab on one thread) share one
// EventSource, and an advancing `?after=` cursor updates the resume value
// without churning the socket.
const registry = new Map<string, Entry>();

/**
 * The connection identity of an SSE url: its path without the query string.
 *
 * Two urls that differ only in query (an advancing `?after=` cursor) share one
 * connection, so the live stream is not torn down every time the cursor moves —
 * the new cursor is used only on the next reconnect.
 */
export function ssePath(url: string | null): string | null {
  return url ? url.split("?")[0] : null;
}

/** Capped exponential backoff (ms) for reconnect attempt `attempt` (0-based). */
export function reconnectDelay(attempt: number, baseMs = 1000, maxMs = 15000): number {
  return Math.min(baseMs * 2 ** attempt, maxMs);
}

/**
 * The url to (re)connect with: the highest `?after=` cursor among the path's
 * subscribers, so a resuming reconnect picks up from the furthest-along cursor
 * instead of replaying the backlog. Subscribers to one stream share a history
 * query, so their cursors track together; any that is briefly behind fills the
 * gap from its own history fetch.
 */
function resolveUrl(entry: Entry): string | null {
  let best: string | null = null;
  let bestAfter = -1;
  for (const get of entry.urlGetters) {
    const url = get();
    if (!url) continue;
    const after = Number(new URLSearchParams(url.split("?")[1] ?? "").get("after") ?? "0");
    if (after >= bestAfter) {
      bestAfter = after;
      best = url;
    }
  }
  return best;
}

function connect(path: string): void {
  const entry = registry.get(path);
  if (!entry || entry.stopped) return;
  const url = resolveUrl(entry);
  if (!url) return;
  const es = new EventSource(url);
  entry.es = es;
  es.onopen = () => {
    entry.attempt = 0; // healthy connection resets the backoff
  };
  es.onmessage = (e: MessageEvent) => {
    for (const sub of entry.subscribers) sub(e.data as string);
  };
  es.onerror = () => {
    // Native EventSource retries transient drops but gives up on hard failures;
    // drive our own capped-backoff reconnect so recovery is deterministic and
    // always resumes from the latest cursor.
    es.close();
    if (entry.stopped) return;
    entry.timer = setTimeout(() => connect(path), reconnectDelay(entry.attempt));
    entry.attempt += 1;
  };
}

/**
 * Subscribe to a server-sent-event stream, sharing one resilient EventSource
 * across all subscribers of the same url *path*. The socket opens on the first
 * subscriber, reconnects on error with capped backoff (resuming from the latest
 * cursor), and closes when the last subscriber unsubscribes. `getUrl` returns
 * the current url (with the live `?after=` cursor), read at connect time. Raw
 * `event.data` strings are forwarded; callers parse. Returns an unsubscribe fn.
 */
export function subscribeToEventSource(getUrl: UrlGetter, onMessage: Subscriber): () => void {
  const path = ssePath(getUrl());
  if (!path) return () => {};

  let entry = registry.get(path);
  if (!entry) {
    entry = {
      es: null,
      subscribers: new Set(),
      urlGetters: new Set(),
      attempt: 0,
      timer: undefined,
      stopped: false,
    };
    registry.set(path, entry);
    entry.subscribers.add(onMessage);
    entry.urlGetters.add(getUrl);
    connect(path);
  } else {
    entry.subscribers.add(onMessage);
    entry.urlGetters.add(getUrl);
  }

  return () => {
    const current = registry.get(path);
    if (!current) return;
    current.subscribers.delete(onMessage);
    current.urlGetters.delete(getUrl);
    if (current.subscribers.size === 0) {
      current.stopped = true;
      if (current.timer) clearTimeout(current.timer);
      current.es?.close();
      registry.delete(path);
    }
  };
}

/** Test-only: close every live socket and clear registry state. Never call in app code. */
export function __clearRegistry(): void {
  for (const entry of registry.values()) {
    entry.stopped = true;
    if (entry.timer) clearTimeout(entry.timer);
    entry.es?.close();
  }
  registry.clear();
}
