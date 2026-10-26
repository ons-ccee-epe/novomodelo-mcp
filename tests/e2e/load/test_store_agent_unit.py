"""Testes da persistência das cargas do modo agent e da leitura de registros antigos."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.e2e.load import store as store_mod
from tests.e2e.load.agent_engine import AgentSample
from tests.e2e.load.fakes import make_agent_outcome, make_outcome
from tests.e2e.load.store import (
    LoadStore,
    build_agent_record,
    build_record,
    index_entry,
    record_mode,
)

AGENT = {"provider": "claude", "label": "Claude Code", "binary": "claude", "denied_tools": []}


@pytest.fixture(autouse=True)
def no_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store_mod, "git_sha", lambda: "abc1234def")


def _agent_record(load_id: str = "20261024_110000_abc1234", **kwargs) -> dict:
    return build_agent_record(load_id, make_agent_outcome(**kwargs), AGENT, server={"command": ["x"]})


class TestAgentRecord:
    def test_totals_keep_transport_and_validation_apart(self) -> None:
        totals = _agent_record()["totals"]
        assert (totals["calls"], totals["ok"], totals["timeouts"], totals["errors"]) == (4, 3, 1, 0)
        assert totals["statuses"] == {"pass": 2, "partial": 0, "fail": 1, "timeout": 1, "error": 0}
        assert totals["pass_rate"] == 0.5
        assert totals["error_rate"] == 0.25

    def test_latency_covers_only_completed_executions(self) -> None:
        totals = _agent_record()["totals"]
        assert totals["max_ms"] == 14_000.0
        assert totals["p50_ms"] == 10_000.0

    def test_throughput_is_also_in_cases_per_minute(self) -> None:
        totals = _agent_record()["totals"]
        assert totals["throughput_cpm"] == pytest.approx(4.0)
        assert totals["throughput_cpm"] == pytest.approx(totals["throughput_cps"] * 60)

    def test_tool_call_means_cover_completed_executions(self) -> None:
        totals = _agent_record()["totals"]
        assert totals["tool_calls_mean"] == pytest.approx(2.0)
        assert totals["mcp_calls_mean"] == pytest.approx(1.0)

    def test_per_case_has_the_group_and_its_own_stats(self) -> None:
        per_case = _agent_record()["per_case"]
        assert list(per_case) == ["docs-list-all", "schema-list-all"]
        assert per_case["docs-list-all"]["group"] == "docs"
        assert per_case["docs-list-all"]["statuses"]["fail"] == 1
        assert per_case["schema-list-all"]["timeouts"] == 1

    def test_series_counts_passed_executions_per_bucket(self) -> None:
        series = _agent_record()["series"]
        assert sum(p["calls"] for p in series) == 4
        assert sum(p["passed"] for p in series) == 2
        assert series[1]["t"] - series[0]["t"] == 5.0

    def test_errors_group_every_execution_that_did_not_pass(self) -> None:
        errors = _agent_record()["errors"]
        assert {(e["case_id"], e["status"]) for e in errors} == {
            ("docs-list-all", "fail"), ("schema-list-all", "timeout"),
        }

    def test_cases_sessions_and_mode_are_recorded(self) -> None:
        record = _agent_record()
        assert record["mode"] == "agent"
        assert record["cases"]["selection"] == "todos os casos"
        assert [c["id"] for c in record["cases"]["selected"]] == ["docs-list-all", "schema-list-all"]
        assert record["cases"]["excluded"][0]["id"] == "deck-edit-json"
        assert record["sessions"]["started"] == 2 and record["sessions"]["failed"] == 0
        assert record["config"]["provider"] == "claude"
        json.dumps(record)

    def test_without_executions_the_record_still_builds(self) -> None:
        record = _agent_record(samples=[])
        assert record["totals"]["calls"] == 0
        assert record["totals"]["pass_rate"] == 0.0
        assert record["per_case"] == {}

    def test_agent_index_entry_has_mode_provider_selection_and_pass_rate(self) -> None:
        entry = index_entry(_agent_record())
        assert entry["mode"] == "agent"
        assert entry["config"]["provider"] == "claude"
        assert entry["config"]["selection"] == {"case_id": None, "group": None, "tags": None}
        assert entry["summary"]["pass_rate"] == 0.5
        assert "tools" not in entry["config"]


class TestCompatibility:
    def test_tools_records_now_carry_the_mode(self) -> None:
        record = build_record("20261024_100000_abc1234", make_outcome())
        assert record["mode"] == "tools"
        assert index_entry(record)["mode"] == "tools"

    def test_a_record_saved_before_the_mode_field_is_read_as_tools(self) -> None:
        record = build_record("20261024_100000_abc1234", make_outcome())
        del record["mode"]
        del record["config"]["mode"]
        assert record_mode(record) == "tools"
        assert index_entry(record)["config"]["tools"] is None

    def test_index_mixes_both_modes_and_rebuilds_from_old_files(self, tmp_path: Path) -> None:
        store = LoadStore(tmp_path)
        old = build_record("20261024_090000_abc1234", make_outcome())
        del old["mode"]
        store.load_dir.mkdir(parents=True)
        (store.load_dir / f"{old['load_id']}.json").write_text(json.dumps(old), encoding="utf-8")
        store.save(_agent_record())
        store.index_path.write_text("{corrompido", encoding="utf-8")
        modes = {r["load_id"]: r["mode"] for r in store.list_runs()}
        assert modes == {"20261024_090000_abc1234": "tools", "20261024_110000_abc1234": "agent"}

    def test_partial_agent_sample_without_group_name_is_still_saved(self, tmp_path: Path) -> None:
        sample = AgentSample("x", "other", 0, 0.0, 1.0, "error", "error", error="boom")
        path = LoadStore(tmp_path).save(_agent_record(samples=[sample]))
        assert json.loads(path.read_text(encoding="utf-8"))["errors"][0]["message"] == "boom"


class TestSandboxAndProfile:
    def test_records_carry_the_copy_block_and_default_to_no_copy(self) -> None:
        tools = build_record("20261024_110000_abc1234", make_outcome())
        agent = _agent_record()
        assert tools["sandbox"] == {"enabled": False}
        assert agent["sandbox"] == {"enabled": False}
        copy = {"enabled": True, "copy_mb": 19.0, "subtrees": ["newave/x"]}
        assert build_record("20261024_110000_abc1234", make_outcome(), sandbox=copy)["sandbox"] == copy

    def test_old_records_without_the_copy_block_still_load(self, tmp_path: Path) -> None:
        record = build_record("20261024_110000_abc1234", make_outcome())
        del record["sandbox"]
        store = LoadStore(tmp_path)
        store.save(record)
        assert "sandbox" not in store.load("20261024_110000_abc1234")
        assert store.list_runs()[0]["load_id"] == "20261024_110000_abc1234"

    def test_heavy_profile_comes_from_the_mix_or_the_selected_cases(self) -> None:
        from tests.e2e.load.mix import CallSpec, Selection
        from tests.e2e.load.store import record_is_heavy

        light = build_record("20261024_110000_abc1234", make_outcome())
        assert record_is_heavy(light) is False
        outcome = make_outcome()
        outcome.selection = Selection(specs=[CallSpec("run_plan#x", "run_plan", {})])
        assert record_is_heavy(build_record("20261024_110000_abc1234", outcome)) is True
        agent = _agent_record()
        assert record_is_heavy(agent) is False
        agent["cases"]["selected"].append({"id": "b", "group": "bridge", "tool": "case_validate/bridge_check_newave"})
        assert record_is_heavy(agent) is True
