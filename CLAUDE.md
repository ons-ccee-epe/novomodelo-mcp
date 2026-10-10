# <repositório anterior> — Agent Guidelines

<repositório anterior> is an offline MCP (Model Context Protocol) server that wraps the
existing `cobre-bridge` and `cobre` CLIs. Each tool envelopes one CLI subcommand
(with `--json`) or an official `cobre-python` binding and relays the result.
`README.md` is the source of truth for what the server does and how it is laid
out; this file adds only what an agent working in this checkout needs beyond it.

## Read first

- `README.md` — tools, environment variables, security model, project layout.
- `src/cobre_mcp/server.py` — how the FastMCP server boots and registers tools.
- `src/cobre_mcp/adapters/` — the shared transport pieces (CLI runners, path
  guard, error envelope).
- `src/cobre_mcp/tools/` — the registered MCP tools, grouped by phase.

## Quick commands

```bash
uv sync --extra dev                 # install (use --system-certs behind a corporate CA)
uv run cobre-mcp                     # start the server on stdio
python3 tests/smoke.py               # stdlib smoke tests (offline, no deps)
python3 tests/smoke_deck.py && python3 tests/smoke_results.py && python3 tests/smoke_paths.py
uv run pytest                        # full suite (after uv sync)
uv run ruff check . && uv run ruff format --check .   # as CI runs it
```

## Rules

Path-scoped rules in `.claude/rules/` load automatically when a matching file is
read and are the authoritative statements; do not restate them here:

- `.claude/rules/comments.md` (`**/*.py`) — comment and docstring discipline.
- `.claude/rules/doc-integrity.md` (`*.md`) — prose docs: no hand-frozen counts
  or versions, every cited path resolves, sober voice.
- `.claude/rules/testing.md` (`tests/`) — the smoke/pytest tiers, offline
  discipline, the fake CLI, and the no-network contract.
- `.claude/rules/mcp-facade.md` (`src/`) — the thin-facade contract, the error
  envelope, the workspace path guard, and tool-shaping limits.

## Hard rules

These are non-negotiable. Fix them before any commit.

- **Thin facade, no business logic.** A tool envelopes a CLI subcommand (with
  `--json`) or a `cobre-python` binding and relays the result. Never reimplement
  conversion, validation, comparison, or solving inside this server. New
  behaviour belongs in `cobre` or `cobre-bridge`, not here.
- **Offline only.** The server speaks stdio and makes no outbound network
  request. Tests run offline and must stay that way. A tool that needs the
  network is out of scope.
- **Never raise to the caller.** Every tool and adapter returns an error
  envelope on failure (`adapters/envelope.py` is the single owner of its shape);
  an uncaught exception that crashes the stdio server is a bug. Transport
  failures (missing binary, timeout, non-JSON output) become envelopes.
- **Path guard is fail-closed.** Every tool that takes a path calls
  `ensure_in_workspace(...)` before touching the filesystem. With
  `NOVOMODELO_MCP_WORKSPACE` set, any path outside the allowed roots is refused;
  `resolve()` neutralises symlinks and `..`. Never bypass the guard, and never
  weaken it to fail-open.
- **Force writes are gated.** A schema-violating write (`force=True`) requires
  `NOVOMODELO_MCP_ALLOW_FORCE=1`. Do not remove that gate.
- **NEWAVE/DECOMP tool parity.** A tool added for one conversion track ships for
  the other in the same change, mirroring the existing `*_newave` / `*_decomp`
  pairs — or the asymmetry is recorded.
- **No secrets or credentials** committed; no `.env` files.
- **No plan-structure vocabulary** (`epic`, `ticket`, `sprint`, plan ids) in
  `src/`, `tests/` prose, `README.md`, or `docs/`. Commit messages may reference
  plans.
- **Comments are default-off.** A comment ships only if it survives the Deletion
  Test (`.claude/rules/comments.md`); never delete or weaken a load-bearing
  security or envelope contract.

## Key references

| Resource          | Location                     | Purpose                                  |
| ----------------- | ---------------------------- | ---------------------------------------- |
| Server entry      | `src/cobre_mcp/server.py`    | FastMCP boot and tool registration       |
| Shared transport  | `src/cobre_mcp/adapters/`    | CLI runners, path guard, error envelope  |
| Tools             | `src/cobre_mcp/tools/`       | Registered MCP tools, grouped by phase   |
| Security model    | `README.md` (Segurança)      | Workspace guard and force-write gate     |
