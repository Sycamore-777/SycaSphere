# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_execution.py
创建者    : Sycamore
创建日期  : 2026-07-26
最后修改  : 2026-07-26
版本号    : v1.1.0

■ 用途说明:
  验证自包含仿真运行请求及不可变执行清单的确定性、完整性和边界一致性约束。

■ 主要函数功能:
  - make_request: 构造包含物理世界、调度、采样、后端和输出需求的有效请求
  - make_manifest: 构造排序稳定、哈希闭合且可重复的科学执行输入清单
  - 契约测试: 覆盖严格输入、跨引用、深度不可变配置及清单完整性

■ 功能特性:
  ✓ 验证运行请求不依赖数据库引用、路径或运行状态
  ✓ 验证传感器模型、链路模型、机动能力和输出采样的闭合引用
  ✓ 验证执行清单哈希、排序、输入快照和篡改检测

■ 待办事项:
  - 无

■ 更新日志:
  v1.1.0 (2026-07-26): 增加不可变仿真执行清单契约测试
  v1.0.0 (2026-07-26): 创建 SimulationRunRequest 契约测试

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import pytest
from pydantic import BaseModel, ValidationError
from sycasphere.core._canonical import sha256_canonical_json
from sycasphere.core.entities import (
    GroundStationDefinition,
    OtherSpaceObjectDefinition,
    SpacecraftDefinition,
    SpaceObjectPhysicalProperties,
)
from sycasphere.core.epoch import Epoch, TimeScale
from sycasphere.core.execution import (
    DerivedRandomStream,
    EventOrderingPolicy,
    OutputRequirement,
    PreparedManeuverEntry,
    PreparedManeuverSource,
    PreparedTimeline,
    ResolvedPluginRecord,
    ScienceBackendBinding,
    SimulationExecutionManifest,
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
from sycasphere.core.plugins import PluginKind, PluginRef
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
    ExternalDataRef,
    SimulationDefinition,
)
from sycasphere.core.states import CartesianState

SCHEMA_VERSION = SchemaVersion(major=1, minor=0)
SYNCHRONIZATION_EPOCH = Epoch(value="2026-07-26T00:00:00Z", time_scale=TimeScale.UTC)
START_EPOCH = Epoch(value="2026-07-26T00:00:10Z", time_scale=TimeScale.UTC)
SCHEDULE_END_EPOCH = Epoch(value="2026-07-26T00:00:50Z", time_scale=TimeScale.UTC)
END_EPOCH = Epoch(value="2026-07-26T00:01:00Z", time_scale=TimeScale.UTC)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


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


def test_request_revalidates_copied_backend_configuration() -> None:
    request = make_request()
    mutable = {"nested": []}
    copied = request.backend.model_copy(update={"configuration": mutable})
    data = request.model_dump(mode="python")
    data["backend"] = copied

    accepted = SimulationRunRequest.model_validate(data)
    mutable["nested"].append("changed")

    assert accepted.backend is not copied
    assert accepted.backend.configuration["nested"] == ()
    with pytest.raises(AttributeError):
        accepted.backend.configuration["nested"].append("still-mutable")


def test_request_rejects_nonfinite_copied_backend_configuration() -> None:
    request = make_request()
    copied = request.backend.model_copy(update={"configuration": {"value": math.nan}})
    data = request.model_dump(mode="python")
    data["backend"] = copied

    with pytest.raises(ValidationError):
        SimulationRunRequest.model_validate(data)


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


# =============================👐Seperate👐=============================
# Immutable simulation execution manifest fixtures
# =============================👐Seperate👐=============================
def make_manifest_request(
    *,
    random_seed: int = 42,
    backend_configuration: object | None = None,
    two_schedules: bool = False,
) -> SimulationRunRequest:
    """Return a request whose planned and commanded maneuvers are prepared."""
    request = make_request()
    data = request.model_dump(mode="python")
    data["random_seed"] = random_seed
    data["command_timeline"] = (make_impulsive_command(),)

    if backend_configuration is not None:
        data["backend"] = ScienceBackendBinding(
            ref=request.backend.ref,
            configuration=backend_configuration,
        )

    if two_schedules:
        second = request.observation_schedules[0].model_copy(update={"schedule_id": "schedule-0"})
        data["observation_schedules"] = (
            request.observation_schedules[0],
            second,
        )

    return SimulationRunRequest.model_validate(data)


