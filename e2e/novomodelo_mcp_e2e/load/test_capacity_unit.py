"""Testes do limitador de sessões simultâneas: fórmula, histórico, perfil da seleção, disco,
psutil ausente e tetos."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from novomodelo_mcp_e2e.load import store as store_mod
from novomodelo_mcp_e2e.load.capacity import (
    DEFAULT_COST,
    HARD_CAPS,
    SelectionProfile,
    cases_profile,
    estimate_capacity,
    history_cost,
    tools_profile,
)
from novomodelo_mcp_e2e.load.fakes import make_agent_outcome, make_case, make_outcome
from novomodelo_mcp_e2e.load.mix import CallSpec, Selection
from novomodelo_mcp_e2e.load.sandbox import SandboxPlan
from novomodelo_mcp_e2e.load.store import LoadStore, build_agent_record, build_record

_MB = 1024 * 1024


@pytest.fixture(autouse=True)
def no_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store_mod, "git_sha", lambda: "abc1234def")


def _psutil(available_mb: float, total_mb: float = 16_000.0):
    memory = SimpleNamespace(total=total_mb * _MB, available=available_mb * _MB)
    return lambda: SimpleNamespace(virtual_memory=lambda: memory)


def _estimate(
    mode="tools",
    provider=None,
    store=None,
    available_mb=8_000.0,
    cores=8,
    psutil=True,
    profile=None,
    free_disk_mb=100_000.0,
):
    return estimate_capacity(
        mode,
        provider,
        store=store,
        psutil_loader=_psutil(available_mb) if psutil else (lambda: None),
        cpu_count=lambda: cores,
        profile=profile,
        work_dir="C:/tmp",
        disk_usage=lambda _path: SimpleNamespace(free=free_disk_mb * _MB),
    )


def _copy_profile(copy_mb: float) -> SelectionProfile:
    plan = SandboxPlan(
        fixtures=Path("C:/fixtures"),
        subtrees=("newave/novomodelo-mini",),
        enabled=True,
        copy_bytes=int(copy_mb * _MB),
    )
    return SelectionProfile(write_tools=("deck_edit_json",), sandbox=plan)


def _resources(peak_rss_mb: float, avg_cpu: float) -> dict:
    return {
        "available": True,
        "samples": [{"t": 0, "cpu_percent": avg_cpu, "rss_mb": peak_rss_mb, "processes": 4}],
        "avg_cpu_percent": avg_cpu,
        "peak_cpu_percent": avg_cpu,
        "peak_rss_mb": peak_rss_mb,
        "peak_processes": 4,
    }


def _save_tools(
    store: LoadStore, load_id: str, peak: float, cpu: float, started: int = 2, heavy: bool = False
) -> None:
    outcome = make_outcome()
    if heavy:
        outcome.selection = Selection(
            specs=[CallSpec("bridge_check_newave#x", "bridge_check_newave", {})]
        )
    record = build_record(load_id, outcome)
    record["resources"] = _resources(peak, cpu)
    record["startup"]["started"] = started
    store.save(record)


def _save_agent(store: LoadStore, load_id: str, provider: str, peak: float) -> None:
    agent = {"provider": provider, "label": provider, "binary": provider, "denied_tools": []}
    record = build_agent_record(load_id, make_agent_outcome(provider=provider), agent)
    record["resources"] = _resources(peak, 40.0)
    store.save(record)


class TestFormula:
    def test_memory_bound(self) -> None:
        result = _estimate(mode="agent", provider="claude", available_mb=2_000.0)
        assert result["limits"]["memory"] == 2  # 2000 × 0,75 ÷ 600
        assert result["recommended"] == 2
        assert result["limiting_factor"] == "memória"
        assert "2000 MB livres" in result["explanation"]
        assert "600 MB/sessão" in result["explanation"]

    def test_cpu_bound(self) -> None:
        result = _estimate(mode="tools", available_mb=64_000.0, cores=4)
        assert result["limits"]["cpu"] == 3  # (4 − 1) ÷ 1 núcleo/sessão
        assert result["recommended"] == 3
        assert result["limiting_factor"] == "CPU"

    def test_hard_cap_bound_and_preferred_on_ties(self) -> None:
        result = _estimate(mode="agent", provider="kiro-cli", available_mb=6_400.0, cores=64)
        assert result["limits"]["memory"] == 8
        assert result["recommended"] == HARD_CAPS["agent"]
        assert result["limiting_factor"] == "teto do modo"

    def test_never_below_one_session_but_warns(self) -> None:
        result = _estimate(mode="agent", available_mb=100.0)
        assert result["recommended"] == 1
        assert any("insuficiente" in w for w in result["warnings"])

    def test_without_psutil_only_cores_count_and_it_says_so(self) -> None:
        result = _estimate(mode="tools", cores=4, psutil=False)
        assert result["memory"] is None
        assert result["limits"]["memory"] is None
        assert result["recommended"] == 3
        assert any("psutil" in w for w in result["warnings"])

    def test_unknown_mode_is_refused(self) -> None:
        with pytest.raises(ValueError, match="modo desconhecido"):
            _estimate(mode="x")


class TestHistory:
    def test_without_history_the_documented_estimate_is_used(self, tmp_path: Path) -> None:
        result = _estimate(store=LoadStore(tmp_path))
        assert result["per_session"]["source"] == "estimativa"
        assert result["per_session"]["rss_mb"] == DEFAULT_COST[("tools", False)].rss_mb
        assert any("sem carga gravada" in w for w in result["warnings"])

    def test_history_divides_the_peak_by_the_sessions_that_started(self, tmp_path: Path) -> None:
        store = LoadStore(tmp_path)
        _save_tools(store, "20261024_100000_abc1234", peak=400.0, cpu=160.0, started=2)
        result = _estimate(store=store, available_mb=1_000.0)
        assert result["per_session"] == {
            "rss_mb": 200.0,
            "cpu_cores": 0.8,
            "source": "histórico",
            "runs": 1,
            "profile": "leve",
        }
        assert result["limits"]["memory"] == 3  # 1000 × 0,75 ÷ 200
        assert "1 carga(s) gravada(s)" in result["explanation"]

    def test_the_most_expensive_recent_run_wins(self, tmp_path: Path) -> None:
        store = LoadStore(tmp_path)
        _save_tools(store, "20261024_100000_abc1234", peak=200.0, cpu=100.0)
        _save_tools(store, "20261024_100100_abc1234", peak=600.0, cpu=100.0)
        assert _estimate(store=store)["per_session"]["rss_mb"] == 300.0

    def test_agent_history_is_per_provider_and_ignores_tools_runs(self, tmp_path: Path) -> None:
        store = LoadStore(tmp_path)
        _save_tools(store, "20261024_100000_abc1234", peak=9_000.0, cpu=100.0)
        _save_agent(store, "20261024_100100_abc1234", "kiro-cli", peak=800.0)
        _save_agent(store, "20261024_100200_abc1234", "claude", peak=1_400.0)
        claude = _estimate(mode="agent", provider="claude", store=store)
        kiro = _estimate(mode="agent", provider="kiro-cli", store=store)
        assert claude["per_session"]["rss_mb"] == 700.0
        assert kiro["per_session"]["rss_mb"] == 400.0

    def test_runs_without_measured_resources_are_ignored(self) -> None:
        unmeasured = {"resources": {"available": False}, "startup": {"started": 2}}
        no_sessions = {"resources": _resources(500.0, 10.0), "startup": {"started": 0}}
        assert history_cost([unmeasured, no_sessions]) is None


class TestSelectionProfile:
    def test_heavy_selection_uses_the_larger_documented_estimate(self) -> None:
        heavy = SelectionProfile(heavy_tools=("bridge_check_newave",))
        result = _estimate(profile=heavy, available_mb=64_000.0, cores=8)
        assert result["per_session"]["profile"] == "pesada"
        assert result["per_session"]["rss_mb"] == DEFAULT_COST[("tools", True)].rss_mb
        assert result["limits"]["cpu"] == 4  # (8 − 1) ÷ 1,5 núcleo/sessão
        assert "seleção pesada" in result["explanation"]
        assert result["selection"]["heavy_tools"] == ["bridge_check_newave"]

    def test_heavy_history_only_estimates_heavy_selections(self, tmp_path: Path) -> None:
        store = LoadStore(tmp_path)
        _save_tools(store, "20261024_100000_abc1234", peak=400.0, cpu=100.0)
        _save_tools(store, "20261024_100100_abc1234", peak=1_600.0, cpu=300.0, heavy=True)
        light = _estimate(store=store)
        heavy = _estimate(store=store, profile=SelectionProfile(heavy_tools=("run_plan",)))
        assert (light["per_session"]["rss_mb"], light["per_session"]["profile"]) == (200.0, "leve")
        assert heavy["per_session"]["rss_mb"] == 800.0
        assert heavy["per_session"]["source"] == "histórico"

    def test_old_records_without_heavy_tools_count_as_light(self, tmp_path: Path) -> None:
        store = LoadStore(tmp_path)
        _save_tools(store, "20261024_100000_abc1234", peak=400.0, cpu=100.0)
        heavy = _estimate(store=store, profile=SelectionProfile(heavy_tools=("run_plan",)))
        assert heavy["per_session"]["source"] == "estimativa"


class TestDisk:
    def test_read_only_selection_has_no_disk_limit(self) -> None:
        result = _estimate()
        assert result["limits"]["disk"] is None
        assert result["disk"] is None
        assert result["selection"]["writes"] is False

    def test_the_copy_plus_growth_bounds_the_sessions(self) -> None:
        result = _estimate(
            profile=_copy_profile(400.0), free_disk_mb=2_000.0, available_mb=64_000.0
        )
        assert result["disk"]["per_session_mb"] == pytest.approx(800.0)
        assert result["limits"]["disk"] == 2  # 2000 × 0,9 ÷ 800
        assert result["limiting_factor"] == "disco"
        assert result["recommended"] == 2
        assert "limitado por disco" in result["explanation"]
        assert "cópia de 400 MB" in result["explanation"]
        assert result["selection"]["copy_mb"] == pytest.approx(400.0)

    def test_disk_too_small_for_one_copy_warns(self) -> None:
        result = _estimate(profile=_copy_profile(400.0), free_disk_mb=500.0)
        assert result["recommended"] == 1
        assert any("disco insuficiente" in w for w in result["warnings"])


class TestProfilesFromTheSelection:
    def test_default_tools_mix_is_light_and_copies_nothing(self, tmp_path: Path) -> None:
        profile = tools_profile(tmp_path, None)
        assert not profile.heavy and not profile.writes

    def test_writing_and_heavy_tools_mark_the_profile(self, tmp_path: Path) -> None:
        deck = tmp_path / "newave" / "novomodelo-mini"
        deck.mkdir(parents=True)
        (deck / "config.json").write_text("{}", encoding="utf-8")
        profile = tools_profile(tmp_path, ["deck_edit_json", "run_plan", "docs_list"])
        assert profile.heavy_tools == ("run_plan",)
        assert profile.write_tools == ("deck_edit_json",)
        assert profile.sandbox is not None
        assert profile.sandbox.subtrees == ("newave/novomodelo-mini",)
        assert profile.sandbox.copy_bytes == 2

    def test_unknown_tool_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="fora do catálogo"):
            tools_profile(tmp_path, ["run_start"])

    def test_cases_profile_follows_the_expected_tools(self, tmp_path: Path) -> None:
        cases = [make_case("a", tool="bridge_check_newave"), make_case("b", tool="docs_list")]
        profile = cases_profile(tmp_path, cases)
        assert profile.heavy and not profile.writes
        writing = cases_profile(tmp_path, [make_case("c", tool="case_init")])
        assert writing.writes and writing.write_tools == ("case_init",)
