# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_states.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.0.0

■ 用途说明:
  验证 CartesianState 的三维 SI 状态向量边界契约、不可变性和数值数组访问。

■ 主要函数功能:
  - 状态向量验证: 验证长度、严格浮点类型与有限数值约束。
  - 数组访问验证: 验证返回独立的 float64 NumPy 数组。

■ 功能特性:
  ✓ 覆盖 JSON 序列化和不可变性契约。
  ✓ 覆盖状态向量的边界验证和数值访问。

■ 更新日志:
  v1.0.0 (2026-07-20): 创建 CartesianState 合同测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import ValidationError
from sycasphere.core import (
    CartesianState,
    CoordinateRepresentation,
    EarthFixedFrameSpec,
    Epoch,
    FrameKind,
    FrameRef,
    ReferenceEllipsoid,
    TimeScale,
)

# =============================👐Seperate👐=============================
# Cartesian state contract tests
# =============================👐Seperate👐=============================
_EPOCH = Epoch(value="2026-07-20T10:00:00Z", scale=TimeScale.UTC)
_FRAME = FrameRef(kind=FrameKind.J2000)


def _valid_state() -> CartesianState:
    return CartesianState(
        epoch=_EPOCH,
        frame=_FRAME,
        position_m=[7_000_000.0, 0.0, 0.0],
        velocity_mps=[0.0, 7_500.0, 0.0],
    )


@pytest.mark.parametrize("field_name", ["position_m", "velocity_mps"])
@pytest.mark.parametrize("values", [[1.0, 2.0], [1.0, 2.0, 3.0, 4.0]])
def test_state_vectors_require_exactly_three_components(
    field_name: str, values: list[float]
) -> None:
    state_data = _valid_state().model_dump()
    state_data[field_name] = values

    with pytest.raises(ValidationError):
        CartesianState(**state_data)


@pytest.mark.parametrize("invalid_component", [math.nan, math.inf, -math.inf])
def test_state_vectors_reject_non_finite_components(invalid_component: float) -> None:
    state_data = _valid_state().model_dump()
    state_data["position_m"] = [invalid_component, 0.0, 0.0]

    with pytest.raises(ValidationError):
        CartesianState(**state_data)


def test_state_vectors_reject_string_coercion() -> None:
    state_data = _valid_state().model_dump()
    state_data["position_m"] = ["7000000", 0.0, 0.0]

    with pytest.raises(ValidationError):
        CartesianState(**state_data)


def test_state_rejects_geodetic_frame_representation() -> None:
    frame = FrameRef(
        kind=FrameKind.EARTH_FIXED,
        representation=CoordinateRepresentation.GEODETIC,
        ellipsoid=ReferenceEllipsoid.WGS84,
        earth_fixed=EarthFixedFrameSpec(
            itrf_realization="ITRF2020",
            iers_conventions="IERS_2010",
            eop_data_id="iers-bulletin-a:2026-07-20",
        ),
    )

    with pytest.raises(ValidationError):
        CartesianState(
            epoch=_EPOCH,
            frame=frame,
            position_m=[7_000_000.0, 0.0, 0.0],
            velocity_mps=[0.0, 7_500.0, 0.0],
        )


def test_state_serializes_si_unit_fields_as_json_arrays() -> None:
    state = _valid_state()

    assert state.model_dump(mode="json") == {
        "epoch": {"value": "2026-07-20T10:00:00Z", "scale": "UTC"},
        "frame": {
            "kind": "J2000",
            "representation": "CARTESIAN",
            "earth_fixed": None,
            "ellipsoid": None,
            "owner_id": None,
            "convention": None,
            "reference_epoch": None,
        },
        "position_m": [7_000_000.0, 0.0, 0.0],
        "velocity_mps": [0.0, 7_500.0, 0.0],
    }


def test_state_is_frozen_and_stores_immutable_vector_tuples() -> None:
    state = _valid_state()

    assert state.position_m == (7_000_000.0, 0.0, 0.0)
    assert state.velocity_mps == (0.0, 7_500.0, 0.0)
    with pytest.raises(ValidationError):
        state.position_m = (0.0, 0.0, 0.0)


def test_position_array_is_an_independent_float64_vector() -> None:
    state = _valid_state()
    position = state.position_array()

    assert position.dtype == np.float64
    assert position.shape == (3,)
    np.testing.assert_array_equal(position, [7_000_000.0, 0.0, 0.0])
    position[0] = 1.0
    assert state.position_m == (7_000_000.0, 0.0, 0.0)


def test_velocity_array_is_an_independent_float64_vector() -> None:
    state = _valid_state()
    velocity = state.velocity_array()

    assert velocity.dtype == np.float64
    assert velocity.shape == (3,)
    np.testing.assert_array_equal(velocity, [0.0, 7_500.0, 0.0])
    velocity[1] = 1.0
    assert state.velocity_mps == (0.0, 7_500.0, 0.0)
