# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : geometry.py
创建者    : Sycamore
创建日期  : 2026-07-22
最后修改  : 2026-07-22
版本号    : v1.1.0

■ 用途说明:
  定义传感器安装刚体变换、显式右手传感器轴以及有效 WGS84 大地坐标位置的不可变边界契约。

■ 主要函数功能:
  - RigidTransform: 验证父坐标系到子坐标系的 SI 平移和 wxyz 旋转。
  - SensorAxes: 验证单位、正交且右手的 SENSOR 坐标轴。
  - GeodeticLocation: 验证 EARTH_FIXED/GEODETIC/WGS84 帧和纬度、经度、椭球高。

■ 功能特性:
  ✓ 固定四元数顺序和父到子旋转方向。
  ✓ 使用严格有限浮点值并拒绝静默归一化。

■ 待办事项:
  - 无

■ 更新日志:
  v1.1.0 (2026-07-22): 新增 WGS84 大地坐标位置契约。
  v1.0.0 (2026-07-22): 创建安装变换和传感器轴契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math
from typing import Annotated, Any

import numpy as np
from pydantic import (
    AllowInfNan,
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    field_validator,
    model_validator,
)
from sycasphere.core.frames import (
    CoordinateRepresentation,
    FrameKind,
    FrameRef,
    ReferenceEllipsoid,
)

type FiniteComponent = Annotated[float, Strict(), AllowInfNan(False)]
type Vector3 = tuple[FiniteComponent, FiniteComponent, FiniteComponent]
type QuaternionWxyz = tuple[
    FiniteComponent,
    FiniteComponent,
    FiniteComponent,
    FiniteComponent,
]

_GEOMETRY_TOLERANCE = 1e-9


def _as_vector(value: Vector3) -> np.ndarray:
    """Return a validated three-component tuple as a float64 array."""
    return np.asarray(value, dtype=np.float64)


def _validate_component_container(value: Any) -> Any:
    """Require JSON-array containers with explicit built-in float components."""
    if not isinstance(value, (list, tuple)):
        raise ValueError("geometry components must be supplied as a list or tuple")
    if any(type(component) is not float for component in value):
        raise ValueError("geometry components must be built-in floats")
    return value


# =============================👐Seperate👐==============================
# Immutable installation and sensor-axis geometry
# =============================👐Seperate👐==============================
class RigidTransform(BaseModel):
    """A fixed parent-to-child transform with scalar-first quaternion order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    translation_m: Vector3
    rotation_parent_to_child_wxyz: QuaternionWxyz

    @field_validator("translation_m", "rotation_parent_to_child_wxyz", mode="before")
    @classmethod
    def validate_component_container(cls, value: Any) -> Any:
        """Require JSON-array containers with explicit float components."""
        return _validate_component_container(value)

    @model_validator(mode="after")
    def validate_unit_quaternion(self) -> RigidTransform:
        """Require a unit wxyz quaternion without silently normalizing it."""
        norm = math.sqrt(
            sum(component * component for component in self.rotation_parent_to_child_wxyz)
        )
        if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=_GEOMETRY_TOLERANCE):
            raise ValueError("rotation_parent_to_child_wxyz must be a unit quaternion")
        return self


class SensorAxes(BaseModel):
    """Explicit right-handed boresight and image-plane axes in SENSOR coordinates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    boresight: Vector3
    horizontal: Vector3
    vertical: Vector3

    @field_validator("boresight", "horizontal", "vertical", mode="before")
    @classmethod
    def validate_component_container(cls, value: Any) -> Any:
        """Require JSON-array containers with explicit float components."""
        return _validate_component_container(value)

    @model_validator(mode="after")
    def validate_right_handed_orthonormal_axes(self) -> SensorAxes:
        """Require unit, orthogonal axes where horizontal × vertical equals boresight."""
        boresight = _as_vector(self.boresight)
        horizontal = _as_vector(self.horizontal)
        vertical = _as_vector(self.vertical)

        for name, vector in (
            ("boresight", boresight),
            ("horizontal", horizontal),
            ("vertical", vertical),
        ):
            if not math.isclose(
                float(np.linalg.norm(vector)),
                1.0,
                rel_tol=0.0,
                abs_tol=_GEOMETRY_TOLERANCE,
            ):
                raise ValueError(f"{name} must be a unit vector")

        for first, second in (
            (boresight, horizontal),
            (boresight, vertical),
            (horizontal, vertical),
        ):
            if not math.isclose(
                float(np.dot(first, second)),
                0.0,
                rel_tol=0.0,
                abs_tol=_GEOMETRY_TOLERANCE,
            ):
                raise ValueError("sensor axes must be pairwise orthogonal")

        if not np.allclose(
            np.cross(horizontal, vertical),
            boresight,
            rtol=0.0,
            atol=_GEOMETRY_TOLERANCE,
        ):
            raise ValueError("sensor axes must satisfy horizontal cross vertical = boresight")
        return self


class GeodeticLocation(BaseModel):
    """A validated WGS84 location in an explicitly versioned Earth-fixed frame."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    frame: FrameRef
    longitude_rad: FiniteComponent = Field(ge=-math.pi, le=math.pi)
    latitude_rad: FiniteComponent = Field(ge=-math.pi / 2, le=math.pi / 2)
    ellipsoid_height_m: FiniteComponent

    @field_validator("longitude_rad", "latitude_rad", "ellipsoid_height_m", mode="before")
    @classmethod
    def validate_builtin_float(cls, value: Any) -> Any:
        """Require explicit built-in floats at this scalar serialization boundary."""
        if type(value) is not float:
            raise ValueError("geodetic coordinates must be built-in floats")
        return value

    @model_validator(mode="after")
    def validate_wgs84_geodetic_frame(self) -> GeodeticLocation:
        """Require EARTH_FIXED/GEODETIC with the WGS84 reference ellipsoid."""
        if (
            self.frame.kind is not FrameKind.EARTH_FIXED
            or self.frame.representation is not CoordinateRepresentation.GEODETIC
            or self.frame.ellipsoid is not ReferenceEllipsoid.WGS84
        ):
            raise ValueError("GeodeticLocation requires an EARTH_FIXED GEODETIC WGS84 frame")
        return self
