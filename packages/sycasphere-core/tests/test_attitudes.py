# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_attitudes.py
创建者    : Sycamore
创建日期  : 2026-07-28
最后修改  : 2026-07-28
版本号    : v1.0.0

■ 用途说明:
  验证不可变姿态状态的参考系、四元数和角速度边界契约。

■ 主要函数功能:
  - 姿态状态验证: 覆盖参考系到本体 WXYZ 四元数和角速度约束
  - 参考系验证: 覆盖允许的笛卡尔参考系与禁止的本体和传感器参考系

■ 功能特性:
  ✓ 覆盖不可变快照和嵌套模型重验证
  ✓ 覆盖四元数单位范数与严格内置浮点数要求

■ 待办事项:
  - [ ] 无

■ 更新日志:
  v1.0.0 (2026-07-28): 创建姿态状态契约测试

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from sycasphere.core.attitudes import AttitudeState
from sycasphere.core.epoch import Epoch, TimeScale
from sycasphere.core.frames import (
    CoordinateRepresentation,
    EarthFixedFrameSpec,
    FrameKind,
    FrameRef,
    ReferenceEllipsoid,
)

# =============================👐Seperate👐=============================
# Attitude-state contract tests
# =============================👐Seperate👐=============================
EPOCH = Epoch(value="2026-07-28T00:00:00Z", time_scale=TimeScale.UTC)
_EARTH_FIXED_SPEC = EarthFixedFrameSpec(
    itrf_realization="ITRF2020",
    iers_conventions="IERS_2010",
    eop_data_id="iers-bulletin-a:2026-07-28",
)


def test_attitude_state_is_reference_to_body_wxyz_and_frozen() -> None:
    state = AttitudeState(
        epoch=EPOCH,
        reference_frame=FrameRef(kind=FrameKind.J2000),
        rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
        angular_velocity_body_wrt_reference_rad_s=(0.0, 0.0, 0.01),
    )

    assert state.rotation_reference_to_body_wxyz == (1.0, 0.0, 0.0, 0.0)
    assert state.angular_velocity_body_wrt_reference_rad_s == (0.0, 0.0, 0.01)
    with pytest.raises(ValidationError):
        state.rotation_reference_to_body_wxyz = (0.0, 1.0, 0.0, 0.0)


@pytest.mark.parametrize(
    "rotation",
    [
        (2.0, 0.0, 0.0, 0.0),
        (math.nan, 0.0, 0.0, 0.0),
        (1, 0.0, 0.0, 0.0),
    ],
)
def test_attitude_state_rejects_invalid_quaternion(rotation: object) -> None:
    with pytest.raises(ValidationError):
        AttitudeState(
            epoch=EPOCH,
            reference_frame=FrameRef(kind=FrameKind.J2000),
            rotation_reference_to_body_wxyz=rotation,
        )


@pytest.mark.parametrize("kind", [FrameKind.BODY, FrameKind.SENSOR])
def test_attitude_state_rejects_body_and_sensor_reference_frames(kind: FrameKind) -> None:
    with pytest.raises(ValidationError, match="reference_frame"):
        AttitudeState(
            epoch=EPOCH,
            reference_frame=FrameRef(
                kind=kind,
                owner_id="owner-1",
                convention="RIGHT_HANDED",
                reference_epoch=EPOCH,
            ),
            rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
        )


@pytest.mark.parametrize(
    "reference_frame",
    [
        FrameRef(kind=FrameKind.J2000),
        FrameRef(kind=FrameKind.EARTH_FIXED, earth_fixed=_EARTH_FIXED_SPEC),
        FrameRef(
            kind=FrameKind.LVLH,
            owner_id="spacecraft-1",
            convention="RIGHT_HANDED",
            reference_epoch=EPOCH,
        ),
        FrameRef(
            kind=FrameKind.VVLH,
            owner_id="spacecraft-1",
            convention="RIGHT_HANDED",
            reference_epoch=EPOCH,
        ),
    ],
)
def test_attitude_state_accepts_every_allowed_cartesian_reference_frame(
    reference_frame: FrameRef,
) -> None:
    state = AttitudeState(
        epoch=EPOCH,
        reference_frame=reference_frame,
        rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
    )

    assert state.reference_frame == reference_frame


def test_attitude_state_rejects_non_cartesian_reference_frame() -> None:
    geodetic_frame = FrameRef(
        kind=FrameKind.EARTH_FIXED,
        representation=CoordinateRepresentation.GEODETIC,
        ellipsoid=ReferenceEllipsoid.WGS84,
        earth_fixed=_EARTH_FIXED_SPEC,
    )

    with pytest.raises(
        ValidationError,
        match="reference_frame must use CARTESIAN representation",
    ):
        AttitudeState(
            epoch=EPOCH,
            reference_frame=geodetic_frame,
            rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
        )


def test_attitude_state_distinguishes_unknown_and_zero_angular_velocity() -> None:
    unknown = AttitudeState(
        epoch=EPOCH,
        reference_frame=FrameRef(kind=FrameKind.J2000),
        rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
    )
    zero = AttitudeState(
        epoch=EPOCH,
        reference_frame=FrameRef(kind=FrameKind.J2000),
        rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
        angular_velocity_body_wrt_reference_rad_s=(0.0, 0.0, 0.0),
    )

    assert unknown.angular_velocity_body_wrt_reference_rad_s is None
    assert zero.angular_velocity_body_wrt_reference_rad_s == (0.0, 0.0, 0.0)


def test_attitude_state_rejects_invalid_angular_velocity_shape_and_types() -> None:
    invalid_angular_velocities: list[object] = [
        (0.0, 0.0),
        (0.0, 0.0, 0.0, 0.0),
        (0, 0.0, 0.0),
        (math.inf, 0.0, 0.0),
    ]

    for angular_velocity in invalid_angular_velocities:
        with pytest.raises(ValidationError):
            AttitudeState(
                epoch=EPOCH,
                reference_frame=FrameRef(kind=FrameKind.J2000),
                rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
                angular_velocity_body_wrt_reference_rad_s=angular_velocity,
            )


def test_attitude_state_rejects_ambiguous_quaternion_aliases() -> None:
    with pytest.raises(ValidationError):
        AttitudeState(
            epoch=EPOCH,
            reference_frame=FrameRef(kind=FrameKind.J2000),
            rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
            quaternion_xyzw=(0.0, 0.0, 0.0, 1.0),
        )


def test_attitude_state_revalidates_nested_instances() -> None:
    invalid_frame = FrameRef.model_construct(kind=FrameKind.BODY)

    with pytest.raises(ValidationError):
        AttitudeState(
            epoch=EPOCH,
            reference_frame=invalid_frame,
            rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
        )
