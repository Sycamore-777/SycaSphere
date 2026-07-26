# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : maneuvers.py
创建者    : Sycamore
创建日期  : 2026-07-26
最后修改  : 2026-07-26
版本号    : v1.0.0

■ 用途说明:
  定义后端中立、SI 单位且不可变的航天器机动计划、命令和推进能力契约。

■ 主要函数功能:
  - _validate_maneuver_binding: 验证机动与航天器、时刻和推进能力的绑定。
  - _validate_maneuver_frame: 验证机动矢量的坐标表示和局部坐标系绑定。

■ 功能特性:
  ✓ 支持脉冲和有限推力两种判别机动载荷
  ✓ 严格验证有限浮点 SI 数值、非零向量和局部坐标系语义

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-26): 创建机动领域契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    AllowInfNan,
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    field_serializer,
    field_validator,
    model_validator,
)
from sycasphere.core._definitions import DefinitionString
from sycasphere.core.epoch import Epoch
from sycasphere.core.frames import CoordinateRepresentation, FrameKind, FrameRef
from sycasphere.core.model_refs import ModelRef

type FiniteManeuverComponent = Annotated[
    float,
    Strict(),
    AllowInfNan(False),
]
type PositiveFiniteManeuverFloat = Annotated[
    float,
    Strict(),
    AllowInfNan(False),
    Field(gt=0.0),
]


class ManeuverType(StrEnum):
    """Kinds of propulsive maneuver supported by the public Core contract."""

    IMPULSIVE = "IMPULSIVE"
    FINITE_BURN = "FINITE_BURN"


def _normalize_supported_types(value: Any) -> tuple[ManeuverType, ...]:
    """Normalize supported maneuver kinds and reject empty or duplicate collections."""
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError("supported_types must be a collection of maneuver types")

    normalized: list[ManeuverType] = []
    for item in value:
        try:
            normalized.append(ManeuverType(item))
        except (TypeError, ValueError) as error:
            raise ValueError("supported_types must contain valid maneuver types") from error

    if not normalized:
        raise ValueError("supported_types must not be empty")
    if len(normalized) != len(set(normalized)):
        raise ValueError("supported_types must not contain duplicates")
    return tuple(normalized)


def _validate_builtin_float_vector(value: Any, field_name: str) -> Any:
    """Reject non-vector inputs and all numeric coercion before model validation."""
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a three-element vector")
    if any(type(component) is not float for component in value):
        raise ValueError(f"{field_name} components must be built-in floats")
    return value


def _validate_nonzero_vector(value: tuple[float, float, float], field_name: str) -> None:
    """Require a finite, physically meaningful three-component maneuver vector."""
    norm = math.hypot(*value)
    if math.isclose(norm, 0.0, abs_tol=0.0):
        raise ValueError(f"{field_name} must not be a zero vector")


def _validate_maneuver_frame(
    maneuver: ManeuverSpec,
    spacecraft_id: str | None = None,
    epoch: Epoch | None = None,
) -> None:
    """Validate vector-frame semantics and, when known, local-frame ownership."""
    frame = maneuver.frame
    if frame.representation is not CoordinateRepresentation.CARTESIAN:
        raise ValueError("maneuver frame must use CARTESIAN representation")
    if frame.kind is FrameKind.SENSOR:
        raise ValueError("maneuver frame must not use SENSOR")

    local_kinds = {FrameKind.LVLH, FrameKind.VVLH, FrameKind.BODY}
    if frame.kind in local_kinds and spacecraft_id is not None and frame.owner_id != spacecraft_id:
        raise ValueError("local maneuver frame owner_id must match spacecraft_id")
    if frame.kind in local_kinds and epoch is not None and frame.reference_epoch != epoch:
        raise ValueError("local maneuver frame reference_epoch must match maneuver epoch")


