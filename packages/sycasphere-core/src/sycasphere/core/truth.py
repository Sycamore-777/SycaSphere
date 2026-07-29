# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : truth.py
创建者    : Sycamore
创建日期  : 2026-07-28
最后修改  : 2026-07-28
版本号    : v1.0.0

■ 用途说明:
  定义仿真引擎输出的不可变真值状态快照和真实机动事实契约。

■ 主要函数功能:
  - TruthState: 验证实体的笛卡尔状态、可选姿态和质量快照
  - TruthManeuver: 验证实际 J2000 机动、来源谱系和前后状态一致性

■ 功能特性:
  ✓ 保持真值状态与真实机动的深度不可变边界
  ✓ 严格验证真实机动的实体、历元、坐标系和质量语义

■ 待办事项:
  - [ ] 无

■ 更新日志:
  v1.0.0 (2026-07-28): 创建真值状态和真实机动结果契约

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

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
from sycasphere.core._validation import (
    StrictFiniteFloat,
    require_builtin_float_sequence,
    snapshot_model_input,
)
from sycasphere.core.attitudes import AttitudeState
from sycasphere.core.epoch import Epoch, _is_strictly_before_same_scale
from sycasphere.core.frames import FrameKind
from sycasphere.core.states import CartesianState

# =============================👐Seperate👐=============================
# Strict truth-result boundary types
# =============================👐Seperate👐=============================
PositiveStrictFiniteFloat = Annotated[float, Strict(), AllowInfNan(False), Field(gt=0.0)]
type Vector3 = tuple[StrictFiniteFloat, StrictFiniteFloat, StrictFiniteFloat]


class ManeuverTruthSource(StrEnum):
    """The authoritative input lineage that caused an executed truth maneuver."""

    PLANNED = "PLANNED"
    COMMAND = "COMMAND"


# =============================👐Seperate👐=============================
# Immutable truth state snapshot
# =============================👐Seperate👐=============================
class TruthState(BaseModel):
    """An immutable simulation-truth snapshot for one entity at one Cartesian epoch."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    entity_id: DefinitionString
    cartesian_state: CartesianState
    attitude_state: AttitudeState | None = None
    mass_kg: PositiveStrictFiniteFloat | None = None

    @field_validator("cartesian_state", "attitude_state", mode="before")
    @classmethod
    def _snapshot_nested_model(cls, value: Any) -> Any:
        """Snapshot nested records so their boundary validation always reruns."""
        return snapshot_model_input(value)

    @field_validator("mass_kg", mode="before")
    @classmethod
    def _require_builtin_float_mass(cls, value: Any) -> Any:
        """Reject integer and coercible mass values before finite positive validation."""
        if value is not None and type(value) is not float:
            raise ValueError("mass_kg must be a built-in float")
        return value

    @model_validator(mode="after")
    def _validate_attitude_epoch(self) -> TruthState:
        """Require any attitude snapshot to describe the Cartesian state epoch."""
        if (
            self.attitude_state is not None
            and self.attitude_state.epoch != self.cartesian_state.epoch
        ):
            raise ValueError("attitude_state epoch must equal cartesian_state epoch")
        return self

    @property
    def epoch(self) -> Epoch:
        """Return the sole serialized state epoch from the Cartesian snapshot."""
        return self.cartesian_state.epoch


# =============================👐Seperate👐=============================
# Immutable executed truth maneuver
# =============================👐Seperate👐=============================
class TruthManeuver(BaseModel):
    """An immutable fact recording one executed J2000 truth maneuver and its snapshots."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    maneuver_event_id: DefinitionString
    source_kind: ManeuverTruthSource
    source_id: DefinitionString
    entity_id: DefinitionString
    scheduled_epoch: Epoch
    executed_epoch: Epoch
    actual_delta_v_j2000_mps: Vector3
    state_before: TruthState
    state_after: TruthState

    @field_validator(
        "scheduled_epoch",
        "executed_epoch",
        "state_before",
        "state_after",
        mode="before",
    )
    @classmethod
    def _snapshot_nested_model(cls, value: Any) -> Any:
        """Snapshot nested records so their boundary validation always reruns."""
        return snapshot_model_input(value)

    @field_validator("actual_delta_v_j2000_mps", mode="before")
    @classmethod
    def _require_builtin_float_components(cls, value: Any) -> Any:
        """Reject coercible actual Δv components before tuple and finite-value validation."""
        return require_builtin_float_sequence(value, "actual_delta_v_j2000_mps")

    @model_validator(mode="after")
    def _validate_execution_fact(self) -> TruthManeuver:
        """Require state lineage and physical semantics for an executed truth maneuver."""
        states = (self.state_before, self.state_after)
        if any(state.entity_id != self.entity_id for state in states):
            raise ValueError("truth maneuver states must match entity_id")
        if any(state.epoch != self.executed_epoch for state in states):
            raise ValueError("truth maneuver states must match executed_epoch")
        if any(state.cartesian_state.frame.kind is not FrameKind.J2000 for state in states):
            raise ValueError("truth maneuver states must use J2000")
        if _is_strictly_before_same_scale(self.executed_epoch, self.scheduled_epoch) is True:
            raise ValueError("executed_epoch must not be before scheduled_epoch")
        before_mass = self.state_before.mass_kg
        after_mass = self.state_after.mass_kg
        if before_mass is not None and after_mass is not None and after_mass > before_mass:
            raise ValueError("truth maneuver mass must not increase")
        return self
