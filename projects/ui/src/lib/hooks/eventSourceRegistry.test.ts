import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { subscribeToEventSource, __clearRegistry } from "./eventSourceRegistry";

// Minimal fake EventSource so we can count instances + drive messages in jsdom.
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onopen: (() => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  emit(data: string) {
    this.onmessage?.({ data });
  }
  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
  __clearRegistry();
  vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
});
afterEach(() => {
  __clearRegistry();
  vi.unstubAllGlobals();
});

test("two subscribers to the same path share one EventSource", () => {
  const a = vi.fn();
  const b = vi.fn();
  subscribeToEventSource(() => "/x/stream?after=0", a);
  subscribeToEventSource(() => "/x/stream?after=0", b);
  expect(FakeEventSource.instances.length).toBe(1);

  FakeEventSource.instances[0].emit("hello");
  expect(a).toHaveBeenCalledWith("hello");
  expect(b).toHaveBeenCalledWith("hello");
});

test("subscribers on the same path but different cursors still share one socket", () => {
  subscribeToEventSource(() => "/x/stream?after=0", vi.fn());
  subscribeToEventSource(() => "/x/stream?after=9", vi.fn());
  // A live socket is not torn down for a newcomer — the second subscriber joins
  // the existing connection (opened at the first cursor); it fills any gap from
  // its own history. Resume-from-highest-cursor only applies on reconnect.
  expect(FakeEventSource.instances.length).toBe(1);
  expect(FakeEventSource.instances[0].url).toBe("/x/stream?after=0");
});

test("socket stays open until the last subscriber unsubscribes", () => {
  const unsubA = subscribeToEventSource(() => "/x/stream?after=0", vi.fn());
  const unsubB = subscribeToEventSource(() => "/x/stream?after=0", vi.fn());
  const es = FakeEventSource.instances[0];

  unsubA();
  expect(es.closed).toBe(false);
  unsubB();
  expect(es.closed).toBe(true);
});

test("different paths get different sockets", () => {
  subscribeToEventSource(() => "/x/stream", vi.fn());
  subscribeToEventSource(() => "/y/stream", vi.fn());
  expect(FakeEventSource.instances.length).toBe(2);
});

test("double-unsubscribe is a harmless no-op", () => {
  const unsub = subscribeToEventSource(() => "/x/stream?after=0", vi.fn());
  expect(() => {
    unsub();
    unsub();
  }).not.toThrow();
  expect(FakeEventSource.instances[0].closed).toBe(true);
});