# =============================👐Seperate👐=============================
# Public maneuver payloads and capability
# =============================👐Seperate👐=============================
class ManeuverCapability(BaseModel):
    """Immutable physical propulsion capability available to one spacecraft."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    supported_types: frozenset[ManeuverType]
    propulsion_model: ModelRef

    @field_validator("supported_types", mode="before")
    @classmethod
    def normalize_supported_types(cls, value: Any) -> tuple[ManeuverType, ...]:
        """Validate capability kinds before Pydantic freezes them as a set."""
        return _normalize_supported_types(value)

    @field_serializer("supported_types", when_used="always")
    def serialize_supported_types(self, value: frozenset[ManeuverType]) -> list[str]:
        """Serialize supported kinds in stable enum-value order."""
        return [item.value for item in sorted(value, key=lambda item: item.value)]


class ImpulsiveManeuverSpec(BaseModel):
    """An instantaneous SI delta-velocity maneuver vector."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    maneuver_type: Literal[ManeuverType.IMPULSIVE] = ManeuverType.IMPULSIVE
    delta_v_mps: tuple[
        FiniteManeuverComponent,
        FiniteManeuverComponent,
        FiniteManeuverComponent,
    ]
    frame: FrameRef

    @field_validator("delta_v_mps", mode="before")
    @classmethod
    def validate_delta_v_input(cls, value: Any) -> Any:
        """Reject integer, boolean, and string vector components before coercion."""
        return _validate_builtin_float_vector(value, "delta_v_mps")

    @model_validator(mode="after")
    def validate_maneuver(self) -> ImpulsiveManeuverSpec:
        """Require a nonzero Cartesian vector in a permitted public frame."""
        _validate_nonzero_vector(self.delta_v_mps, "delta_v_mps")
        _validate_maneuver_frame(self)
        return self


class FiniteBurnManeuverSpec(BaseModel):
    """A finite-duration SI thrust vector maneuver."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    maneuver_type: Literal[ManeuverType.FINITE_BURN] = ManeuverType.FINITE_BURN
    duration_s: PositiveFiniteManeuverFloat
    thrust_n: tuple[
        FiniteManeuverComponent,
        FiniteManeuverComponent,
        FiniteManeuverComponent,
    ]
    frame: FrameRef

    @field_validator("duration_s", mode="before")
    @classmethod
    def validate_duration_input(cls, value: Any) -> Any:
        """Reject numeric coercion while preserving finite-value validation."""
        if type(value) is not float:
            raise ValueError("duration_s must be a built-in float")
        return value

    @field_validator("thrust_n", mode="before")
    @classmethod
    def validate_thrust_input(cls, value: Any) -> Any:
        """Reject integer, boolean, and string vector components before coercion."""
        return _validate_builtin_float_vector(value, "thrust_n")

    @model_validator(mode="after")
    def validate_maneuver(self) -> FiniteBurnManeuverSpec:
        """Require a nonzero Cartesian thrust vector in a permitted public frame."""
        _validate_nonzero_vector(self.thrust_n, "thrust_n")
        _validate_maneuver_frame(self)
        return self


type ManeuverSpec = Annotated[
    ImpulsiveManeuverSpec | FiniteBurnManeuverSpec,
    Field(discriminator="maneuver_type"),
]


# =============================👐Seperate👐=============================
# Maneuver plans, commands, and binding validation
# =============================👐Seperate👐=============================
class PlannedTruthManeuver(BaseModel):
    """A planned physical truth maneuver belonging to one spacecraft timeline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    maneuver_id: DefinitionString
    spacecraft_id: DefinitionString
    epoch: Epoch
    maneuver: ManeuverSpec

    @model_validator(mode="after")
    def validate_local_frame_binding(self) -> PlannedTruthManeuver:
        """Bind locally expressed truth maneuvers to this spacecraft and epoch."""
        _validate_maneuver_frame(self.maneuver, self.spacecraft_id, self.epoch)
        return self


class ManeuverCommand(BaseModel):
    """An immutable maneuver command addressed to one spacecraft at one epoch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: DefinitionString
    spacecraft_id: DefinitionString
    epoch: Epoch
    maneuver: ManeuverSpec

    @model_validator(mode="after")
    def validate_local_frame_binding(self) -> ManeuverCommand:
        """Bind locally expressed commands to their recipient spacecraft and epoch."""
        _validate_maneuver_frame(self.maneuver, self.spacecraft_id, self.epoch)
        return self


def _validate_maneuver_binding(
    maneuver: ManeuverSpec,
    spacecraft_id: str,
    epoch: Epoch,
    capability: ManeuverCapability | None,
) -> None:
    """Require compatible propulsion capability and valid local-frame maneuver binding."""
    _validate_maneuver_frame(maneuver, spacecraft_id, epoch)
    if capability is None:
        raise ValueError("spacecraft has no maneuver capability")
    if maneuver.maneuver_type not in capability.supported_types:
        raise ValueError("spacecraft maneuver capability has unsupported maneuver type")
