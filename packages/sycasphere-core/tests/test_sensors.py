# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_sensors.py
创建者    : Sycamore
创建日期  : 2026-07-21
最后修改  : 2026-07-22
版本号    : v1.0.0

■ 用途说明:
  验证传感器定义的嵌套组件、模型引用、不可变性和无独立轨道边界。

■ 主要函数功能:
  - 传感器组成验证: 验证安装、轴、模型和元数据。
  - 模型集合验证: 验证必填测量模型和唯一模型 ID。

■ 功能特性:
  ✓ 覆盖四种首版传感器类型。
  ✓ 拒绝独立状态、重复模型和可变输入别名。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-21): 创建 SensorDefinition 契约测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from sycasphere.core.geometry import RigidTransform, SensorAxes
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.schema import SchemaVersion
from sycasphere.core.sensors import SensorDefinition, SensorType


# =============================👐Seperate👐==============================
# SensorDefinition contract tests
# =============================👐Seperate👐==============================
def _model(model_id: str) -> ModelRef:
    return ModelRef(
        model_id=model_id,
        interface_version=SchemaVersion(major=1, minor=0),
        configuration={},
    )


def _sensor() -> SensorDefinition:
    return SensorDefinition(
        id="optical-sensor-1",
        name="Optical Sensor 1",
        revision=1,
        schema_version=SchemaVersion(major=1, minor=0),
        tags=["optical", "ssa"],
        metadata={"manufacturer": "Sycamore", "bands": ["visible"]},
        sensor_type=SensorType.OPTICAL,
        mount_transform=RigidTransform(
            translation_m=[1.0, 0.0, 0.0],
            rotation_parent_to_child_wxyz=[1.0, 0.0, 0.0, 0.0],
        ),
        axes=SensorAxes(
            boresight=[1.0, 0.0, 0.0],
            horizontal=[0.0, 1.0, 0.0],
            vertical=[0.0, 0.0, 1.0],
        ),
        pointing_model=_model("sycasphere.pointing.fixed"),
        field_of_view_model=_model("sycasphere.fov.conical"),
        visibility_model=_model("sycasphere.visibility.basic"),
        measurement_models=[_model("sycasphere.measurement.angles_ra_dec")],
        error_profiles=[_model("sycasphere.error.optical_default")],
        availability_model=None,
    )


def test_sensor_exposes_strong_structure_and_data_only_models() -> None:
    sensor = _sensor()

    assert sensor.sensor_type is SensorType.OPTICAL
    assert sensor.axes.boresight == (1.0, 0.0, 0.0)
    assert sensor.measurement_models[0].model_id == "sycasphere.measurement.angles_ra_dec"
    assert sensor.availability_model is None


def test_sensor_type_contains_only_approved_values() -> None:
    assert {item.value for item in SensorType} == {"OPTICAL", "RADAR", "RADIO", "CUSTOM"}


def test_sensor_requires_at_least_one_measurement_model() -> None:
    data = _sensor().model_dump(mode="python")
    data["measurement_models"] = []

    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(data)


@pytest.mark.parametrize(
    "required_field",
    ["pointing_model", "field_of_view_model", "visibility_model", "measurement_models"],
)
def test_sensor_requires_each_scientific_model_component(required_field: str) -> None:
    data = _sensor().model_dump(mode="json")
    del data[required_field]

    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(data)


@pytest.mark.parametrize("field_name", ["measurement_models", "error_profiles"])
def test_sensor_rejects_duplicate_model_ids(field_name: str) -> None:
    data = _sensor().model_dump(mode="python")
    model = _model("duplicate.model")
    data[field_name] = [model, model]

    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(data)


def test_sensor_rejects_independent_orbit_and_state_fields() -> None:
    data = _sensor().model_dump(mode="json")
    data["initial_state"] = {
        "position_m": [0.0, 0.0, 0.0],
        "velocity_mps": [0.0, 0.0, 0.0],
    }

    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(data)


def test_sensor_deeply_freezes_metadata_and_isolates_input_aliases() -> None:
    metadata = {"calibration": {"coefficients": [1.0, 2.0]}}
    data = _sensor().model_dump(mode="python")
    data["metadata"] = metadata
    sensor = SensorDefinition.model_validate(data)

    metadata["calibration"]["coefficients"].append(3.0)

    assert sensor.metadata["calibration"]["coefficients"] == (1.0, 2.0)
    with pytest.raises(TypeError):
        sensor.metadata["calibration"]["coefficients"][0] = 0.0


@pytest.mark.parametrize("tags", [["ssa", " ssa "], [" "]])
def test_sensor_rejects_blank_or_duplicate_tags(tags: list[str]) -> None:
    data = _sensor().model_dump(mode="python")
    data["tags"] = tags

    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(data)


@pytest.mark.parametrize("revision", [0, -1, "1", True, 1.0])
def test_sensor_revision_is_a_strict_positive_integer(revision: object) -> None:
    data = _sensor().model_dump(mode="python")
    data["revision"] = revision

    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(data)


@pytest.mark.parametrize(("field_name", "value"), [("id", " "), ("name", "")])
def test_sensor_requires_non_blank_identity_fields(field_name: str, value: str) -> None:
    data = _sensor().model_dump(mode="python")
    data[field_name] = value

    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(data)


def test_sensor_rejects_non_finite_metadata_and_freezes_default_metadata() -> None:
    data = _sensor().model_dump(mode="python")
    data["metadata"] = {"calibration": math.nan}
    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(data)

    default_data = _sensor().model_dump(mode="python")
    del default_data["metadata"]
    default_sensor = SensorDefinition.model_validate(default_data)
    with pytest.raises(TypeError):
        default_sensor.metadata["changed"] = True


def test_sensor_treats_tags_as_an_order_independent_immutable_set() -> None:
    data = _sensor().model_dump(mode="python")
    data["tags"] = ["ssa", "optical"]
    sensor = SensorDefinition.model_validate(data)
    serialized = sensor.model_dump(mode="json")
    restored = SensorDefinition.model_validate(serialized)

    assert sensor.tags == frozenset({"optical", "ssa"})
    assert serialized["tags"] == ["optical", "ssa"]
    assert serialized["metadata"] == {
        "bands": ["visible"],
        "manufacturer": "Sycamore",
    }
    assert restored == sensor


def test_sensor_is_frozen_and_rejects_unknown_fields() -> None:
    sensor = _sensor()

    with pytest.raises(ValidationError):
        sensor.name = "Changed"
    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(
            {**sensor.model_dump(mode="json"), "mission_role": "PRIMARY"}
        )
