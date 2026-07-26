# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_schedules.py
创建者    : Sycamore
创建日期  : 2026-07-26
最后修改  : 2026-07-26
版本号    : v1.0.0

■ 用途说明:
  验证仿真时间范围、输出采样和观测调度的不可变边界契约。

■ 主要函数功能:
  - 调度契约测试: 覆盖周期和显式观测调度的类型、时间与序列化约束。
  - 输出采样测试: 覆盖产品唯一性和严格有限正采样间隔。

■ 功能特性:
  ✓ 验证同时间尺度排序与跨时间尺度延迟比较
  ✓ 验证所有调度模型拒绝未知字段且不可变

■ 更新日志:
  v1.0.0 (2026-07-26): 创建时间范围、输出采样和观测调度契约测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError
from sycasphere.core.epoch import Epoch, TimeScale
from sycasphere.core.schedules import (
    ExplicitObservationSchedule,
    ObservationSchedule,
    ObservationScheduleKind,
    OutputProduct,
    OutputSampling,
    PeriodicObservationSchedule,
    SamplingRule,
    SimulationTimeRange,
)

# =============================👐Seperate👐=============================
# Schedule contract fixtures
# =============================👐Seperate👐=============================
EPOCH_0 = Epoch(value="2026-07-26T00:00:00Z", time_scale=TimeScale.UTC)
EPOCH_10 = Epoch(value="2026-07-26T00:00:10Z", time_scale=TimeScale.UTC)


def _periodic_schedule() -> PeriodicObservationSchedule:
    """Return a minimal valid periodic observation schedule."""
    return PeriodicObservationSchedule(
        schedule_id="schedule-1",
        sensor_id="sensor-1",
        target_id="target-1",
        measurement_model_id="sycasphere.measurement.angles",
        start_epoch=EPOCH_0,
        end_epoch=EPOCH_10,
        cadence_s=2.0,
    )


def _explicit_schedule() -> ExplicitObservationSchedule:
    """Return a minimal valid explicit observation schedule."""
    return ExplicitObservationSchedule(
        schedule_id="schedule-1",
        sensor_id="sensor-1",
        target_id="target-1",
        measurement_model_id="sycasphere.measurement.angles",
        epochs=(EPOCH_0, EPOCH_10),
    )


# =============================👐Seperate👐=============================
# Output sampling contracts
# =============================👐Seperate👐=============================
def test_output_product_values_are_exact() -> None:
    assert {value.value for value in OutputProduct} == {
        "TRUTH_STATE",
        "ATTITUDE_STATE",
        "DERIVED_GEOMETRY",
    }


def test_sampling_rules_reject_duplicate_products_and_invalid_intervals() -> None:
    rule = SamplingRule(product="TRUTH_STATE", interval_s=3.0)

    with pytest.raises(ValidationError, match="product"):
        OutputSampling(rules=(rule, rule))
    for invalid in (0.0, -1.0, math.nan, math.inf, 3, True, "3"):
        with pytest.raises(ValidationError):
            SamplingRule(product="TRUTH_STATE", interval_s=invalid)


# =============================👐Seperate👐=============================
# Time range contracts
# =============================👐Seperate👐=============================
def test_simulation_time_range_is_a_nonempty_closed_interval() -> None:
    assert SimulationTimeRange(start=EPOCH_0, end=EPOCH_10).start == EPOCH_0

    with pytest.raises(ValidationError):
        SimulationTimeRange(start=EPOCH_10, end=EPOCH_0)
    with pytest.raises(ValidationError):
        SimulationTimeRange(start=EPOCH_0, end=EPOCH_0)


def test_simulation_time_range_leaves_cross_scale_ordering_to_engine() -> None:
    tai_epoch = Epoch(value="2026-07-25T23:59:59", time_scale=TimeScale.TAI)

    time_range = SimulationTimeRange(start=EPOCH_0, end=tai_epoch)

    assert time_range.end == tai_epoch


# =============================👐Seperate👐=============================
# Observation schedule contracts
# =============================👐Seperate👐=============================
def test_observation_schedule_kind_values_are_exact() -> None:
    assert {value.value for value in ObservationScheduleKind} == {"PERIODIC", "EXPLICIT"}


