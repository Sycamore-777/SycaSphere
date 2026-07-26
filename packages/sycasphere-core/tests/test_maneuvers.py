# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_maneuvers.py
创建者    : Sycamore
创建日期  : 2026-07-26
最后修改  : 2026-07-26
版本号    : v1.0.0

■ 用途说明:
  验证机动载荷、命令绑定和航天器推进能力的不可变领域契约。

■ 主要函数功能:
  - 机动载荷验证: 验证脉冲和有限推力机动的严格 SI 输入。
  - 命令绑定验证: 验证局部坐标系、航天器和时刻的一致性。

■ 功能特性:
  ✓ 覆盖判别联合、严格浮点数、非零向量和局部坐标系约束
  ✓ 覆盖推进能力和机动类型的兼容性检查

■ 待办事项:
  - [ ] 无

■ 更新日志:
  v1.0.0 (2026-07-26): 创建机动领域契约测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError
from sycasphere.core.epoch import Epoch, TimeScale
from sycasphere.core.frames import (
    CoordinateRepresentation,
    EarthFixedFrameSpec,
    FrameKind,
    FrameRef,
    ReferenceEllipsoid,
)
from sycasphere.core.maneuvers import (
    FiniteBurnManeuverSpec,
    ImpulsiveManeuverSpec,
    ManeuverCapability,
    ManeuverCommand,
    ManeuverSpec,
    ManeuverType,
    PlannedTruthManeuver,
    _validate_maneuver_binding,
)
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.schema import SchemaVersion

EPOCH = Epoch(value="2026-07-21T00:00:00Z", time_scale=TimeScale.UTC)
OTHER_EPOCH = Epoch(value="2026-07-21T00:01:00Z", time_scale=TimeScale.UTC)


def model_ref(model_id: str) -> ModelRef:
    """Return a minimal valid data-only scientific model reference."""
    return ModelRef(
        model_id=model_id,
        interface_version=SchemaVersion(major=1, minor=0),
        configuration={},
    )


def test_impulsive_and_finite_burn_are_discriminated_and_frozen() -> None:
    impulse = ImpulsiveManeuverSpec(
        maneuver_type="IMPULSIVE",
        delta_v_mps=(0.0, 1.0, 0.0),
        frame=FrameRef(kind=FrameKind.J2000),
    )
    burn = FiniteBurnManeuverSpec(
        maneuver_type="FINITE_BURN",
        duration_s=30.0,
        thrust_n=(0.0, 20.0, 0.0),
        frame=FrameRef(kind=FrameKind.J2000),
    )

    assert TypeAdapter(ManeuverSpec).validate_python(impulse.model_dump(mode="json")) == impulse
    assert TypeAdapter(ManeuverSpec).validate_python(burn.model_dump(mode="json")) == burn
    with pytest.raises(ValidationError):
        impulse.delta_v_mps = (1.0, 0.0, 0.0)


@pytest.mark.parametrize(
    ("model", "field_name", "invalid"),
    [
        (ImpulsiveManeuverSpec, "delta_v_mps", (0.0, 0.0, 0.0)),
        (ImpulsiveManeuverSpec, "delta_v_mps", (1, 0.0, 0.0)),
        (ImpulsiveManeuverSpec, "delta_v_mps", (math.nan, 0.0, 0.0)),
        (FiniteBurnManeuverSpec, "duration_s", 0.0),
        (FiniteBurnManeuverSpec, "duration_s", 1),
        (FiniteBurnManeuverSpec, "thrust_n", (0.0, 0.0, 0.0)),
    ],
)
def test_maneuver_payloads_reject_invalid_strict_values(
    model: type[BaseModel], field_name: str, invalid: object
) -> None:
    valid_data: dict[type[BaseModel], dict[str, object]] = {
        ImpulsiveManeuverSpec: {
            "maneuver_type": "IMPULSIVE",
            "delta_v_mps": (0.0, 1.0, 0.0),
            "frame": FrameRef(kind=FrameKind.J2000),
        },
        FiniteBurnManeuverSpec: {
            "maneuver_type": "FINITE_BURN",
            "duration_s": 30.0,
            "thrust_n": (0.0, 20.0, 0.0),
            "frame": FrameRef(kind=FrameKind.J2000),
        },
    }
    data = dict(valid_data[model])
    data[field_name] = invalid

    with pytest.raises(ValidationError):
        model.model_validate(data)