def make_resolved_plugin(
    component_id: str,
    *,
    kind: PluginKind,
    plugin_id: str,
    implementation_version: str = "1.0.0",
    configuration_hash: str = SHA_A,
) -> ResolvedPluginRecord:
    """Return one exact, content-addressed resolved plugin record."""
    return ResolvedPluginRecord(
        component_id=component_id,
        kind=kind,
        ref=PluginRef(
            plugin_id=plugin_id,
            implementation_version=implementation_version,
            interface_version=SCHEMA_VERSION,
        ),
        configuration_hash=configuration_hash,
    )


def make_resolved_plugins() -> tuple[ResolvedPluginRecord, ...]:
    """Return deliberately unsorted plugin records."""
    return (
        make_resolved_plugin(
            "measurement",
            kind=PluginKind.MEASUREMENT_MODEL,
            plugin_id="sycasphere.measurement",
            configuration_hash=SHA_B,
        ),
        make_resolved_plugin(
            "backend",
            kind=PluginKind.SCIENCE_BACKEND,
            plugin_id="sycasphere.orekit",
        ),
    )


def make_external_data() -> tuple[ExternalDataRef, ...]:
    """Return deliberately unsorted resolved external scientific data."""
    return (
        ExternalDataRef(data_id="z-eop", version="2026-07", sha256=SHA_C),
        ExternalDataRef(data_id="a-leap-seconds", version="2026-01", sha256=SHA_B),
    )


def make_random_streams() -> tuple[DerivedRandomStream, ...]:
    """Return deliberately unsorted deterministic random-stream records."""
    return (
        DerivedRandomStream(
            component_id="sensor-1",
            purpose="reported-noise",
            interface_version=SCHEMA_VERSION,
            derived_seed=10,
        ),
        DerivedRandomStream(
            component_id="backend",
            purpose="propagation",
            interface_version=SCHEMA_VERSION,
            derived_seed=20,
        ),
    )


def make_prepared_timeline(request: SimulationRunRequest) -> PreparedTimeline:
    """Return the compact prepared timeline corresponding to one request."""
    planned = request.simulation_definition.planned_maneuvers[0]
    command = request.command_timeline[0]
    return PreparedTimeline(
        maneuvers=(
            PreparedManeuverEntry(
                order_index=0,
                source=PreparedManeuverSource.PLANNED,
                event_id=planned.maneuver_id,
                spacecraft_id=planned.spacecraft_id,
                epoch=planned.epoch,
                maneuver=planned.maneuver,
            ),
            PreparedManeuverEntry(
                order_index=1,
                source=PreparedManeuverSource.COMMAND,
                event_id=command.command_id,
                spacecraft_id=command.spacecraft_id,
                epoch=command.epoch,
                maneuver=command.maneuver,
            ),
        ),
        observation_schedules=tuple(reversed(request.observation_schedules)),
        output_sampling=request.output_sampling,
    )


def make_manifest(
    *,
    source_request: SimulationRunRequest | None = None,
    resolved_plugins: tuple[ResolvedPluginRecord, ...] | None = None,
    resolved_external_data: tuple[ExternalDataRef, ...] | None = None,
    derived_random_streams: tuple[DerivedRandomStream, ...] | None = None,
    prepared_timeline: PreparedTimeline | None = None,
) -> SimulationExecutionManifest:
    """Create one deterministic immutable simulation execution manifest."""
    request = make_manifest_request() if source_request is None else source_request
    return SimulationExecutionManifest.create(
        schema_version=SCHEMA_VERSION,
        source_request=request,
        resolved_plugins=(
            make_resolved_plugins() if resolved_plugins is None else resolved_plugins
        ),
        resolved_external_data=(
            make_external_data() if resolved_external_data is None else resolved_external_data
        ),
        derived_random_streams=(
            make_random_streams() if derived_random_streams is None else derived_random_streams
        ),
        prepared_timeline=(
            make_prepared_timeline(request) if prepared_timeline is None else prepared_timeline
        ),
    )


