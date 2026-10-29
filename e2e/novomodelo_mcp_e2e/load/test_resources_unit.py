"""Testes da amostragem opcional de CPU/RSS dos servidores."""

from __future__ import annotations

from types import SimpleNamespace

from novomodelo_mcp_e2e.load.resources import ResourceSampler, load_psutil, summarize_resources


class _Error(Exception):
    pass


class _Process:
    def __init__(self, pid: int, cpu: float, rss: int, dies: bool = False) -> None:
        self.pid = pid
        self._cpu = cpu
        self._rss = rss
        self._dies = dies

    def cpu_percent(self, interval=None) -> float:
        if self._dies:
            raise _Error("sumiu")
        return self._cpu

    def memory_info(self):
        return SimpleNamespace(rss=self._rss)


def _fake_psutil(children, root_error: bool = False):
    class Root:
        def __init__(self, _pid) -> None:
            if root_error:
                raise _Error("sem processo")

        def children(self, recursive: bool):
            assert recursive is True
            return children

    return SimpleNamespace(Process=Root, Error=_Error)


def test_sample_sums_cpu_and_rss_of_the_descendants() -> None:
    mb = 1024 * 1024
    psutil = _fake_psutil([_Process(1, 40.0, 100 * mb), _Process(2, 25.5, 50 * mb)])
    sample = ResourceSampler(psutil, root_pid=99).sample()
    assert sample == {"cpu_percent": 65.5, "rss_mb": 150.0, "processes": 2}


def test_a_process_that_vanishes_is_skipped() -> None:
    mb = 1024 * 1024
    psutil = _fake_psutil([_Process(1, 10.0, mb), _Process(2, 0.0, mb, dies=True)])
    sample = ResourceSampler(psutil, root_pid=99).sample()
    assert sample["processes"] == 1


def test_sample_is_none_when_the_root_is_gone() -> None:
    assert ResourceSampler(_fake_psutil([], root_error=True), root_pid=99).sample() is None


def test_process_objects_are_reused_between_samples_to_keep_cpu_deltas() -> None:
    first = _Process(1, 10.0, 1024)
    psutil = _fake_psutil([first])
    sampler = ResourceSampler(psutil, root_pid=99)
    sampler.sample()
    psutil_replacement = _Process(1, 99.0, 1024)
    psutil.Process = type(
        "Root",
        (),
        {
            "__init__": lambda self, pid: None,
            "children": lambda self, recursive: [psutil_replacement],
        },
    )
    assert sampler.sample()["cpu_percent"] == 10.0


class TestSummarize:
    def test_without_psutil_the_block_says_unavailable(self) -> None:
        assert summarize_resources(None) == {"available": False, "reason": "psutil não instalado"}

    def test_aggregates_average_and_peaks(self) -> None:
        samples = [
            {"t": 0.0, "cpu_percent": 10.0, "rss_mb": 100.0, "processes": 2},
            {"t": 1.0, "cpu_percent": 30.0, "rss_mb": 140.0, "processes": 4},
        ]
        block = summarize_resources(samples)
        assert block["available"] is True
        assert block["avg_cpu_percent"] == 20.0
        assert block["peak_cpu_percent"] == 30.0
        assert block["peak_rss_mb"] == 140.0
        assert block["peak_processes"] == 4

    def test_no_samples_is_reported_without_failing(self) -> None:
        assert summarize_resources([])["samples"] == []


def test_load_psutil_returns_the_module_or_none() -> None:
    module = load_psutil()
    assert module is None or hasattr(module, "Process")
