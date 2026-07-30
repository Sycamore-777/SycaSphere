# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_preparation.py
创建者    : Sycamore
创建日期  : 2026-07-31
最后修改  : 2026-07-31
版本号    : v1.0.0

■ 用途说明:
  验证 Engine 准备期的边界快照、v0.1 范围分类、插件解析和稳定时间线。

■ 主要函数功能:
  - test_prepare_*: 验证不可变 Manifest、错误优先级和后端端口调用次数
  - test_prepare_orders_*: 验证适配器驱动的机动时序及同刻稳定顺序

■ 功能特性:
  ✓ 使用真实 Core 请求与公开 FakeBackend 注册项
  ✓ 覆盖通用注册项的外部数据和可变输入快照
  ✓ 保证 prepare 不创建 runtime

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-31): 创建 Manifest 准备期合同测试

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import cast

import pytest
from conftest import (
    SCHEMA_VERSION,
    fake_impulse,
    fake_model,
    make_fake_request,
    utc,
)
from pydantic import JsonValue
from sycasphere.core import (
    CartesianState,
    CoordinateRepresentation,
    EarthFixedFrameSpec,
    EnvironmentDefinition,
    Epoch,
    ErrorCategory,
    ExternalDataRef,
    FiniteBurnManeuverSpec,
    FrameKind,
    FrameRef,
    ManeuverCapability,
    ManeuverCommand,
    ManeuverType,
    OutputProduct,
    OutputRequirement,
    OutputSampling,
    PeriodicObservationSchedule,
    PlannedTruthManeuver,
    PluginRef,
    RigidTransform,
    SamplingRule,
    ScienceBackendBinding,
    SensorAxes,
    SensorDefinition,
    SensorType,
    SimulationExecutionManifest,
    SimulationRunRequest,
    SimulationTimeRange,
    SpacecraftDefinition,
    TimeScale,
)
from sycasphere.engine.backend import (
    BackendConfigurationValidator,
    PreparationTimeAdapter,
    ScienceBackendFactory,
    ScienceBackendRegistration,
    ScienceBackendRuntime,
)
from sycasphere.engine.errors import SimulationPreparationError
from sycasphere.engine.preparation import ManifestPreparer
from sycasphere.engine.registry import PluginRegistry
from sycasphere.engine.testing import fake_backend_registration

# =============================👐Seperate👐=============================
# Recording backend dependencies
# =============================👐Seperate👐=============================


@dataclass
class RecordingValidator:
    """Count validation calls while preserving the real validator behavior."""

    delegate: BackendConfigurationValidator
    validate_calls: int = 0

    def validate(self, request: SimulationRunRequest) -> None:
        """Record and delegate one configuration validation."""
        self.validate_calls += 1
        self.delegate.validate(request)


@dataclass
class RecordingFactory:
    """Count runtime creations while retaining a complete public factory double."""

    delegate: ScienceBackendFactory
    create_calls: int = 0

    def create(self, manifest: SimulationExecutionManifest) -> ScienceBackendRuntime:
        """Record an accidental runtime creation before delegating."""
        self.create_calls += 1
        return self.delegate.create(manifest)


@dataclass
class RecordingTimeAdapter:
    """Record absolute comparisons while delegating their scientific semantics."""

    delegate: PreparationTimeAdapter
    compare_calls: list[tuple[Epoch, Epoch]] = field(default_factory=list)

    def compare(self, left: Epoch, right: Epoch) -> int:
        """Record and delegate one absolute epoch comparison."""
        self.compare_calls.append((left, right))
        return self.delegate.compare(left, right)

    def seconds_between(self, start: Epoch, end: Epoch) -> float:
        """Delegate SI duration calculation."""
        return self.delegate.seconds_between(start, end)

    def add_seconds(self, epoch: Epoch, seconds: float) -> Epoch:
        """Delegate finite SI-second addition."""
        return self.delegate.add_seconds(epoch, seconds)

    def same_instant(self, left: Epoch, right: Epoch) -> bool:
        """Delegate absolute-instant equality."""
        return self.delegate.same_instant(left, right)


