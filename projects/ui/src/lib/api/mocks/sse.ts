import type { components } from "../schema";

type RunEventOut = components["schemas"]["RunEventOut"];

/** Build a ReadableStream that emits SSE frames for the given RunEventOut list. */
export function buildEventStream(events: RunEventOut[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();

  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const event of events) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
      }
      controller.close();
    },
  });
}
