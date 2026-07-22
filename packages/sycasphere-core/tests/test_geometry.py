# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_geometry.py
创建者    : Sycamore
创建日期  : 2026-07-22
最后修改  : 2026-07-22
版本号    : v1.1.0

■ 用途说明:
  验证传感器安装刚体变换、显式传感器坐标轴以及有效 WGS84 大地坐标位置契约。

■ 主要函数功能:
  - 安装变换验证: 验证 SI 平移、父到子旋转方向和 wxyz 单位四元数。
  - 传感器轴验证: 验证单位、正交且右手的 SENSOR 坐标轴。
  - 大地坐标位置验证: 验证 WGS84 帧约束、有限的纬度、经度、椭球高和不可变性。

■ 功能特性:
  ✓ 覆盖有限值、固定长度、严格数值输入、容差与不可变性。
  ✓ 覆盖 JSON 往返和非默认视轴的显式语义。

■ 待办事项:
  - 无

■ 更新日志:
  v1.1.0 (2026-07-22): 新增 WGS84 大地坐标位置契约测试。
  v1.0.0 (2026-07-22): 创建安装变换和传感器轴契约测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math
from collections import deque

import numpy as np
import pytest
from pydantic import ValidationError
from sycasphere.core.frames import (
    CoordinateRepresentation,
    EarthFixedFrameSpec,
    FrameKind,
    FrameRef,
    ReferenceEllipsoid,
)
from sycasphere.core.geometry import GeodeticLocation, RigidTransform, SensorAxes


# =============================👐Seperate👐==============================
# Rigid-transform and sensor-axes tests
# =============================👐Seperate👐==============================
def _identity_transform() -> RigidTransform:
    return RigidTransform(
        translation_m=[1.0, 2.0, 3.0],
        rotation_parent_to_child_wxyz=[1.0, 0.0, 0.0, 0.0],
    )


def _right_handed_axes() -> SensorAxes:
    return SensorAxes(
        boresight=[0.0, 0.0, 1.0],
        horizontal=[1.0, 0.0, 0.0],
        vertical=[0.0, 1.0, 0.0],
    )


def _axes_data_for_boresight(boresight: object) -> dict[str, object]:
    """Create a right-handed basis for the exact iterable used as boresight."""
    boresight_array = np.asarray(tuple(boresight), dtype=np.float64)
    reference = np.array([1.0, 0.0, 0.0])
    if math.isclose(abs(float(boresight_array[0])), 1.0, abs_tol=1e-9):
        reference = np.array([0.0, 1.0, 0.0])

    horizontal = np.cross(reference, boresight_array)
    horizontal /= np.linalg.norm(horizontal)
    vertical = np.cross(boresight_array, horizontal)
    return {
        "boresight": boresight,
        "horizontal": tuple(horizontal),
        "vertical": tuple(vertical),
    }


def test_rigid_transform_uses_explicit_parent_to_child_wxyz_contract() -> None:
    transform = _identity_transform()

    assert transform.translation_m == (1.0, 2.0, 3.0)
    assert transform.rotation_parent_to_child_wxyz == (1.0, 0.0, 0.0, 0.0)
    assert transform.model_dump(mode="json") == {
        "translation_m": [1.0, 2.0, 3.0],
        "rotation_parent_to_child_wxyz": [1.0, 0.0, 0.0, 0.0],
    }


def test_rigid_transform_round_trips_as_json_without_normalizing_within_tolerance() -> None:
    transform = RigidTransform(
        translation_m=[1.0, 2.0, 3.0],
        rotation_parent_to_child_wxyz=[1.0 + 5e-10, 0.0, 0.0, 0.0],
    )
    serialized = transform.model_dump(mode="json")

    assert serialized["rotation_parent_to_child_wxyz"] == [1.0 + 5e-10, 0.0, 0.0, 0.0]
    assert RigidTransform.model_validate(serialized) == transform


def test_rigid_transform_rejects_xyzw_compatibility_field() -> None:
    with pytest.raises(ValidationError):
        RigidTransform.model_validate(
            {
                "translation_m": [0.0, 0.0, 0.0],
                "rotation_parent_to_child_xyzw": [0.0, 0.0, 0.0, 1.0],
            }
        )


