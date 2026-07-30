# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : conftest.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  为 Engine 确定性 FakeBackend 测试构造完整、不可变的 Core 请求与 Manifest。

■ 主要函数功能:
  - make_fake_request: 构造可选实体和机动的 FakeBackend 运行请求。
  - make_fake_manifest: 从请求构造等价的不可变执行清单。

■ 功能特性:
  ✓ 固定 FakeBackend 与三个测试模型的稳定身份
  ✓ 提供 SI/J2000 航天器、地面站和准备后机动数据

■ 待办事项:
  - [ ] 无

■ 更新日志:
  v1.0.0 (2026-07-30): 创建 FakeBackend 测试数据构造器与夹具

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import JsonValue
from sycasphere.core import (
    CartesianState,
    CentralBody,
    CoordinateRepresentation,
    EarthFixedFrameSpec,
    EntityDefinition,
    EnvironmentDefinition,
    Epoch,
    FrameKind,
    FrameRef,
    GeodeticLocation,
    GroundStationDefinition,
    ImpulsiveManeuverSpec,
    ManeuverCapability,
    ManeuverCommand,
    ManeuverSpec,
    ManeuverType,
    ModelRef,
    OutputProduct,
    OutputRequirement,
    OutputSampling,
    PlannedTruthManeuver,
    PluginKind,
    PluginRef,
    PreparedManeuverEntry,
    PreparedManeuverSource,
    PreparedTimeline,
    ReferenceEllipsoid,
    ResolvedPluginRecord,
    SamplingRule,
    SchemaVersion,
    ScienceBackendBinding,
    SimulationDefinition,
    SimulationExecutionManifest,
    SimulationRunRequest,
    SimulationTimeRange,
    SpacecraftDefinition,
    SpaceObjectPhysicalProperties,
    TimeScale,
)

# =============================👐Seperate👐=============================
# Stable FakeBackend test identities and time helpers
# =============================👐Seperate👐=============================
FAKE_BACKEND_ID = "sycasphere.testing.fake"
FAKE_DYNAMICS_ID = "sycasphere.testing.constant-velocity"
FAKE_ATTITUDE_ID = "sycasphere.testing.identity-attitude"
FAKE_PROPULSION_ID = "sycasphere.testing.impulsive-propulsion"
SCHEMA_VERSION = SchemaVersion(major=1, minor=0)


def utc(value: str) -> Epoch:
    """Build one explicit UTC epoch."""
    return Epoch(value=value, time_scale=TimeScale.UTC)


def fake_model(
    model_id: str,
    configuration: dict[str, JsonValue] | None = None,
) -> ModelRef:
    """Build one FakeBackend-owned model reference."""
    return ModelRef(
        model_id=model_id,
        interface_version=SCHEMA_VERSION,
        configuration={} if configuration is None else configuration,
    )


def fake_spacecraft(
    *,
    entity_id: str = "spacecraft-1",
    position_m: tuple[float, float, float] = (7_000_000.0, 0.0, 0.0),
    velocity_mps: tuple[float, float, float] = (0.0, 7_500.0, 0.0),
    mass_kg: float = 500.0,
    epoch: Epoch | None = None,
) -> SpacecraftDefinition:
    """Build one maneuver-capable constant-velocity spacecraft."""
    initial_epoch = utc("2026-07-30T00:00:00Z") if epoch is None else epoch
    return SpacecraftDefinition(
        id=entity_id,
        name=f"Fake {entity_id}",
        revision=1,
        schema_version=SCHEMA_VERSION,
        initial_state=CartesianState(
            epoch=initial_epoch,
            frame=FrameRef(kind=FrameKind.J2000),
            position_m=position_m,
            velocity_mps=velocity_mps,
        ),
        physical_properties=SpaceObjectPhysicalProperties(
            mass_kg=mass_kg,
            cross_section_area_m2=10.0,
        ),
        dynamics_model=fake_model(FAKE_DYNAMICS_ID),
        attitude_model=fake_model(FAKE_ATTITUDE_ID),
        maneuver_capability=ManeuverCapability(
            supported_types=frozenset({ManeuverType.IMPULSIVE}),
            propulsion_model=fake_model(FAKE_PROPULSION_ID),
        ),
    )


def fake_ground_station() -> GroundStationDefinition:
    """Build one supported non-propagated ground station."""
    return GroundStationDefinition(
        id="ground-station-1",
        name="Fake Ground Station",
        revision=1,
        schema_version=SCHEMA_VERSION,
        location=GeodeticLocation(
            frame=FrameRef(
                kind=FrameKind.EARTH_FIXED,
                representation=CoordinateRepresentation.GEODETIC,
                earth_fixed=EarthFixedFrameSpec(
                    itrf_realization="ITRF2020",
                    iers_conventions="IERS_2010",
                    eop_data_id="fake-eop",
                ),
                ellipsoid=ReferenceEllipsoid.WGS84,
            ),
            longitude_rad=0.0,
            latitude_rad=0.0,
            ellipsoid_height_m=0.0,
        ),
        body_axes_convention="NED_RH",
    )


def fake_impulse(
    *,
    delta_v_mps: tuple[float, float, float] = (1.0, -2.0, 0.5),
    frame: FrameRef | None = None,
) -> ImpulsiveManeuverSpec:
    """Build one nonzero impulsive maneuver."""
    return ImpulsiveManeuverSpec(
        delta_v_mps=delta_v_mps,
        frame=FrameRef(kind=FrameKind.J2000) if frame is None else frame,
    )