class AcceptingValidator:
    """Accept generic v0.1 backend configuration without side effects."""

    def validate(self, request: SimulationRunRequest) -> None:
        """Accept the already revalidated public request."""


@pytest.fixture
def recording_fake_registration() -> ScienceBackendRegistration:
    """Return FakeBackend with recording preparation and factory dependencies."""
    base = fake_backend_registration()
    return replace(
        base,
        configuration_validator=RecordingValidator(base.configuration_validator),
        time_adapter=RecordingTimeAdapter(base.time_adapter),
        factory=RecordingFactory(base.factory),
    )


def _generic_registration(
    *,
    time_adapter: PreparationTimeAdapter | None = None,
) -> ScienceBackendRegistration:
    """Return a generic registration that accepts locked external data."""
    base = fake_backend_registration()
    generic_ref = PluginRef(
        plugin_id="example.generic.backend",
        implementation_version="2.3.4",
        interface_version=SCHEMA_VERSION,
    )
    return replace(
        base,
        manifest=base.manifest.model_copy(update={"ref": generic_ref}),
        configuration_validator=RecordingValidator(AcceptingValidator()),
        time_adapter=base.time_adapter if time_adapter is None else time_adapter,
        factory=RecordingFactory(base.factory),
    )


def _recording_validator(
    registration: ScienceBackendRegistration,
) -> RecordingValidator:
    """Return the test-owned complete validator recorder."""
    return cast(RecordingValidator, registration.configuration_validator)


def _recording_factory(registration: ScienceBackendRegistration) -> RecordingFactory:
    """Return the test-owned complete factory recorder."""
    return cast(RecordingFactory, registration.factory)


# =============================👐Seperate👐=============================
# Request construction helpers
# =============================👐Seperate👐=============================


def _validated_request(
    request: SimulationRunRequest,
    **updates: object,
) -> SimulationRunRequest:
    """Apply updates and prove the resulting request is a valid Core boundary."""
    candidate = request.model_copy(update=updates)
    return SimulationRunRequest.model_validate(candidate.model_dump(mode="python"))


def _earth_fixed_frame() -> FrameRef:
    """Return a fully specified Cartesian Earth-fixed frame."""
    return FrameRef(
        kind=FrameKind.EARTH_FIXED,
        representation=CoordinateRepresentation.CARTESIAN,
        earth_fixed=EarthFixedFrameSpec(
            itrf_realization="ITRF2020",
            iers_conventions="IERS_2010",
            eop_data_id="fake-eop",
        ),
    )


def _sensor() -> SensorDefinition:
    """Return one complete sensor used only to form a valid unsupported schedule."""
    return SensorDefinition(
        id="sensor-1",
        name="Unsupported Observation Sensor",
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
        pointing_model=fake_model("example.pointing.fixed"),
        field_of_view_model=fake_model("example.fov.conical"),
        visibility_model=fake_model("example.visibility.basic"),
        measurement_models=(fake_model("example.measurement.angles"),),
    )


def _with_observation_schedule(request: SimulationRunRequest) -> SimulationRunRequest:
    """Return a valid Core request containing one Engine-v0.1 unsupported schedule."""
    spacecraft = request.simulation_definition.entities[0]
    assert isinstance(spacecraft, SpacecraftDefinition)
    observed_spacecraft = spacecraft.model_copy(update={"sensors": (_sensor(),)})
    definition = request.simulation_definition.model_copy(
        update={"entities": (observed_spacecraft,)}
    )
    schedule = PeriodicObservationSchedule(
        schedule_id="schedule-1",
        sensor_id="sensor-1",
        target_id=spacecraft.id,
        measurement_model_id="example.measurement.angles",
        start_epoch=request.time_range.start,
        end_epoch=request.time_range.end,
        cadence_s=5.0,
    )
    return _validated_request(
        request,
        simulation_definition=definition,
        observation_schedules=(schedule,),
    )


def _with_link_model(request: SimulationRunRequest) -> SimulationRunRequest:
    """Return a valid Core request containing one Engine-v0.1 unsupported link model."""
    return _validated_request(
        request,
        link_models=(fake_model("example.link.nominal"),),
    )


