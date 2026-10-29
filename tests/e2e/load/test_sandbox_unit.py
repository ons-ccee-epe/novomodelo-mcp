"""Testes da cópia das fixtures por sessão: o que é copiado, isolamento, reset, disco e limpeza."""

from __future__ import annotations

import os
from itertools import combinations
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.e2e.load.engine import LoadError
from tests.e2e.load.sandbox import (
    SANDBOX_GROWTH,
    SandboxPlan,
    SessionSandbox,
    ToolsSessions,
    check_disk,
    make_run_root,
    plan_for,
    remove_tree,
    sandbox_summary,
    subtrees_in,
)

DECK = "newave/novomodelo-mini"
RESULTS = "results/sample_run"


@pytest.fixture
def fixtures(tmp_path: Path) -> Path:
    root = tmp_path / "fixtures"
    (root / DECK / "system").mkdir(parents=True)
    (root / DECK / "config.json").write_text('{"a": 1}', encoding="utf-8")
    (root / DECK / "system" / "buses.parquet").write_bytes(b"0123456789")
    (root / RESULTS / "training").mkdir(parents=True)
    (root / RESULTS / "training" / "metadata.json").write_text("{}", encoding="utf-8")
    (root / "decomp" / "nao-usado").mkdir(parents=True)
    (root / "decomp" / "nao-usado" / "grande.dat").write_bytes(b"x" * 1000)
    return root.resolve()


def _plan(fixtures: Path, *subtrees: str) -> SandboxPlan:
    texts = [str(fixtures / s) for s in subtrees]
    return plan_for(fixtures, texts, enabled=True)


class TestWhatIsCopied:
    def test_only_the_cited_case_folders_exist_ones_are_copied(self, fixtures: Path) -> None:
        texts = [
            f"Gere o dashboard do caso {fixtures / DECK}?",
            f"read_parquet('{(fixtures / RESULTS).as_posix()}/training/x.parquet')",
            f"Valide o caso em {fixtures / 'nonexistent-case'}",
            f"Exporte para {fixtures / 'scratch' / 'schemas'}",
        ]
        assert subtrees_in(texts, fixtures) == {DECK, RESULTS}

    def test_a_sentence_ending_dot_does_not_hide_the_folder(self, fixtures: Path) -> None:
        assert subtrees_in([f"Liste o caso {fixtures / DECK}."], fixtures) == {DECK}

    def test_a_selection_that_does_not_write_copies_nothing(self, fixtures: Path) -> None:
        plan = plan_for(fixtures, [str(fixtures / DECK)], enabled=False)
        assert not plan.enabled and plan.subtrees == () and plan.copy_bytes == 0

    def test_the_plan_measures_the_copy_and_the_disk_per_session(self, fixtures: Path) -> None:
        plan = _plan(fixtures, DECK)
        assert plan.subtrees == (DECK,)
        assert plan.copy_bytes == len('{"a": 1}') + 10
        assert plan.per_session_mb == pytest.approx(plan.copy_mb * (1 + SANDBOX_GROWTH))


