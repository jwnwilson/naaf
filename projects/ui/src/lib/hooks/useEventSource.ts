import { useEffect, useRef } from "react";
import { ssePath, subscribeToEventSource } from "./eventSourceRegistry";

export { reconnectDelay, ssePath } from "./eventSourceRegistry";

/**
 * Resilient, shared SSE subscription.
 *
 * Delegates to a per-path registry so that:
 * - duplicate subscribers to the same stream path share ONE EventSource
 *   (a chat panel + a detail tab on the same thread don't open two sockets);
 * - the connection is keyed on the url *path*, so an advancing `?after=` cursor
 *   updates the resume value without tearing down the live stream;
 * - a dropped connection reconnects with capped backoff, resuming from the
 *   latest cursor.
 */
export function useEventSource<T>(url: string | null, onMessage: (data: T) => void): void {
  const cb = useRef(onMessage);
  cb.current = onMessage;
  // Latest url (with the current cursor), read by the registry at (re)connect time.
  const urlRef = useRef(url);
  urlRef.current = url;

  const path = ssePath(url);

  useEffect(() => {
    if (!path) return;
    // Guard: jsdom does not implement EventSource; skip in non-browser environments.
    if (typeof EventSource === "undefined") return;

    const unsubscribe = subscribeToEventSource(
      () => urlRef.current,
      (raw) => {
        try {
          cb.current(JSON.parse(raw) as T);
        } catch {
          // Ignore malformed frames.
        }
      },
    );
    return unsubscribe;
  }, [path]);
}
