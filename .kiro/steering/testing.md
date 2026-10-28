---
inclusion: fileMatch
fileMatchPattern: 'tests/**'
---

<!-- GENERATED FILE — DO NOT EDIT.
     Source of truth: .claude/rules/testing.md
     Regenerate: python scripts/gen/sync-kiro-steering.py -->

# novomodelo-mcp Testing Rules

How novomodelo-mcp is tested. The server is a thin, offline relay, so the tests exist
to prove two things: the envelope/guard contracts hold, and nothing reaches the
network or escapes the workspace. Auto-loads under `tests/`.

## Two tiers

1. **Offline suite (default).** `uv run pytest` runs every `tests/test_*.py`
   with the fake CLIs and no network. This is the gate every change passes, on
   every Python version and platform the CI matrix covers.
2. **Opt-in real-world tests.** Tests marked `executaveis_reais` (the real
   `novomodelo`, `novomodelo-bridge` and `novomodelo-python`) or `rede` (the
   official domains) are skipped unless their option is passed
   (`--executaveis-reais`, `--com-rede`; `tests/conftest.py` owns the options).
   With the option, a missing binary or network is a failure, not a skip. CI
   runs them in its own job; a new real-world test carries the marker.

Use the cheapest tier that catches the regression: a transport or guard
contract gets an offline test with the fake CLI first.

## Offline and sandbox discipline

- **No network outside the `rede` marker.** No offline test makes an outbound
  request; a test that needs one is marked `rede` and stays skipped by default.
- **No real binaries required.** CLI-dependent behaviour is exercised through
  `tests/fake_novomodelo_bridge.py` (a stand-in CLI), not a real `novomodelo-bridge`
  install. A test must not fail merely because the real binary is absent.
- **The path guard is tested on both sides.** `tests/test_paths_guard.py` asserts
  that an in-workspace path is accepted and an out-of-workspace path is refused — a
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