# =============================👐Seperate👐=============================
# Manifest hashes, deterministic ordering, and immutable shape
# =============================👐Seperate👐=============================
def test_manifest_create_computes_all_three_hashes_and_fixed_versions() -> None:
    manifest = make_manifest()

    assert manifest.source_request_hash == sha256_canonical_json(manifest.source_request)
    assert manifest.simulation_definition_hash == sha256_canonical_json(
        manifest.source_request.simulation_definition
    )
    assert manifest.canonicalization_version == "SYCASPHERE_CANONICAL_JSON_V1"
    assert manifest.random_derivation_version == "SYCASPHERE_SEED_V1"
    assert manifest.event_ordering_policy is EventOrderingPolicy.POST_MANEUVER_OBSERVATION_V1
    assert manifest.content_hash == sha256_canonical_json(
        manifest.model_dump(mode="json", exclude={"content_hash"})
    )


def test_equivalent_inputs_create_byte_equivalent_manifests() -> None:
    first = make_manifest()
    second = make_manifest()

    assert first.model_dump_json() == second.model_dump_json()
    assert first.content_hash == second.content_hash


def test_manifest_records_and_prepared_schedules_sort_deterministically() -> None:
    request = make_manifest_request(two_schedules=True)
    manifest = make_manifest(source_request=request)

    assert [record.component_id for record in manifest.resolved_plugins] == [
        "backend",
        "measurement",
    ]
    assert [record.data_id for record in manifest.resolved_external_data] == [
        "a-leap-seconds",
        "z-eop",
    ]
    assert [
        (stream.component_id, stream.purpose) for stream in manifest.derived_random_streams
    ] == [
        ("backend", "propagation"),
        ("sensor-1", "reported-noise"),
    ]
    assert [
        schedule.schedule_id for schedule in manifest.prepared_timeline.observation_schedules
    ] == ["schedule-0", "schedule-1"]


def test_manifest_expected_outputs_equal_request_and_serialize_in_value_order() -> None:
    manifest = make_manifest()

    assert manifest.expected_outputs == manifest.source_request.output_requirements
    assert manifest.model_dump(mode="json")["expected_outputs"] == [
        "IDEAL_OBSERVATIONS",
        "TRUTH",
    ]


def test_manifest_and_source_request_are_frozen() -> None:
    manifest = make_manifest()

    with pytest.raises(ValidationError):
        manifest.content_hash = SHA_A
    with pytest.raises(ValidationError):
        manifest.source_request.random_seed = 43


@pytest.mark.parametrize(
    "model_type",
    [
        ResolvedPluginRecord,
        DerivedRandomStream,
        PreparedManeuverEntry,
        PreparedTimeline,
        SimulationExecutionManifest,
    ],
)
def test_manifest_public_models_are_frozen_and_extra_forbid(
    model_type: type[BaseModel],
) -> None:
    assert model_type.model_config["frozen"] is True
    assert model_type.model_config["extra"] == "forbid"


def test_manifest_contains_no_runtime_lifecycle_or_path_fields() -> None:
    fields = set(SimulationExecutionManifest.model_fields)

    assert fields.isdisjoint(
        {
            "prepared_at",
            "started_at",
            "ended_at",
            "status",
            "error",
            "output_hashes",
            "output_path",
            "runtime_command_journal",
        }
    )


def test_prepared_timeline_is_compact_for_periodic_schedules() -> None:
    manifest = make_manifest()
    serialized = manifest.prepared_timeline.model_dump(mode="json")

    assert serialized["observation_schedules"][0]["schedule_type"] == "PERIODIC"
    assert "expanded_epochs" not in serialized


# =============================👐Seperate👐=============================
# Manifest integrity, identity, and source equivalence validation
# =============================👐Seperate👐=============================
@pytest.mark.parametrize(
    "field_name",
    ["source_request_hash", "simulation_definition_hash", "content_hash"],
)
def test_manifest_rejects_tampered_source_definition_or_content_hash(
    field_name: str,
) -> None:
    manifest = make_manifest()
    data = manifest.model_dump(mode="python")
    data[field_name] = "0" * 64

    with pytest.raises(ValidationError, match=field_name):
        SimulationExecutionManifest.model_validate(data)