def make_fake_request(
    *,
    entities: tuple[EntityDefinition, ...] | None = None,
    planned_maneuvers: tuple[PlannedTruthManeuver, ...] = (),
    commands: tuple[ManeuverCommand, ...] = (),
    include_attitude: bool = True,
) -> SimulationRunRequest:
    """Build one complete valid FakeBackend request."""
    synchronization_epoch = utc("2026-07-30T00:00:00Z")
    selected_entities = (
        (fake_spacecraft(epoch=synchronization_epoch),) if entities is None else entities
    )
    rules = [
        SamplingRule(product=OutputProduct.TRUTH_STATE, interval_s=10.0),
    ]
    requirements = [OutputRequirement.TRUTH]
    if include_attitude:
        rules.append(SamplingRule(product=OutputProduct.ATTITUDE_STATE, interval_s=10.0))
        requirements.append(OutputRequirement.ATTITUDE)
    definition = SimulationDefinition(
        id="fake-simulation",
        name="FakeBackend Simulation",
        revision=1,
        schema_version=SCHEMA_VERSION,
        synchronization_epoch=synchronization_epoch,
        environment=EnvironmentDefinition(
            id="fake-environment",
            name="Fake Earth",
            revision=1,
            schema_version=SCHEMA_VERSION,
            central_body=CentralBody.EARTH,
        ),
        entities=selected_entities,
        planned_maneuvers=planned_maneuvers,
    )
    return SimulationRunRequest(
        schema_version=SCHEMA_VERSION,
        simulation_definition=definition,
        time_range=SimulationTimeRange(
            start=synchronization_epoch,
            end=utc("2026-07-30T00:00:10Z"),
        ),
        output_sampling=OutputSampling(rules=tuple(rules)),
        command_timeline=commands,
        backend=ScienceBackendBinding(
            ref=PluginRef(
                plugin_id=FAKE_BACKEND_ID,
                implementation_version="0.1.0",
                interface_version=SCHEMA_VERSION,
            )
        ),
        random_seed=20260730,
        output_requirements=frozenset(requirements),
    )


def _prepared_maneuvers(request: SimulationRunRequest) -> tuple[PreparedManeuverEntry, ...]:
    """Translate source maneuver records into deterministic prepared entries."""
    combined: list[tuple[PreparedManeuverSource, str, str, Epoch, ManeuverSpec]] = [
        (
            PreparedManeuverSource.PLANNED,
            item.maneuver_id,
            item.spacecraft_id,
            item.epoch,
            item.maneuver,
        )
        for item in request.simulation_definition.planned_maneuvers
    ]
    combined.extend(
        (
            PreparedManeuverSource.COMMAND,
            item.command_id,
            item.spacecraft_id,
            item.epoch,
            item.maneuver,
        )
        for item in request.command_timeline
    )
    combined.sort(key=lambda item: (item[3].value, item[0].value, item[1]))
    return tuple(
        PreparedManeuverEntry(
            order_index=index,
            source=source,
            event_id=event_id,
            spacecraft_id=spacecraft_id,
            epoch=epoch,
            maneuver=maneuver,
        )
        for index, (source, event_id, spacecraft_id, epoch, maneuver) in enumerate(combined)
    )


def make_fake_manifest(
    request: SimulationRunRequest | None = None,
) -> SimulationExecutionManifest:
    """Create one immutable manifest equivalent to its FakeBackend source request."""
    source = make_fake_request() if request is None else request
    return SimulationExecutionManifest.create(
        schema_version=SCHEMA_VERSION,
        source_request=source,
        resolved_plugins=(
            ResolvedPluginRecord.create(
                component_id="science-backend",
                kind=PluginKind.SCIENCE_BACKEND,
                ref=source.backend.ref,
                configuration=source.backend.configuration,
            ),
        ),
        resolved_external_data=(),
        derived_random_streams=(),
        prepared_timeline=PreparedTimeline(
            maneuvers=_prepared_maneuvers(source),
            observation_schedules=source.observation_schedules,
            output_sampling=source.output_sampling,
        ),
    )


def prepared_impulse(
    *,
    epoch: Epoch | None = None,
    spacecraft_id: str = "spacecraft-1",
    maneuver: ManeuverSpec | None = None,
) -> PreparedManeuverEntry:
    """Build one direct runtime maneuver entry at the default current epoch."""
    return PreparedManeuverEntry(
        order_index=0,
        source=PreparedManeuverSource.COMMAND,
        event_id="command-1",
        spacecraft_id=spacecraft_id,
        epoch=utc("2026-07-30T00:00:00Z") if epoch is None else epoch,
        maneuver=fake_impulse() if maneuver is None else maneuver,
    )


# =============================👐Seperate👐=============================
# Pytest fixtures
# =============================👐Seperate👐=============================
@pytest.fixture
def fake_request() -> SimulationRunRequest:
    """Return the canonical FakeBackend request."""
    return make_fake_request()


@pytest.fixture
def fake_manifest() -> SimulationExecutionManifest:
    """Return the canonical FakeBackend execution manifest."""
    return make_fake_manifest()


@pytest.fixture
def fake_request_factory() -> Callable[..., SimulationRunRequest]:
    """Return the reusable request constructor."""
    return make_fake_request


@pytest.fixture
def fake_manifest_factory() -> Callable[..., SimulationExecutionManifest]:
    """Return the reusable manifest constructor."""
    return make_fake_manifest