class TestIsolation:
    def test_sessions_get_distinct_copies_and_a_workspace_of_their_own(
        self, fixtures: Path, tmp_path: Path
    ) -> None:
        plan = _plan(fixtures, DECK, RESULTS)
        boxes = [SessionSandbox(plan, tmp_path / "run" / f"s{i}") for i in range(3)]
        for box in boxes:
            box.create()
            assert (box.root / DECK / "config.json").read_text(encoding="utf-8") == '{"a": 1}'
            assert (box.root / "scratch").is_dir()
            assert not (box.root / "decomp").exists()
            assert box.workspace_roots() == [box.root]
            assert not box.root.is_relative_to(fixtures)
        for a, b in combinations(boxes, 2):
            assert not a.root.is_relative_to(b.root) and not b.root.is_relative_to(a.root)

    def test_prompts_and_posix_paths_are_rewritten_to_the_copy(
        self, fixtures: Path, tmp_path: Path
    ) -> None:
        box = SessionSandbox(_plan(fixtures, DECK), tmp_path / "s0")
        prompt = f"Leia {fixtures / DECK / 'config.json'} e read_parquet('{fixtures.as_posix()}/x')"
        rewritten = box.rewrite(prompt)
        assert str(fixtures) not in rewritten and fixtures.as_posix() not in rewritten
        assert str(box.root / DECK / "config.json") in rewritten
        assert f"{box.root.as_posix()}/x" in rewritten

    def test_without_copy_the_session_reads_the_original_fixtures(
        self, fixtures: Path, tmp_path: Path
    ) -> None:
        box = SessionSandbox(SandboxPlan(fixtures=fixtures), tmp_path / "s0")
        assert box.create() == 0.0
        assert box.root == fixtures
        assert box.rewrite(str(fixtures / DECK)) == str(fixtures / DECK)
        assert box.workspace_roots()[0] == fixtures
        assert not (tmp_path / "s0").exists()

    def test_writing_in_a_copy_leaves_the_originals_and_other_copies_alone(
        self, fixtures: Path, tmp_path: Path
    ) -> None:
        plan = _plan(fixtures, DECK)
        first, second = (SessionSandbox(plan, tmp_path / f"s{i}") for i in range(2))
        first.create()
        second.create()
        (first.root / DECK / "config.json").write_text('{"a": 2}', encoding="utf-8")
        assert (fixtures / DECK / "config.json").read_text(encoding="utf-8") == '{"a": 1}'
        assert (second.root / DECK / "config.json").read_text(encoding="utf-8") == '{"a": 1}'


