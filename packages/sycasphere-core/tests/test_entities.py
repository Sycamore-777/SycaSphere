# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_entities.py
创建者    : Sycamore
创建日期  : 2026-07-22
最后修改  : 2026-07-22
版本号    : v1.0.0

■ 用途说明:
  验证航天器、其他空间对象和地面站的判别联合与传感器组合边界。

■ 主要函数功能:
  - 实体类型验证: 验证三种具体实体和物理参数。
  - 组合验证: 验证传感器父子关系、唯一 ID 和任务角色隔离。

■ 功能特性:
  ✓ 覆盖空间对象初始状态和地面站 WGS84 位置。
  ✓ 覆盖不可变 metadata、capabilities 和 JSON 联合往返。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-22): 创建实体层级契约测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import pytest
from pydantic import TypeAdapter, ValidationError
from sycasphere.core.entities import (
    EntityDefinition,
    EntityType,
    GroundStationDefinition,
    OtherSpaceObjectDefinition,
    SpacecraftDefinition,
    SpaceObjectPhysicalProperties,
)
from sycasphere.core.epoch import Epoch, TimeScale
from sycasphere.core.frames import (
    CoordinateRepresentation,
    EarthFixedFrameSpec,
    FrameKind,
    FrameRef,
    ReferenceEllipsoid,
)
from sycasphere.core.geometry import GeodeticLocation, RigidTransform, SensorAxes
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.schema import SchemaVersion
from sycasphere.core.sensors import SensorDefinition, SensorType
from sycasphere.core.states import CartesianState

_ENTITY_ADAPTER = TypeAdapter(EntityDefinition)


# =============================👐Seperate👐==============================
# Entity fixtures
# =============================👐Seperate👐==============================
def _model(model_id: str) -> ModelRef:
    return ModelRef(
        model_id=model_id,
        interface_version=SchemaVersion(major=1, minor=0),
        configuration={},
    )


def _sensor(sensor_id: str = "sensor-1") -> SensorDefinition:
    return SensorDefinition(
        id=sensor_id,
        name=sensor_id,
        revision=1,
        schema_version=SchemaVersion(major=1, minor=0),
        sensor_type=SensorType.OPTICAL,
        mount_transform=RigidTransform(
            translation_m=[0.0, 0.0, 0.0],
            rotation_parent_to_child_wxyz=[1.0, 0.0, 0.0, 0.0],
        ),
        axes=SensorAxes(
            boresight=[0.0, 0.0, 1.0],
            horizontal=[1.0, 0.0, 0.0],
            vertical=[0.0, 1.0, 0.0],
        ),
        pointing_model=_model("sycasphere.pointing.fixed"),
        field_of_view_model=_model("sycasphere.fov.conical"),
        visibility_model=_model("sycasphere.visibility.basic"),
        measurement_models=[_model("sycasphere.measurement.angles_ra_dec")],
    )


def _state() -> CartesianState:
    return CartesianState(
        epoch=Epoch(value="2026-07-21T00:00:00Z", time_scale=TimeScale.UTC),
        frame=FrameRef(kind=FrameKind.J2000),
        position_m=[7_000_000.0, 0.0, 0.0],
        velocity_mps=[0.0, 7_500.0, 0.0],
    )


def _properties() -> SpaceObjectPhysicalProperties:
    return SpaceObjectPhysicalProperties(
        mass_kg=1_000.0,
        cross_section_area_m2=12.0,
        drag_coefficient=2.2,
        solar_radiation_pressure_coefficient=1.3,
    )


def _location() -> GeodeticLocation:
    return GeodeticLocation(
        frame=FrameRef(
            kind=FrameKind.EARTH_FIXED,
            representation=CoordinateRepresentation.GEODETIC,
            earth_fixed=EarthFixedFrameSpec(
                itrf_realization="ITRF2020",
                iers_conventions="IERS_2010",
                eop_data_id="iers-bulletin-a:2026-07-21",
            ),
            ellipsoid=ReferenceEllipsoid.WGS84,
        ),
        longitude_rad=2.0,
        latitude_rad=0.5,
        ellipsoid_height_m=50.0,
    )


def _spacecraft() -> SpacecraftDefinition:
    return SpacecraftDefinition(
        id="spacecraft-1",
        name="Observer",
        revision=1,
        schema_version=SchemaVersion(major=1, minor=0),
        tags=["observer"],
        metadata={"programme": {"name": "demo"}},
        capabilities=["sensor_host", "maneuverable"],
        initial_state=_state(),
        physical_properties=_properties(),
        dynamics_model=_model("sycasphere.dynamics.numerical"),
        attitude_model=_model("sycasphere.attitude.nadir"),
        sensors=[_sensor()],
    )


