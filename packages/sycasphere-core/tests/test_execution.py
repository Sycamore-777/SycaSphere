# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_execution.py
创建者    : Sycamore
创建日期  : 2026-07-26
最后修改  : 2026-07-26
版本号    : v1.0.0

■ 用途说明:
  验证自包含仿真运行请求的序列化、引用解析、能力、时间与输出一致性约束。

■ 主要函数功能:
  - make_request: 构造包含物理世界、调度、采样、后端和输出需求的有效请求
  - 运行请求测试: 覆盖严格输入、跨引用、深度不可变配置及边界一致性

■ 功能特性:
  ✓ 验证运行请求不依赖数据库引用、路径或运行状态
  ✓ 验证传感器模型、链路模型、机动能力和输出采样的闭合引用

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-26): 创建 SimulationRunRequest 契约测试

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from sycasphere.core.entities import (
    GroundStationDefinition,
    OtherSpaceObjectDefinition,
    SpacecraftDefinition,
    SpaceObjectPhysicalProperties,
)
from sycasphere.core.epoch import Epoch, TimeScale
from sycasphere.core.execution import (
    OutputRequirement,
    ScienceBackendBinding,
    SimulationRunRequest,
)
from sycasphere.core.frames import (
    CoordinateRepresentation,
    EarthFixedFrameSpec,
    FrameKind,
    FrameRef,
    ReferenceEllipsoid,
)
from sycasphere.core.geometry import GeodeticLocation, RigidTransform, SensorAxes
from sycasphere.core.maneuvers import (
    FiniteBurnManeuverSpec,
    ImpulsiveManeuverSpec,
    ManeuverCapability,
    ManeuverCommand,
    ManeuverType,
    PlannedTruthManeuver,
)
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.plugins import PluginRef
from sycasphere.core.schedules import (
    ExplicitObservationSchedule,
    OutputProduct,
    OutputSampling,
    PeriodicObservationSchedule,
    SamplingRule,
    SimulationTimeRange,
)
from sycasphere.core.schema import SchemaVersion
from sycasphere.core.sensors import SensorDefinition, SensorType
from sycasphere.core.simulations import (
    CentralBody,
    EnvironmentDefinition,
    SimulationDefinition,
)
from sycasphere.core.states import CartesianState

SCHEMA_VERSION = SchemaVersion(major=1, minor=0)
SYNCHRONIZATION_EPOCH = Epoch(value="2026-07-26T00:00:00Z", time_scale=TimeScale.UTC)
START_EPOCH = Epoch(value="2026-07-26T00:00:10Z", time_scale=TimeScale.UTC)
SCHEDULE_END_EPOCH = Epoch(value="2026-07-26T00:00:50Z", time_scale=TimeScale.UTC)
END_EPOCH = Epoch(value="2026-07-26T00:01:00Z", time_scale=TimeScale.UTC)


# =============================👐Seperate👐=============================
# Reusable valid request fixtures
# =============================👐Seperate👐=============================
def make_model(model_id: str, configuration: object | None = None) -> ModelRef:
    """Return a minimal immutable scientific model reference."""
    return ModelRef(
        model_id=model_id,
        interface_version=SCHEMA_VERSION,
        configuration={} if configuration is None else configuration,
    )


def make_state(epoch: Epoch = SYNCHRONIZATION_EPOCH) -> CartesianState:
    """Return a valid J2000 Cartesian state at the requested epoch."""
    return CartesianState(
        epoch=epoch,
        frame=FrameRef(kind=FrameKind.J2000),
        position_m=(7_000_000.0, 0.0, 0.0),
        velocity_mps=(0.0, 7_500.0, 0.0),
    )


def make_properties() -> SpaceObjectPhysicalProperties:
    """Return finite SI physical properties for a propagated space object."""
    return SpaceObjectPhysicalProperties(mass_kg=500.0, cross_section_area_m2=8.0)


def make_sensor() -> SensorDefinition:
    """Return the observer's sensor with one measurement and one error model."""
    return SensorDefinition(
        id="sensor-1",
        name="Observer Sensor",
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
        error_profiles=(make_model("sycasphere.error.optical"),),
    )


