"""Testes unitários de percentis, agregação e série temporal da carga."""

from __future__ import annotations

import pytest

from novomodelo_mcp_e2e.load.stats import (
    LiveStats,
    Sample,
    aggregate,
    percentile,
    summarize,
    time_series,
)


def _ok(tool: str, started_s: float, latency_ms: float) -> Sample:
    return Sample(tool, started_s, latency_ms, "ok")


class TestPercentile:
    def test_single_value_is_every_percentile(self) -> None:
        assert percentile([7.0], 0) == 7.0
        assert percentile([7.0], 50) == 7.0
        assert percentile([7.0], 99) == 7.0

    def test_two_values_interpolate_linearly(self) -> None:
        assert percentile([10.0, 20.0], 50) == 15.0
        assert percentile([10.0, 20.0], 95) == pytest.approx(19.5)

    def test_three_values_hit_the_middle_rank(self) -> None:
        assert percentile([1.0, 2.0, 9.0], 50) == 2.0
        assert percentile([1.0, 2.0, 9.0], 99) == pytest.approx(8.86)

    def test_extremes_are_min_and_max(self) -> None:
        values = [3.0, 5.0, 8.0, 13.0]
        assert percentile(values, 0) == 3.0
        assert percentile(values, 100) == 13.0

    def test_matches_known_hundred_value_series(self) -> None:
        values = [float(v) for v in range(1, 101)]
        assert percentile(values, 50) == pytest.approx(50.5)
        assert percentile(values, 95) == pytest.approx(95.05)
        assert percentile(values, 99) == pytest.approx(99.01)

    def test_empty_list_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            percentile([], 50)

    @pytest.mark.parametrize("p", [-1, 100.1])
    def test_percentile_outside_range_is_rejected(self, p: float) -> None:
        with pytest.raises(ValueError):
            percentile([1.0], p)


class TestSummarize:
    def test_counts_and_error_rate_include_timeouts(self) -> None:
        samples = [
            _ok("a", 0.0, 10),
            _ok("a", 0.1, 30),
            Sample("a", 0.2, 5, "error", "boom"),
            Sample("a", 0.3, 60000, "timeout", "sem resposta"),
        ]
        summary = summarize(samples, duration_s=2.0)
        assert (summary["calls"], summary["ok"], summary["errors"], summary["timeouts"]) == (
            4,
            2,
            1,
            1,
        )
        assert summary["error_rate"] == 0.5
        assert summary["throughput_cps"] == 2.0

    def test_latency_covers_only_ok_calls(self) -> None:
        samples = [
            _ok("a", 0.0, 10),
            _ok("a", 0.1, 30),
            Sample("a", 0.2, 1, "error"),
            Sample("a", 0.3, 60000, "timeout"),
        ]
        summary = summarize(samples, 1.0)
        assert summary["min_ms"] == 10
        assert summary["max_ms"] == 30
        assert summary["mean_ms"] == 20
        assert summary["p50_ms"] == 20

    def test_no_ok_calls_leaves_latency_empty(self) -> None:
        summary = summarize([Sample("a", 0.0, 5, "error")], 1.0)
        assert summary["p50_ms"] is None
        assert summary["max_ms"] is None
        assert summary["error_rate"] == 1.0

    def test_empty_input_is_all_zero(self) -> None:
        summary = summarize([], 0.0)
        assert summary["calls"] == 0
        assert summary["error_rate"] == 0.0
        assert summary["throughput_cps"] == 0.0


class TestTimeSeries:
    def test_buckets_by_completion_time_and_keeps_empty_ones(self) -> None:
        samples = [_ok("a", 0.1, 100), _ok("a", 0.2, 300), _ok("a", 2.4, 200)]
        series = time_series(samples, duration_s=4.0)
        assert [point["t"] for point in series] == [0.0, 1.0, 2.0, 3.0]
        assert [point["calls"] for point in series] == [2, 0, 1, 0]
        assert series[1]["p50_ms"] is None
        assert series[0]["p50_ms"] == 200

    def test_tail_after_the_window_extends_the_series(self) -> None:
        series = time_series([_ok("a", 3.9, 400)], duration_s=2.0)
        assert len(series) == 5
        assert series[4]["calls"] == 1

    def test_failed_counts_errors_and_timeouts(self) -> None:
        samples = [
            Sample("a", 0.0, 10, "error"),
            Sample("a", 0.1, 10, "timeout"),
            _ok("a", 0.2, 10),
        ]
        assert time_series(samples, 1.0)[0]["failed"] == 2


def test_aggregate_splits_totals_per_tool_sorted() -> None:
    samples = [_ok("b", 0.0, 10), _ok("a", 0.1, 20), _ok("a", 0.2, 40)]
    result = aggregate(samples, 1.0)
    assert list(result["per_tool"]) == ["a", "b"]
    assert result["per_tool"]["a"]["calls"] == 2
    assert result["totals"]["calls"] == 3
    assert result["series"][0]["calls"] == 3


def test_live_stats_agree_with_the_exact_aggregation() -> None:
    samples = [
        _ok("a", 0.0, 12),
        _ok("a", 0.4, 48),
        _ok("b", 1.1, 20),
        Sample("b", 1.2, 5, "error"),
        Sample("a", 1.3, 400, "timeout"),
        _ok("a", 2.2, 31),
    ]
    live = LiveStats()
    for sample in samples:
        live.add(sample)
    expected = summarize(samples, 3.0)
    assert live.summary(3.0) == pytest.approx(expected)
    exact_series = time_series(samples, 3.0)
    assert live.recent_series(2.5, window=10)[: len(exact_series)] == exact_series


def test_live_stats_recent_series_is_limited_to_the_window() -> None:
    live = LiveStats()
    for second in range(10):
        live.add(_ok("a", float(second), 10))
    recent = live.recent_series(now_s=9.5, window=3)
    assert [point["t"] for point in recent] == [7.0, 8.0, 9.0]
