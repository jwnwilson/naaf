import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ThreadDetail } from "../../lib/api/hooks/useThread";
import { ThreadRail } from "./ThreadRail";

const thread: ThreadDetail = {
  id: "wi-42",
  workItemId: "wi-42",
  projectId: "proj-1",
  title: "OAuth refresh",
  status: "in_progress",
  lastMessage: null,
  messageCount: 7,
  participants: ["lead", "backend", "user"],
  participantDetails: [
    { kind: "user", role: "user", name: "You", model: null, status: null },
    { kind: "agent", role: "lead", name: "Lead Agent", model: "claude-opus-4", status: "idle" },
    { kind: "agent", role: "backend", name: "Backend Engineer", model: "claude-opus-4", status: "running" },
  ],
  createdAt: "2026-07-03T10:38:00Z",
  filesWritten: [{ path: "src/auth/refresh.py" }],
};

vi.mock("../../lib/api/hooks", () => ({ useThread: () => ({ data: thread }) }));

describe("ThreadRail", () => {
  it("lists each participant with its display name", () => {
    render(<ThreadRail workItemId="wi-42" />);
    expect(screen.getByText("Lead Agent")).toBeInTheDocument();
    expect(screen.getByText("Backend Engineer")).toBeInTheDocument();
  });

  it("shows role subtitles for user and lead, and status for subagents", () => {
    render(<ThreadRail workItemId="wi-42" />);
    expect(screen.getByText("Owner")).toBeInTheDocument();
    expect(screen.getByText("Orchestrator")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  it("renders a THREAD INFO section with the message count", () => {
    render(<ThreadRail workItemId="wi-42" />);
    expect(screen.getByText("THREAD INFO")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("lists files written", () => {
    render(<ThreadRail workItemId="wi-42" />);
    expect(screen.getByText("src/auth/refresh.py")).toBeInTheDocument();
  });
});