def _with_non_j2000_state(request: SimulationRunRequest) -> SimulationRunRequest:
    """Return a valid request whose propagated state uses an unsupported public frame."""
    spacecraft = request.simulation_definition.entities[0]
    assert isinstance(spacecraft, SpacecraftDefinition)
    state = CartesianState(
        epoch=spacecraft.initial_state.epoch,
        frame=_earth_fixed_frame(),
        position_m=spacecraft.initial_state.position_m,
        velocity_mps=spacecraft.initial_state.velocity_mps,
    )
    definition = request.simulation_definition.model_copy(
        update={"entities": (spacecraft.model_copy(update={"initial_state": state}),)}
    )
    return _validated_request(request, simulation_definition=definition)


def _with_non_j2000_maneuver(request: SimulationRunRequest) -> SimulationRunRequest:
    """Return a valid request whose impulse uses an unsupported public frame."""
    maneuver = PlannedTruthManeuver(
        maneuver_id="earth-fixed-impulse",
        spacecraft_id="spacecraft-1",
        epoch=request.time_range.start,
        maneuver=fake_impulse(frame=_earth_fixed_frame()),
    )
    definition = request.simulation_definition.model_copy(update={"planned_maneuvers": (maneuver,)})
    return _validated_request(request, simulation_definition=definition)


def _with_output(
    request: SimulationRunRequest,
    requirement: OutputRequirement,
) -> SimulationRunRequest:
    """Return a Core-valid request containing one unsupported output."""
    rules = request.output_sampling.rules
    if requirement is OutputRequirement.GEOMETRY:
        rules = (
            *rules,
            SamplingRule(product=OutputProduct.DERIVED_GEOMETRY, interval_s=10.0),
        )
    return _validated_request(
        request,
        output_sampling=OutputSampling(rules=rules),
        output_requirements=frozenset({*request.output_requirements, requirement}),
    )


def _with_finite_burn(request: SimulationRunRequest) -> SimulationRunRequest:
    """Return a Core-valid request and spacecraft capability containing one finite burn."""
    spacecraft = request.simulation_definition.entities[0]
    assert isinstance(spacecraft, SpacecraftDefinition)
    capability = ManeuverCapability(
        supported_types=frozenset({ManeuverType.IMPULSIVE, ManeuverType.FINITE_BURN}),
        propulsion_model=fake_model("sycasphere.testing.impulsive-propulsion"),
    )
    capable_spacecraft = spacecraft.model_copy(update={"maneuver_capability": capability})
    planned = PlannedTruthManeuver(
        maneuver_id="finite-burn-1",
        spacecraft_id=spacecraft.id,
        epoch=request.time_range.start,
        maneuver=FiniteBurnManeuverSpec(
            duration_s=1.0,
            thrust_n=(1.0, 0.0, 0.0),
            frame=FrameRef(kind=FrameKind.J2000),
        ),
    )
    definition = request.simulation_definition.model_copy(
        update={
            "entities": (capable_spacecraft,),
            "planned_maneuvers": (planned,),
        }
    )
    return _validated_request(request, simulation_definition=definition)


def _with_environment(
    request: SimulationRunRequest,
    *,
    model_refs: tuple[object, ...] = (),
    external_data_refs: tuple[ExternalDataRef, ...] = (),
) -> SimulationRunRequest:
    """Return a valid request with explicitly versioned environment dependencies."""
    environment = EnvironmentDefinition.model_validate(
        request.simulation_definition.environment.model_copy(
            update={
                "model_refs": model_refs,
                "external_data_refs": external_data_refs,
            }
        ).model_dump(mode="python")
    )
    definition = request.simulation_definition.model_copy(update={"environment": environment})
    return _validated_request(request, simulation_definition=definition)


def _with_unknown_dynamics(request: SimulationRunRequest) -> SimulationRunRequest:
    """Return a valid request selecting an unknown Fake dynamics model."""
    spacecraft = request.simulation_definition.entities[0]
    assert isinstance(spacecraft, SpacecraftDefinition)
    definition = request.simulation_definition.model_copy(
        update={
            "entities": (
                spacecraft.model_copy(
                    update={"dynamics_model": fake_model("example.unknown.dynamics")}
                ),
            )
        }
    )
    return _validated_request(request, simulation_definition=definition)


