---
inclusion: fileMatch
fileMatchPattern: 'src/**/*.py'
---

<!-- GENERATED FILE — DO NOT EDIT.
     Source of truth: .claude/rules/mcp-facade.md
     Regenerate: python scripts/gen/sync-kiro-steering.py -->

# <repositório anterior> Facade Rules

How every module under `src/novomodelo_mcp/` must behave. These are contracts, not
style preferences: a plausible-looking deviation turns a safe, offline relay
into a server that reimplements business logic, crashes the client, or escapes
the workspace sandbox. Auto-loads on `src/**/*.py`.

## 1. Thin facade — relay, never reimplement

A tool envelopes exactly one CLI subcommand (`novomodelo-bridge` or `novomodelo`, invoked
with `--json`) or one official `novomodelo-python` binding, and relays the result.
Conversion, validation, comparison, and solving live in `novomodelo` and
`novomodelo-bridge` — never here. The wrong-but-compiling alternative is to "fix" a
CLI gap by computing the answer in Python: it works for one case and silently
diverges from the tool the rest of the ecosystem trusts. If a capability is
missing, it is added upstream, not reimplemented in the server.

## 2. The error envelope is the single return contract

`adapters/envelope.py` owns the envelope shape (`status`, `exit_code`,
`diagnostics`). Every adapter and tool returns it on failure; `error(...)` and
`as_error(...)` are the only constructors — do not hand-build a dict with the
same keys elsewhere, and do not duplicate `MAX_DETAIL_CHARS`. Detail strings are
truncated through that owner so an agent is never flooded with raw stderr.

## 3. Never raise to the caller

The server speaks stdio to an MCP client; an uncaught exception crashes the
session. Every tool and every adapter catches its failure path and returns an
envelope instead. Subprocess transport failures each map to a stable code:
missing binary → `127`, timeout → `-1`, non-JSON CLI output → an error envelope
carrying the truncated raw text. A new adapter mirrors `run_bridge`'s
catch-everything shape (`FileNotFoundError`, `TimeoutExpired`, `OSError`); it
does not let any of them propagate.

## 4. The workspace path guard is fail-closed

Every tool that accepts a path calls `ensure_in_workspace(...)` (`adapters/
paths.py`) as its first statement, before any filesystem access:

```python
if (err := ensure_in_workspace(src, dst, settings=settings)):
    return err
```

With `NOVOMODELO_MCP_WORKSPACE` set, a path outside the allowed roots is refused and
`resolve()` neutralises symlinks and `..`. Treat every agent-supplied path as
untrusted. The wrong-but-compiling alternative is to resolve a path once and
reuse it, or to guard only the "write" tools: a read tool that skips the guard
leaks arbitrary file contents. Guard every path-bearing tool, read or write.
Never relax the guard to fail-open when roots are configured.

## 5. Force writes stay gated

A schema-violating edit (`force=True` on a deck-edit tool) is honoured only when
`NOVOMODELO_MCP_ALLOW_FORCE=1`. The gate is deliberate; do not remove it or default
it on.

## 6. NEWAVE/DECOMP tool parity

The pre-run and post-run tools come in `*_newave` / `*_decomp` pairs that mirror
each other's signature and behaviour. A change to one track's tool lands on the
other in the same change. A new capability that applies to both tracks ships as
a pair, not as one side with a TODO for the other.

## 7. Settings come from the environment, through `Settings`

Configuration is read once into `Settings` (`config.py`) and threaded in as a
parameter — tools and adapters do not read `os.environ` directly. A new knob is
added to `Settings`, documented in `README.md`'s environment table, and passed
down, never fetched ad hoc at a call site.

## 8. Output shaping is applied, not bypassed

Tool results pass through the shaping helpers (`tools/shaping.py` —
`cap_envelope`, `attach_artifact`) so diagnostics, rows, and summary sizes stay
within the configured ceilings. A tool returns a shaped envelope; it does not
hand back an unbounded CLI payload.