# =============================👐Seperate👐==============================
# Entity hierarchy tests
# =============================👐Seperate👐==============================
def test_entity_type_contains_only_three_physical_entity_kinds() -> None:
    assert {item.value for item in EntityType} == {
        "SPACECRAFT",
        "OTHER_SPACE_OBJECT",
        "GROUND_STATION",
    }


def test_spacecraft_composes_state_physics_models_and_sensors() -> None:
    spacecraft = _spacecraft()

    assert spacecraft.entity_type is EntityType.SPACECRAFT
    assert spacecraft.sensors[0].id == "sensor-1"
    assert spacecraft.initial_state.frame.kind is FrameKind.J2000


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("id", " "),
        ("name", ""),
        ("revision", 0),
        ("revision", -1),
        ("revision", "1"),
        ("revision", True),
        ("tags", ["observer", " observer "]),
        ("capabilities", ["sensor_host", " sensor_host "]),
    ],
)
def test_entity_common_fields_reject_blank_duplicate_or_non_strict_values(
    field_name: str,
    value: object,
) -> None:
    data = _spacecraft().model_dump(mode="python")
    data[field_name] = value

    with pytest.raises(ValidationError):
        SpacecraftDefinition.model_validate(data)


def test_other_space_object_has_no_sensor_field() -> None:
    other = OtherSpaceObjectDefinition(
        id="debris-1",
        name="Debris",
        revision=1,
        schema_version=SchemaVersion(major=1, minor=0),
        initial_state=_state(),
        physical_properties=_properties(),
        dynamics_model=_model("sycasphere.dynamics.numerical"),
        attitude_model=_model("sycasphere.attitude.tumbling"),
    )

    assert other.entity_type is EntityType.OTHER_SPACE_OBJECT
    with pytest.raises(ValidationError):
        OtherSpaceObjectDefinition.model_validate(
            {**other.model_dump(mode="json"), "sensors": [_sensor().model_dump(mode="json")]}
        )


def test_ground_station_uses_wgs84_location_and_nested_sensors() -> None:
    station = GroundStationDefinition(
        id="ground-station-1",
        name="Ground Station",
        revision=1,
        schema_version=SchemaVersion(major=1, minor=0),
        capabilities=["sensor_host"],
        location=_location(),
        body_axes_convention="NED_RH",
        environment_models=[_model("sycasphere.environment.standard")],
        sensors=[_sensor("ground-optical-1")],
    )

    assert station.entity_type is EntityType.GROUND_STATION
    assert station.location.frame.ellipsoid is ReferenceEllipsoid.WGS84
    assert station.sensors[0].id == "ground-optical-1"


def test_parent_entity_rejects_duplicate_sensor_ids() -> None:
    data = _spacecraft().model_dump(mode="python")
    data["sensors"] = [_sensor("duplicate"), _sensor("duplicate")]

    with pytest.raises(ValidationError):
        SpacecraftDefinition.model_validate(data)


def test_ground_station_rejects_duplicate_environment_model_ids() -> None:
    model = _model("duplicate.environment")

    with pytest.raises(ValidationError):
        GroundStationDefinition(
            id="ground-station-1",
            name="Ground Station",
            revision=1,
            schema_version=SchemaVersion(major=1, minor=0),
            location=_location(),
            body_axes_convention="NED_RH",
            environment_models=[model, model],
        )


def test_ground_station_rejects_duplicate_sensor_ids_and_independent_state() -> None:
    station = GroundStationDefinition(
        id="ground-station-1",
        name="Ground Station",
        revision=1,
        schema_version=SchemaVersion(major=1, minor=0),
        location=_location(),
        body_axes_convention="NED_RH",
        sensors=[_sensor("duplicate")],
    )
    duplicate_data = station.model_dump(mode="python")
    duplicate_data["sensors"] = [_sensor("duplicate"), _sensor("duplicate")]
    with pytest.raises(ValidationError):
        GroundStationDefinition.model_validate(duplicate_data)

    state_data = station.model_dump(mode="json")
    state_data["initial_state"] = _state().model_dump(mode="json")
    with pytest.raises(ValidationError):
        GroundStationDefinition.model_validate(state_data)