def _planned(event_id: str, epoch: Epoch) -> PlannedTruthManeuver:
    """Create one J2000 planned impulse."""
    return PlannedTruthManeuver(
        maneuver_id=event_id,
        spacecraft_id="spacecraft-1",
        epoch=epoch,
        maneuver=fake_impulse(),
    )


def _command(event_id: str, epoch: Epoch) -> ManeuverCommand:
    """Create one J2000 command impulse."""
    return ManeuverCommand(
        command_id=event_id,
        spacecraft_id="spacecraft-1",
        epoch=epoch,
        maneuver=fake_impulse(),
    )


# =============================👐Seperate👐=============================
# Boundary snapshot, resolution, provenance, and call counts
# =============================👐Seperate👐=============================


def test_prepare_resolves_backend_without_creating_runtime(
    fake_request: SimulationRunRequest,
    recording_fake_registration: ScienceBackendRegistration,
) -> None:
    """Preparation resolves and validates once but never crosses the factory boundary."""
    preparer = ManifestPreparer(PluginRegistry((recording_fake_registration,)))

    manifest = preparer.prepare(fake_request)

    assert manifest.source_request == fake_request
    assert manifest.source_request is not fake_request
    assert manifest.source_request.simulation_definition is not fake_request.simulation_definition
    assert manifest.resolved_plugins[0].component_id == "science-backend"
    assert manifest.resolved_plugins[0].ref == recording_fake_registration.manifest.ref
    assert manifest.resolved_external_data == ()
    assert manifest.derived_random_streams == ()
    assert _recording_validator(recording_fake_registration).validate_calls == 1
    assert _recording_factory(recording_fake_registration).create_calls == 0


def test_prepare_is_deterministic_and_calls_validator_once_per_request(
    fake_request: SimulationRunRequest,
    recording_fake_registration: ScienceBackendRegistration,
) -> None:
    """Identical explicit inputs produce identical dumps and content hashes."""
    preparer = ManifestPreparer(PluginRegistry((recording_fake_registration,)))

    first = preparer.prepare(fake_request)
    second = preparer.prepare(fake_request)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.content_hash == second.content_hash
    assert _recording_validator(recording_fake_registration).validate_calls == 2
    assert _recording_factory(recording_fake_registration).create_calls == 0


def test_prepare_snapshots_construct_bypassed_mutable_configuration(
    fake_request: SimulationRunRequest,
) -> None:
    """Caller-owned mutable configuration cannot alias the prepared request snapshot."""
    registration = _generic_registration()
    mutable_configuration: dict[str, JsonValue] = {
        "integrator": {"steps_s": [1.0, 2.0]},
    }
    bypassed_binding = ScienceBackendBinding.model_construct(
        ref=registration.manifest.ref,
        configuration=mutable_configuration,
    )
    bypassed_request = fake_request.model_copy(update={"backend": bypassed_binding})
    preparer = ManifestPreparer(PluginRegistry((registration,)))

    manifest = preparer.prepare(bypassed_request)
    original_dump = manifest.model_dump(mode="json")
    nested = cast(dict[str, JsonValue], mutable_configuration["integrator"])
    cast(list[JsonValue], nested["steps_s"]).append(3.0)

    assert manifest.model_dump(mode="json") == original_dump
    assert manifest.source_request.backend is not bypassed_request.backend
    assert _recording_validator(registration).validate_calls == 1


def test_prepare_copies_generic_external_refs_into_resolved_provenance(
    fake_request: SimulationRunRequest,
) -> None:
    """Generic backends lock exact versioned environment data without artifact access."""
    registration = _generic_registration()
    data_refs = (
        ExternalDataRef(
            data_id="iers-eop",
            version="2026-07-31",
            sha256="a" * 64,
        ),
        ExternalDataRef(
            data_id="gravity-field",
            version="egm2008-v1",
            sha256="b" * 64,
        ),
    )
    request = _with_environment(fake_request, external_data_refs=data_refs)
    request = _validated_request(
        request,
        backend=ScienceBackendBinding(ref=registration.manifest.ref),
    )

    manifest = ManifestPreparer(PluginRegistry((registration,))).prepare(request)

    assert manifest.resolved_external_data == tuple(
        sorted(data_refs, key=lambda item: (item.data_id, item.version, item.sha256))
    )
    assert manifest.derived_random_streams == ()
    assert manifest.resolved_plugins[0].ref == registration.manifest.ref
    assert _recording_validator(registration).validate_calls == 1
    assert _recording_factory(registration).create_calls == 0


