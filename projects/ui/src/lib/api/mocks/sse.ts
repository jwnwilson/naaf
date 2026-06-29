import type { components } from "../schema";

type LogLine = components["schemas"]["LogLine"];

/** Build a ReadableStream that emits a scripted SSE sequence for a fixture run. */
export function buildRunStream(): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();

  const frames: LogLine[] = [
    {
      timestamp: new Date().toISOString(),
      type: "status",
      tool: null,
      target: null,
      message: "Streaming: starting generate phase",
    },
    {
      timestamp: new Date().toISOString(),
      type: "tool_call",
      tool: "write_file",
      target: "src/sandbox/runner.py",
      message: null,
    },
    {
      timestamp: new Date().toISOString(),
      type: "result",
      tool: "write_file",
      target: "src/sandbox/runner.py",
      message: "File written successfully",
    },
  ];

  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(frame)}\n\n`));
      }
      controller.close();
    },
  });
}