@pytest.mark.parametrize(
    ("field_name", "invalid"),
    [
        ("mass_kg", 0.0),
        ("mass_kg", -1.0),
        ("mass_kg", math.nan),
        ("mass_kg", math.inf),
        ("mass_kg", "1000.0"),
        ("mass_kg", 1_000),
        ("mass_kg", True),
        ("cross_section_area_m2", 0.0),
        ("cross_section_area_m2", -1.0),
        ("cross_section_area_m2", 12),
        ("drag_coefficient", -0.1),
        ("drag_coefficient", 2),
        ("solar_radiation_pressure_coefficient", -0.1),
        ("solar_radiation_pressure_coefficient", 1),
    ],
)
def test_space_object_physical_properties_reject_invalid_values(
    field_name: str,
    invalid: object,
) -> None:
    data = _properties().model_dump()
    data[field_name] = invalid

    with pytest.raises(ValidationError):
        SpaceObjectPhysicalProperties.model_validate(data)


def test_physical_coefficients_can_be_zero_or_missing() -> None:
    properties = SpaceObjectPhysicalProperties(
        mass_kg=1.0,
        cross_section_area_m2=1.0,
        drag_coefficient=0.0,
        solar_radiation_pressure_coefficient=None,
    )

    assert properties.drag_coefficient == 0.0
    assert properties.solar_radiation_pressure_coefficient is None


@pytest.mark.parametrize("role_field", ["target_role", "mission_role", "primary_sensor"])
def test_entities_reject_fixed_task_role_fields(role_field: str) -> None:
    data = _spacecraft().model_dump(mode="json")
    data[role_field] = "TRACKING_TARGET"

    with pytest.raises(ValidationError):
        SpacecraftDefinition.model_validate(data)


def test_entity_metadata_capabilities_and_tags_are_deeply_immutable() -> None:
    metadata = {"programme": {"members": ["a"]}}
    capabilities = ["sensor_host"]
    data = _spacecraft().model_dump(mode="python")
    data["metadata"] = metadata
    data["capabilities"] = capabilities
    entity = SpacecraftDefinition.model_validate(data)

    metadata["programme"]["members"].append("b")
    capabilities.append("changed")

    assert entity.metadata["programme"]["members"] == ("a",)
    assert entity.capabilities == frozenset({"sensor_host"})

    default_data = _spacecraft().model_dump(mode="python")
    del default_data["metadata"]
    default_entity = SpacecraftDefinition.model_validate(default_data)
    with pytest.raises(TypeError):
        default_entity.metadata["changed"] = True


def test_capabilities_are_order_independent_and_serialize_in_sorted_order() -> None:
    data = _spacecraft().model_dump(mode="python")
    data["capabilities"] = ["sensor_host", "maneuverable"]
    entity = SpacecraftDefinition.model_validate(data)

    assert entity.capabilities == frozenset({"maneuverable", "sensor_host"})
    assert entity.model_dump(mode="json")["capabilities"] == [
        "maneuverable",
        "sensor_host",
    ]


def test_entity_definition_discriminates_and_round_trips_all_concrete_types() -> None:
    entities = (
        _spacecraft(),
        OtherSpaceObjectDefinition(
            id="debris-1",
            name="Debris",
            revision=1,
            schema_version=SchemaVersion(major=1, minor=0),
            initial_state=_state(),
            physical_properties=_properties(),
            dynamics_model=_model("sycasphere.dynamics.numerical"),
            attitude_model=_model("sycasphere.attitude.tumbling"),
        ),
        GroundStationDefinition(
            id="ground-station-1",
            name="Ground Station",
            revision=1,
            schema_version=SchemaVersion(major=1, minor=0),
            location=_location(),
            body_axes_convention="NED_RH",
            sensors=[_sensor("ground-optical-1")],
        ),
    )

    for entity in entities:
        serialized = _ENTITY_ADAPTER.dump_python(entity, mode="json")
        restored = _ENTITY_ADAPTER.validate_python(serialized)
        assert type(restored) is type(entity)
        assert restored == entity


@pytest.mark.parametrize("invalid_type", ["SENSOR", "spacecraft", ""])
def test_entity_definition_rejects_unknown_discriminator(invalid_type: str) -> None:
    data = _spacecraft().model_dump(mode="json")
    data["entity_type"] = invalid_type

    with pytest.raises(ValidationError):
        _ENTITY_ADAPTER.validate_python(data)


def test_entities_are_frozen() -> None:
    entity = _spacecraft()

    with pytest.raises(ValidationError):
        entity.name = "Changed"