@pytest.mark.parametrize(
    "quaternion",
    [
        [0.0, 0.0, 0.0, 0.0],
        [2.0, 0.0, 0.0, 0.0],
        [1.0 + 2e-9, 0.0, 0.0, 0.0],
        [math.nan, 0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [1.0, 0.0, 0.0, 0.0, 0.0],
        ["1.0", 0.0, 0.0, 0.0],
        [1, 0.0, 0.0, 0.0],
    ],
)
def test_rigid_transform_rejects_invalid_quaternions(quaternion: list[object]) -> None:
    with pytest.raises(ValidationError):
        RigidTransform(
            translation_m=[0.0, 0.0, 0.0],
            rotation_parent_to_child_wxyz=quaternion,
        )


@pytest.mark.parametrize(
    "translation",
    [
        [0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0],
        [math.inf, 0.0, 0.0],
        ["0.0", 0.0, 0.0],
        [0, 0.0, 0.0],
    ],
)
def test_rigid_transform_rejects_invalid_translation(translation: list[object]) -> None:
    with pytest.raises(ValidationError):
        RigidTransform(
            translation_m=translation,
            rotation_parent_to_child_wxyz=[1.0, 0.0, 0.0, 0.0],
        )


@pytest.mark.parametrize(
    "container",
    [
        deque([1.0, 2.0, 3.0]),
        {1.0, 2.0, 3.0},
        np.array([1.0, 2.0, 3.0]),
    ],
)
def test_rigid_transform_rejects_non_json_component_containers(container: object) -> None:
    with pytest.raises(ValidationError):
        RigidTransform(
            translation_m=container,
            rotation_parent_to_child_wxyz=[1.0, 0.0, 0.0, 0.0],
        )


@pytest.mark.parametrize("container_type", [list, tuple])
def test_rigid_transform_accepts_list_and_tuple_float_components(
    container_type: type[list[float]] | type[tuple[float, ...]],
) -> None:
    transform = RigidTransform(
        translation_m=container_type([1.0, 2.0, 3.0]),
        rotation_parent_to_child_wxyz=container_type([1.0, 0.0, 0.0, 0.0]),
    )

    assert transform.translation_m == (1.0, 2.0, 3.0)


def test_sensor_axes_accept_explicit_right_handed_non_default_boresight() -> None:
    axes = _right_handed_axes()

    assert axes.boresight == (0.0, 0.0, 1.0)
    assert axes.horizontal == (1.0, 0.0, 0.0)
    assert axes.vertical == (0.0, 1.0, 0.0)


def test_sensor_axes_round_trip_as_json_and_preserve_within_tolerance_values() -> None:
    axes = SensorAxes(
        boresight=[0.0, 0.0, 1.0 + 5e-10],
        horizontal=[1.0, 0.0, 0.0],
        vertical=[0.0, 1.0, 0.0],
    )
    serialized = axes.model_dump(mode="json")

    assert serialized["boresight"] == [0.0, 0.0, 1.0 + 5e-10]
    assert SensorAxes.model_validate(serialized) == axes


@pytest.mark.parametrize(
    "overrides",
    [
        {"boresight": [0.0, 0.0, 2.0]},
        {"horizontal": [1.0, 1.0, 0.0]},
        {"vertical": [1.0, 0.0, 0.0]},
        {"vertical": [0.0, -1.0, 0.0]},
        {"boresight": [math.nan, 0.0, 1.0]},
        {"horizontal": [1.0, 0.0]},
        {"vertical": ["0.0", 1.0, 0.0]},
        {"vertical": [0, 1.0, 0.0]},
    ],
)
def test_sensor_axes_reject_non_unit_non_orthogonal_or_left_handed_axes(
    overrides: dict[str, list[object]],
) -> None:
    data = _right_handed_axes().model_dump()
    data.update(overrides)

    with pytest.raises(ValidationError):
        SensorAxes.model_validate(data)


@pytest.mark.parametrize(
    "boresight",
    [
        deque([0.0, 0.0, 1.0]),
        {0.0, 0.6, 0.8},
        np.array([0.0, 0.0, 1.0]),
    ],
)
def test_sensor_axes_reject_non_json_component_containers(boresight: object) -> None:
    with pytest.raises(ValidationError):
        SensorAxes.model_validate(_axes_data_for_boresight(boresight))


@pytest.mark.parametrize("container_type", [list, tuple])
def test_sensor_axes_accept_list_and_tuple_float_components(
    container_type: type[list[float]] | type[tuple[float, ...]],
) -> None:
    axes = SensorAxes(
        boresight=container_type([0.0, 0.0, 1.0]),
        horizontal=container_type([1.0, 0.0, 0.0]),
        vertical=container_type([0.0, 1.0, 0.0]),
    )

    assert axes.boresight == (0.0, 0.0, 1.0)


def test_geometry_models_are_frozen() -> None:
    transform = _identity_transform()
    axes = _right_handed_axes()

    with pytest.raises(ValidationError):
        transform.translation_m = (0.0, 0.0, 0.0)
    with pytest.raises(ValidationError):
        axes.boresight = (1.0, 0.0, 0.0)


# =============================👐Seperate👐==============================
# WGS84 geodetic-location tests
# =============================👐Seperate👐==============================
def _geodetic_frame() -> FrameRef:
    return FrameRef(
        kind=FrameKind.EARTH_FIXED,
        representation=CoordinateRepresentation.GEODETIC,
        earth_fixed=EarthFixedFrameSpec(
            itrf_realization="ITRF2020",
            iers_conventions="IERS_2010",
            eop_data_id="iers-bulletin-a:2026-07-21",
        ),
        ellipsoid=ReferenceEllipsoid.WGS84,
    )


def test_geodetic_location_accepts_wgs84_and_negative_ellipsoid_height() -> None:
    location = GeodeticLocation(
        frame=_geodetic_frame(),
        longitude_rad=2.03444394,
        latitude_rad=0.69625189,
        ellipsoid_height_m=-20.0,
    )

    assert location.frame.ellipsoid is ReferenceEllipsoid.WGS84
    assert location.ellipsoid_height_m == -20.0


@pytest.mark.parametrize(
    ("longitude_rad", "latitude_rad"),
    [
        (math.pi + 1e-6, 0.0),
        (-math.pi - 1e-6, 0.0),
        (0.0, math.pi / 2 + 1e-6),
        (0.0, -math.pi / 2 - 1e-6),
    ],
)
def test_geodetic_location_rejects_out_of_range_angles(
    longitude_rad: float,
    latitude_rad: float,
) -> None:
    with pytest.raises(ValidationError):
        GeodeticLocation(
            frame=_geodetic_frame(),
            longitude_rad=longitude_rad,
            latitude_rad=latitude_rad,
            ellipsoid_height_m=0.0,
        )


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_geodetic_location_rejects_non_finite_height(invalid: float) -> None:
    with pytest.raises(ValidationError):
        GeodeticLocation(
            frame=_geodetic_frame(),
            longitude_rad=0.0,
            latitude_rad=0.0,
            ellipsoid_height_m=invalid,
        )


def test_geodetic_location_rejects_non_geodetic_or_non_wgs84_frame() -> None:
    with pytest.raises(ValidationError):
        GeodeticLocation(
            frame=FrameRef(kind=FrameKind.J2000),
            longitude_rad=0.0,
            latitude_rad=0.0,
            ellipsoid_height_m=0.0,
        )


@pytest.mark.parametrize("field_name", ["longitude_rad", "latitude_rad", "ellipsoid_height_m"])
def test_geodetic_location_rejects_non_float_number_coercion(field_name: str) -> None:
    data: dict[str, object] = {
        "frame": _geodetic_frame(),
        "longitude_rad": 0.0,
        "latitude_rad": 0.0,
        "ellipsoid_height_m": 0.0,
    }
    data[field_name] = "2.0"

    with pytest.raises(ValidationError):
        GeodeticLocation.model_validate(data)


@pytest.mark.parametrize("field_name", ["longitude_rad", "latitude_rad", "ellipsoid_height_m"])
def test_geodetic_location_rejects_non_builtin_float_numbers(field_name: str) -> None:
    data: dict[str, object] = {
        "frame": _geodetic_frame(),
        "longitude_rad": 0.0,
        "latitude_rad": 0.0,
        "ellipsoid_height_m": 0.0,
    }
    data[field_name] = 0

    with pytest.raises(ValidationError):
        GeodeticLocation.model_validate(data)


def test_geodetic_location_round_trips_and_is_frozen() -> None:
    location = GeodeticLocation(
        frame=_geodetic_frame(),
        longitude_rad=1.0,
        latitude_rad=0.5,
        ellipsoid_height_m=100.0,
    )
    restored = GeodeticLocation.model_validate(location.model_dump(mode="json"))

    assert restored == location
    with pytest.raises(ValidationError):
        location.longitude_rad = 0.0
