---
inclusion: fileMatch
fileMatchPattern: 'tests/**'
---

<!-- GENERATED FILE — DO NOT EDIT.
     Source of truth: .claude/rules/testing.md
     Regenerate: python scripts/gen/sync-kiro-steering.py -->

# <repositório anterior> Testing Rules

How <repositório anterior> is tested. The server is a thin, offline relay, so the tests exist
to prove two things: the envelope/guard contracts hold, and nothing reaches the
network or escapes the workspace. Auto-loads under `tests/`.

## Two tiers

1. **Smoke (stdlib, offline, no deps).** The `tests/smoke*.py` scripts run under
   plain `python3` with no third-party imports and no installed server. They are
   the fast gate and must stay dependency-free — a smoke test that needs `pytest`
   or a real `cobre`/`cobre-bridge` binary belongs in tier 2.
2. **pytest suite.** `tests/test_*.py` run after `uv sync`. They cover adapters,
   validation, imports, and bundled reference data.

Use the cheapest tier that catches the regression; add a smoke test for a
transport/guard contract before reaching for the pytest suite.

## Offline and sandbox discipline

- **No network, ever.** No test makes an outbound request. The server is offline
  by contract and the suite proves it.
- **No real binaries required.** CLI-dependent behaviour is exercised through
  `tests/fake_cobre_bridge.py` (a stand-in CLI), not a real `cobre-bridge`
  install. A test must not fail merely because the real binary is absent.
- **The path guard is tested on both sides.** `tests/smoke_paths.py` asserts that
  an in-workspace path is accepted and an out-of-workspace path is refused — a
  guard test that only checks the happy path proves nothing about fail-closed
  behaviour.

## Contracts worth a dedicated test

- **Error envelopes, not exceptions.** Assert that a failing adapter/tool returns
  the envelope shape (`status == "error"`, an `exit_code`, `diagnostics`) rather
  than raising. The stable codes (`127` missing binary, `-1` timeout) are part of
  the contract.
- **NEWAVE/DECOMP parity.** When a tool pair is tested, both tracks are covered;
  a test for `*_newave` without its `*_decomp` sibling leaves the parity hard
  rule unguarded.
- **Shaping ceilings.** Diagnostics/rows/summary truncation is asserted against
  the configured limits, not left to chance.

## Hygiene

- Tests write only to temporary directories; nothing is written into a real
  workspace or committed deck.
- `tests/try_tools.py` is a manual utility, not a CI test — do not wire it into
  the automated run.