def make_observer() -> SpacecraftDefinition:
    """Return a maneuver-capable observer spacecraft with one sensor."""
    return SpacecraftDefinition(
        id="observer-1",
        name="Observer",
        revision=1,
        schema_version=SCHEMA_VERSION,
        initial_state=make_state(),
        physical_properties=make_properties(),
        dynamics_model=make_model("sycasphere.dynamics.numerical"),
        attitude_model=make_model("sycasphere.attitude.nadir"),
        sensors=(make_sensor(),),
        maneuver_capability=ManeuverCapability(
            supported_types=(ManeuverType.IMPULSIVE,),
            propulsion_model=make_model("sycasphere.propulsion.impulsive"),
        ),
    )


def make_target() -> OtherSpaceObjectDefinition:
    """Return a propagated target space object."""
    return OtherSpaceObjectDefinition(
        id="target-1",
        name="Target",
        revision=1,
        schema_version=SCHEMA_VERSION,
        initial_state=make_state(),
        physical_properties=make_properties(),
        dynamics_model=make_model("sycasphere.dynamics.numerical"),
        attitude_model=make_model("sycasphere.attitude.tumbling"),
    )


def make_ground_station() -> GroundStationDefinition:
    """Return a non-space-object entity for target-kind validation."""
    return GroundStationDefinition(
        id="ground-1",
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
            longitude_rad=1.0,
            latitude_rad=0.5,
            ellipsoid_height_m=100.0,
        ),
        body_axes_convention="NED_RH",
    )


def make_request() -> SimulationRunRequest:
    """Return one self-contained, internally consistent simulation run request."""
    planned = PlannedTruthManeuver(
        maneuver_id="planned-1",
        spacecraft_id="observer-1",
        epoch=START_EPOCH,
        maneuver=ImpulsiveManeuverSpec(
            delta_v_mps=(0.0, 0.1, 0.0),
            frame=FrameRef(kind=FrameKind.J2000),
        ),
    )
    definition = SimulationDefinition(
        id="simulation-1",
        name="Execution Fixture",
        revision=1,
        schema_version=SCHEMA_VERSION,
        synchronization_epoch=SYNCHRONIZATION_EPOCH,
        environment=EnvironmentDefinition(
            id="environment-1",
            name="Earth",
            revision=1,
            schema_version=SCHEMA_VERSION,
            central_body=CentralBody.EARTH,
        ),
        entities=(make_observer(), make_target()),
        planned_maneuvers=(planned,),
    )
    return SimulationRunRequest(
        schema_version=SCHEMA_VERSION,
        simulation_definition=definition,
        time_range=SimulationTimeRange(start=START_EPOCH, end=END_EPOCH),
        output_sampling=OutputSampling(
            rules=(SamplingRule(product=OutputProduct.TRUTH_STATE, interval_s=5.0),)
        ),
        observation_schedules=(
            PeriodicObservationSchedule(
                schedule_id="schedule-1",
                sensor_id="sensor-1",
                target_id="target-1",
                measurement_model_id="sycasphere.measurement.angles",
                error_profile_id="sycasphere.error.optical",
                link_model_id="sycasphere.link.nominal",
                start_epoch=START_EPOCH,
                end_epoch=SCHEDULE_END_EPOCH,
                cadence_s=10.0,
            ),
        ),
        backend=ScienceBackendBinding(
            ref=PluginRef(
                plugin_id="sycasphere.orekit",
                implementation_version="13.1.7",
                interface_version=SCHEMA_VERSION,
            ),
            configuration={"integrator": {"kind": "DOP853", "max_step_s": 60.0}},
        ),
        link_models=(make_model("sycasphere.link.nominal"),),
        random_seed=42,
        output_requirements=(
            OutputRequirement.TRUTH,
            OutputRequirement.IDEAL_OBSERVATIONS,
        ),
    )


def request_data() -> dict[str, object]:
    """Return mutable Python-mode data for one valid request."""
    return make_request().model_dump(mode="python")


# =============================👐Seperate👐=============================
# Self-contained shape, strict values, and serialization
# =============================👐Seperate👐=============================
def test_request_is_self_contained_and_round_trips() -> None:
    request = make_request()
    serialized = request.model_dump(mode="json")

    assert "simulation_definition" in serialized
    assert "simulation_definition_ref" not in serialized
    assert "measurement_model_refs" not in serialized
    assert "error_model_refs" not in serialized
    assert SimulationRunRequest.model_validate(serialized) == request


@pytest.mark.parametrize("random_seed", [-1, 2**64, True, 1.0, "42"])
def test_request_requires_unsigned_64_bit_seed(random_seed: object) -> None:
    data = request_data()
    data["random_seed"] = random_seed

    with pytest.raises(ValidationError):
        SimulationRunRequest.model_validate(data)