def test_prepare_resolves_the_complete_plugin_ref_before_scope_checks(
    fake_request: SimulationRunRequest,
) -> None:
    """A same-ID but different implementation cannot fall back to the registered Fake."""
    request = _with_observation_schedule(fake_request)
    mismatched_ref = request.backend.ref.model_copy(update={"implementation_version": "0.1.1"})
    request = _validated_request(
        request,
        backend=ScienceBackendBinding(ref=mismatched_ref),
    )

    with pytest.raises(SimulationPreparationError) as captured:
        ManifestPreparer(PluginRegistry((fake_backend_registration(),))).prepare(request)

    assert captured.value.detail.category is ErrorCategory.PLUGIN_MISSING
    assert captured.value.detail.code == "plugin.backend_missing"
    assert captured.value.detail.context == {
        "plugin_ref": mismatched_ref.model_dump(mode="json"),
    }


# =============================👐Seperate👐=============================
# Public boundary and Engine v0.1 scope classification
# =============================👐Seperate👐=============================


def test_prepare_revalidates_a_construct_bypassed_nonpositive_output_interval(
    fake_request: SimulationRunRequest,
) -> None:
    """A Pydantic construct bypass is translated at the public preparation boundary."""
    bad_truth_rule = SamplingRule.model_construct(
        product=OutputProduct.TRUTH_STATE,
        interval_s=0.0,
    )
    bypassed_sampling = OutputSampling.model_construct(
        rules=(bad_truth_rule, *fake_request.output_sampling.rules[1:])
    )
    bypassed_request = fake_request.model_copy(update={"output_sampling": bypassed_sampling})

    with pytest.raises(SimulationPreparationError) as captured:
        ManifestPreparer(PluginRegistry((fake_backend_registration(),))).prepare(bypassed_request)

    assert captured.value.detail.category is ErrorCategory.VALIDATION_ERROR
    assert captured.value.detail.code == "engine.request_invalid"
    assert captured.value.detail.context == {
        "validation_stage": "simulation_run_request",
    }


@pytest.mark.parametrize(
    ("mutator", "expected_code", "expected_feature"),
    [
        (
            _with_observation_schedule,
            "engine.observations_unsupported",
            "observation_schedules",
        ),
        (
            _with_link_model,
            "engine.link_models_unsupported",
            "link_models",
        ),
    ],
)
def test_prepare_classifies_observation_and_link_inputs_as_unsupported_measurement(
    fake_request: SimulationRunRequest,
    recording_fake_registration: ScienceBackendRegistration,
    mutator: Callable[[SimulationRunRequest], SimulationRunRequest],
    expected_code: str,
    expected_feature: str,
) -> None:
    """Engine-owned measurement scope takes precedence over plugin validation."""
    request = mutator(fake_request)

    with pytest.raises(SimulationPreparationError) as captured:
        ManifestPreparer(PluginRegistry((recording_fake_registration,))).prepare(request)

    assert captured.value.detail.category is ErrorCategory.UNSUPPORTED_MEASUREMENT
    assert captured.value.detail.code == expected_code
    assert captured.value.detail.context == {"feature": expected_feature}
    assert _recording_validator(recording_fake_registration).validate_calls == 0


