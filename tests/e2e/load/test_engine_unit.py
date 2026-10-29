"""Testes do motor de carga com clientes falsos (sem subir o servidor MCP)."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest

from tests.e2e.load import engine
from tests.e2e.load.engine import LoadConfig, LoadError, LoadRunner
from tests.e2e.load.fakes import Behavior, FakeFactory

NO_FIXTURE_TOOLS = ("docs_list", "docs_search", "schema_list")


@pytest.fixture(autouse=True)
def short_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "MIN_DURATION_S", 0.05)
    monkeypatch.setattr(engine, "PROGRESS_INTERVAL_S", 0.05)


def _config(**overrides) -> LoadConfig:
    values = {"concurrency": 2, "duration_s": 0.4, "tools": NO_FIXTURE_TOOLS, "timeout_s": 5.0}
    values.update(overrides)
    return LoadConfig(**values)


def _run(runner: LoadRunner):
    return asyncio.run(runner.run())


def _runner(tmp_path: Path, factory: FakeFactory, **config) -> LoadRunner:
    return LoadRunner(_config(**config), tmp_path, factory)


class TestConfigValidation:
    @pytest.mark.parametrize("concurrency", [0, 33, -1])
    def test_concurrency_outside_1_32_is_rejected(self, concurrency: int) -> None:
        with pytest.raises(ValueError, match="concorrência"):
            LoadConfig(concurrency=concurrency, duration_s=10)

    @pytest.mark.parametrize("duration", [0.5, 1801, float("inf"), float("nan")])
    def test_duration_outside_1_1800_is_rejected(
        self, duration: float, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.undo()
        with pytest.raises(ValueError, match="duração"):
            LoadConfig(concurrency=1, duration_s=duration)

    @pytest.mark.parametrize("bound", [1, 1800])
    def test_duration_bounds_are_inclusive(
        self, bound: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.undo()
        assert LoadConfig(concurrency=1, duration_s=bound).duration_s == bound

    @pytest.mark.parametrize("timeout", [0, -3, float("inf"), 1801])
    def test_timeout_must_be_finite_and_positive(self, timeout: float) -> None:
        with pytest.raises(ValueError, match="timeout"):
            LoadConfig(concurrency=1, duration_s=10, timeout_s=timeout)

    def test_iterations_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="iterações"):
            LoadConfig(concurrency=1, duration_s=10, iterations=0)

    def test_tools_outside_the_catalog_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="fora do catálogo"):
            LoadConfig(concurrency=1, duration_s=10, tools=("docs_list", "run_start"))


class TestRun:
    def test_every_client_calls_and_the_clock_starts_after_all_are_ready(
        self, tmp_path: Path
    ) -> None:
        factory = FakeFactory(startup_delay_s={0: 0.0, 1: 0.5, 2: 0.0})
        outcome = _run(_runner(tmp_path, factory, concurrency=3, duration_s=0.3))

        workers = {index for index, _tool in factory.calls if index >= 0}
        assert workers == {0, 1, 2}
        assert outcome.startup_wall_s >= 0.5
        assert min(sample.started_s for sample in outcome.samples) >= 0.0
        assert outcome.duration_s == pytest.approx(0.3, abs=0.25)
        assert sorted(factory.closed) == sorted(factory.opened)

    def test_iterations_are_per_client_and_end_the_run_early(self, tmp_path: Path) -> None:
        factory = FakeFactory()
        outcome = _run(_runner(tmp_path, factory, concurrency=3, duration_s=30, iterations=4))
        assert len(outcome.samples) == 12
        assert outcome.duration_s < 5

    def test_duration_wins_when_iterations_are_not_reached(self, tmp_path: Path) -> None:
        factory = FakeFactory(behaviors={tool: Behavior(delay_s=0.05) for tool in NO_FIXTURE_TOOLS})
        outcome = _run(_runner(tmp_path, factory, concurrency=1, duration_s=0.3, iterations=1000))
        assert 0 < len(outcome.samples) < 1000

    def test_calls_are_spread_over_the_mix(self, tmp_path: Path) -> None:
        factory = FakeFactory()
        outcome = _run(_runner(tmp_path, factory, concurrency=2, duration_s=30, iterations=9))
        tools = {sample.tool for sample in outcome.samples}
        assert tools == {"docs_list", "docs_search", "schema_list"}

    def test_warmup_calls_stay_out_of_the_metrics(self, tmp_path: Path) -> None:
        factory = FakeFactory()
        outcome = _run(_runner(tmp_path, factory, concurrency=2, duration_s=30, iterations=3))
        measured = len(outcome.samples)
        warmup_calls = [c for c in factory.calls if c[0] >= 0]
        assert measured == 6
        assert len(warmup_calls) == measured + 2 * 3

    def test_without_warmup_every_call_is_measured(self, tmp_path: Path) -> None:
        factory = FakeFactory()
        outcome = _run(
            _runner(tmp_path, factory, concurrency=2, duration_s=30, iterations=3, warmup=False)
        )
        worker_calls = [c for c in factory.calls if c[0] >= 0]
        assert len(outcome.samples) == len(worker_calls) == 6

    def test_a_timeout_is_counted_and_the_client_is_recreated(self, tmp_path: Path) -> None:
        factory = FakeFactory(behaviors={"docs_search": Behavior(broken=True)})
        outcome = _run(_runner(tmp_path, factory, concurrency=2, duration_s=0.5, warmup=False))

        timeouts = [s for s in outcome.samples if s.outcome == "timeout"]
        respawns = [s for s in outcome.startups if s["kind"] == "respawn"]
        assert timeouts
        assert len(respawns) >= len(timeouts) - 2
        assert all(entry["ok"] for entry in respawns)
        assert factory.opened.count(0) > 1

    def test_a_warmup_that_loses_the_session_fails_that_client_start(self, tmp_path: Path) -> None:
        factory = FakeFactory(behaviors={"docs_search": Behavior(broken=True)})
        with pytest.raises(LoadError, match="aquecimento"):
            _run(_runner(tmp_path, factory, concurrency=2, duration_s=0.3))

    def test_startup_time_is_reported_apart_from_call_latency(self, tmp_path: Path) -> None:
        factory = FakeFactory(startup_delay_s={0: 0.3})
        outcome = _run(_runner(tmp_path, factory, concurrency=1, duration_s=0.2))
        initial = [s for s in outcome.startups if s["kind"] == "initial"]
        assert initial[0]["ms"] >= 300
        assert max(s.latency_ms for s in outcome.samples) < 100

    def test_a_failed_client_is_recorded_and_the_others_run(self, tmp_path: Path) -> None:
        factory = FakeFactory(fail_startup={1})
        outcome = _run(_runner(tmp_path, factory, concurrency=3, duration_s=0.3))
        failed = [s for s in outcome.startups if not s["ok"]]
        assert [s["client"] for s in failed] == [1]
        assert "não subiu" in failed[0]["error"]
        assert {index for index, _ in factory.calls if index >= 0} == {0, 2}

    def test_no_client_starting_is_a_load_error(self, tmp_path: Path) -> None:
        factory = FakeFactory(fail_startup={0, 1})
        with pytest.raises(LoadError, match="nenhum cliente iniciou"):
            _run(_runner(tmp_path, factory, concurrency=2, duration_s=0.3))

    def test_the_server_not_starting_in_preflight_is_a_load_error(self, tmp_path: Path) -> None:
        factory = FakeFactory(fail_startup={-1})
        with pytest.raises(LoadError, match="não iniciou"):
            _run(_runner(tmp_path, factory))


class TestPreflight:
    def test_a_call_that_errors_is_excluded_and_never_enters_the_load(self, tmp_path: Path) -> None:
        factory = FakeFactory(
            behaviors={"docs_search": Behavior(outcome="error", error="parâmetro inválido")}
        )
        outcome = _run(_runner(tmp_path, factory, concurrency=1, duration_s=0.3))
        assert "docs_search" not in {sample.tool for sample in outcome.samples}
        excluded = {e.tool: e.reason for e in outcome.selection.excluded}
        assert "pré-voo" in excluded["docs_search"]
        assert "parâmetro inválido" in excluded["docs_search"]

    def test_a_hanging_call_is_excluded_and_validation_continues(self, tmp_path: Path) -> None:
        factory = FakeFactory(behaviors={"docs_list": Behavior(broken=True)})
        outcome = _run(_runner(tmp_path, factory, concurrency=1, duration_s=0.2))
        assert {s.tool for s in outcome.samples} >= {"schema_list"}
        assert any(
            "pré-voo" in e.reason for e in outcome.selection.excluded if e.tool == "docs_list"
        )

    def test_tool_that_the_server_does_not_declare_read_only_leaves_the_mix(
        self, tmp_path: Path
    ) -> None:
        factory = FakeFactory(tools=("docs_list", "schema_list"))
        outcome = _run(_runner(tmp_path, factory, concurrency=1, duration_s=0.2))
        assert "docs_search" not in {s.tool for s in outcome.samples}
        assert any(
            e.tool == "docs_search" and "ausente" in e.reason for e in outcome.selection.excluded
        )

    def test_empty_mix_is_a_load_error_with_the_reasons(self, tmp_path: Path) -> None:
        factory = FakeFactory(tools=())
        with pytest.raises(LoadError, match="nenhuma chamada disponível"):
            _run(_runner(tmp_path, factory))


class TestStop:
    def test_request_stop_from_another_thread_interrupts_and_cancels_in_flight_calls(
        self, tmp_path: Path
    ) -> None:
        factory = FakeFactory(
            behaviors={tool: Behavior(hang=False, delay_s=0.5) for tool in NO_FIXTURE_TOOLS}
        )
        stop_scheduled = threading.Event()

        def stop_shortly_after_the_load_starts(snapshot: dict) -> None:
            if snapshot["phase"] == "running" and not stop_scheduled.is_set():
                stop_scheduled.set()
                threading.Timer(0.2, runner.request_stop).start()

        runner = LoadRunner(
            _config(concurrency=2, duration_s=60),
            tmp_path,
            factory,
            on_progress=stop_shortly_after_the_load_starts,
        )

        started = time.monotonic()
        outcome = _run(runner)

        assert outcome.interrupted
        assert time.monotonic() - started < 10
        assert outcome.abandoned_calls >= 1
        assert sorted(factory.closed) == sorted(factory.opened)

    def test_a_call_that_never_answers_is_abandoned_after_the_grace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(engine, "DRAIN_GRACE_S", 0.3)
        factory = FakeFactory(behaviors={"docs_list": Behavior(hang_only_workers=True)})
        runner = _runner(
            tmp_path, factory, concurrency=1, duration_s=0.3, warmup=False, tools=("docs_list",)
        )

        started = time.monotonic()
        outcome = _run(runner)

        assert outcome.abandoned_calls == 1
        assert not outcome.interrupted
        assert time.monotonic() - started < 10

    def test_stop_before_the_run_starts_returns_an_interrupted_outcome(
        self, tmp_path: Path
    ) -> None:
        runner = _runner(tmp_path, FakeFactory())
        runner.request_stop()
        outcome = _run(runner)
        assert outcome.interrupted
        assert outcome.samples == []


class TestProgress:
    def test_phases_advance_and_counters_grow(self, tmp_path: Path) -> None:
        snapshots: list[dict] = []
        runner = LoadRunner(
            _config(duration_s=0.6), tmp_path, FakeFactory(), on_progress=snapshots.append
        )
        _run(runner)

        phases = []
        for snap in snapshots:
            if not phases or phases[-1] != snap["phase"]:
                phases.append(snap["phase"])
        assert phases[0] == "preflight"
        assert "starting" in phases or "running" in phases
        running = [s for s in snapshots if s["phase"] == "running"]
        assert running
        assert running[-1]["calls"] >= running[0]["calls"]
        assert running[-1]["clients"] == {"requested": 2, "ready": 2, "failed": 0, "respawns": 0}
        assert running[-1]["series"]


def _deck_fixtures(root: Path) -> Path:
    deck = root / "fixtures" / "newave" / "novomodelo-mini"
    (deck / "constraints").mkdir(parents=True)
    (deck / "config.json").write_text("{}", encoding="utf-8")
    (deck / "constraints" / "thermal_bounds.parquet").write_bytes(b"x")
    for source in ("newave/newave-mini", "decomp/decomp-mini"):
        (root / "fixtures" / source).mkdir(parents=True)
        (root / "fixtures" / source / "caso.dat").write_text("x", encoding="utf-8")
    return root / "fixtures"


class TestSessionsWithCopy:
    """Com ``sandbox.ToolsSessions``: cada sessão chama na sua cópia, nunca nas originais."""

    TOOLS = ("deck_edit_json", "case_init", "docs_list")

    def _run_with_copy(self, tmp_path: Path, **config):
        from tests.e2e.load.mix import select_specs
        from tests.e2e.load.sandbox import ToolsSessions, plan_for_specs

        fixtures = _deck_fixtures(tmp_path)
        tools = config.pop("tools", self.TOOLS)
        plan = plan_for_specs(fixtures, select_specs(fixtures, tools).specs)
        sessions = ToolsSessions(tmp_path / "run", plan)
        factory = FakeFactory(tools=("docs_list",), writing_tools=("deck_edit_json", "case_init"))
        runner = LoadRunner(_config(tools=tools, **config), fixtures, factory, sessions=sessions)
        outcome = _run(runner)
        return fixtures, sessions, factory, outcome

    def test_every_call_points_to_the_copy_of_its_own_session(self, tmp_path: Path) -> None:
        fixtures, sessions, factory, _ = self._run_with_copy(tmp_path, duration_s=30, iterations=4)
        run_root = (tmp_path / "run").resolve()
        paths = [
            (index, value)
            for index, tool, args in factory.arguments
            for value in args.values()
            if isinstance(value, str) and Path(value).is_absolute()
        ]
        assert {index for index, _ in paths} == {-1, 0, 1}
        for index, value in paths:
            folder = "preflight" if index < 0 else f"s{index}"
            assert Path(value).is_relative_to(run_root / folder / "fixtures"), value
            assert not Path(value).is_relative_to(fixtures.resolve())
        assert (run_root / "s0" / "fixtures" / "newave/novomodelo-mini/config.json").is_file()
        assert sessions.close()
        assert not run_root.exists()

    def test_case_init_gets_a_new_folder_on_every_call_of_a_session(self, tmp_path: Path) -> None:
        _, sessions, factory, _ = self._run_with_copy(tmp_path, duration_s=30, iterations=6)
        folders = [
            args["directory"]
            for index, tool, args in factory.arguments
            if tool == "case_init" and index == 0
        ]
        assert len(folders) >= 2
        assert len(set(folders)) == len(folders)
        sessions.close()

    def test_the_copy_is_timed_apart_and_the_preflight_copy_is_released(
        self, tmp_path: Path
    ) -> None:
        _, sessions, _, outcome = self._run_with_copy(tmp_path, duration_s=30, iterations=2)
        by_kind = {(s["kind"], s["client"]): s for s in outcome.startups}
        assert by_kind[("preflight", -1)]["copy_ms"] is not None
        assert by_kind[("initial", 0)]["copy_ms"] is not None
        assert not (tmp_path / "run" / "preflight").exists()
        summary = sessions.summary()
        assert summary["enabled"] and summary["sessions"] == 2
        assert summary["subtrees"] == ["newave/novomodelo-mini"]
        sessions.close()

    def test_sessions_get_their_own_folders_workspace_and_no_solver_runs(
        self, tmp_path: Path
    ) -> None:
        _, sessions, _, _ = self._run_with_copy(tmp_path, duration_s=30, iterations=1)
        first, second = sessions.env(0), sessions.env(1)
        assert first["NOVOMODELO_MCP_WORKSPACE"] == str(sessions.root(0))
        assert first["NOVOMODELO_MCP_WORKSPACE"] != second["NOVOMODELO_MCP_WORKSPACE"]
        assert first["TEMP"] != second["TEMP"]
        assert first["NOVOMODELO_MCP_STATE_DIR"] != second["NOVOMODELO_MCP_STATE_DIR"]
        assert first["NOVOMODELO_MCP_MAX_JOBS"] == "0"
        sessions.close()

    def test_a_stalled_bridge_skips_the_rest_of_the_group_in_preflight(
        self, tmp_path: Path
    ) -> None:
        from tests.e2e.load.engine import BRIDGE_STDIN_HINT

        fixtures = _deck_fixtures(tmp_path)
        tools = ("bridge_check_newave", "bridge_check_decomp", "docs_list")
        factory = FakeFactory(
            tools=tools,
            behaviors={"bridge_check_newave": Behavior(broken=True)},
        )
        outcome = _run(
            LoadRunner(_config(tools=tools, concurrency=1, duration_s=0.2), fixtures, factory)
        )
        reasons = {e.tool: e.reason for e in outcome.selection.excluded}
        assert BRIDGE_STDIN_HINT in reasons["bridge_check_newave"]
        assert "não chamada" in reasons["bridge_check_decomp"]
        assert "bridge_check_decomp" not in {tool for _index, tool in factory.calls}
