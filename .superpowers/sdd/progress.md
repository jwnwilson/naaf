# Inbox thread → work-item link — SDD execution ledger

Plan: docs/superpowers/plans/2026-07-05-inbox-thread-work-item-link.md
Worktree: .worktrees/inbox-thread-link  (branch feat/inbox-thread-work-item-link)
Base: origin/main @ 312f1f7

## Tasks
- Task 1: backend ThreadView.project_id — pending
- Task 2: backend ThreadOut.projectId — pending
- Task 3: OpenAPI yaml + schema regen — pending
- Task 4: mock db + fixtures projectId — pending
- Task 5: banner -> Link — pending
- Task 6: gates + PR — pending

## Log
Task 1: complete (commits 99bee99..f7ab91f, review clean)
  Minor (defer to final): add explicit test for thread_from_project().project_id == project.id
Task 2: complete (commits f7ab91f..54dd63f, review clean)
Task 3: complete (commits 54dd63f..32a2c16, review clean)
Task 4: complete (commits 32a2c16..34a0142, review clean)
  Minor (defer to final): handlers.test.ts projectId assertion uses toBeTruthy() — prefer toBe("proj-1")
Task 5: complete (commits 34a0142..ee839c7, review clean after 1 fix loop: added project-thread test + inline-block truncate)
