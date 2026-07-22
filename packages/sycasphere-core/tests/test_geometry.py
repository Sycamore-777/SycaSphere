# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_geometry.py
创建者    : Sycamore
创建日期  : 2026-07-22
最后修改  : 2026-07-22
版本号    : v1.0.0

■ 用途说明:
  验证传感器安装刚体变换和显式传感器坐标轴的边界契约。

■ 主要函数功能:
  - 安装变换验证: 验证 SI 平移、父到子旋转方向和 wxyz 单位四元数。
  - 传感器轴验证: 验证单位、正交且右手的 SENSOR 坐标轴。

■ 功能特性:
  ✓ 覆盖有限值、固定长度、严格数值输入、容差与不可变性。
  ✓ 覆盖 JSON 往返和非默认视轴的显式语义。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-22): 创建安装变换和传感器轴契约测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from sycasphere.core.geometry import RigidTransform, SensorAxes


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


def test_geometry_models_are_frozen() -> None:
    transform = _identity_transform()
    axes = _right_handed_axes()

    with pytest.raises(ValidationError):
        transform.translation_m = (0.0, 0.0, 0.0)
    with pytest.raises(ValidationError):
        axes.boresight = (1.0, 0.0, 0.0)
