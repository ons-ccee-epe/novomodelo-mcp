"""Testes do motor do modo agent com runners falsos (sem agente real nem tokens)."""

from __future__ import annotations

import json
import threading
import time

import pytest

from novomodelo_mcp_e2e.load import agent_engine
from novomodelo_mcp_e2e.load.agent_cases import AgentSelection, CaseSelection
from novomodelo_mcp_e2e.load.agent_engine import (
    AgentLoadConfig,
    AgentLoadRunner,
    PreflightResult,
    agent_failure,
)
from novomodelo_mcp_e2e.load.engine import LoadError
from novomodelo_mcp_e2e.load.fakes import (
    AlwaysValid,
    FakeCaseRunner,
    fake_build_result,
    make_case,
    make_query_result,
)

CASE_A = make_case("case-a", tool="docs_list")
CASE_B = make_case("case-b", tool="schema_list", tags=("schema",))


@pytest.fixture(autouse=True)
def fast_ticks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_engine, "PROGRESS_INTERVAL_S", 0.02)
    monkeypatch.setattr(agent_engine, "MIN_DURATION_S", 0.05)


def _config(**overrides) -> AgentLoadConfig:
    values = {"concurrency": 2, "duration_s": 5.0, "iterations": 2, "provider": "claude"}
    values.update(overrides)
    return AgentLoadConfig(**values)


def _preflight(*cases):
    selected = list(cases) or [CASE_A, CASE_B]
    return lambda: PreflightResult(AgentSelection(cases=selected), {})


class _Factory:
    def __init__(self, fail: set[int] | None = None, **runner_kwargs) -> None:
        self.fail = fail or set()
        self.kwargs = runner_kwargs
        self.log: list[tuple[str, int, str]] = []
        self.runners: dict[int, FakeCaseRunner] = {}

    def __call__(self, index: int, _preflight: PreflightResult) -> FakeCaseRunner:
        self.log.append(("open", index, ""))
        if index in self.fail:
            raise RuntimeError(f"sessão {index} não subiu")
        runner = FakeCaseRunner(index, log=self.log, **self.kwargs)
        self.runners[index] = runner
        return runner


def _runner(config=None, factory=None, preflight=None, statuses=None, progress=None):
    return AgentLoadRunner(
        config or _config(),
        preflight or _preflight(),
        factory or _Factory(),
        build_result=fake_build_result(statuses),
        validator=AlwaysValid(),
        on_progress=progress,
    )


class TestConfig:
    @pytest.mark.parametrize("concurrency", [0, 9, -1])
    def test_sessions_outside_the_agent_cap_are_rejected(self, concurrency: int) -> None:
        with pytest.raises(ValueError, match="sessões simultâneas"):
            AgentLoadConfig(concurrency=concurrency, duration_s=10)

    def test_unknown_provider_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="provedor desconhecido"):
            AgentLoadConfig(concurrency=1, duration_s=10, provider="gpt")

    @pytest.mark.parametrize("timeout", [0, -1, 1801, float("nan")])
    def test_timeout_outside_the_limits_is_rejected(self, timeout: float) -> None:
        with pytest.raises(ValueError, match="timeout"):
            AgentLoadConfig(concurrency=1, duration_s=10, timeout_s=timeout)

    def test_default_timeout_is_the_one_of_each_case(self) -> None:
        config = AgentLoadConfig(concurrency=1, duration_s=10)
        assert config.timeout_s is None
        assert config.to_dict()["mode"] == "agent"

    def test_selection_is_kept_in_the_dict(self) -> None:
        config = AgentLoadConfig(
            concurrency=1, duration_s=10, selection=CaseSelection(group="docs")
        )
        assert config.to_dict()["selection"] == {"case_id": None, "group": "docs", "tags": None}


