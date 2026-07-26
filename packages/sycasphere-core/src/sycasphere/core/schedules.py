# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : schedules.py
创建者    : Sycamore
创建日期  : 2026-07-26
最后修改  : 2026-07-26
版本号    : v1.0.0

■ 用途说明:
  定义仿真运行的时间范围、输出采样及周期和显式观测调度的不可变契约。

■ 主要函数功能:
  - SimulationTimeRange: 校验闭合且非空的仿真时间区间。
  - OutputSampling: 校验唯一产品的严格有限正秒级采样间隔。
  - ObservationSchedule: 表示周期或显式时刻的观测尝试计划。

■ 功能特性:
  ✓ 仅比较相同时间尺度的历法顺序
  ✓ 跨时间尺度顺序延迟至 Engine 进行权威比较
  ✓ 保持调度输入不可变并拒绝未知字段

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-26): 创建运行时间、输出采样和观测调度契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AllowInfNan,
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    field_validator,
    model_validator,
)
from sycasphere.core._definitions import DefinitionString
from sycasphere.core.epoch import Epoch, TimeScale, _is_strictly_before_same_scale

# =============================👐Seperate👐=============================
# Shared strict numeric and epoch-order validation
# =============================👐Seperate👐=============================
type PositiveStrictFiniteFloat = Annotated[
    float,
    Strict(),
    AllowInfNan(False),
    Field(gt=0.0),
]


def _require_builtin_float(value: Any) -> float:
    """Reject non-float inputs before Pydantic can coerce their numeric values."""
    if type(value) is not float:
        raise ValueError("intervals must be built-in float values")
    return value


def _require_same_scale_strict_order(start: Epoch, end: Epoch, field_name: str) -> None:
    """Reject equal or reversed epochs only when their declared scales match."""
    if _is_strictly_before_same_scale(start, end) is False:
        raise ValueError(f"{field_name} must be strictly increasing for the same time_scale")


# =============================👐Seperate👐=============================
# Simulation time range and output sampling
# =============================👐Seperate👐=============================
class SimulationTimeRange(BaseModel):
    """A closed, nonempty simulation interval whose cross-scale order is deferred."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: Epoch
    end: Epoch

    @model_validator(mode="after")
    def validate_nonempty_interval(self) -> Self:
        """Require start to be before end whenever both epochs share a time scale."""
        _require_same_scale_strict_order(self.start, self.end, "time range")
        return self


class OutputProduct(StrEnum):
    """Scientific products that can be sampled from a simulation run."""

    TRUTH_STATE = "TRUTH_STATE"
    ATTITUDE_STATE = "ATTITUDE_STATE"
    DERIVED_GEOMETRY = "DERIVED_GEOMETRY"


class SamplingRule(BaseModel):
    """An immutable sampling interval for one output product, expressed in SI seconds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    product: OutputProduct
    interval_s: PositiveStrictFiniteFloat

    @field_validator("interval_s", mode="before")
    @classmethod
    def validate_interval_type(cls, value: Any) -> float:
        """Require a concrete built-in float interval before numeric validation."""
        return _require_builtin_float(value)


class OutputSampling(BaseModel):
    """The immutable collection of output sampling rules for one run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rules: tuple[SamplingRule, ...] = ()

    @model_validator(mode="after")
    def validate_unique_products(self) -> Self:
        """Require at most one sampling rule for each output product."""
        products = tuple(rule.product for rule in self.rules)
        if len(products) != len(set(products)):
            raise ValueError("rules must contain unique product values")
        return self


# =============================👐Seperate👐=============================
# Observation schedule contracts
# =============================👐Seperate👐=============================
class ObservationScheduleKind(StrEnum):
    """Supported v1 observation scheduling strategies."""

    PERIODIC = "PERIODIC"
    EXPLICIT = "EXPLICIT"


class _ObservationScheduleBase(BaseModel):
    """Common immutable identity and model references for observation schedules."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schedule_id: DefinitionString
    sensor_id: DefinitionString
    target_id: DefinitionString
    measurement_model_id: DefinitionString
    error_profile_id: DefinitionString | None = None
    link_model_id: DefinitionString | None = None


class PeriodicObservationSchedule(_ObservationScheduleBase):
    """An observation attempt repeated at a fixed strictly positive SI-second cadence."""

    schedule_type: Literal[ObservationScheduleKind.PERIODIC] = ObservationScheduleKind.PERIODIC
    start_epoch: Epoch
    end_epoch: Epoch
    cadence_s: PositiveStrictFiniteFloat

    @field_validator("cadence_s", mode="before")
    @classmethod
    def validate_cadence_type(cls, value: Any) -> float:
        """Require a concrete built-in float cadence before numeric validation."""
        return _require_builtin_float(value)

    @model_validator(mode="after")
    def validate_epoch_order(self) -> Self:
        """Require a nonempty same-scale periodic range while deferring cross-scale order."""
        _require_same_scale_strict_order(self.start_epoch, self.end_epoch, "periodic epochs")
        return self


class ExplicitObservationSchedule(_ObservationScheduleBase):
    """A nonempty ordered sequence of individual observation attempt epochs."""

    schedule_type: Literal[ObservationScheduleKind.EXPLICIT] = ObservationScheduleKind.EXPLICIT
    epochs: tuple[Epoch, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_epochs(self) -> Self:
        """Reject exact duplicates and reversed same-scale epoch subsequences."""
        if len(self.epochs) != len(set(self.epochs)):
            raise ValueError("epochs must not contain duplicate values")
        previous_by_scale: dict[TimeScale, Epoch] = {}
        for epoch in self.epochs:
            previous = previous_by_scale.get(epoch.time_scale)
            if previous is not None:
                _require_same_scale_strict_order(previous, epoch, "explicit epochs")
            previous_by_scale[epoch.time_scale] = epoch
        return self


type ObservationSchedule = Annotated[
    PeriodicObservationSchedule | ExplicitObservationSchedule,
    Field(discriminator="schedule_type"),
]
