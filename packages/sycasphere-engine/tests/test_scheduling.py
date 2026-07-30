# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_scheduling.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.1

■ 用途说明:
  验证 Engine 同时间尺度日历运算、闭区间惰性采样和确定性事件合并。

■ 主要函数功能:
  - test_sampling_forces_closed_interval_end: 验证非整除周期仍精确包含结束时刻。
  - test_event_merge_groups_maneuvers_and_sorted_products: 验证同刻机动及产品稳定排序。

■ 功能特性:
  ✓ 覆盖 UTC、TAI 和 TT 的日历进位与规范化。
  ✓ 覆盖跨尺度、闰秒、无穷秒数和非前进适配器错误。
  ✓ 验证采样及多路事件合并保持惰性与确定性。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.1 (2026-07-30): 增加前导小数零、预产出校验和不兼容类别回归覆盖。
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import islice

import pytest
from sycasphere.core import (
    Epoch,
    ErrorCategory,
    FrameKind,
    FrameRef,
    ImpulsiveManeuverSpec,
    OutputProduct,
    OutputSampling,
    PreparedManeuverEntry,
    PreparedManeuverSource,
    PreparedTimeline,
    SamplingRule,
    SimulationExecutionManifest,
    SimulationRunRequest,
    SimulationTimeRange,
    TimeScale,
)
from sycasphere.engine.errors import SimulationPreparationError
from sycasphere.engine.scheduling import (
    SameScaleCalendarTimeAdapter,
    iter_event_groups,
    iter_sampling_epochs,
)

# =============================👐Seperate👐=============================
# Test data builders
# =============================👐Seperate👐=============================


def utc(value: str) -> Epoch:
    """Build a UTC test epoch."""
    return Epoch(value=value, time_scale=TimeScale.UTC)


def tai(value: str) -> Epoch:
    """Build a TAI test epoch."""
    return Epoch(value=value, time_scale=TimeScale.TAI)


def tt(value: str) -> Epoch:
    """Build a TT test epoch."""
    return Epoch(value=value, time_scale=TimeScale.TT)


def prepared_maneuver(
    *,
    order_index: int,
    source: PreparedManeuverSource,
    epoch: Epoch,
) -> PreparedManeuverEntry:
    """Build one valid prepared impulsive maneuver."""
    return PreparedManeuverEntry(
        order_index=order_index,
        source=source,
        event_id=f"event-{order_index}",
        spacecraft_id="spacecraft-1",
        epoch=epoch,
        maneuver=ImpulsiveManeuverSpec(
            delta_v_mps=(1.0, 0.0, 0.0),
            frame=FrameRef(kind=FrameKind.J2000),
        ),
    )


def minimal_manifest(
    *,
    time_range: SimulationTimeRange,
    rules: tuple[SamplingRule, ...],
    maneuvers: tuple[PreparedManeuverEntry, ...],
) -> SimulationExecutionManifest:
    """Build only the validated Core manifest branches consumed by scheduling."""
    source_request = SimulationRunRequest.model_construct(time_range=time_range)
    timeline = PreparedTimeline(
        maneuvers=maneuvers,
        output_sampling=OutputSampling(rules=rules),
    )
    return SimulationExecutionManifest.model_construct(
        source_request=source_request,
        prepared_timeline=timeline,
    )


class CountingTimeAdapter(SameScaleCalendarTimeAdapter):
    """Count offsets to prove callers do not precompute a complete schedule."""

    def __init__(self) -> None:
        self.add_calls = 0

    def add_seconds(self, epoch: Epoch, seconds: float) -> Epoch:
        """Count and delegate one calendar offset."""
        self.add_calls += 1
        return super().add_seconds(epoch, seconds)


class StagnantTimeAdapter(SameScaleCalendarTimeAdapter):
    """Return the input epoch to exercise the scheduler progress guard."""

    def add_seconds(self, epoch: Epoch, seconds: float) -> Epoch:
        """Deliberately make no progress."""
        return epoch


