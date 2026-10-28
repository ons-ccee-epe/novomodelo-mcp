---
paths:
  - "*.md"
  - "docs/**/*.md"
  - ".claude/rules/*.md"
---

# novomodelo-mcp Prose Documentation Integrity Rules

Governs every Markdown file that serves as a user-facing or agent-facing
artifact: `CLAUDE.md`, `README.md`, `docs/**`, and `.claude/rules/*`. The
code-comment counterpart is `.claude/rules/comments.md`.

## 1. Reader per doc

- **CLAUDE.md / `.claude/rules/*`** — an agent that acts on assertions.
  Durability and anti-drift dominate; a stale claim here is executed, not read.
- **README.md** — operators configuring and running the server, most with no
  checkout. Teaching voice is the job; promotional voice is not (§4). It is the
  source of truth for the environment-variable table, the tool list, and the
  security model.
- **docs/** — the same reader as README; the same rules apply.

## 2. The one adaptation that does the heavy lifting

> **Name the external contract (env var / flag / tool name / path), but never
> freeze a COUNT, VERSION, ENUMERATION, or run-snapshot NUMBER. Pin any literal
> that must appear with a guard, not by hand — otherwise state the invariant
> instead of the number.**

For this server specifically:

- The environment-variable table in `README.md` is the single owner of each
  knob's name and default. `CLAUDE.md` and `docs/` point to it; they do not
  re-list defaults that would drift.
- State the rule, not the census: "every tool returns the error envelope on
  failure" (a contract a test enforces), not "all N tools" (a count that rots as
  tools are added).
- Default values (timeouts, ceilings) live in `Settings` (`src/novomodelo_mcp/
  config.py`) and are surfaced in the README table — prose elsewhere references
  the knob by name, never a hand-copied number.

## 3. Failure modes to check on every doc edit

1. **Single-source fan-out.** One fact cached into N docs drifts. One owner per
   fact; other docs carry a shape-only pointer.
2. **Stale current-state snapshots.** A tool count or completeness claim with no
   adjacent diff to force an edit. State the durable invariant, not the count.
3. **Audience-bleed.** Internal symbols on an operator page, or operator config
   buried in an agent-facing contract. Match content to the doc's reader.
4. **Unresolvable claims.** Every cited repo-relative path, command, and flag
   must resolve against the live tree or the server's real env vars. Never cite
   gitignored or machine-local paths in shipped docs.
5. **Self-executable instructions.** A command a doc tells the reader to run
   (`uv sync`, `uv run novomodelo-mcp`, a smoke script) must itself succeed — verify
   by running it.
6. **False-confidence guards.** A passing test is evidence only for the
   fact-class it checks; audit coverage, not just pass/fail.

## 4. Voice register — sober reference, not marketing

Docs teach; they do not sell. Banned: hype adjectives ("powerful", "robust",
"seamless", "production-grade"), contrasting-affirmatives ("not just X, it's
Y"), reader-minimizers ("simply", "just", "easily", "obviously"), and
unsubstantiated quality claims. The deletion test for voice: delete the
adjective — if the sentence still states a true, checkable fact, the deletion
was correct; if it only lost enthusiasm, it was hype. Accurate technical
descriptors ("offline", "stdio", "read-only", "fail-closed") are not hype — keep
them.

## 5. Plan-structure leakage

No `epic`/`ticket`/`sprint` vocabulary or plan ids in shipped docs — plans live
outside the repo; public artifacts describe behaviour, not how the work was
organized. Commit messages may reference plan structure.
