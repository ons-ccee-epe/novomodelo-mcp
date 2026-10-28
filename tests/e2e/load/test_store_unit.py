"""Testes da persistência das cargas em results/load/."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.e2e.load import store as store_mod
from tests.e2e.load.fakes import make_outcome
from tests.e2e.load.stats import Sample
from tests.e2e.load.store import LOAD_SUBDIR, LoadStore, build_record, index_entry

FIXED_SHA = "abc1234def5678abc1234def5678abc1234def56"


class _FrozenDatetime:
    @staticmethod
    def now():
        from datetime import datetime

        return datetime(2026, 10, 24, 10, 0, 0)


@pytest.fixture(autouse=True)
def no_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store_mod, "git_sha", lambda: FIXED_SHA)


def _record(load_id: str = "20261024_100000_abc1234", **kwargs) -> dict:
    return build_record(load_id, make_outcome(**kwargs), server={"command": ["python"]})


def test_new_id_follows_the_batch_id_format(tmp_path: Path) -> None:
    assert re.fullmatch(r"\d{8}_\d{6}_abc1234", LoadStore(tmp_path).new_id())


def test_new_id_does_not_collide_with_an_existing_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store_mod, "datetime", _FrozenDatetime)
    store = LoadStore(tmp_path)
    first = store.new_id()
    store.save(_record(first))
    second = store.new_id()
    store.save(_record(second))
    third = store.new_id()

    assert first == "20261024_100000_abc1234"
    assert second == "20261024_100000_abc1234_2"
    assert third == "20261024_100000_abc1234_3"


def test_save_writes_under_load_subdir_and_keeps_the_battery_index_untouched(
    tmp_path: Path,
) -> None:
    battery_index = tmp_path / "index.json"
    battery_index.write_text('{"batches": []}', encoding="utf-8")
    store = LoadStore(tmp_path)

    path = store.save(_record())

    assert path == tmp_path / LOAD_SUBDIR / "20261024_100000_abc1234.json"
    assert (tmp_path / LOAD_SUBDIR / "index.json").exists()
    assert battery_index.read_text(encoding="utf-8") == '{"batches": []}'
    assert not list((tmp_path / LOAD_SUBDIR).glob("*.tmp"))


def test_roundtrip_and_index_summary(tmp_path: Path) -> None:
    store = LoadStore(tmp_path)
    record = _record()
    store.save(record)

    assert store.load(record["load_id"]) == json.loads(json.dumps(record))
    [entry] = store.list_runs()
    assert entry["load_id"] == record["load_id"]
    assert entry["summary"]["calls"] == 4
    assert entry["config"]["concurrency"] == 2
    assert set(entry["summary"]) >= {"error_rate", "throughput_cps", "p50_ms", "p95_ms", "p99_ms"}


def test_index_is_listed_newest_first_and_replaces_a_resaved_id(tmp_path: Path) -> None:
    store = LoadStore(tmp_path)
    older = _record("20261024_100000_abc1234")
    newer = _record("20261024_110000_abc1234")
    newer["timestamp"] = "2026-10-24T11:00:00"
    store.save(older)
    store.save(newer)
    store.save(older)

    assert [r["load_id"] for r in store.list_runs()] == [newer["load_id"], older["load_id"]]


def test_corrupt_index_is_rebuilt_from_the_run_files(tmp_path: Path) -> None:
    store = LoadStore(tmp_path)
    store.save(_record("20261024_100000_abc1234"))
    store.index_path.write_text("{ não é json", encoding="utf-8")

    store.save(_record("20261024_110000_abc1234"))

    assert {r["load_id"] for r in store.list_runs()} == {
        "20261024_100000_abc1234",
        "20261024_110000_abc1234",
    }


@pytest.mark.parametrize("load_id", ["../index", "..\\x", "a/b", "20261024_100000", "", "x" * 5])
def test_load_rejects_ids_that_are_not_run_ids(tmp_path: Path, load_id: str) -> None:
    with pytest.raises(ValueError):
        LoadStore(tmp_path).load(load_id)


def test_load_of_a_missing_run_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        LoadStore(tmp_path).load("20261024_100000_abc1234")


class TestBuildRecord:
    def test_has_the_sections_the_frontend_reads(self) -> None:
        record = _record()
        assert set(record) >= {
            "load_id",
            "timestamp",
            "version",
            "git_commit_sha",
            "interrupted",
            "config",
            "server",
            "mix",
            "startup",
            "duration_seconds",
            "totals",
            "per_tool",
            "series",
            "errors",
            "resources",
        }
        assert record["totals"]["calls"] == 4
        assert list(record["per_tool"]) == ["docs_list", "docs_search"]
        assert record["mix"]["calls"][0] == {"id": "docs_list#todas", "tool": "docs_list"}

    def test_startup_is_summarized_apart_from_call_metrics(self) -> None:
        startup = _record()["startup"]
        assert startup["clients"] == 2
        assert (startup["started"], startup["failed"], startup["respawns"]) == (2, 0, 0)
        assert startup["min_ms"] == 700.0
        assert startup["max_ms"] == 760.0
        assert startup["preflight_ms"] == 900.0
        assert startup["warmup_mean_ms"] == 115.0
        assert startup["wall_ms"] == 900.0

    def test_errors_are_grouped_and_counted(self) -> None:
        samples = [
            Sample("a", 0.0, 10, "error", "boom"),
            Sample("a", 0.1, 10, "error", "boom"),
            Sample("b", 0.2, 10, "timeout", "sem resposta"),
            Sample("a", 0.3, 10, "ok"),
        ]
        errors = _record(samples=samples)["errors"]
        assert errors[0] == {"tool": "a", "outcome": "error", "message": "boom", "count": 2}
        assert len(errors) == 2

    def test_resources_are_marked_unavailable_without_samples(self) -> None:
        assert _record()["resources"]["available"] is False

    def test_the_record_is_json_serializable(self) -> None:
        json.dumps(_record())

    def test_index_entry_keeps_only_the_summary_fields(self) -> None:
        entry = index_entry(_record())
        assert "series" not in entry
        assert "per_tool" not in entry


def test_git_sha_does_not_hang_when_the_inherited_stdin_is_a_pipe_being_read() -> None:
    import shutil
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[3]
    if (
        shutil.which("git") is None
        or subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        ).returncode
        != 0
    ):
        pytest.skip("sem git ou fora de um checkout")

    code = (
        "import sys, threading;"
        "threading.Thread(target=sys.stdin.readline, daemon=True).start();"
        "from tests.e2e.load.store import git_sha; print(git_sha())"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=repo_root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        output = child.stdout.read()
    finally:
        child.stdin.close()
        child.wait(timeout=30)
    assert re.fullmatch(r"[0-9a-f]{40}", output.strip())