@pytest.mark.parametrize(
    ("mutator", "source_kind", "source_id"),
    [
        (_with_non_j2000_state, "initial_state", "spacecraft-1"),
        (_with_non_j2000_maneuver, "planned_maneuver", "earth-fixed-impulse"),
    ],
)
def test_prepare_classifies_non_j2000_scientific_inputs_as_unsupported_frame(
    fake_request: SimulationRunRequest,
    recording_fake_registration: ScienceBackendRegistration,
    mutator: Callable[[SimulationRunRequest], SimulationRunRequest],
    source_kind: str,
    source_id: str,
) -> None:
    """Engine v0.1 rejects every propagated or maneuver vector outside J2000."""
    request = mutator(fake_request)

    with pytest.raises(SimulationPreparationError) as captured:
        ManifestPreparer(PluginRegistry((recording_fake_registration,))).prepare(request)

    assert captured.value.detail.category is ErrorCategory.UNSUPPORTED_FRAME
    assert captured.value.detail.code == "engine.frame_unsupported"
    assert captured.value.detail.context == {
        "source_kind": source_kind,
        "source_id": source_id,
        "frame": FrameKind.EARTH_FIXED.value,
    }
    assert _recording_validator(recording_fake_registration).validate_calls == 0


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (
            lambda request: _with_output(request, OutputRequirement.GEOMETRY),
            "engine.output_unsupported",
        ),
        (
            lambda request: _with_output(request, OutputRequirement.DIAGNOSTICS),
            "engine.output_unsupported",
        ),
        (_with_finite_burn, "engine.finite_burn_unsupported"),
    ],
)
def test_prepare_classifies_unimplemented_v01_outputs_and_finite_burns(
    fake_request: SimulationRunRequest,
    recording_fake_registration: ScienceBackendRegistration,
    mutator: Callable[[SimulationRunRequest], SimulationRunRequest],
    expected_code: str,
) -> None:
    """Universal v0.1 omissions fail before backend-owned configuration checks."""
    request = mutator(fake_request)

    with pytest.raises(SimulationPreparationError) as captured:
        ManifestPreparer(PluginRegistry((recording_fake_registration,))).prepare(request)

    assert captured.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE
    assert captured.value.detail.code == expected_code
    assert _recording_validator(recording_fake_registration).validate_calls == 0


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (
            lambda request: _with_environment(
                request,
                model_refs=(fake_model("example.environment.model"),),
            ),
            "fake_backend.environment_models_unsupported",
        ),
        (
            lambda request: _with_environment(
                request,
                external_data_refs=(
                    ExternalDataRef(
                        data_id="leap-seconds",
                        version="2026",
                        sha256="c" * 64,
                    ),
                ),
            ),
            "fake_backend.external_data_unsupported",
        ),
        (_with_unknown_dynamics, "fake_backend.dynamics_model_unsupported"),
    ],
)
def test_prepare_preserves_fake_backend_environment_and_model_errors(
    fake_request: SimulationRunRequest,
    recording_fake_registration: ScienceBackendRegistration,
    mutator: Callable[[SimulationRunRequest], SimulationRunRequest],
    expected_code: str,
) -> None:
    """Existing structured Fake errors pass through without recategorization."""
    request = mutator(fake_request)

    with pytest.raises(SimulationPreparationError) as captured:
        ManifestPreparer(PluginRegistry((recording_fake_registration,))).prepare(request)

    assert captured.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE
    assert captured.value.detail.code == expected_code
    assert _recording_validator(recording_fake_registration).validate_calls == 1


@pytest.mark.parametrize(
    ("end_epoch", "expected_code"),
    [
        (
            Epoch(value="2026-07-30T00:00:10", time_scale=TimeScale.TAI),
            "ENGINE_TIME_SCALE_MISMATCH",
        ),
        (
            Epoch(value="2026-12-31T23:59:60Z", time_scale=TimeScale.UTC),
            "ENGINE_TIME_LEAP_SECOND_UNSUPPORTED",
        ),
    ],
)
def test_prepare_classifies_fake_time_incompatibilities(
    fake_request: SimulationRunRequest,
    recording_fake_registration: ScienceBackendRegistration,
    end_epoch: Epoch,
    expected_code: str,
) -> None:
    """Mixed scales and UTC leap seconds remain explicit plugin incompatibilities."""
    request = _validated_request(
        fake_request,
        time_range=fake_request.time_range.model_copy(update={"end": end_epoch}),
    )

    with pytest.raises(SimulationPreparationError) as captured:
        ManifestPreparer(PluginRegistry((recording_fake_registration,))).prepare(request)

    assert captured.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE
    assert captured.value.detail.code == expected_code
    assert _recording_validator(recording_fake_registration).validate_calls == 1


