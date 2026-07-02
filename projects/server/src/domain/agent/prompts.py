from domain.agent.context import StageContext
from domain.runs.run import Stage

_BASE = (
    "You are an autonomous software engineer working in a git workspace. "
    "Use the provided tools to inspect and change files and run commands. "
    "When you have completed the stage, stop calling tools and give a one-line summary."
)

_STAGE_INSTRUCTIONS = {
    Stage.PLAN: "Read the ticket and relevant files, then write an implementation plan to plan.md.",
    Stage.PROVISION: "Ensure the workspace is on a fresh agent branch and note anything needed.",
    Stage.IMPLEMENT: "Implement the ticket. Edit files, run the build, and commit your changes.",
    Stage.VERIFY: (
        "You are QA in a fresh context. Run the tests, lint, and build, and check the "
        "acceptance criteria. Report whether the work is done."
    ),
    Stage.PR: (
        "Push the agent branch and run `gh pr create` to open a pull request summarizing the "
        "plan, changes, and QA result. End your reply with the PR URL on its own line."
    ),
    Stage.LEARN: (
        "You are the curator. Distill durable, reusable lessons from this run into a short "
        "memory diff, append them to the project memory file (CLAUDE.md or AGENTS.md), and "
        "commit the change. Keep it concise."
    ),
}


def system_prompt(ctx: StageContext) -> str:
    persona = ctx.agent.persona_prompt or f"You are the {ctx.role} agent."
    return f"{persona}\n\n{_BASE}"


def stage_instruction(ctx: StageContext) -> str:
    wi = ctx.work_item
    criteria = "\n".join(f"- {c}" for c in wi.acceptance_criteria) or "- (none given)"
    return (
        f"# Ticket: {wi.title}\n\n{wi.body}\n\n"
        f"## Acceptance criteria\n{criteria}\n\n"
        f"## Your task ({ctx.stage.value})\n{_STAGE_INSTRUCTIONS[ctx.stage]}"
    )
