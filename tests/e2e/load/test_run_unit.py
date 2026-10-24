"""Testes da CLI do teste de carga (validação, saída, gravação e códigos de saída)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.e2e.load import run as run_mod
from tests.e2e.load import store as store_mod
from tests.e2e.load.engine import LoadError
from tests.e2e.load.fakes import make_outcome
from tests.e2e.load.mix import Excluded
from tests.e2e.load.store import build_record

VALID = ["--concurrency", "2", "--duration", "5"]


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store_mod, "git_sha", lambda: "abc1234def")
    monkeypatch.setattr(run_mod._PARENT_GONE, "is_set", lambda: False)


def _fake_execute(outcome=None):
    def execute(_config, _args, _command, _command_args):
        return None, outcome or make_outcome()

    return execute


class TestValidation:
    @pytest.mark.parametrize(
        "extra",
        [
            ["--concurrency", "0", "--duration", "5"],
            ["--concurrency", "33", "--duration", "5"],
            ["--concurrency", "2", "--duration", "0"],
            ["--concurrency", "2", "--duration", "1801"],
            ["--concurrency", "2", "--duration", "5", "--iterations", "0"],
            ["--concurrency", "2", "--duration", "5", "--timeout", "0"],
            ["--concurrency", "2", "--duration", "5", "--tools", "run_start"],
            ["--concurrency", "2", "--duration", "5", "--tools", "docs_list,deck_edit_json"],
        ],
    )
    def test_invalid_values_exit_2_without_running(
        self, extra: list[str], monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        monkeypatch.setattr(run_mod, "_execute", lambda *a: pytest.fail("não deveria rodar"))
        assert run_mod.main(extra) == 2
        assert "erro:" in capsys.readouterr().err

    def test_missing_required_arguments_exit_2(self) -> None:
        with pytest.raises(SystemExit) as info:
            run_mod.main(["--duration", "5"])
        assert info.value.code == 2

    def test_tools_are_split_on_commas_and_trimmed(self) -> None:
        assert run_mod._parse_tools(" docs_list , schema_list,") == ("docs_list", "schema_list")
        assert run_mod._parse_tools(None) is None

    def test_server_command_override_is_split_into_command_and_args(self) -> None:
        command, args = run_mod._server_command("python -m outro_servidor")
        assert (command, args) == ("python", ["-m", "outro_servidor"])

    def test_default_server_command_is_the_current_interpreter(self) -> None:
        import sys

        command, args = run_mod._server_command(None)
        assert command == sys.executable
        assert args == ["-m", "novomodelo_mcp"]


class TestOutput:
    def test_human_mode_prints_the_report_and_saves_under_load(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        monkeypatch.setattr(run_mod, "_execute", _fake_execute())

        code = run_mod.main([*VALID, "--results-dir", str(tmp_path)])

        out = capsys.readouterr().out
        assert code == 0
        assert "Carga " in out
        assert "docs_search" in out
        assert "Gravado em:" in out
        saved = list((tmp_path / "load").glob("2*.json"))
        assert len(saved) == 1
        assert (tmp_path / "load" / "index.json").exists()

    def test_no_save_writes_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        monkeypatch.setattr(run_mod, "_execute", _fake_execute())
        assert run_mod.main([*VALID, "--no-save", "--results-dir", str(tmp_path)]) == 0
        assert not (tmp_path / "load").exists()
        assert "Gravado em" not in capsys.readouterr().out

    def test_json_mode_prints_only_json_lines_ending_with_saved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        monkeypatch.setattr(run_mod, "_execute", _fake_execute())
        monkeypatch.setattr(run_mod, "_watch_stdin", lambda _runner: None)

        code = run_mod.main([*VALID, "--json-progress", "--results-dir", str(tmp_path)])

        lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
        assert code == 0
        assert [event["event"] for event in lines] == ["saved"]
        assert lines[0]["load_id"].startswith("2")

    def test_interrupted_run_is_saved_as_partial_and_exits_130(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outcome = make_outcome()
        outcome.interrupted = True
        monkeypatch.setattr(run_mod, "_execute", _fake_execute(outcome))

        assert run_mod.main([*VALID, "--results-dir", str(tmp_path)]) == 130
        [saved] = (tmp_path / "load").glob("2*.json")
        assert json.loads(saved.read_text(encoding="utf-8"))["interrupted"] is True

    def test_load_error_exits_1_with_the_message_on_stderr(
        self, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        def execute(*_args):
            raise LoadError("o servidor MCP não iniciou: x")

        monkeypatch.setattr(run_mod, "_execute", execute)
        assert run_mod.main([*VALID, "--no-save"]) == 1
        assert "não iniciou" in capsys.readouterr().err

    def test_load_error_in_json_mode_is_an_error_event(
        self, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        def execute(*_args):
            raise LoadError("mix vazio")

        monkeypatch.setattr(run_mod, "_execute", execute)
        monkeypatch.setattr(run_mod, "_watch_stdin", lambda _runner: None)
        assert run_mod.main([*VALID, "--json-progress"]) == 1
        assert json.loads(capsys.readouterr().out) == {"event": "error", "message": "mix vazio"}

    def test_stopped_by_the_launcher_saves_nothing_and_exits_3(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        monkeypatch.setattr(run_mod, "_execute", _fake_execute())
        monkeypatch.setattr(run_mod._PARENT_GONE, "is_set", lambda: True)

        code = run_mod.main([*VALID, "--json-progress", "--results-dir", str(tmp_path)])

        assert code == 3
        assert json.loads(capsys.readouterr().out) == {"event": "cancelled"}
        assert not (tmp_path / "load").exists()


class TestFormatReport:
    def test_report_lists_totals_tools_exclusions_and_errors(self) -> None:
        excluded = [Excluded("deck_list#x", "deck_list", "fonte ausente ou vazia: x/config.json")]
        record = build_record("20261024_100000_abc1234", make_outcome(excluded=excluded))

        report = run_mod.format_report(record)

        assert "Total: 4 chamadas" in report
        assert "taxa de erro 25.0%" in report
        assert "docs_list" in report and "docs_search" in report
        assert "Fora do mix (1)" in report
        assert "fonte ausente ou vazia" in report
        assert "falha simulada" in report
        assert "CPU/RSS não medidos" in report
        assert "Subida: 2/2 cliente(s)" in report


class TestCtrlC:
    def test_first_ctrl_c_asks_for_a_graceful_stop_and_the_second_aborts(self) -> None:
        import signal
        from types import SimpleNamespace

        stops: list[str] = []
        runner = SimpleNamespace(request_stop=lambda: stops.append("stop"))
        previous = signal.getsignal(signal.SIGINT)
        try:
            run_mod._install_stop_handlers(runner, json_mode=False)
            signal.raise_signal(signal.SIGINT)
            assert stops == ["stop"]
            with pytest.raises(KeyboardInterrupt):
                signal.raise_signal(signal.SIGINT)
        finally:
            signal.signal(signal.SIGINT, previous)
