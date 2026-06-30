import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "../lib/api/mocks/server";
import { db } from "../lib/api/mocks/db";

// Polyfill localStorage for jsdom environments that stub it without full Storage API
const makeLocalStorage = () => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = String(value); },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
    get length() { return Object.keys(store).length; },
    key: (index: number) => Object.keys(store)[index] ?? null,
  };
};
Object.defineProperty(globalThis, "localStorage", {
  value: makeLocalStorage(),
  writable: true,
  configurable: true,
});

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  db.reset();
  localStorage.clear();
});
afterAll(() => server.close());