def test_output_requirements_are_nonempty_unique_and_deterministic() -> None:
    data = request_data()

    for requirements in ((), ("TRUTH", "TRUTH")):
        with pytest.raises(ValidationError, match="output_requirements"):
            SimulationRunRequest.model_validate({**data, "output_requirements": requirements})

    data["output_requirements"] = ("IDEAL_OBSERVATIONS", "TRUTH")
    request = SimulationRunRequest.model_validate(data)
    assert request.model_dump(mode="json")["output_requirements"] == [
        "IDEAL_OBSERVATIONS",
        "TRUTH",
    ]


def test_output_requirement_values_are_exact() -> None:
    assert {item.value for item in OutputRequirement} == {
        "TRUTH",
        "ATTITUDE",
        "GEOMETRY",
        "IDEAL_OBSERVATIONS",
        "REPORTED_OBSERVATIONS",
        "DELIVERY_SUMMARY",
        "COMMAND_TRACE",
        "DIAGNOSTICS",
    }


def test_backend_configuration_is_finite_alias_independent_and_deeply_frozen() -> None:
    configuration = {"integrator": {"tolerances": [1.0e-9, 1.0e-12]}}
    backend = ScienceBackendBinding(
        ref=make_request().backend.ref,
        configuration=configuration,
    )
    configuration["integrator"]["tolerances"].append(1.0)

    assert backend.configuration["integrator"]["tolerances"] == (1.0e-9, 1.0e-12)
    assert backend.model_dump(mode="json")["configuration"] == {
        "integrator": {"tolerances": [1.0e-9, 1.0e-12]}
    }
    with pytest.raises(TypeError):
        backend.configuration["new"] = True
    with pytest.raises(TypeError):
        backend.configuration["integrator"]["tolerances"][0] = 0.0

    for invalid in ({"value": math.nan}, {"value": object()}):
        with pytest.raises(ValidationError):
            ScienceBackendBinding(ref=make_request().backend.ref, configuration=invalid)


def test_backend_default_configuration_is_frozen() -> None:
    backend = ScienceBackendBinding(ref=make_request().backend.ref)

    with pytest.raises(TypeError):
        backend.configuration["new"] = True


@pytest.mark.parametrize(
    "field_name",
    ["output_path", "retention_policy", "run_status", "database_ref"],
)
def test_request_is_frozen_and_rejects_infrastructure_or_ui_fields(field_name: str) -> None:
    request = make_request()
    with pytest.raises(ValidationError):
        request.random_seed = 43

    data = request.model_dump(mode="json")
    data[field_name] = "not-domain-input"
    with pytest.raises(ValidationError):
        SimulationRunRequest.model_validate(data)


# =============================👐Seperate👐=============================
# Schedule and model cross-reference validation
# =============================👐Seperate👐=============================
def test_reported_output_requires_error_profile_on_every_schedule() -> None:
    data = request_data()
    schedule = make_request().observation_schedules[0]
    data["observation_schedules"] = (schedule.model_copy(update={"error_profile_id": None}),)
    data["output_requirements"] = ("TRUTH", "REPORTED_OBSERVATIONS")

    with pytest.raises(ValidationError, match="error_profile"):
        SimulationRunRequest.model_validate(data)


def test_request_resolves_every_schedule_reference() -> None:
    request = make_request()
    data = request_data()
    schedule = request.observation_schedules[0]
    data["observation_schedules"] = (schedule.model_copy(update={"sensor_id": "missing-sensor"}),)

    with pytest.raises(ValidationError, match="sensor"):
        SimulationRunRequest.model_validate(data)


@pytest.mark.parametrize("field_name", ["schedule_id", "link_model"])
def test_request_rejects_duplicate_schedule_or_link_model_ids(field_name: str) -> None:
    request = make_request()
    data = request_data()
    if field_name == "schedule_id":
        data["observation_schedules"] = (
            request.observation_schedules[0],
            request.observation_schedules[0],
        )
        match = "schedule_id"
    else:
        data["link_models"] = (request.link_models[0], request.link_models[0])
        match = "model_id"

    with pytest.raises(ValidationError, match=match):
        SimulationRunRequest.model_validate(data)