class TestExecution:
    def test_each_session_runs_its_iterations_starting_at_its_own_offset(self) -> None:
        factory = _Factory()
        outcome = _runner(factory=factory).run()
        executed = [(i, case) for kind, i, case in factory.log if kind == "execute"]
        assert sorted(executed) == [(0, "case-a"), (0, "case-b"), (1, "case-a"), (1, "case-b")]
        first_by_session = {i: case for i, case in reversed(executed)}
        assert first_by_session == {0: "case-a", 1: "case-b"}
        assert len(outcome.samples) == 4
        assert [s["executions"] for s in outcome.sessions] == [2, 2]

    def test_all_runners_exist_before_any_agent_runs(self) -> None:
        factory = _Factory()
        _runner(config=_config(concurrency=3), factory=factory).run()
        kinds = [kind for kind, _i, _c in factory.log]
        assert kinds[:3] == ["open", "open", "open"]
        assert "open" not in kinds[3:]

    def test_runners_are_closed_at_the_end(self) -> None:
        factory = _Factory()
        _runner(factory=factory).run()
        assert all(r.closed for r in factory.runners.values())

    def test_validation_status_is_kept_apart_from_the_transport_outcome(self) -> None:
        outcome = _runner(statuses={"case-a": "fail", "case-b": "partial"}).run()
        assert {s.outcome for s in outcome.samples} == {"ok"}
        assert {s.status for s in outcome.samples} == {"fail", "partial"}
        assert all(s.error and s.error.startswith("validação") for s in outcome.samples)

    def test_tool_calls_are_counted_per_execution(self) -> None:
        factory = _Factory(
            respond=lambda case: make_query_result(
                case, tools=("docs_list", "read_file", "docs_read")
            )
        )
        sample = _runner(factory=factory).run().samples[0]
        assert (sample.tool_calls, sample.mcp_calls) == (3, 2)

    @pytest.mark.parametrize(
        ("result", "outcome", "status", "message"),
        [
            (lambda c: make_query_result(c, status="timeout"), "timeout", "timeout", "encerrada"),
            (
                lambda c: make_query_result(c, tools=(), response=""),
                "error",
                "error",
                "sem resposta",
            ),
            (
                lambda c: make_query_result(
                    c,
                    tools=(),
                    response="",
                    stdout=json.dumps(
                        {"type": "result", "is_error": True, "result": "429 rate limit"}
                    ),
                ),
                "error",
                "error",
                "429",
            ),
        ],
    )
    def test_incomplete_runs_are_errors_or_timeouts(self, result, outcome, status, message) -> None:
        sample = _runner(factory=_Factory(respond=result)).run().samples[0]
        assert (sample.outcome, sample.status) == (outcome, status)
        assert message in sample.error

    def test_an_exception_in_one_execution_does_not_stop_the_session(self) -> None:
        calls = {"n": 0}

        def flaky(case):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("pipe quebrado")
            return make_query_result(case)

        outcome = _runner(config=_config(concurrency=1), factory=_Factory(respond=flaky)).run()
        assert [s.outcome for s in outcome.samples] == ["error", "ok"]
        assert "pipe quebrado" in outcome.samples[0].error


class TestWindow:
    # Janela folgada para a thread da sessão começar dentro dela mesmo com a máquina ocupada.
    def test_no_case_starts_after_the_window_but_the_running_one_finishes(self) -> None:
        factory = _Factory(delay_s=1.2)
        config = _config(concurrency=1, duration_s=0.6, iterations=None)
        outcome = _runner(config=config, factory=factory).run()
        assert len(outcome.samples) == 1
        assert outcome.abandoned_calls == 0
        assert outcome.duration_s >= 1.1

    def test_finishing_phase_while_a_case_runs_past_the_window(self) -> None:
        snapshots: list[dict] = []
        config = _config(concurrency=1, duration_s=0.6, iterations=None)
        _runner(config=config, factory=_Factory(delay_s=1.2), progress=snapshots.append).run()
        assert any(s["phase"] == "finishing" and s["sessions"]["running"] == 1 for s in snapshots)


class TestStop:
    def test_stop_kills_running_agents_and_counts_them_as_abandoned(self) -> None:
        factory = _Factory(block=True)
        runner = _runner(config=_config(iterations=None, duration_s=60), factory=factory)
        result: dict = {}
        thread = threading.Thread(target=lambda: result.setdefault("outcome", runner.run()))
        thread.start()
        deadline = time.monotonic() + 5
        while len([k for k, _i, _c in factory.log if k == "execute"]) < 2:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        runner.request_stop()
        thread.join(5)
        outcome = result["outcome"]
        assert outcome.interrupted
        assert outcome.abandoned_calls == 2
        assert outcome.samples == []
        assert all(r.cancelled for r in factory.runners.values())

    def test_stop_before_the_sessions_open_runs_nothing(self) -> None:
        factory = _Factory()
        runner = _runner(factory=factory)
        runner.request_stop()
        outcome = runner.run()
        assert outcome.interrupted and outcome.samples == []
        assert not [k for k, _i, _c in factory.log if k == "execute"]


class TestFailures:
    def test_a_session_that_does_not_open_is_reported_and_the_others_run(self) -> None:
        outcome = _runner(factory=_Factory(fail={1})).run()
        assert [s["ok"] for s in outcome.sessions] == [True, False]
        assert "não subiu" in outcome.sessions[1]["error"]
        assert {s.session for s in outcome.samples} == {0}

    def test_no_session_opening_is_a_load_error(self) -> None:
        with pytest.raises(LoadError, match="nenhuma sessão"):
            _runner(factory=_Factory(fail={0, 1})).run()

    def test_preflight_failure_propagates(self) -> None:
        def broken():
            raise LoadError("o servidor MCP do agente não iniciou: x")

        with pytest.raises(LoadError, match="não iniciou"):
            _runner(preflight=broken).run()

    def test_empty_preflight_is_a_load_error(self) -> None:
        empty = lambda: PreflightResult(AgentSelection(), {})  # noqa: E731 - fábrica de uma linha
        with pytest.raises(LoadError, match="nenhum caso"):
            _runner(preflight=empty).run()