class TestReset:
    def test_reset_undoes_what_a_case_wrote(self, fixtures: Path, tmp_path: Path) -> None:
        box = SessionSandbox(_plan(fixtures, DECK), tmp_path / "s0")
        box.create()
        config = box.root / DECK / "config.json"
        config.write_text('{"a": 99, "b": 2}', encoding="utf-8")
        (box.root / DECK / "config.json.bak").write_text("{}", encoding="utf-8")
        (box.root / "scratch" / "new-case" / "deep").mkdir(parents=True)
        (box.root / "scratch" / "new-case" / "deep" / "f.json").write_text("{}", encoding="utf-8")
        (box.root / DECK / "system" / "buses.parquet").unlink()

        box.reset()

        assert config.read_text(encoding="utf-8") == '{"a": 1}'
        assert not (box.root / DECK / "config.json.bak").exists()
        assert list((box.root / "scratch").iterdir()) == []
        assert (box.root / DECK / "system" / "buses.parquet").read_bytes() == b"0123456789"

    def test_reset_of_an_untouched_copy_changes_nothing(
        self, fixtures: Path, tmp_path: Path
    ) -> None:
        box = SessionSandbox(_plan(fixtures, DECK), tmp_path / "s0")
        box.create()
        before = os.stat(box.root / DECK / "config.json").st_mtime_ns
        box.reset()
        assert os.stat(box.root / DECK / "config.json").st_mtime_ns == before

    def test_a_file_that_cannot_be_restored_is_skipped_and_counted(
        self, fixtures: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import shutil as shutil_mod

        box = SessionSandbox(_plan(fixtures, DECK), tmp_path / "s0")
        box.create()
        (box.root / DECK / "config.json").write_text("{}", encoding="utf-8")
        (box.root / "scratch" / "novo.json").write_text("{}", encoding="utf-8")

        def locked(*_args, **_kwargs):
            raise PermissionError("arquivo em uso")

        monkeypatch.setattr(shutil_mod, "copy2", locked)
        box.reset()
        assert box.reset_skipped == 1
        assert not (box.root / "scratch" / "novo.json").exists()


class TestDisk:
    def _usage(self, free_mb: float):
        return lambda _path: SimpleNamespace(free=free_mb * 1024 * 1024)

    def test_copies_that_do_not_fit_refuse_the_load(self, fixtures: Path) -> None:
        plan = SandboxPlan(
            fixtures=fixtures, subtrees=(DECK,), enabled=True, copy_bytes=400 * 1024 * 1024
        )
        with pytest.raises(LoadError, match="disco insuficiente"):
            check_disk(plan, 4, fixtures, disk_usage=self._usage(3000.0))
        check_disk(plan, 3, fixtures, disk_usage=self._usage(3000.0))

    def test_without_copy_the_disk_is_not_checked(self, fixtures: Path) -> None:
        check_disk(SandboxPlan(fixtures=fixtures), 32, fixtures, disk_usage=self._usage(0.0))


class TestToolsSessions:
    def test_each_session_has_its_folders_its_copy_and_no_solver_runs(
        self, fixtures: Path, tmp_path: Path
    ) -> None:
        sessions = ToolsSessions(make_run_root(tmp_path, "run-"), _plan(fixtures, DECK))
        for index in (-1, 0, 1):
            assert sessions.prepare(index) >= 0.0
        assert sessions.prepare(0) == 0.0
        envs = [sessions.env(i) for i in (-1, 0, 1)]
        for env, index in zip(envs, (-1, 0, 1), strict=True):
            root = sessions.root(index)
            assert env["NOVOMODELO_MCP_WORKSPACE"] == str(root)
            assert env["NOVOMODELO_MCP_MAX_JOBS"] == "0"
            assert (root / DECK / "config.json").is_file()
            assert Path(env["TEMP"]).is_dir() and Path(env["NOVOMODELO_MCP_STATE_DIR"]).is_dir()
        for a, b in combinations(envs, 2):
            assert a["TEMP"] != b["TEMP"]
            assert a["NOVOMODELO_MCP_WORKSPACE"] != b["NOVOMODELO_MCP_WORKSPACE"]
        sessions.release(-1)
        assert not (sessions.run_root / "preflight").exists()
        summary = sessions.summary()
        assert summary["enabled"] and summary["sessions"] == 2
        assert summary["copy_ms_mean"] is not None and summary["final_mb_max"] > 0
        assert sessions.close()
        assert not sessions.run_root.exists()

    def test_without_copy_sessions_still_get_their_own_temp_and_state(
        self, fixtures: Path, tmp_path: Path
    ) -> None:
        sessions = ToolsSessions(make_run_root(tmp_path, "run-"), SandboxPlan(fixtures=fixtures))
        sessions.prepare(0)
        env = sessions.env(0)
        assert sessions.root(0) == fixtures
        assert env["NOVOMODELO_MCP_WORKSPACE"].split(os.pathsep)[0] == str(fixtures)
        assert env["NOVOMODELO_MCP_MAX_JOBS"] == "0"
        assert Path(env["TEMP"]).is_relative_to(sessions.run_root)
        assert sessions.summary() == {"enabled": False}
        sessions.close()


def test_summary_of_a_copy_reports_the_slowest_and_the_largest(
    fixtures: Path, tmp_path: Path
) -> None:
    plan = _plan(fixtures, DECK)
    boxes = [SessionSandbox(plan, tmp_path / f"s{i}") for i in range(2)]
    for box in boxes:
        box.create()
    (boxes[1].root / "scratch" / "out.bin").write_bytes(b"x" * 2048)
    summary = sandbox_summary(plan, boxes)
    assert summary["sessions"] == 2
    assert summary["final_mb_max"] == pytest.approx((plan.copy_bytes + 2048) / 1024 / 1024)
    assert summary["copy_ms_max"] >= summary["copy_ms_mean"]


def test_remove_tree_clears_everything(tmp_path: Path) -> None:
    (tmp_path / "run" / "s0" / "fixtures").mkdir(parents=True)
    (tmp_path / "run" / "s0" / "fixtures" / "a.json").write_text("{}", encoding="utf-8")
    assert remove_tree(tmp_path / "run")
    assert not (tmp_path / "run").exists()