@pytest.mark.parametrize(
    ("field_name", "missing_id", "message"),
    [
        ("sensor_id", "missing-sensor", "sensor"),
        ("target_id", "missing-target", "target"),
    ],
)
def test_request_rejects_missing_schedule_endpoints(
    field_name: str, missing_id: str, message: str
) -> None:
    request = make_request()
    data = request_data()
    data["observation_schedules"] = (
        request.observation_schedules[0].model_copy(update={field_name: missing_id}),
    )

    with pytest.raises(ValidationError, match=message):
        SimulationRunRequest.model_validate(data)


def test_request_requires_schedule_target_to_be_a_space_object() -> None:
    request = make_request()
    definition = request.simulation_definition.model_copy(
        update={
            "entities": (
                *request.simulation_definition.entities,
                make_ground_station(),
            )
        }
    )
    data = request_data()
    data["simulation_definition"] = definition
    data["observation_schedules"] = (
        request.observation_schedules[0].model_copy(update={"target_id": "ground-1"}),
    )

    with pytest.raises(ValidationError, match="space object"):
        SimulationRunRequest.model_validate(data)


@pytest.mark.parametrize(
    ("field_name", "invalid_id", "message"),
    [
        ("measurement_model_id", "sycasphere.measurement.other", "measurement"),
        ("error_profile_id", "sycasphere.error.other", "error"),
        ("link_model_id", "sycasphere.link.missing", "link"),
    ],
)
def test_request_resolves_schedule_models_from_their_own_collections(
    field_name: str, invalid_id: str, message: str
) -> None:
    request = make_request()
    data = request_data()
    data["observation_schedules"] = (
        request.observation_schedules[0].model_copy(update={field_name: invalid_id}),
    )

    with pytest.raises(ValidationError, match=message):
        SimulationRunRequest.model_validate(data)


# =============================👐Seperate👐=============================
# Maneuver command and time validation
# =============================👐Seperate👐=============================
def make_impulsive_command(
    command_id: str = "command-1",
    spacecraft_id: str = "observer-1",
) -> ManeuverCommand:
    """Return a valid impulsive command within the fixture interval."""
    return ManeuverCommand(
        command_id=command_id,
        spacecraft_id=spacecraft_id,
        epoch=START_EPOCH,
        maneuver=ImpulsiveManeuverSpec(
            delta_v_mps=(0.0, 0.2, 0.0),
            frame=FrameRef(kind=FrameKind.J2000),
        ),
    )


def test_request_rejects_command_id_colliding_with_planned_maneuver() -> None:
    request = make_request()
    planned = request.simulation_definition.planned_maneuvers[0]
    data = request_data()
    data["command_timeline"] = (
        ManeuverCommand(
            command_id=planned.maneuver_id,
            spacecraft_id=planned.spacecraft_id,
            epoch=planned.epoch,
            maneuver=planned.maneuver,
        ),
    )

    with pytest.raises(ValidationError, match="command_id"):
        SimulationRunRequest.model_validate(data)


def test_request_rejects_duplicate_command_ids() -> None:
    data = request_data()
    data["command_timeline"] = (
        make_impulsive_command(),
        make_impulsive_command(),
    )

    with pytest.raises(ValidationError, match="command_id"):
        SimulationRunRequest.model_validate(data)


@pytest.mark.parametrize("spacecraft_id", ["missing-spacecraft", "target-1"])
def test_request_requires_command_target_to_be_an_existing_spacecraft(
    spacecraft_id: str,
) -> None:
    data = request_data()
    data["command_timeline"] = (make_impulsive_command(spacecraft_id=spacecraft_id),)

    with pytest.raises(ValidationError, match="spacecraft"):
        SimulationRunRequest.model_validate(data)


def test_request_requires_command_target_to_have_maneuver_capability() -> None:
    request = make_request()
    observer = make_observer().model_copy(update={"maneuver_capability": None})
    definition = request.simulation_definition.model_copy(
        update={"entities": (observer, make_target()), "planned_maneuvers": ()}
    )
    data = request_data()
    data["simulation_definition"] = definition
    data["command_timeline"] = (make_impulsive_command(),)

    with pytest.raises(ValidationError, match="capability"):
        SimulationRunRequest.model_validate(data)