class TestProgress:
    def test_snapshot_shows_sessions_running_and_cases_in_flight(self) -> None:
        snapshots: list[dict] = []
        factory = _Factory(delay_s=0.5)
        _runner(config=_config(iterations=1), factory=factory, progress=snapshots.append).run()
        running = [s for s in snapshots if s["sessions"]["running"] == 2]
        assert running
        assert {item["case_id"] for item in running[0]["in_flight"]} == {"case-a", "case-b"}
        last = snapshots[-1]
        assert last["mode"] == "agent"
        assert last["calls"] == 2 and last["statuses"] == {"pass": 2} and last["pass_rate"] == 1.0
        assert last["sessions"]["finished"] == 2
        assert last["clients"] == {"requested": 2, "ready": 2, "failed": 0, "respawns": 0}


class TestAgentFailure:
    def test_a_response_without_tool_calls_is_not_a_failure(self) -> None:
        assert agent_failure(make_query_result(CASE_A, tools=(), response="Python é...")) is None

    def test_tool_calls_without_text_are_not_a_failure(self) -> None:
        assert agent_failure(make_query_result(CASE_A, response="")) is None

    @pytest.mark.parametrize("status", ["failed", "pending"])
    def test_mcp_server_that_did_not_connect_is_an_error_even_with_tool_calls(
        self, status: str
    ) -> None:
        init = {
            "type": "system",
            "subtype": "init",
            "mcp_servers": [{"name": "novomodelo", "status": status}],
        }
        result = make_query_result(CASE_A, tools=("Glob", "Bash"), stdout=json.dumps(init))
        assert f"não conectou no agente (status: {status})" in agent_failure(result)

    def test_connected_mcp_server_is_not_a_failure(self) -> None:
        init = {
            "type": "system",
            "subtype": "init",
            "mcp_servers": [{"name": "novomodelo", "status": "connected"}],
        }
        assert agent_failure(make_query_result(CASE_A, stdout=json.dumps(init))) is None

    def test_stderr_tail_is_kept_in_the_message(self) -> None:
        result = make_query_result(CASE_A, tools=(), response="", stderr="erro de login\n")
        assert "erro de login" in agent_failure(result)


class TestCopyPerSession:
    def test_the_copy_time_of_each_session_is_recorded_apart(self) -> None:
        factory = _Factory()

        def with_copy(index, preflight):
            runner = factory(index, preflight)
            runner.copy_ms = 120.0 + index
            return runner

        outcome = _runner(factory=with_copy).run()
        assert [s["copy_ms"] for s in outcome.sessions] == [120.0, 121.0]

    def test_the_preflight_plan_reaches_the_outcome(self) -> None:
        plan = object()
        preflight = lambda: PreflightResult(  # noqa: E731 - pré-voo falso de uma linha
            AgentSelection(cases=[CASE_A]), {}, sandbox_plan=plan
        )
        outcome = _runner(preflight=preflight).run()
        assert outcome.sandbox_plan is plan


class TestPreflight:
    """O pré-voo real (casos de um YAML temporário), sem subir servidor: as dicas são falsas."""

    def _setup(self, tmp_path):
        from novomodelo_mcp_e2e.load.mix import ToolHints

        cases = tmp_path / "cases.yaml"
        cases.write_text(
            "- id: deck-edit-json\n"
            "  query: No caso {caso:bridge_newave_mini}, edite o config.json\n"
            "  expected: {uses_mcp: true, tool: deck_edit_json, status: ok}\n"
            "- id: docs-list-all\n"
            "  query: Liste as docs\n"
            "  expected: {uses_mcp: true, tool: docs_list}\n",
            encoding="utf-8",
        )
        hints = {
            "deck_edit_json": ToolHints(read_only=False, open_world=False),
            "docs_list": ToolHints(read_only=True, open_world=False),
        }
        return tmp_path, cases, (lambda: hints)

    def test_the_preflight_selects_the_cases_and_plans_no_copy(self, tmp_path) -> None:
        from novomodelo_mcp_e2e.load.agent_setup import make_preflight

        fixtures, cases, lister = self._setup(tmp_path)
        result = make_preflight(_config(), fixtures, lister, cases)()
        assert [c.id for c in result.selection.cases] == ["docs-list-all"]
        assert [e.id for e in result.selection.excluded] == ["deck-edit-json"]
        assert result.sandbox_plan is None

    def test_a_selection_without_runnable_cases_fails_the_preflight(self, tmp_path) -> None:
        from novomodelo_mcp_e2e.load.agent_setup import make_preflight

        fixtures, cases, lister = self._setup(tmp_path)
        config = _config(selection=CaseSelection(case_id="docs-list-all"))
        result = make_preflight(config, fixtures, lister, cases)()
        assert [c.id for c in result.selection.cases] == ["docs-list-all"]

        def no_hints():
            return {}

        with pytest.raises(LoadError, match="nenhum caso da seleção"):
            make_preflight(config, fixtures, no_hints, cases)()
