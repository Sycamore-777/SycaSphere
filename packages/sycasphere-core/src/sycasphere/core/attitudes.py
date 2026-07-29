# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : attitudes.py
创建者    : Sycamore
创建日期  : 2026-07-28
最后修改  : 2026-07-28
版本号    : v1.0.0

■ 用途说明:
  定义姿态真值和估计结果共享的不可变姿态状态边界模型。

■ 主要函数功能:
  - AttitudeState: 验证参考系到本体的 WXYZ 单位四元数和可选本体角速度

■ 功能特性:
  ✓ 限制姿态参考系为笛卡尔 J2000、EARTH_FIXED、LVLH 或 VVLH
  ✓ 拒绝非单位、非有限或非内置浮点数四元数及角速度分量

■ 待办事项:
  - [ ] 无

■ 更新日志:
  v1.0.0 (2026-07-28): 创建不可变姿态状态边界模型

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sycasphere.core._validation import (
    StrictFiniteFloat,
    require_builtin_float_sequence,
    snapshot_model_input,
)
from sycasphere.core.epoch import Epoch
from sycasphere.core.frames import CoordinateRepresentation, FrameKind, FrameRef

# =============================👐Seperate👐=============================
# Attitude-state validation constants
# =============================👐Seperate👐=============================
_ATTITUDE_TOLERANCE = 1e-9
_ALLOWED_REFERENCE_KINDS = {
    FrameKind.J2000,
    FrameKind.EARTH_FIXED,
    FrameKind.LVLH,
    FrameKind.VVLH,
}


# =============================👐Seperate👐=============================
# Immutable attitude state boundary model
# =============================👐Seperate👐=============================
class AttitudeState(BaseModel):
    """An immutable reference-to-body attitude quaternion at an explicit epoch."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    epoch: Epoch
    reference_frame: FrameRef
    rotation_reference_to_body_wxyz: tuple[
        StrictFiniteFloat,
        StrictFiniteFloat,
        StrictFiniteFloat,
        StrictFiniteFloat,
    ]
    angular_velocity_body_wrt_reference_rad_s: (
        tuple[
            StrictFiniteFloat,
            StrictFiniteFloat,
            StrictFiniteFloat,
        ]
        | None
    ) = None

    @field_validator("epoch", "reference_frame", mode="before")
    @classmethod
    def _snapshot_nested_model(cls, value: Any) -> Any:
        """Snapshot nested records so their public-boundary validation always reruns."""
        return snapshot_model_input(value)

    @field_validator(
        "rotation_reference_to_body_wxyz",
        "angular_velocity_body_wrt_reference_rad_s",
        mode="before",
    )
    @classmethod
    def _require_builtin_float_components(cls, value: Any, info: Any) -> Any:
        """Reject coercible numeric components before tuple and finite-value validation."""
        if value is None:
            return None
        return require_builtin_float_sequence(value, info.field_name)

    @model_validator(mode="after")
    def _validate_reference_frame_and_rotation(self) -> AttitudeState:
        """Require an allowed Cartesian reference frame and a unit WXYZ quaternion."""
        if self.reference_frame.kind not in _ALLOWED_REFERENCE_KINDS:
            raise ValueError("reference_frame must not be BODY or SENSOR")
        if self.reference_frame.representation is not CoordinateRepresentation.CARTESIAN:
            raise ValueError("reference_frame must use CARTESIAN representation")

        norm = math.sqrt(
            sum(component * component for component in self.rotation_reference_to_body_wxyz)
        )
        if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=_ATTITUDE_TOLERANCE):
            raise ValueError("rotation_reference_to_body_wxyz must have unit norm")
        return self