def test_request_rejects_command_type_not_supported_by_spacecraft() -> None:
    data = request_data()
    data["command_timeline"] = (
        ManeuverCommand(
            command_id="command-finite",
            spacecraft_id="observer-1",
            epoch=START_EPOCH,
            maneuver=FiniteBurnManeuverSpec(
                duration_s=10.0,
                thrust_n=(0.0, 1.0, 0.0),
                frame=FrameRef(kind=FrameKind.J2000),
            ),
        ),
    )

    with pytest.raises(ValidationError, match="unsupported"):
        SimulationRunRequest.model_validate(data)


def test_request_requires_synchronization_epoch_not_after_start() -> None:
    request = make_request()
    later_synchronization = Epoch(
        value="2026-07-26T00:00:20Z",
        time_scale=TimeScale.UTC,
    )
    data = request_data()
    data["simulation_definition"] = request.simulation_definition.model_copy(
        update={"synchronization_epoch": later_synchronization}
    )

    with pytest.raises(ValidationError, match="synchronization_epoch"):
        SimulationRunRequest.model_validate(data)


@pytest.mark.parametrize(
    ("field_name", "epoch"),
    [
        (
            "start_epoch",
            Epoch(value="2026-07-26T00:00:09Z", time_scale=TimeScale.UTC),
        ),
        (
            "end_epoch",
            Epoch(value="2026-07-26T00:01:01Z", time_scale=TimeScale.UTC),
        ),
    ],
)
def test_periodic_schedule_must_remain_inside_closed_request_interval(
    field_name: str, epoch: Epoch
) -> None:
    request = make_request()
    data = request_data()
    data["observation_schedules"] = (
        request.observation_schedules[0].model_copy(update={field_name: epoch}),
    )

    with pytest.raises(ValidationError, match="interval"):
        SimulationRunRequest.model_validate(data)


def test_explicit_schedule_must_remain_inside_closed_request_interval() -> None:
    data = request_data()
    data["observation_schedules"] = (
        ExplicitObservationSchedule(
            schedule_id="explicit-1",
            sensor_id="sensor-1",
            target_id="target-1",
            measurement_model_id="sycasphere.measurement.angles",
            epochs=(
                Epoch(value="2026-07-26T00:00:09Z", time_scale=TimeScale.UTC),
                START_EPOCH,
            ),
        ),
    )

    with pytest.raises(ValidationError, match="interval"):
        SimulationRunRequest.model_validate(data)


def test_request_defers_mixed_scale_ordering_to_engine() -> None:
    data = request_data()
    tai_start = Epoch(value="2026-07-26T00:00:10", time_scale=TimeScale.TAI)
    tai_end = Epoch(value="2026-07-26T00:01:00", time_scale=TimeScale.TAI)
    data["time_range"] = SimulationTimeRange(start=tai_start, end=tai_end)

    assert SimulationRunRequest.model_validate(data).time_range.start == tai_start


# =============================👐Seperate👐=============================
# Output sampling consistency
# =============================👐Seperate👐=============================
@pytest.mark.parametrize(
    ("product", "requirement"),
    [
        (OutputProduct.TRUTH_STATE, OutputRequirement.TRUTH),
        (OutputProduct.ATTITUDE_STATE, OutputRequirement.ATTITUDE),
        (OutputProduct.DERIVED_GEOMETRY, OutputRequirement.GEOMETRY),
    ],
)
def test_each_sampled_product_requires_its_output(
    product: OutputProduct,
    requirement: OutputRequirement,
) -> None:
    data = request_data()
    data["output_sampling"] = OutputSampling(rules=(SamplingRule(product=product, interval_s=5.0),))
    data["output_requirements"] = (OutputRequirement.IDEAL_OBSERVATIONS,)

    with pytest.raises(ValidationError, match=requirement.value):
        SimulationRunRequest.model_validate(data)


@pytest.mark.parametrize(
    ("product", "requirement"),
    [
        (OutputProduct.TRUTH_STATE, OutputRequirement.TRUTH),
        (OutputProduct.ATTITUDE_STATE, OutputRequirement.ATTITUDE),
        (OutputProduct.DERIVED_GEOMETRY, OutputRequirement.GEOMETRY),
    ],
)
def test_each_sampled_output_requires_its_sampling_rule(
    product: OutputProduct,
    requirement: OutputRequirement,
) -> None:
    data = request_data()
    data["output_sampling"] = OutputSampling()
    data["output_requirements"] = (
        requirement,
        OutputRequirement.IDEAL_OBSERVATIONS,
    )

    with pytest.raises(ValidationError, match=product.value):
        SimulationRunRequest.model_validate(data)