_UNSUPPORTED_TIME_RANGES = (
    (
        SimulationTimeRange(
            start=utc("2026-07-30T00:00:00Z"),
            end=tai("2026-07-30T00:00:37"),
        ),
        "ENGINE_TIME_SCALE_MISMATCH",
    ),
    (
        SimulationTimeRange(
            start=utc("2016-12-31T23:59:60Z"),
            end=utc("2017-01-01T00:00:01Z"),
        ),
        "ENGINE_TIME_LEAP_SECOND_UNSUPPORTED",
    ),
    (
        SimulationTimeRange(
            start=utc("2016-12-31T23:59:58Z"),
            end=utc("2016-12-31T23:59:60Z"),
        ),
        "ENGINE_TIME_LEAP_SECOND_UNSUPPORTED",
    ),
)


# =============================👐Seperate👐=============================
# Same-scale time arithmetic
# =============================👐Seperate👐=============================


def test_time_adapter_compares_and_measures_exact_fractional_calendar_values() -> None:
    adapter = SameScaleCalendarTimeAdapter()
    start = tt("2026-07-30T23:59:59.1234567890123456789")
    end = tt("2026-07-31T00:00:00.2234567890123456789")

    assert adapter.compare(start, end) == -1
    assert adapter.compare(end, start) == 1
    assert adapter.compare(start, start) == 0
    assert adapter.seconds_between(start, end) == 1.1
    assert adapter.same_instant(start, start)


@pytest.mark.parametrize(
    ("start", "seconds", "expected"),
    (
        (utc("2024-02-28T23:59:59.5Z"), 0.5, utc("2024-02-29T00:00:00Z")),
        (tai("2026-12-31T23:59:59.9"), 0.2, tai("2027-01-01T00:00:00.1")),
        (tt("2026-03-01T00:00:00"), -0.1, tt("2026-02-28T23:59:59.9")),
    ),
)
def test_time_adapter_adds_across_calendar_boundaries_without_fraction_noise(
    start: Epoch,
    seconds: float,
    expected: Epoch,
) -> None:
    adapter = SameScaleCalendarTimeAdapter()

    assert adapter.add_seconds(start, seconds) == expected


def test_time_adapter_preserves_long_decimal_fraction_through_carry() -> None:
    adapter = SameScaleCalendarTimeAdapter()

    assert adapter.add_seconds(
        tt("2026-07-30T00:00:00.92445678901234567890123456789"),
        0.999,
    ) == tt("2026-07-30T00:00:01.92345678901234567890123456789")


def test_time_adapter_preserves_leading_fractional_zeros_and_inverse_consistency() -> None:
    adapter = SameScaleCalendarTimeAdapter()
    start = tt("2026-07-30T00:00:00.000000000000000000000000000001")
    expected = tt("2026-07-30T00:00:00.100000000000000000000000000001")

    assert adapter.add_seconds(start, 0.1) == expected
    difference = adapter.seconds_between(start, expected)
    assert difference == 0.1
    assert adapter.add_seconds(start, difference) == expected


@pytest.mark.parametrize(
    "operation",
    (
        lambda adapter: adapter.compare(
            utc("2026-07-30T00:00:00Z"),
            tai("2026-07-30T00:00:37"),
        ),
        lambda adapter: adapter.seconds_between(
            utc("2026-07-30T00:00:00Z"),
            tai("2026-07-30T00:00:37"),
        ),
        lambda adapter: adapter.same_instant(
            utc("2026-07-30T00:00:00Z"),
            tai("2026-07-30T00:00:37"),
        ),
    ),
)
def test_time_adapter_rejects_cross_scale_as_plugin_incompatible(
    operation: Callable[[SameScaleCalendarTimeAdapter], object],
) -> None:
    adapter = SameScaleCalendarTimeAdapter()

    with pytest.raises(SimulationPreparationError, match="time scale") as captured:
        operation(adapter)

    assert captured.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE
    assert captured.value.detail.code == "ENGINE_TIME_SCALE_MISMATCH"


