# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : sensors.py
创建者    : Sycamore
创建日期  : 2026-07-22
最后修改  : 2026-07-22
版本号    : v1.0.0

■ 用途说明:
  定义依附于父平台、无独立轨道且科学子模型可插拔的传感器契约。

■ 主要函数功能:
  - SensorType: 声明首版传感器类别。
  - SensorDefinition: 验证安装、轴、模型引用和不可变定义元数据。

■ 功能特性:
  ✓ 强制至少一个测量模型并拒绝重复模型 ID。
  ✓ 不含独立轨道、状态、加载器或后端实现。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-22): 创建传感器定义契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import field_validator
from sycasphere.core._definitions import _DefinitionBase
from sycasphere.core.geometry import RigidTransform, SensorAxes
from sycasphere.core.model_refs import ModelRef


def _require_unique_model_ids(
    values: tuple[ModelRef, ...], field_name: str
) -> tuple[ModelRef, ...]:
    """Reject ambiguous duplicate model identities in one configured collection."""
    model_ids = tuple(value.model_id for value in values)
    if len(model_ids) != len(set(model_ids)):
        raise ValueError(f"{field_name} must contain unique model_id values")
    return values


# =============================👐Seperate👐==============================
# Immutable sensor definitions
# =============================👐Seperate👐==============================
class SensorType(StrEnum):
    """Supported first-version physical sensor categories."""

    OPTICAL = "OPTICAL"
    RADAR = "RADAR"
    RADIO = "RADIO"
    CUSTOM = "CUSTOM"


class SensorDefinition(_DefinitionBase):
    """A sensor child component whose state is derived from its parent platform."""

    sensor_type: SensorType
    mount_transform: RigidTransform
    axes: SensorAxes
    pointing_model: ModelRef
    field_of_view_model: ModelRef
    visibility_model: ModelRef
    measurement_models: tuple[ModelRef, ...]
    error_profiles: tuple[ModelRef, ...] = ()
    availability_model: ModelRef | None = None

    @field_validator("measurement_models")
    @classmethod
    def validate_measurement_models(cls, value: tuple[ModelRef, ...]) -> tuple[ModelRef, ...]:
        """Require at least one non-ambiguous ideal-observation model."""
        if not value:
            raise ValueError("measurement_models must not be empty")
        return _require_unique_model_ids(value, "measurement_models")

    @field_validator("error_profiles")
    @classmethod
    def validate_error_profiles(cls, value: tuple[ModelRef, ...]) -> tuple[ModelRef, ...]:
        """Require unambiguous optional error-profile references."""
        return _require_unique_model_ids(value, "error_profiles")
