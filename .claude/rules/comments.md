---
paths:
  - "**/*.py"
---

# <repositório anterior> Comment & Docstring Rules

Governs every `#` comment and docstring in any `.py` file in this repo. The
Deletion Test and the Four Voices match the wider Novomodelo ecosystem's comment
discipline; the directives are adapted to this server's domain (an offline relay
over external CLIs). Auto-loads on `**/*.py`.

**Default is silence.** A comment is a liability — it costs reader attention and
it can rot away from the code it describes. Keep the small set that prevents
real bugs and delete everything else.

---

## 0. The Default-Off Discipline

Write code with **no comments** until one earns its place against §1. In order:

1. **Refactor first.** Rename → extract a well-named function/constant →
   introduce a dataclass/enum. A comment a better name would carry is a refactor
   you skipped.
2. **Relocate.** The why of a _change_ goes in the commit message; a durable
   contract goes in `.claude/rules/*.md` or a module docstring; a behavioural
   fact goes in a **test name**. Inline comments are the residual.
3. **Hoist.** A fact repeated across siblings is stated once at the enclosing
   scope.
4. **Only then comment** — the shortest form that survives the Deletion Test.

### The docstring floor (terse, not absent)

Public modules, classes, and tools carry a docstring. Pay that floor with one
terse purpose line plus only the sections that carry a nugget (an `Args:` entry
with a contract an agent must respect, a `Raises:`/returns-envelope note). The
tool docstrings are the agent-facing API — they describe what the tool does and
its key arguments, not a narration of the body.

---

## 1. The Deletion Test (the one gate)

> **Delete the comment.** Reading only the code, would a competent engineer
> (a) introduce a bug, (b) "simplify" something correct into something wrong, or
> (c) be unable to recover a fact that lives **outside this file**?
> **If none → leave it deleted. If any → restore it, cut to the single clause
> that triggers the "yes".**

The common bloat shapes, all DELETE: a docstring narrating its own body; a
call-site comment naming the function it precedes (rename the function instead);
pipeline labels (`# Step 1`); the same clause repeated down a function; an
`Args:` list restating each parameter's name and type.

When in doubt, **delete** and put the thought in the commit message.

---

## 2. The Four Voices — the only comments that survive §1

- **Voice 1 — Contract.** A present-tense invariant **+ the wrong-but-running
  alternative it forbids +** the owning symbol. _Exemplar (this repo):_ "guard
  every path-bearing tool, read ones too — a read tool that skips
  `ensure_in_workspace` leaks arbitrary file contents."
- **Voice 2 — Rationale.** Why a non-obvious choice was made, kept only while
  the wrong simplification is still plausible. _Exemplar:_ "parse the last
  `{`-line, not the first — the CLI may print logs before its JSON envelope."
- **Voice 3 — ~~Narrator~~ (NOT ALLOWED).** What the next line does; how it used
  to work; which ticket changed it. Belongs in names, git, or test names.
- **Voice 4 — Intent/Seam.** Why a currently-unused item exists and what
  activates it — pinned to the suppression or guard that anchors it.

---

## 3. Directives

### DO

- **D1 — Contracts.** When the obvious alternative is wrong, say so: invariant +
  forbidden alternative + owning symbol. One clause.
- **D2 — Error-path and exit-code contracts.** The mapping from a transport
  failure to a stable code (`127` missing binary, `-1` timeout) and the
  never-raise rule are out-of-file facts — one clause naming the code and why.
- **D3 — Rationale above suppression.** Every `# noqa: CODE`,
  `# type: ignore[code]`, `pytest.mark.xfail`, and every deliberate
  `except`-and-return-envelope carries a reason on the same line or above: why
  the fix the diagnostic asks for is inappropriate. Blanket suppressions without
  a code are banned.
- **D4 — Security traps.** A path-guard or force-gate site that would be unsafe
  if "simplified" (resolving once and reusing, guarding only writes, failing
  open) carries one clause naming the trap.

### DON'T

- **N1 — No what-narration.** Rename instead.
- **N2 — No history narration.** No `replaces`/`formerly`, no project-event
  dates, no plan tokens. Keep the present-tense fact.
- **N3 — No drift-prone refs.** No `file.py:NNN`, commit hashes, `MEMORY.md`,
  `.claude/` paths other than `.claude/rules/*`, machine-local (`~/git/...`) or
  gitignored paths. Reference by symbol, by named test, or by a stable external
  anchor. For a symbol+line hybrid, keep the symbol, strip the line.
- **N4 — No plan/workstream leakage** in `src/`, `README.md`, or `docs/`. No
  `epic`/`ticket`/`sprint` vocabulary or plan ids. Plan refs in test names stay
  allowed.
- **N5 — No banners fencing groups inside one long function** — extract a
  function. Dividers between top-level sections of a large module are fine.
- **N6 — No duplicated source-of-truth in prose** — a mirror restates the shape
  and references the owner by symbol; it never copies a magic number. A drifted
  mirror is a lie.

### TODO/FIXME

A shipped `TODO` carries a durable behavioural tag and names the guard or test
enforcing the current limitation. Never a plan token. Bare ownerless `TODO`s are
discouraged.

---

## 4. Protected Contracts (never delete)

- **Error-envelope and never-raise clauses (Voice 1).** The stdio server crashes
  on an uncaught exception; a comment naming that failure mode is load-bearing.
- **Path-guard / force-gate contracts (D4).** "Fail-closed", "guard reads too",
  "`resolve()` neutralises `..`/symlinks" clauses are the difference between a
  sandbox and an escape.

Tighten these to one clause + owning symbol; never lose the invariant.