@pytest.mark.parametrize(
    "operation",
    (
        lambda adapter: adapter.add_seconds(utc("2016-12-31T23:59:60Z"), 1.0),
        lambda adapter: adapter.compare(
            utc("2016-12-31T23:59:60Z"),
            utc("2017-01-01T00:00:00Z"),
        ),
        lambda adapter: adapter.seconds_between(
            utc("2016-12-31T23:59:59Z"),
            utc("2016-12-31T23:59:60Z"),
        ),
        lambda adapter: adapter.same_instant(
            utc("2016-12-31T23:59:60Z"),
            utc("2016-12-31T23:59:60Z"),
        ),
    ),
)
def test_time_adapter_rejects_utc_leap_second_as_plugin_incompatible(
    operation: Callable[[SameScaleCalendarTimeAdapter], object],
) -> None:
    adapter = SameScaleCalendarTimeAdapter()

    with pytest.raises(SimulationPreparationError, match="leap second") as captured:
        operation(adapter)

    assert captured.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE
    assert captured.value.detail.code == "ENGINE_TIME_LEAP_SECOND_UNSUPPORTED"


@pytest.mark.parametrize("seconds", (float("nan"), float("inf"), float("-inf")))
def test_time_adapter_rejects_non_finite_offsets(seconds: float) -> None:
    adapter = SameScaleCalendarTimeAdapter()

    with pytest.raises(SimulationPreparationError, match="finite") as captured:
        adapter.add_seconds(utc("2026-07-30T00:00:00Z"), seconds)

    assert captured.value.detail.category is ErrorCategory.VALIDATION_ERROR
    assert captured.value.detail.code == "ENGINE_TIME_OFFSET_INVALID"


@pytest.mark.parametrize(
    ("epoch", "seconds"),
    (
        (utc("9999-12-31T23:59:59Z"), 1.0),
        (utc("0001-01-01T00:00:00Z"), -0.1),
    ),
)
def test_time_adapter_reports_calendar_range_overflow_as_structured_error(
    epoch: Epoch,
    seconds: float,
) -> None:
    adapter = SameScaleCalendarTimeAdapter()

    with pytest.raises(SimulationPreparationError, match="calendar range") as captured:
        adapter.add_seconds(epoch, seconds)

    assert captured.value.detail.category is ErrorCategory.VALIDATION_ERROR
    assert captured.value.detail.code == "ENGINE_TIME_CALENDAR_RANGE"


# =============================👐Seperate👐=============================
# Lazy closed-interval sampling
# =============================👐Seperate👐=============================


def test_sampling_forces_closed_interval_end() -> None:
    adapter = SameScaleCalendarTimeAdapter()
    time_range = SimulationTimeRange(
        start=utc("2026-07-30T00:00:00Z"),
        end=utc("2026-07-30T00:00:10Z"),
    )
    rule = SamplingRule(product=OutputProduct.TRUTH_STATE, interval_s=3.0)
    assert tuple(epoch.value for epoch in iter_sampling_epochs(time_range, rule, adapter)) == (
        "2026-07-30T00:00:00Z",
        "2026-07-30T00:00:03Z",
        "2026-07-30T00:00:06Z",
        "2026-07-30T00:00:09Z",
        "2026-07-30T00:00:10Z",
    )


def test_sampling_emits_divisible_end_exactly_once() -> None:
    adapter = SameScaleCalendarTimeAdapter()
    time_range = SimulationTimeRange(
        start=tai("2026-07-30T00:00:00"),
        end=tai("2026-07-30T00:00:10"),
    )
    rule = SamplingRule(product=OutputProduct.TRUTH_STATE, interval_s=5.0)

    assert tuple(epoch.value for epoch in iter_sampling_epochs(time_range, rule, adapter)) == (
        "2026-07-30T00:00:00",
        "2026-07-30T00:00:05",
        "2026-07-30T00:00:10",
    )


def test_sampling_is_lazy_for_a_large_future_range() -> None:
    adapter = CountingTimeAdapter()
    time_range = SimulationTimeRange(
        start=utc("2026-07-30T00:00:00Z"),
        end=utc("9999-12-31T23:59:59Z"),
    )
    rule = SamplingRule(product=OutputProduct.TRUTH_STATE, interval_s=1.0)

    first_three = tuple(islice(iter_sampling_epochs(time_range, rule, adapter), 3))

    assert tuple(epoch.value for epoch in first_three) == (
        "2026-07-30T00:00:00Z",
        "2026-07-30T00:00:01Z",
        "2026-07-30T00:00:02Z",
    )
    assert adapter.add_calls == 2


