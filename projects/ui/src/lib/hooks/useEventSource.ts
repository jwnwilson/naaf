import { useEffect, useRef } from "react";

export function useEventSource<T>(url: string | null, onMessage: (data: T) => void): void {
  const cb = useRef(onMessage);
  cb.current = onMessage;

  useEffect(() => {
    if (!url) return;
    // Guard: jsdom does not implement EventSource; skip in non-browser environments.
    if (typeof EventSource === "undefined") return;

    const es = new EventSource(url);
    es.onmessage = (e) => {
      try {
        cb.current(JSON.parse(e.data) as T);
      } catch {
        // Ignore malformed frames.
      }
    };
    return () => es.close();
  }, [url]);
}
