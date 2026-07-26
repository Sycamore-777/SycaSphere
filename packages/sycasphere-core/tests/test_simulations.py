# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_simulations.py
创建者    : Sycamore
创建日期  : 2026-07-26
最后修改  : 2026-07-26
版本号    : v1.0.0

■ 用途说明:
  验证物理环境与可复用仿真世界定义的跨对象完整性约束。

■ 主要函数功能:
  - make_simulation_definition: 构造可复用的有效仿真世界输入。
  - 仿真定义测试: 覆盖全局标识、同步时刻和预设机动绑定。

■ 功能特性:
  ✓ 覆盖环境模型、外部数据和实体/传感器的全局唯一性
  ✓ 覆盖空间对象同步和预设机动的能力、时间与局部坐标系约束

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-26): 创建仿真世界契约测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sycasphere.core.entities import (
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
from sycasphere.core.maneuvers import (
    ImpulsiveManeuverSpec,
    ManeuverCapability,
    ManeuverType,
    PlannedTruthManeuver,
)
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.schema import SchemaVersion
from sycasphere.core.sensors import SensorDefinition, SensorType
from sycasphere.core.simulations import (
    CentralBody,
    EnvironmentDefinition,
    ExternalDataRef,
    SimulationDefinition,
)
from sycasphere.core.states import CartesianState

EPOCH = Epoch(value="2026-07-26T00:00:00Z", time_scale=TimeScale.UTC)
SCHEMA_VERSION = SchemaVersion(major=1, minor=0)


def make_model(model_id: str) -> ModelRef:
    """Return a minimal immutable scientific model reference."""
    return ModelRef(
        model_id=model_id,
        interface_version=SCHEMA_VERSION,
        configuration={},
    )


def make_sensor(sensor_id: str = "sensor-1") -> SensorDefinition:
    """Return a nested optical sensor definition."""
    return SensorDefinition(
        id=sensor_id,
        name=sensor_id,
        revision=1,
        schema_version=SCHEMA_VERSION,
        sensor_type=SensorType.OPTICAL,
        mount_transform=RigidTransform(
            translation_m=(0.0, 0.0, 0.0),
            rotation_parent_to_child_wxyz=(1.0, 0.0, 0.0, 0.0),
        ),
        axes=SensorAxes(
            boresight=(0.0, 0.0, 1.0),
            horizontal=(1.0, 0.0, 0.0),
            vertical=(0.0, 1.0, 0.0),
        ),
        pointing_model=make_model("sycasphere.pointing.fixed"),
        field_of_view_model=make_model("sycasphere.fov.conical"),
        visibility_model=make_model("sycasphere.visibility.basic"),
        measurement_models=(make_model("sycasphere.measurement.angles"),),
    )


def make_state() -> CartesianState:
    """Return an initial J2000 Cartesian state at the synchronization epoch."""
    return CartesianState(
        epoch=EPOCH,
        frame=FrameRef(kind=FrameKind.J2000),
        position_m=(7_000_000.0, 0.0, 0.0),
        velocity_mps=(0.0, 7_500.0, 0.0),
    )


def make_properties() -> SpaceObjectPhysicalProperties:
    """Return valid SI physical properties for a propagated space object."""
    return SpaceObjectPhysicalProperties(mass_kg=1000.0, cross_section_area_m2=12.0)


def make_capability() -> ManeuverCapability:
    """Return a propulsion capability that supports impulsive maneuvers."""
    return ManeuverCapability(
        supported_types=(ManeuverType.IMPULSIVE,),
        propulsion_model=make_model("sycasphere.propulsion.impulsive"),
    )


def make_spacecraft(spacecraft_id: str = "spacecraft-1") -> SpacecraftDefinition:
    """Return a maneuver-capable spacecraft with one nested sensor."""
    return SpacecraftDefinition(
        id=spacecraft_id,
        name="Observer",
        revision=1,
        schema_version=SCHEMA_VERSION,
        initial_state=make_state(),
        physical_properties=make_properties(),
        dynamics_model=make_model("sycasphere.dynamics.numerical"),
        attitude_model=make_model("sycasphere.attitude.nadir"),
        sensors=(make_sensor(),),
        maneuver_capability=make_capability(),
    )


def make_ground_station() -> GroundStationDefinition:
    """Return a WGS84 ground station for target-type validation."""
    return GroundStationDefinition(
        id="ground-station-1",
        name="Ground Station",
        revision=1,
        schema_version=SCHEMA_VERSION,
        location=GeodeticLocation(
            frame=FrameRef(
                kind=FrameKind.EARTH_FIXED,
                representation=CoordinateRepresentation.GEODETIC,
                earth_fixed=EarthFixedFrameSpec(
                    itrf_realization="ITRF2020",
                    iers_conventions="IERS_2010",
                    eop_data_id="iers-eop",
                ),
                ellipsoid=ReferenceEllipsoid.WGS84,
            ),
            longitude_rad=2.0,
            latitude_rad=0.5,
            ellipsoid_height_m=50.0,
        ),
        body_axes_convention="NED_RH",
        sensors=(make_sensor("ground-sensor-1"),),
    )


def make_planned_maneuver(spacecraft_id: str = "spacecraft-1") -> PlannedTruthManeuver:
    """Return a valid planned truth impulsive maneuver at the synchronization epoch."""
    return PlannedTruthManeuver(
        maneuver_id="maneuver-1",
        spacecraft_id=spacecraft_id,
        epoch=EPOCH,
        maneuver=ImpulsiveManeuverSpec(
            delta_v_mps=(0.0, 1.0, 0.0),
            frame=FrameRef(kind=FrameKind.J2000),
        ),
    )


def make_simulation_definition() -> SimulationDefinition:
    """Return an internally consistent reusable physical-world definition."""
    return SimulationDefinition(
        id="simulation-1",
        name="Baseline World",
        revision=1,
        schema_version=SCHEMA_VERSION,
        synchronization_epoch=EPOCH,
        environment=EnvironmentDefinition(
            id="environment-1",
            name="Earth Environment",
            revision=1,
            schema_version=SCHEMA_VERSION,
            central_body=CentralBody.EARTH,
            model_refs=(make_model("sycasphere.environment.gravity"),),
            external_data_refs=(
                ExternalDataRef(
                    data_id="iers-eop",
                    version="2026-07-26",
                    sha256="a" * 64,
                ),
            ),
        ),
        entities=(make_spacecraft(), make_ground_station()),
        planned_maneuvers=(make_planned_maneuver(),),
    )


def test_environment_and_simulation_definition_round_trip() -> None:
    definition = make_simulation_definition()

    restored = SimulationDefinition.model_validate(definition.model_dump(mode="json"))

    assert restored == definition
    assert restored.environment.central_body is CentralBody.EARTH


@pytest.mark.parametrize("sha256", ["", "A" * 64, "a" * 63, "g" * 64, "/tmp/eop.dat"])
def test_external_data_ref_requires_lowercase_sha256(sha256: str) -> None:
    with pytest.raises(ValidationError):
        ExternalDataRef(data_id="iers-eop", version="2026-07-26", sha256=sha256)


def test_simulation_requires_at_least_one_space_object() -> None:
    data = make_simulation_definition().model_dump(mode="python")
    data["entities"] = [make_ground_station()]

    with pytest.raises(ValidationError, match="space object"):
        SimulationDefinition.model_validate(data)


def test_simulation_rejects_global_entity_or_sensor_id_collisions() -> None:
    definition = make_simulation_definition()
    duplicate_entity_data = definition.model_dump(mode="python")
    duplicate_entity_data["entities"] = (definition.entities[0], definition.entities[0])
    with pytest.raises(ValidationError, match="entity"):
        SimulationDefinition.model_validate(duplicate_entity_data)

    sensor_collision_data = definition.model_dump(mode="python")
    entities = list(definition.entities)
    sensor_owner = entities[0].model_copy(update={"id": "sensor-1"})
    sensor_collision_data["entities"] = (sensor_owner, *entities[1:])
    with pytest.raises(ValidationError, match="sensor"):
        SimulationDefinition.model_validate(sensor_collision_data)


def test_simulation_rejects_asynchronous_initial_state_in_v1() -> None:
    definition = make_simulation_definition()
    data = definition.model_dump(mode="python")
    spacecraft = definition.entities[0]
    assert isinstance(spacecraft, SpacecraftDefinition)
    changed_state = spacecraft.initial_state.model_copy(
        update={
            "epoch": Epoch(
                value="2026-07-26T00:00:01Z",
                time_scale=TimeScale.UTC,
            )
        }
    )
    data["entities"] = (
        spacecraft.model_copy(update={"initial_state": changed_state}),
        *definition.entities[1:],
    )

    with pytest.raises(ValidationError, match="synchronization_epoch"):
        SimulationDefinition.model_validate(data)


def test_planned_maneuver_requires_existing_capable_spacecraft() -> None:
    definition = make_simulation_definition()
    data = definition.model_dump(mode="python")
    planned = definition.planned_maneuvers[0]
    data["planned_maneuvers"] = (
        planned.model_copy(update={"spacecraft_id": "missing-spacecraft"}),
    )

    with pytest.raises(ValidationError, match="spacecraft"):
        SimulationDefinition.model_validate(data)


def test_environment_rejects_duplicate_model_and_external_data_ids() -> None:
    environment = make_simulation_definition().environment
    duplicate_model_data = environment.model_dump(mode="python")
    duplicate_model_data["model_refs"] = (environment.model_refs[0], environment.model_refs[0])
    with pytest.raises(ValidationError, match="model_id"):
        EnvironmentDefinition.model_validate(duplicate_model_data)

    duplicate_data_data = environment.model_dump(mode="python")
    duplicate_data_data["external_data_refs"] = (
        environment.external_data_refs[0],
        environment.external_data_refs[0],
    )
    with pytest.raises(ValidationError, match="data_id"):
        EnvironmentDefinition.model_validate(duplicate_data_data)


def test_simulation_rejects_duplicate_planned_maneuver_ids() -> None:
    definition = make_simulation_definition()
    data = definition.model_dump(mode="python")
    data["planned_maneuvers"] = (
        definition.planned_maneuvers[0],
        definition.planned_maneuvers[0],
    )

    with pytest.raises(ValidationError, match="maneuver_id"):
        SimulationDefinition.model_validate(data)


@pytest.mark.parametrize("target_id", ["ground-station-1", "missing-spacecraft"])
def test_planned_maneuver_rejects_ground_station_or_missing_target(target_id: str) -> None:
    definition = make_simulation_definition()
    data = definition.model_dump(mode="python")
    data["planned_maneuvers"] = (
        definition.planned_maneuvers[0].model_copy(update={"spacecraft_id": target_id}),
    )

    with pytest.raises(ValidationError, match="spacecraft"):
        SimulationDefinition.model_validate(data)


def test_planned_maneuver_rejects_unsupported_capability_type() -> None:
    definition = make_simulation_definition()
    spacecraft = definition.entities[0]
    assert isinstance(spacecraft, SpacecraftDefinition)
    impulsive_only = make_capability()
    finite_maneuver = PlannedTruthManeuver(
        maneuver_id="maneuver-1",
        spacecraft_id=spacecraft.id,
        epoch=EPOCH,
        maneuver={
            "maneuver_type": "FINITE_BURN",
            "duration_s": 1.0,
            "thrust_n": (0.0, 1.0, 0.0),
            "frame": {"kind": "J2000"},
        },
    )
    data = definition.model_dump(mode="python")
    data["entities"] = (
        spacecraft.model_copy(update={"maneuver_capability": impulsive_only}),
        *definition.entities[1:],
    )
    data["planned_maneuvers"] = (finite_maneuver,)

    with pytest.raises(ValidationError, match="unsupported"):
        SimulationDefinition.model_validate(data)


@pytest.mark.parametrize(
    "frame",
    [
        FrameRef(
            kind=FrameKind.LVLH,
            owner_id="other-spacecraft",
            convention="LVLH_RH",
            reference_epoch=EPOCH,
        ),
        FrameRef(
            kind=FrameKind.BODY,
            owner_id="spacecraft-1",
            convention="BODY_RH",
            reference_epoch=Epoch(value="2026-07-26T00:00:01Z", time_scale=TimeScale.UTC),
        ),
    ],
)
def test_simulation_rejects_invalid_local_planned_maneuver_binding(frame: FrameRef) -> None:
    definition = make_simulation_definition()
    maneuver = ImpulsiveManeuverSpec(delta_v_mps=(0.0, 1.0, 0.0), frame=frame)
    invalid_planned = PlannedTruthManeuver.model_construct(
        maneuver_id="maneuver-1",
        spacecraft_id="spacecraft-1",
        epoch=EPOCH,
        maneuver=maneuver,
    )
    data = definition.model_dump(mode="python")
    data["planned_maneuvers"] = (invalid_planned,)

    with pytest.raises(ValidationError, match=r"(owner_id|reference_epoch)"):
        SimulationDefinition.model_validate(data)


def test_simulation_rejects_earlier_same_scale_planned_maneuver() -> None:
    definition = make_simulation_definition()
    data = definition.model_dump(mode="python")
    earlier = definition.planned_maneuvers[0].model_copy(
        update={"epoch": Epoch(value="2026-07-25T23:59:59Z", time_scale=TimeScale.UTC)}
    )
    data["planned_maneuvers"] = (earlier,)

    with pytest.raises(ValidationError, match="earlier"):
        SimulationDefinition.model_validate(data)


def test_simulation_accepts_later_fractional_second_same_scale_maneuver() -> None:
    definition = make_simulation_definition()
    data = definition.model_dump(mode="python")
    later = definition.planned_maneuvers[0].model_copy(
        update={"epoch": Epoch(value="2026-07-26T00:00:00.5Z", time_scale=TimeScale.UTC)}
    )
    data["planned_maneuvers"] = (later,)

    assert SimulationDefinition.model_validate(data).planned_maneuvers == (later,)


def test_simulation_rejects_earlier_fractional_second_same_scale_maneuver() -> None:
    definition = make_simulation_definition()
    synchronization_epoch = Epoch(value="2026-07-26T00:00:00.5Z", time_scale=TimeScale.UTC)
    data = definition.model_dump(mode="python")
    spacecraft = definition.entities[0]
    assert isinstance(spacecraft, SpacecraftDefinition)
    data["synchronization_epoch"] = synchronization_epoch
    data["entities"] = (
        spacecraft.model_copy(
            update={
                "initial_state": spacecraft.initial_state.model_copy(
                    update={"epoch": synchronization_epoch}
                )
            }
        ),
        *definition.entities[1:],
    )
    data["planned_maneuvers"] = (
        definition.planned_maneuvers[0].model_copy(update={"epoch": EPOCH}),
    )

    with pytest.raises(ValidationError, match="earlier"):
        SimulationDefinition.model_validate(data)


def test_simulation_leaves_cross_time_scale_maneuver_ordering_to_engine() -> None:
    definition = make_simulation_definition()
    data = definition.model_dump(mode="python")
    cross_scale = definition.planned_maneuvers[0].model_copy(
        update={"epoch": Epoch(value="2026-07-25T23:59:59", time_scale=TimeScale.TAI)}
    )
    data["planned_maneuvers"] = (cross_scale,)

    assert SimulationDefinition.model_validate(data).planned_maneuvers == (cross_scale,)


def test_simulation_keeps_source_collections_immutable() -> None:
    entities = [make_spacecraft()]
    model_refs = [make_model("sycasphere.environment.gravity")]
    external_data_refs = [
        ExternalDataRef(data_id="iers-eop", version="2026-07-26", sha256="a" * 64)
    ]
    environment = EnvironmentDefinition(
        id="environment-1",
        name="Earth Environment",
        revision=1,
        schema_version=SCHEMA_VERSION,
        central_body=CentralBody.EARTH,
        model_refs=model_refs,
        external_data_refs=external_data_refs,
    )
    definition = SimulationDefinition(
        id="simulation-1",
        name="Baseline World",
        revision=1,
        schema_version=SCHEMA_VERSION,
        synchronization_epoch=EPOCH,
        environment=environment,
        entities=entities,
    )

    entities.append(make_ground_station())
    model_refs.append(make_model("sycasphere.environment.drag"))
    external_data_refs.append(
        ExternalDataRef(data_id="space-weather", version="2026-07-26", sha256="b" * 64)
    )

    assert tuple(entity.id for entity in definition.entities) == ("spacecraft-1",)
    assert tuple(model.model_id for model in definition.environment.model_refs) == (
        "sycasphere.environment.gravity",
    )
    assert tuple(data.data_id for data in definition.environment.external_data_refs) == (
        "iers-eop",
    )


def test_other_space_object_satisfies_required_space_object_category() -> None:
    definition = make_simulation_definition()
    spacecraft = definition.entities[0]
    assert isinstance(spacecraft, SpacecraftDefinition)
    other = OtherSpaceObjectDefinition(
        id="debris-1",
        name="Debris",
        revision=1,
        schema_version=SCHEMA_VERSION,
        initial_state=make_state(),
        physical_properties=make_properties(),
        dynamics_model=spacecraft.dynamics_model,
        attitude_model=spacecraft.attitude_model,
    )
    data = definition.model_dump(mode="python")
    data["entities"] = (other, make_ground_station())
    data["planned_maneuvers"] = ()

    assert SimulationDefinition.model_validate(data).entities[0] == other