def test_sampling_rejects_an_adapter_that_does_not_advance() -> None:
    time_range = SimulationTimeRange(
        start=utc("2026-07-30T00:00:00Z"),
        end=utc("2026-07-30T00:00:10Z"),
    )
    rule = SamplingRule(product=OutputProduct.TRUTH_STATE, interval_s=1.0)

    with pytest.raises(SimulationPreparationError, match="advance"):
        tuple(iter_sampling_epochs(time_range, rule, StagnantTimeAdapter()))


@pytest.mark.parametrize(
    ("time_range", "expected_code"),
    _UNSUPPORTED_TIME_RANGES,
)
def test_sampling_validates_unsupported_range_before_first_yield(
    time_range: SimulationTimeRange,
    expected_code: str,
) -> None:
    rule = SamplingRule(product=OutputProduct.TRUTH_STATE, interval_s=1.0)

    with pytest.raises(SimulationPreparationError) as captured:
        next(iter_sampling_epochs(time_range, rule, SameScaleCalendarTimeAdapter()))

    assert captured.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE
    assert captured.value.detail.code == expected_code


# =============================👐Seperate👐=============================
# Deterministic lazy event merge
# =============================👐Seperate👐=============================


def test_event_merge_groups_maneuvers_and_sorted_products() -> None:
    adapter = SameScaleCalendarTimeAdapter()
    time_range = SimulationTimeRange(
        start=utc("2026-07-30T00:00:05Z"),
        end=utc("2026-07-30T00:00:15Z"),
    )
    shared_epoch = utc("2026-07-30T00:00:05Z")
    manifest = minimal_manifest(
        time_range=time_range,
        rules=(
            SamplingRule(product=OutputProduct.TRUTH_STATE, interval_s=5.0),
            SamplingRule(product=OutputProduct.ATTITUDE_STATE, interval_s=10.0),
        ),
        maneuvers=(
            prepared_maneuver(
                order_index=0,
                source=PreparedManeuverSource.PLANNED,
                epoch=shared_epoch,
            ),
            prepared_maneuver(
                order_index=1,
                source=PreparedManeuverSource.COMMAND,
                epoch=shared_epoch,
            ),
        ),
    )

    groups = tuple(iter_event_groups(manifest, adapter))
    group = next(item for item in groups if item.epoch == shared_epoch)

    assert tuple(entry.source for entry in group.maneuvers) == (
        PreparedManeuverSource.PLANNED,
        PreparedManeuverSource.COMMAND,
    )
    assert group.sample_products == (
        OutputProduct.ATTITUDE_STATE,
        OutputProduct.TRUTH_STATE,
    )
    assert tuple(item.epoch.value for item in groups) == (
        "2026-07-30T00:00:05Z",
        "2026-07-30T00:00:10Z",
        "2026-07-30T00:00:15Z",
    )


def test_event_merge_keeps_only_one_sampling_lookahead_per_rule() -> None:
    adapter = CountingTimeAdapter()
    time_range = SimulationTimeRange(
        start=utc("2026-07-30T00:00:00Z"),
        end=utc("9999-12-31T23:59:59Z"),
    )
    manifest = minimal_manifest(
        time_range=time_range,
        rules=(
            SamplingRule(product=OutputProduct.TRUTH_STATE, interval_s=1.0),
            SamplingRule(product=OutputProduct.ATTITUDE_STATE, interval_s=2.0),
        ),
        maneuvers=(),
    )

    first_group = next(iter_event_groups(manifest, adapter))

    assert first_group.epoch == time_range.start
    assert first_group.sample_products == (
        OutputProduct.ATTITUDE_STATE,
        OutputProduct.TRUTH_STATE,
    )
    assert adapter.add_calls == 2


@pytest.mark.parametrize(
    ("time_range", "expected_code"),
    _UNSUPPORTED_TIME_RANGES,
)
def test_empty_event_merge_validates_unsupported_range(
    time_range: SimulationTimeRange,
    expected_code: str,
) -> None:
    manifest = minimal_manifest(time_range=time_range, rules=(), maneuvers=())

    with pytest.raises(SimulationPreparationError) as captured:
        next(iter_event_groups(manifest, SameScaleCalendarTimeAdapter()))

    assert captured.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE
    assert captured.value.detail.code == expected_code