@pytest.mark.parametrize("invalid_hash", ["a" * 63, "A" * 64, "g" * 64])
def test_all_manifest_hash_fields_require_64_lowercase_hexadecimal_characters(
    invalid_hash: str,
) -> None:
    with pytest.raises(ValidationError, match="configuration_hash"):
        make_resolved_plugin(
            "backend",
            kind=PluginKind.SCIENCE_BACKEND,
            plugin_id="sycasphere.orekit",
            configuration_hash=invalid_hash,
        )

    with pytest.raises(ValidationError, match="sha256"):
        ExternalDataRef(data_id="eop", version="v1", sha256=invalid_hash)

    data = make_manifest().model_dump(mode="python")
    for field_name in (
        "source_request_hash",
        "simulation_definition_hash",
        "content_hash",
    ):
        invalid = {**data, field_name: invalid_hash}
        with pytest.raises(ValidationError, match=field_name):
            SimulationExecutionManifest.model_validate(invalid)


def test_manifest_rejects_duplicate_resolved_plugin_component_ids() -> None:
    plugins = make_resolved_plugins()
    duplicate = plugins[0].model_copy(update={"component_id": plugins[1].component_id})

    with pytest.raises(ValidationError, match="component_id"):
        make_manifest(resolved_plugins=(*plugins, duplicate))


def test_manifest_rejects_duplicate_external_data_ids() -> None:
    data = make_external_data()
    duplicate = data[0].model_copy(update={"version": "other-version", "sha256": SHA_A})

    with pytest.raises(ValidationError, match="data_id"):
        make_manifest(resolved_external_data=(*data, duplicate))


def test_manifest_rejects_duplicate_derived_stream_identities() -> None:
    streams = make_random_streams()
    duplicate = streams[0].model_copy(update={"derived_seed": 99})

    with pytest.raises(ValidationError, match=r"component_id.*purpose"):
        make_manifest(derived_random_streams=(*streams, duplicate))


@pytest.mark.parametrize("order_indices", [(1, 2), (1, 0), (0, 0)])
def test_prepared_maneuver_order_indices_are_exactly_consecutive(
    order_indices: tuple[int, int],
) -> None:
    timeline = make_prepared_timeline(make_manifest_request())
    maneuvers = tuple(
        entry.model_copy(update={"order_index": order_index})
        for entry, order_index in zip(timeline.maneuvers, order_indices, strict=True)
    )

    with pytest.raises(ValidationError, match="order_index"):
        PreparedTimeline(
            maneuvers=maneuvers,
            observation_schedules=timeline.observation_schedules,
            output_sampling=timeline.output_sampling,
        )


def test_prepared_timeline_rejects_duplicate_maneuver_event_ids() -> None:
    timeline = make_prepared_timeline(make_manifest_request())
    duplicate = timeline.maneuvers[1].model_copy(
        update={"event_id": timeline.maneuvers[0].event_id}
    )

    with pytest.raises(ValidationError, match="event_id"):
        PreparedTimeline(
            maneuvers=(timeline.maneuvers[0], duplicate),
            observation_schedules=timeline.observation_schedules,
            output_sampling=timeline.output_sampling,
        )


def test_prepared_timeline_rejects_duplicate_schedule_ids() -> None:
    request = make_manifest_request()
    schedule = request.observation_schedules[0]

    with pytest.raises(ValidationError, match="schedule_id"):
        PreparedTimeline(
            observation_schedules=(schedule, schedule),
            output_sampling=request.output_sampling,
        )


def test_manifest_requires_prepared_schedule_ids_to_equal_source_request_ids() -> None:
    request = make_manifest_request()
    timeline = make_prepared_timeline(request)
    other_schedule = request.observation_schedules[0].model_copy(
        update={"schedule_id": "other-schedule"}
    )
    mismatched = PreparedTimeline(
        maneuvers=timeline.maneuvers,
        observation_schedules=(other_schedule,),
        output_sampling=timeline.output_sampling,
    )

    with pytest.raises(ValidationError, match="schedule_id"):
        make_manifest(source_request=request, prepared_timeline=mismatched)


def test_manifest_requires_prepared_sampling_to_equal_source_request_sampling() -> None:
    request = make_manifest_request()
    timeline = make_prepared_timeline(request)
    mismatched = PreparedTimeline(
        maneuvers=timeline.maneuvers,
        observation_schedules=timeline.observation_schedules,
        output_sampling=OutputSampling(),
    )

    with pytest.raises(ValidationError, match="output_sampling"):
        make_manifest(source_request=request, prepared_timeline=mismatched)


