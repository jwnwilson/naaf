# ADR-0001: Lean single-uv-workspace structure (no hextech tooling)

**Status:** Accepted (2026-06-29)

## Context

hexrepo is the structural reference, but it carries heavy tooling (the hextech
scaffolding CLI, per-lib CodeArtifact publishing, Terraform per project/env). NAAF is a
single product: one backend server + one UI + a small set of shared libs.

## Decision

Adopt hexrepo's hexagonal **patterns and code** (Repository/UnitOfWork, CrudRouter,
the {success,data,error} envelope, owner-scoping) inside a single `uv` workspace with
`projects/server`, `projects/ui` (A2), and `libs/<pkg>`. Do **not** port hextech, CodeArtifact,
or Terraform. Only genuinely app-agnostic code (e.g. `crud_router`) becomes a workspace lib.

## Consequences

- Shortest path to a running app; less ceremony.
- If NAAF later needs to host many services or cloud publishing, revisit and consider the
  hextech machinery then (YAGNI until then).
