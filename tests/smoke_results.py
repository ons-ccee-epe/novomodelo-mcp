#!/usr/bin/env python3
"""Smoke test das leituras de resultado (stdlib puro; partes com Parquet ficam
para o ambiente com Polars). Roda: python3 tests/smoke_results.py"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from novomodelo_mcp.adapters import results as R  # noqa: E402


def test_read_metadata_ok():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "output"
        (out / "training").mkdir(parents=True)
        (out / "training" / "metadata.json").write_text(json.dumps({
            "status": "complete",
            "bounds": {"final_lower_bound": 1.0, "final_upper_bound": 1.1},
            "convergence": {"achieved": True, "final_gap_percent": 0.9},
        }))
        env = R.read_metadata(str(out))
        assert env["status"] == "ok", env
        assert env["simulation_ran"] is False, env
        assert env["training"]["status"] == "complete", env


def test_read_metadata_missing():
    with tempfile.TemporaryDirectory() as d:
        env = R.read_metadata(d)
        assert env["status"] == "error", env


def test_list_entities_empty():
    with tempfile.TemporaryDirectory() as d:
        assert R.list_entities(d) == []


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passaram")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
