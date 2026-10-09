# AGENTS.md

## Before starting to code

- Keep `PLAN.md` updated as work progresses. Tick phases off.
- Keep `STRUCTURE.md` and `ARCHITECTURE.md` in sync with the real code.
- `.log` files are our friends — use them from one session to another.

## Todo-list discipline (support files are the todo list)

- Every non-trivial task gets a detailed checklist in `PLAN.md` *before* coding starts: what, why, in which files, how to verify. No checklist, no code.
- Tick items off in `PLAN.md` as they complete — never batch the ticking at the end.
- Record progress, decisions, and open issues in `session.log` throughout the session, so the next session can resume from files alone.
- If reality diverges from the plan (new bug found, scope change), update `PLAN.md` first, then continue coding.

## Behave

- KISS — don't overengineer.
- Ask questions rather than assume.
- Don't rebuild what already exists — reuse stdlib, reuse the old repo's

## The two hard rules

- being able to run on lowend, old machine is a nice-to-have, something to aim for.

## Testing

- Run the test suite before committing:

## Git

- commit before changing the code.
- Commit in meaningful chunks; don't fill history with tiny commits.
- Never commit `.env` or secrets.
</content>