def test_periodic_schedule_round_trips_through_discriminated_union() -> None:
    schedule = _periodic_schedule()

    assert (
        TypeAdapter(ObservationSchedule).validate_python(schedule.model_dump(mode="json"))
        == schedule
    )


def test_periodic_schedule_requires_strict_same_scale_time_order_and_float_cadence() -> None:
    data = _periodic_schedule().model_dump(mode="python")

    with pytest.raises(ValidationError):
        PeriodicObservationSchedule.model_validate(
            {**data, "start_epoch": EPOCH_10, "end_epoch": EPOCH_0}
        )
    with pytest.raises(ValidationError):
        PeriodicObservationSchedule.model_validate({**data, "end_epoch": EPOCH_0})
    for invalid in (0.0, -1.0, math.nan, math.inf, 3, True, "2"):
        with pytest.raises(ValidationError):
            PeriodicObservationSchedule.model_validate({**data, "cadence_s": invalid})


def test_periodic_schedule_leaves_cross_scale_time_ordering_to_engine() -> None:
    tai_epoch = Epoch(value="2026-07-25T23:59:59", time_scale=TimeScale.TAI)

    schedule = PeriodicObservationSchedule(
        schedule_id="schedule-1",
        sensor_id="sensor-1",
        target_id="target-1",
        measurement_model_id="sycasphere.measurement.angles",
        start_epoch=EPOCH_0,
        end_epoch=tai_epoch,
        cadence_s=2.0,
    )

    assert schedule.end_epoch == tai_epoch


def test_explicit_schedule_requires_unique_ordered_epochs() -> None:
    with pytest.raises(ValidationError):
        ExplicitObservationSchedule(
            schedule_id="schedule-1",
            sensor_id="sensor-1",
            target_id="target-1",
            measurement_model_id="sycasphere.measurement.angles",
            epochs=(EPOCH_10, EPOCH_0),
        )
    with pytest.raises(ValidationError):
        ExplicitObservationSchedule(
            schedule_id="schedule-1",
            sensor_id="sensor-1",
            target_id="target-1",
            measurement_model_id="sycasphere.measurement.angles",
            epochs=(EPOCH_0, EPOCH_0),
        )
    with pytest.raises(ValidationError):
        ExplicitObservationSchedule(
            schedule_id="schedule-1",
            sensor_id="sensor-1",
            target_id="target-1",
            measurement_model_id="sycasphere.measurement.angles",
            epochs=(),
        )


def test_explicit_schedule_leaves_mixed_scale_ordering_to_engine() -> None:
    tai_epoch = Epoch(value="2026-07-25T23:59:59", time_scale=TimeScale.TAI)

    schedule = ExplicitObservationSchedule(
        schedule_id="schedule-1",
        sensor_id="sensor-1",
        target_id="target-1",
        measurement_model_id="sycasphere.measurement.angles",
        epochs=(EPOCH_10, tai_epoch, EPOCH_0),
    )

    assert schedule.epochs == (EPOCH_10, tai_epoch, EPOCH_0)


def test_optional_schedule_references_round_trip_as_none() -> None:
    schedule = _periodic_schedule()
    restored = PeriodicObservationSchedule.model_validate(schedule.model_dump(mode="json"))

    assert restored.error_profile_id is None
    assert restored.link_model_id is None


@pytest.mark.parametrize(
    "model",
    [
        SimulationTimeRange(start=EPOCH_0, end=EPOCH_10),
        SamplingRule(product="TRUTH_STATE", interval_s=1.0),
        OutputSampling(),
        _periodic_schedule(),
        _explicit_schedule(),
    ],
)
def test_schedule_models_are_frozen_and_reject_unknown_fields(model: BaseModel) -> None:
    with pytest.raises(ValidationError):
        model.unknown = "unknown"  # type: ignore[attr-defined]
    with pytest.raises(ValidationError):
        type(model).model_validate({**model.model_dump(mode="python"), "unknown": "unknown"})
