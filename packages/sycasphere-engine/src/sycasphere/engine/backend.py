# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : backend.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  定义科学后端的无基础设施依赖端口、值对象和显式注册项。

■ 主要函数功能:
  - ManeuverExecution: 验证后端脉冲机动的物理执行快照。
  - ScienceBackendRuntime: 声明单次运行的窄科学后端生命周期。

■ 功能特性:
  ✓ 不导入 Orekit、JPype 或 Java 对象
  ✓ 将后端运行时创建限制在工厂协议中
  ✓ 使用冻结值对象保存显式注册依赖

■ 待办事项:
  - [ ] 后续任务实现准备、调度和运行时端口消费方

■ 更新日志:
  v1.0.0 (2026-07-30): 创建后端端口和注册值对象

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sycasphere.core import (
    AttitudeState,
    Epoch,
    ErrorDetail,
    PluginManifest,
    PreparedManeuverEntry,
    SimulationExecutionManifest,
    SimulationOutputSummary,
    SimulationRunRequest,
    TruthManeuver,
    TruthState,
)
from sycasphere.engine.cancellation import CancellationProbe

# =============================👐Seperate👐=============================
# Preparation and runtime backend ports
# =============================👐Seperate👐=============================


class BackendConfigurationValidator(Protocol):
    """Validate backend-owned configuration without creating a backend runtime."""

    def validate(self, request: SimulationRunRequest) -> None:
        """Validate the backend-owned portion of one simulation request."""


class PreparationTimeAdapter(Protocol):
    """Perform lightweight preparation-time operations on public Core epochs."""

    def compare(self, left: Epoch, right: Epoch) -> int:
        """Return the ordering of two absolute epochs."""

    def seconds_between(self, start: Epoch, end: Epoch) -> float:
        """Return the SI-second interval from ``start`` to ``end``."""

    def add_seconds(self, epoch: Epoch, seconds: float) -> Epoch:
        """Return an epoch offset by finite SI seconds."""

    def same_instant(self, left: Epoch, right: Epoch) -> bool:
        """Return whether two epochs represent the same absolute instant."""


class PropagationOutcome(StrEnum):
    """Terminal result of a runtime propagation request."""

    REACHED_TARGET = "REACHED_TARGET"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class ManeuverExecution:
    """Physical result returned by a backend after one prepared impulse."""

    executed_epoch: Epoch
    actual_delta_v_j2000_mps: tuple[float, float, float]
    state_before: TruthState
    state_after: TruthState

    def __post_init__(self) -> None:
        """Require immutable snapshots and delta-v to describe one execution instant."""
        if self.state_before.entity_id != self.state_after.entity_id:
            raise ValueError("maneuver states must describe the same entity")
        if self.state_before.epoch != self.executed_epoch:
            raise ValueError("state_before epoch must equal executed_epoch")
        if self.state_after.epoch != self.executed_epoch:
            raise ValueError("state_after epoch must equal executed_epoch")
        if not isinstance(self.actual_delta_v_j2000_mps, tuple):
            raise ValueError("actual delta-v must be a tuple")
        if len(self.actual_delta_v_j2000_mps) != 3:
            raise ValueError("actual delta-v must contain three components")
        if any(
            type(component) is not float or not math.isfinite(component)
            for component in self.actual_delta_v_j2000_mps
        ):
            raise ValueError("actual delta-v components must be finite built-in floats")


class ScienceBackendRuntime(Protocol):
    """Narrow mutable lifecycle for one scientific backend run."""

    @property
    def current_epoch(self) -> Epoch:
        """Return the common epoch reached by all initialized space objects."""

    def initialize(self) -> None:
        """Initialize the runtime's per-run scientific state."""

    def propagate_to(
        self, target_epoch: Epoch, cancellation: CancellationProbe
    ) -> PropagationOutcome:
        """Synchronously propagate all objects to a safe point at or before the target."""

    def snapshot_truth(self) -> tuple[TruthState, ...]:
        """Return truth snapshots in stable entity-ID order."""

    def snapshot_attitudes(self) -> tuple[AttitudeState, ...]:
        """Return attitude snapshots in stable entity-ID order."""

    def execute_impulsive_maneuver(self, entry: PreparedManeuverEntry) -> ManeuverExecution:
        """Apply one prepared J2000 impulse and return its physical execution data."""

    def close(self) -> None:
        """Release per-run resources; implementations must make this operation idempotent."""


class ScienceBackendFactory(Protocol):
    """Create one new runtime from a fully prepared, immutable manifest."""

    def create(self, manifest: SimulationExecutionManifest) -> ScienceBackendRuntime:
        """Create a new runtime without reselecting plugins or mutable configuration."""


@dataclass(frozen=True, slots=True)
class ScienceBackendRegistration:
    """Explicit dependencies needed to validate and execute one science backend."""

    manifest: PluginManifest
    configuration_validator: BackendConfigurationValidator
    time_adapter: PreparationTimeAdapter
    factory: ScienceBackendFactory


# =============================👐Seperate👐=============================
# Engine output port
# =============================👐Seperate👐=============================


class SimulationOutputSink(Protocol):
    """Receive immutable Engine outputs through the run lifecycle."""

    def begin(self, manifest: SimulationExecutionManifest) -> None:
        """Start writing outputs for one prepared manifest."""

    def write_truth_states(self, batch: tuple[TruthState, ...]) -> None:
        """Write an immutable batch of truth states."""

    def write_attitude_states(self, batch: tuple[AttitudeState, ...]) -> None:
        """Write an immutable batch of attitude states."""

    def write_truth_maneuvers(self, batch: tuple[TruthManeuver, ...]) -> None:
        """Write an immutable batch of executed truth maneuvers."""

    def commit(self, summary: SimulationOutputSummary) -> None:
        """Commit all previously written output batches."""

    def abort(self, detail: ErrorDetail) -> None:
        """Discard uncommitted output after a structured failure or cancellation."""


__all__ = [
    "BackendConfigurationValidator",
    "ManeuverExecution",
    "PreparationTimeAdapter",
    "PropagationOutcome",
    "ScienceBackendFactory",
    "ScienceBackendRegistration",
    "ScienceBackendRuntime",
    "SimulationOutputSink",
]