# =============================👐Seperate👐=============================
# Adapter-authoritative stable prepared maneuver ordering
# =============================👐Seperate👐=============================


def test_prepare_orders_prestart_and_equal_epoch_maneuvers_stably(
    recording_fake_registration: ScienceBackendRegistration,
) -> None:
    """Primary epoch order precedes stable source priority and original tuple position."""
    early_epoch = utc("2026-07-30T00:00:02Z")
    formal_start = utc("2026-07-30T00:00:05Z")
    planned = (
        _planned("planned-z", formal_start),
        _planned("planned-a", formal_start),
        _planned("planned-early", early_epoch),
    )
    commands = (
        _command("command-z", formal_start),
        _command("command-a", formal_start),
    )
    request = make_fake_request(
        planned_maneuvers=planned,
        commands=commands,
    )
    request = _validated_request(
        request,
        time_range=SimulationTimeRange(
            start=formal_start,
            end=utc("2026-07-30T00:00:10Z"),
        ),
    )

    manifest = ManifestPreparer(PluginRegistry((recording_fake_registration,))).prepare(request)
    entries = manifest.prepared_timeline.maneuvers

    assert tuple(entry.event_id for entry in entries) == (
        "planned-early",
        "planned-z",
        "planned-a",
        "command-z",
        "command-a",
    )
    assert tuple(entry.source.value for entry in entries) == (
        "PLANNED",
        "PLANNED",
        "PLANNED",
        "COMMAND",
        "COMMAND",
    )
    assert tuple(entry.order_index for entry in entries) == tuple(range(5))
    assert cast(
        RecordingTimeAdapter,
        recording_fake_registration.time_adapter,
    ).compare_calls


@dataclass
class RankedTimeAdapter:
    """Test adapter whose two maneuver epochs have a deliberate nonlexical order."""

    delegate: PreparationTimeAdapter
    compare_calls: list[tuple[Epoch, Epoch]] = field(default_factory=list)

    def compare(self, left: Epoch, right: Epoch) -> int:
        """Rank selected epochs explicitly and delegate every other comparison."""
        self.compare_calls.append((left, right))
        ranks = {
            "2026-07-30T00:00:01Z": 2,
            "2026-07-30T00:00:02Z": 1,
        }
        if left.value in ranks and right.value in ranks:
            return (ranks[left.value] > ranks[right.value]) - (
                ranks[left.value] < ranks[right.value]
            )
        return self.delegate.compare(left, right)

    def seconds_between(self, start: Epoch, end: Epoch) -> float:
        """Delegate duration calculation outside this sorting test."""
        return self.delegate.seconds_between(start, end)

    def add_seconds(self, epoch: Epoch, seconds: float) -> Epoch:
        """Delegate epoch arithmetic outside this sorting test."""
        return self.delegate.add_seconds(epoch, seconds)

    def same_instant(self, left: Epoch, right: Epoch) -> bool:
        """Use this adapter's authoritative comparison."""
        return self.compare(left, right) == 0


def test_prepare_uses_registration_time_adapter_as_primary_sort_key(
    fake_request: SimulationRunRequest,
) -> None:
    """Prepared chronology follows the resolved backend adapter, not Epoch text."""
    base = fake_backend_registration()
    ranked_adapter = RankedTimeAdapter(base.time_adapter)
    registration = _generic_registration(time_adapter=ranked_adapter)
    planned = (
        _planned("lexically-first", utc("2026-07-30T00:00:01Z")),
        _planned("adapter-first", utc("2026-07-30T00:00:02Z")),
    )
    definition = fake_request.simulation_definition.model_copy(
        update={"planned_maneuvers": planned}
    )
    request = _validated_request(
        fake_request,
        simulation_definition=definition,
        backend=ScienceBackendBinding(ref=registration.manifest.ref),
    )

    manifest = ManifestPreparer(PluginRegistry((registration,))).prepare(request)

    assert tuple(entry.event_id for entry in manifest.prepared_timeline.maneuvers) == (
        "adapter-first",
        "lexically-first",
    )
    assert ranked_adapter.compare_calls
    assert _recording_validator(registration).validate_calls == 1
    assert _recording_factory(registration).create_calls == 0
