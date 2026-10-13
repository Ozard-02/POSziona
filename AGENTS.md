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

- Run the test suite before committing: `venv/bin/pytest tests/ -q`

## Autonomous long-run mode (directive 2026-10-13, user absent)

- Work indefinitely alone. Keep momentum via small working increments.
- Git is the safety net: commit only *working* features (suite green),
  in meaningful chunks with clear messages. Push to `origin main` when a
  chunk is verified; tags/releases only when explicitly planned in PLAN.md.
- Md files are the memory: `PLAN.md` (checklists + status), `session.log`
  (decisions, findings, open issues), `STRUCTURE.md`/`ARCHITECTURE.md`
  (kept in sync with real code), `docs/` for deep dives. Next session must
  be able to resume from files alone.
- Safety first while unsupervised: read-only investigation before action;
  never kill user processes, never touch live `~/.posziona` data or occupied
  ports (tests must skip when the port is busy); no `rm -rf`, no force-push,
  no `ps | kill` pipelines (match own shell — use `[b]racket` patterns);
  one process per `DATA_DIR`; verify commands are non-destructive.

## Production-quality roadmap (goal: de-facto FOSS POS for small parties)

Order is binding: R first, then C, then S.

### Phase R — Refactor to production quality (do first)
- KISS: remove overengineering, apply best practices, simplify where the
  real code diverged from STRUCTURE.md/ARCHITECTURE.md notes.
- Tests: prune useless/redundant ones, keep only thoughtful tests (one
  behavior per test, no false-positive mocks). Suite must stay fast and green.
- No new features during R unless needed to unblock the refactor.

### Phase C — Connection / discovery / login completion (do second)
- Reason explicitly about topologies with 2 machines on one party: same-box
  (server + client sharing DATA_DIR), LAN Wi-Fi (one server, N clients),
  hotspot (incl. client-isolating ones), server on a different network.
  Exactly ONE server ever (split-brain = split sales); enforce/guide this.
- Polish login + server-pick + persistent data until a non-technical
  operator can't get lost (identity line, one-tap reconnect, no dead pages).
- Study how comparable software solves discovery/reconnect/offline
  (other FOSS POS, Odoo/UniCenta lessons in docs/requirements.md) and adopt
  proven patterns instead of inventing.
- Track live-verification gaps honestly (sandbox can't prove LAN broadcast).

### Phase S — Own suggestions (do last)
- Only after R + C are concluded. Propose in PLAN.md first, then implement.

## Git

- commit before changing the code.
- Commit in meaningful chunks; don't fill history with tiny commits.
- Never commit `.env` or secrets.
</content>
