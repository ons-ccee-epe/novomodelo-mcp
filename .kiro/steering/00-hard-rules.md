---
inclusion: always
---

<!-- GENERATED FILE — DO NOT EDIT.
     Source of truth: CLAUDE.md
     Regenerate: python scripts/gen/sync-kiro-steering.py -->

# novomodelo-mcp — Agent Guidelines

novomodelo-mcp is a local MCP (Model Context Protocol) server that wraps the
existing `novomodelo-bridge` and `novomodelo` CLIs. Each tool envelopes one CLI subcommand
(with `--json`) or an official `novomodelo-python` binding and relays the result.
`README.md` is the source of truth for what the server does and how it is laid
out; `CONTRIBUTING.md` covers setup, tests, gates, pairing and releasing. This
file adds only what an agent working in this checkout needs beyond them.

## Read first

- `README.md` — tools, environment variables, security model, project layout.
- `src/novomodelo_mcp/server.py` — how the FastMCP server boots and registers tools.
- `src/novomodelo_mcp/adapters/` — the shared transport pieces (CLI runners, path
  guard, error envelope).
- `src/novomodelo_mcp/tools/` — the registered MCP tools, grouped by phase.

## Quick commands

```bash
uv sync                                       # install, dev group included (--system-certs behind a corporate CA)
uv run novomodelo-mcp                         # start the server on stdio
uv run pytest -q                              # offline suite; real-binary and network tests skip
uv run ruff check . && uv run ruff format --check .   # whole tree, as CI and the pre-commit hook run it
python3 scripts/ci/check_no_plan_leaks.py     # hard gates, also run by CI
python3 scripts/ci/check_comment_refs.py
python3 scripts/ci/check_doc_paths.py
python3 scripts/gen/sync-kiro-steering.py     # regenerate .kiro/steering/ after editing this file or .claude/rules/
ln -sf ../../scripts/pre-commit .git/hooks/pre-commit
```

No `PYTHONPATH` is needed. If `import novomodelo_mcp` fails inside the venv, check
whether the checkout is in a synced folder (iCloud, OneDrive): it marks the `.venv`
`.pth` files hidden, and Python skips hidden `.pth` files. Keep the environment outside
it with `UV_PROJECT_ENVIRONMENT` (see README, "Pasta sincronizada").

## Rules

Path-scoped rules in `.claude/rules/` load automatically when a matching file is
read and are the authoritative statements; do not restate them here:

- `.claude/rules/comments.md` (`**/*.py`) — comment and docstring discipline.
- `.claude/rules/doc-integrity.md` (`*.md`) — prose docs: no hand-frozen counts
  or versions, every cited path resolves, sober voice.
- `.claude/rules/testing.md` (`tests/`) — the offline and opt-in tiers, the
  fake CLI, and the no-network contract.
- `.claude/rules/mcp-facade.md` (`src/`) — the thin-facade contract, the error
  envelope, the workspace path guard, the single network exit, and tool-shaping
  limits.

## Hard rules

These are non-negotiable. Fix them before any commit.

- **Thin facade, no business logic.** A tool envelopes a CLI subcommand (with
  `--json`) or a `novomodelo-python` binding and relays the result. Never reimplement
  conversion, validation, comparison, or solving inside this server. New
  behaviour belongs in `novomodelo` or `novomodelo-bridge`, not here.
- **Network: official domains, local first, warn when absent.** The server
  speaks stdio. A tool may use the network only through `adapters/versions.py`
  (`fetch_bytes`/`fetch_json`, the single exit point), only to the allow-listed
  official domains, with a short timeout and a local `truststore` context (never
  `truststore.inject_into_ssl()`). Docs and schemas stay bundled. Without
  network the tool still answers, with `aviso_rede` and the manual command.
  Every network tool is listed in `tools/annotations.py::NETWORK_TOOLS` and
  carries `openWorldHint=True`. Tests never touch the network.
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
  `src/`, `tests/` prose, `README.md`, `CONTRIBUTING.md`, or `CHANGELOG.md`.
  Plans live in the gitignored `plans/`. Commit messages may reference them.
- **No rot-prone references** in shipped prose: no `file.py:NNN`, no
  `MEMORY.md`, no machine-local (`~/git/...`) or gitignored paths, no paths into
  another repository's tree. Reference symbols, named tests, or stable anchors.
- **Comments are default-off.** A comment ships only if it survives the Deletion
  Test (`.claude/rules/comments.md`); never delete or weaken a load-bearing
  security or envelope contract.

## Key references

| Resource          | Location                     | Purpose                                  |
| ----------------- | ---------------------------- | ---------------------------------------- |
| Server entry      | `src/novomodelo_mcp/server.py`    | FastMCP boot and tool registration       |
| Shared transport  | `src/novomodelo_mcp/adapters/`    | CLI runners, path guard, error envelope  |
| Tools             | `src/novomodelo_mcp/tools/`       | Registered MCP tools, grouped by phase   |
| Security model    | `README.md` (Segurança)      | Workspace guard and force-write gate     |