def test_manifest_rejects_expected_outputs_different_from_source_request() -> None:
    manifest = make_manifest()
    data = manifest.model_dump(mode="python")
    data["expected_outputs"] = (OutputRequirement.TRUTH,)

    with pytest.raises(ValidationError, match="expected_outputs"):
        SimulationExecutionManifest.model_validate(data)


# =============================👐Seperate👐=============================
# Canonical hash sensitivity and trusted-instance isolation
# =============================👐Seperate👐=============================
@pytest.mark.parametrize(
    "changed_input",
    ["plugin-version", "external-data-hash", "seed", "backend-configuration"],
)
def test_scientific_input_changes_modify_manifest_content_hash(
    changed_input: str,
) -> None:
    baseline = make_manifest()

    if changed_input == "plugin-version":
        plugins = make_resolved_plugins()
        changed_ref = plugins[0].ref.model_copy(update={"implementation_version": "1.0.1"})
        changed_plugins = (
            plugins[0].model_copy(update={"ref": changed_ref}),
            plugins[1],
        )
        changed = make_manifest(resolved_plugins=changed_plugins)
    elif changed_input == "external-data-hash":
        data = make_external_data()
        changed = make_manifest(
            resolved_external_data=(data[0].model_copy(update={"sha256": SHA_A}), data[1])
        )
    elif changed_input == "seed":
        changed = make_manifest(source_request=make_manifest_request(random_seed=43))
    else:
        changed = make_manifest(
            source_request=make_manifest_request(
                backend_configuration={"integrator": {"kind": "DOP853", "max_step_s": 30.0}}
            )
        )

    assert changed.content_hash != baseline.content_hash


def test_negative_and_positive_zero_have_equal_canonical_manifest_hashes() -> None:
    negative = make_manifest(
        source_request=make_manifest_request(
            backend_configuration={"integrator": {"signed_zero": -0.0}}
        )
    )
    positive = make_manifest(
        source_request=make_manifest_request(
            backend_configuration={"integrator": {"signed_zero": 0.0}}
        )
    )

    assert negative.source_request_hash == positive.source_request_hash
    assert negative.simulation_definition_hash == positive.simulation_definition_hash
    assert negative.content_hash == positive.content_hash


def test_manifest_create_revalidates_copied_source_request() -> None:
    invalid_request = make_manifest_request().model_copy(update={"random_seed": -1})

    with pytest.raises(ValidationError, match="random_seed"):
        make_manifest(source_request=invalid_request)


def test_manifest_validation_revalidates_copied_source_request() -> None:
    manifest = make_manifest()
    data = manifest.model_dump(mode="python")
    data["source_request"] = manifest.source_request.model_copy(update={"random_seed": -1})

    with pytest.raises(ValidationError, match="random_seed"):
        SimulationExecutionManifest.model_validate(data)


def test_manifest_create_revalidates_copied_nested_plugin_record() -> None:
    plugins = make_resolved_plugins()
    invalid_ref = plugins[0].ref.model_copy(update={"implementation_version": "not-semver"})
    invalid_plugin = plugins[0].model_copy(update={"ref": invalid_ref})

    with pytest.raises(ValidationError, match="implementation_version"):
        make_manifest(resolved_plugins=(invalid_plugin, plugins[1]))


def test_manifest_validation_revalidates_copied_nested_plugin_record() -> None:
    manifest = make_manifest()
    invalid = manifest.resolved_plugins[0].model_copy(update={"configuration_hash": "not-a-hash"})
    data = manifest.model_dump(mode="python")
    data["resolved_plugins"] = (invalid, manifest.resolved_plugins[1])

    with pytest.raises(ValidationError, match="configuration_hash"):
        SimulationExecutionManifest.model_validate(data)


def test_manifest_snapshots_mutable_aliases_in_copied_source_request() -> None:
    request = make_manifest_request()
    mutable_configuration = {"integrator": {"steps": [1.0, 2.0]}}
    copied_backend = request.backend.model_copy(update={"configuration": mutable_configuration})
    copied_request = request.model_copy(update={"backend": copied_backend})

    manifest = make_manifest(source_request=copied_request)
    mutable_configuration["integrator"]["steps"].append(3.0)

    assert manifest.source_request is not copied_request
    assert manifest.source_request.backend is not copied_backend
    assert manifest.source_request.backend.configuration["integrator"]["steps"] == (
        1.0,
        2.0,
    )