@pytest.mark.parametrize("kind", [FrameKind.LVLH, FrameKind.VVLH, FrameKind.BODY])
def test_local_maneuver_frame_must_match_spacecraft_and_command_epoch(kind: FrameKind) -> None:
    with pytest.raises(ValidationError, match="owner_id"):
        ManeuverCommand(
            command_id="cmd-1",
            spacecraft_id="spacecraft-1",
            epoch=EPOCH,
            maneuver=ImpulsiveManeuverSpec(
                delta_v_mps=(0.0, 1.0, 0.0),
                frame=FrameRef(
                    kind=kind,
                    owner_id="other",
                    convention="TNW_RH",
                    reference_epoch=EPOCH,
                ),
            ),
        )
    with pytest.raises(ValidationError, match="reference_epoch"):
        ManeuverCommand(
            command_id="cmd-1",
            spacecraft_id="spacecraft-1",
            epoch=EPOCH,
            maneuver=ImpulsiveManeuverSpec(
                delta_v_mps=(0.0, 1.0, 0.0),
                frame=FrameRef(
                    kind=kind,
                    owner_id="spacecraft-1",
                    convention="TNW_RH",
                    reference_epoch=OTHER_EPOCH,
                ),
            ),
        )


@pytest.mark.parametrize(
    "frame",
    [
        FrameRef(
            kind=FrameKind.SENSOR,
            owner_id="sensor-1",
            convention="SENSOR_RH",
            reference_epoch=EPOCH,
        ),
        FrameRef(
            kind=FrameKind.EARTH_FIXED,
            representation=CoordinateRepresentation.GEODETIC,
            earth_fixed=EarthFixedFrameSpec(
                itrf_realization="ITRF2020",
                iers_conventions="IERS_2010",
                eop_data_id="iers-bulletin-a:2026-07-21",
            ),
            ellipsoid=ReferenceEllipsoid.WGS84,
        ),
    ],
)
def test_maneuver_specs_reject_sensor_and_non_cartesian_frames(frame: FrameRef) -> None:
    with pytest.raises(ValidationError):
        ImpulsiveManeuverSpec(delta_v_mps=(0.0, 1.0, 0.0), frame=frame)


def test_planned_truth_maneuver_validates_local_frame_binding() -> None:
    with pytest.raises(ValidationError, match="owner_id"):
        PlannedTruthManeuver(
            maneuver_id="truth-1",
            spacecraft_id="spacecraft-1",
            epoch=EPOCH,
            maneuver=ImpulsiveManeuverSpec(
                delta_v_mps=(0.0, 1.0, 0.0),
                frame=FrameRef(
                    kind=FrameKind.BODY,
                    owner_id="other",
                    convention="BODY_RH",
                    reference_epoch=EPOCH,
                ),
            ),
        )


def test_maneuver_capability_normalizes_serializes_and_binds_supported_type() -> None:
    capability = ManeuverCapability(
        supported_types=["FINITE_BURN", "IMPULSIVE"],
        propulsion_model=model_ref("sycasphere.propulsion.combined"),
    )
    maneuver = ImpulsiveManeuverSpec(
        delta_v_mps=(0.0, 1.0, 0.0), frame=FrameRef(kind=FrameKind.J2000)
    )

    assert capability.supported_types == frozenset(
        {ManeuverType.FINITE_BURN, ManeuverType.IMPULSIVE}
    )
    assert capability.model_dump(mode="json")["supported_types"] == ["FINITE_BURN", "IMPULSIVE"]
    _validate_maneuver_binding(maneuver, "spacecraft-1", EPOCH, capability)


@pytest.mark.parametrize(
    "supported_types",
    [[], ["IMPULSIVE", "IMPULSIVE"], [ManeuverType.IMPULSIVE, "IMPULSIVE"]],
)
def test_maneuver_capability_rejects_empty_or_duplicate_supported_types(
    supported_types: object,
) -> None:
    with pytest.raises(ValidationError):
        ManeuverCapability(
            supported_types=supported_types,
            propulsion_model=model_ref("sycasphere.propulsion.impulsive"),
        )


def test_maneuver_binding_requires_capability_and_supported_type() -> None:
    maneuver = FiniteBurnManeuverSpec(
        duration_s=30.0,
        thrust_n=(0.0, 20.0, 0.0),
        frame=FrameRef(kind=FrameKind.J2000),
    )
    impulsive_only = ManeuverCapability(
        supported_types=["IMPULSIVE"],
        propulsion_model=model_ref("sycasphere.propulsion.impulsive"),
    )

    with pytest.raises(ValueError, match="capability"):
        _validate_maneuver_binding(maneuver, "spacecraft-1", EPOCH, None)
    with pytest.raises(ValueError, match="unsupported"):
        _validate_maneuver_binding(maneuver, "spacecraft-1", EPOCH, impulsive_only)
