import { describe, expect, it } from "vitest";
import { avatarVariant, participantInitials, roleLabel } from "./agentIdentity";

describe("roleLabel", () => {
  it("names the user regardless of role", () => {
    expect(roleLabel("user", null)).toBe("You");
  });
  it("maps known agent roles to their display names", () => {
    expect(roleLabel("agent", "lead")).toBe("Lead Agent");
    expect(roleLabel("agent", "backend")).toBe("Backend Engineer");
  });
  it("title-cases an unknown role and defaults a null agent role", () => {
    expect(roleLabel("agent", "security_reviewer")).toBe("Security Reviewer");
    expect(roleLabel("agent", null)).toBe("Agent");
  });
});

describe("avatarVariant", () => {
  it("maps the user to the circular user avatar", () => {
    expect(avatarVariant({ kind: "user", role: "user" })).toBe("user");
  });
  it("maps the lead agent to the violet agent avatar", () => {
    expect(avatarVariant({ kind: "agent", role: "lead" })).toBe("agent");
  });
  it("maps every other agent role to the muted subagent avatar", () => {
    expect(avatarVariant({ kind: "agent", role: "backend" })).toBe("subagent");
    expect(avatarVariant({ kind: "agent", role: "qa" })).toBe("subagent");
  });
});

describe("participantInitials", () => {
  it("uses the first letters of a two-word display name", () => {
    expect(participantInitials({ kind: "agent", role: "lead", name: "Lead Agent" })).toBe("LA");
    expect(participantInitials({ kind: "agent", role: "backend", name: "Backend Engineer" })).toBe("BE");
  });
  it("shows the owner initials for the user regardless of name", () => {
    expect(participantInitials({ kind: "user", role: "user", name: "You" })).toBe("JW");
  });
  it("falls back to the first two characters of a single-word name", () => {
    expect(participantInitials({ kind: "agent", role: "architect", name: "Architect" })).toBe("AR");
  });
});
