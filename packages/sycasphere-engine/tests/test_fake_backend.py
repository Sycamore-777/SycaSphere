# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_fake_backend.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  验证公开 FakeBackend 的严格配置、确定性传播、机动和运行时生命周期。

■ 主要函数功能:
  - test_fake_backend_*: 验证清单、校验器、工厂和单次运行时行为。

■ 功能特性:
  ✓ 覆盖 SI/J2000 匀速传播、WXYZ 单位姿态和质量不变脉冲
  ✓ 覆盖取消原子性、实体排序、地面站隔离和关闭生命周期

■ 待办事项:
  - [ ] 无

■ 更新日志:
  v1.0.0 (2026-07-30): 创建 FakeBackend 合同测试

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
import sycasphere.engine.testing.fake_backend as fake_backend_module
from conftest import (
    FAKE_BACKEND_ID,
    FAKE_DYNAMICS_ID,
    SCHEMA_VERSION,
    fake_ground_station,
    fake_impulse,
    fake_model,
    fake_spacecraft,
    make_fake_manifest,
    prepared_impulse,
    utc,
)
from pydantic import ValidationError
from sycasphere.core import (
    AttitudeState,
    CartesianState,
    DerivedRandomStream,
    EarthFixedFrameSpec,
    EnvironmentDefinition,
    Epoch,
    ErrorCategory,
    ExternalDataRef,
    FiniteBurnManeuverSpec,
    FrameKind,
    FrameRef,
    ManeuverCapability,
    ManeuverType,
    OutputProduct,
    OutputRequirement,
    OutputSampling,
    PluginKind,
    PluginRef,
    PreparedManeuverEntry,
    ResolvedPluginRecord,
    ResourceRequirements,
    SamplingRule,
    ScienceBackendBinding,
    SimulationExecutionManifest,
    SimulationRunRequest,
    SpacecraftDefinition,
    TimeScale,
)
from sycasphere.engine.backend import PropagationOutcome
from sycasphere.engine.cancellation import CancellationToken
from sycasphere.engine.errors import SimulationExecutionError, SimulationPreparationError
from sycasphere.engine.testing import (
    FAKE_PLUGIN_MANIFEST,
    FakeBackendConfigurationValidator,
    FakeScienceBackendFactory,
    fake_backend_registration,
)

# =============================👐Seperate👐=============================
# Stable public manifest and strict preparation validation
# =============================👐Seperate👐=============================


def test_fake_manifest_has_exact_identity_capabilities_and_schema() -> None:
    """The compatibility backend publishes the exact approved data-only manifest."""
    assert FAKE_PLUGIN_MANIFEST.ref.plugin_id == FAKE_BACKEND_ID
    assert FAKE_PLUGIN_MANIFEST.ref.implementation_version == "0.1.0"
    assert FAKE_PLUGIN_MANIFEST.ref.interface_version == SCHEMA_VERSION
    assert FAKE_PLUGIN_MANIFEST.kind is PluginKind.SCIENCE_BACKEND
    assert FAKE_PLUGIN_MANIFEST.capabilities == frozenset(
        {
            "attitude.identity-wxyz",
            "dynamics.constant-velocity",
            "frame.j2000",
            "maneuver.impulsive.j2000",
            "output.attitude",
            "output.truth",
            "time.same-scale",
        }
    )
    assert FAKE_PLUGIN_MANIFEST.configuration_schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    assert FAKE_PLUGIN_MANIFEST.deterministic is True
    assert FAKE_PLUGIN_MANIFEST.resources == ResourceRequirements()


def test_fake_registration_uses_public_manifest_validator_time_adapter_and_factory() -> None:
    """One helper returns the complete explicit registration without mutable configuration."""
    registration = fake_backend_registration()

    assert registration.manifest is FAKE_PLUGIN_MANIFEST
    assert isinstance(registration.configuration_validator, FakeBackendConfigurationValidator)
    assert isinstance(registration.factory, FakeScienceBackendFactory)
    assert registration.time_adapter.same_instant(
        utc("2026-07-30T00:00:00Z"),
        utc("2026-07-30T00:00:00Z"),
    )


def test_fake_factory_rejects_unlocked_backend_or_random_stream_manifest(
    fake_manifest: SimulationExecutionManifest,
) -> None:
    """Factory execution must use exactly the Fake provenance locked by preparation."""
    mismatched_backend = ResolvedPluginRecord.create(
        component_id="science-backend",
        kind=PluginKind.SCIENCE_BACKEND,
        ref=PluginRef(
            plugin_id="sycasphere.testing.other",
            implementation_version="0.1.0",
            interface_version=SCHEMA_VERSION,
        ),
        configuration={},
    )
    unexpected_stream = DerivedRandomStream(
        component_id="science-backend",
        purpose="unused-randomness",
        interface_version=SCHEMA_VERSION,
        derived_seed=1,
    )

    for resolved_plugins, random_streams, expected_code in (
        ((), (), "fake_backend.manifest_backend_mismatch"),
        (
            (mismatched_backend,),
            (),
            "fake_backend.manifest_backend_mismatch",
        ),
        (
            fake_manifest.resolved_plugins,
            (unexpected_stream,),
            "fake_backend.random_streams_unsupported",
        ),
    ):
        invalid_manifest = SimulationExecutionManifest.create(
            schema_version=fake_manifest.schema_version,
            source_request=fake_manifest.source_request,
            resolved_plugins=resolved_plugins,
            resolved_external_data=fake_manifest.resolved_external_data,
            derived_random_streams=random_streams,
            prepared_timeline=fake_manifest.prepared_timeline,
        )

        with pytest.raises(SimulationPreparationError) as exc_info:
            FakeScienceBackendFactory().create(invalid_manifest)

        assert exc_info.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE
        assert exc_info.value.detail.code == expected_code


def test_fake_factory_translates_invalid_manifest_integrity_error(
    fake_manifest: SimulationExecutionManifest,
) -> None:
    """Factory translates Core integrity revalidation without leaking Pydantic errors."""
    invalid_manifest = fake_manifest.model_copy(update={"content_hash": "0" * 64})

    with pytest.raises(SimulationPreparationError) as exc_info:
        FakeScienceBackendFactory().create(invalid_manifest)

    assert exc_info.value.detail.category is ErrorCategory.VALIDATION_ERROR
    assert exc_info.value.detail.code == "fake_backend.manifest_invalid"
    assert exc_info.value.detail.message == "FakeBackend manifest failed integrity validation"
    assert exc_info.value.detail.component_ref == "sycasphere.engine.testing.fake_backend"
    assert exc_info.value.detail.context == {"validation_stage": "manifest_integrity"}


def test_fake_validator_accepts_exact_request_and_ground_station_without_truth(
    fake_request_factory: Callable[..., SimulationRunRequest],
) -> None:
    """A ground station is valid scene context but has no propagated state requirement."""
    request = fake_request_factory(
        entities=(fake_ground_station(), fake_spacecraft()),
    )

    FakeBackendConfigurationValidator().validate(request)
    runtime = FakeScienceBackendFactory().create(make_fake_manifest(request))
    runtime.initialize()

    assert tuple(state.entity_id for state in runtime.snapshot_truth()) == ("spacecraft-1",)
    assert len(runtime.snapshot_attitudes()) == 1


@pytest.mark.parametrize(
    ("request_update", "expected_code"),
    [
        (
            {
                "backend": ScienceBackendBinding(
                    ref=FAKE_PLUGIN_MANIFEST.ref,
                    configuration={"unsupported": True},
                )
            },
            "fake_backend.configuration_unsupported",
        ),
        (
            {"observation_schedules": (object(),)},
            "fake_backend.observations_unsupported",
        ),
        (
            {"link_models": (fake_model("sycasphere.testing.link"),)},
            "fake_backend.link_models_unsupported",
        ),
    ],
)
def test_fake_validator_rejects_unsupported_backend_and_run_configuration(
    fake_request: SimulationRunRequest,
    request_update: dict[str, object],
    expected_code: str,
) -> None:
    """Unsupported backend, observation, and link settings fail with stable details."""
    request = fake_request.model_copy(update=request_update)

    with pytest.raises(SimulationPreparationError) as exc_info:
        FakeBackendConfigurationValidator().validate(request)

    assert exc_info.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE
    assert exc_info.value.detail.code == expected_code


@pytest.mark.parametrize(
    ("field_name", "model_id", "expected_code"),
    [
        ("dynamics_model", "unknown.dynamics", "fake_backend.dynamics_model_unsupported"),
        ("attitude_model", "unknown.attitude", "fake_backend.attitude_model_unsupported"),
    ],
)
def test_fake_validator_rejects_unknown_entity_model_ids(
    fake_request: SimulationRunRequest,
    field_name: str,
    model_id: str,
    expected_code: str,
) -> None:
    """Every propagated entity must select the exact explicit Fake model IDs."""
    spacecraft = fake_request.simulation_definition.entities[0]
    assert isinstance(spacecraft, SpacecraftDefinition)
    invalid_spacecraft = spacecraft.model_copy(update={field_name: fake_model(model_id)})
    invalid_definition = fake_request.simulation_definition.model_copy(
        update={"entities": (invalid_spacecraft,)}
    )
    request = fake_request.model_copy(update={"simulation_definition": invalid_definition})

    with pytest.raises(SimulationPreparationError) as exc_info:
        FakeBackendConfigurationValidator().validate(request)

    assert exc_info.value.detail.code == expected_code


def test_fake_validator_rejects_unknown_propulsion_id_and_nonempty_model_config(
    fake_request: SimulationRunRequest,
) -> None:
    """The validator rejects propulsion identity and all owned model configuration."""
    spacecraft = fake_request.simulation_definition.entities[0]
    assert isinstance(spacecraft, SpacecraftDefinition)
    bad_propulsion = spacecraft.model_copy(
        update={
            "maneuver_capability": ManeuverCapability(
                supported_types=frozenset({ManeuverType.IMPULSIVE}),
                propulsion_model=fake_model("unknown.propulsion"),
            )
        }
    )
    configured_dynamics = spacecraft.model_copy(
        update={
            "dynamics_model": fake_model(
                FAKE_DYNAMICS_ID,
                {"unsupported": True},
            )
        }
    )

    for candidate, code in (
        (bad_propulsion, "fake_backend.propulsion_model_unsupported"),
        (configured_dynamics, "fake_backend.model_configuration_unsupported"),
    ):
        request = fake_request.model_copy(
            update={
                "simulation_definition": fake_request.simulation_definition.model_copy(
                    update={"entities": (candidate,)}
                )
            }
        )
        with pytest.raises(SimulationPreparationError) as exc_info:
            FakeBackendConfigurationValidator().validate(request)
        assert exc_info.value.detail.code == code


def test_fake_validator_rejects_environment_models_and_external_data(
    fake_request: SimulationRunRequest,
) -> None:
    """Fake propagation is isolated from all environment and external-data inputs."""
    environment = fake_request.simulation_definition.environment
    for update, code in (
        (
            {"model_refs": (fake_model("sycasphere.testing.environment"),)},
            "fake_backend.environment_models_unsupported",
        ),
        (
            {
                "external_data_refs": (
                    ExternalDataRef(
                        data_id="leap-seconds",
                        version="2026",
                        sha256="a" * 64,
                    ),
                )
            },
            "fake_backend.external_data_unsupported",
        ),
    ):
        invalid_environment = EnvironmentDefinition.model_validate(
            environment.model_copy(update=update).model_dump(mode="python")
        )
        request = fake_request.model_copy(
            update={
                "simulation_definition": fake_request.simulation_definition.model_copy(
                    update={"environment": invalid_environment}
                )
            }
        )
        with pytest.raises(SimulationPreparationError) as exc_info:
            FakeBackendConfigurationValidator().validate(request)
        assert exc_info.value.detail.code == code


def test_fake_validator_rejects_non_j2000_frames_and_unsupported_outputs(
    fake_request: SimulationRunRequest,
) -> None:
    """FakeBackend cannot transform frames or emit products outside Truth/Attitude."""
    spacecraft = fake_request.simulation_definition.entities[0]
    assert isinstance(spacecraft, SpacecraftDefinition)
    non_j2000_state = CartesianState(
        epoch=spacecraft.initial_state.epoch,
        frame=FrameRef(
            kind=FrameKind.EARTH_FIXED,
            earth_fixed=EarthFixedFrameSpec(
                itrf_realization="ITRF2020",
                iers_conventions="IERS_2010",
                eop_data_id="fake-eop",
            ),
        ),
        position_m=spacecraft.initial_state.position_m,
        velocity_mps=spacecraft.initial_state.velocity_mps,
    )
    request_with_frame = fake_request.model_copy(
        update={
            "simulation_definition": fake_request.simulation_definition.model_copy(
                update={
                    "entities": (spacecraft.model_copy(update={"initial_state": non_j2000_state}),)
                }
            )
        }
    )
    request_with_output = fake_request.model_copy(
        update={
            "output_sampling": OutputSampling(
                rules=(
                    *fake_request.output_sampling.rules,
                    SamplingRule(
                        product=OutputProduct.DERIVED_GEOMETRY,
                        interval_s=10.0,
                    ),
                )
            ),
            "output_requirements": frozenset(
                {*fake_request.output_requirements, OutputRequirement.GEOMETRY}
            ),
        }
    )

    for request, code, category in (
        (
            request_with_frame,
            "fake_backend.frame_unsupported",
            ErrorCategory.UNSUPPORTED_FRAME,
        ),
        (
            request_with_output,
            "fake_backend.output_unsupported",
            ErrorCategory.PLUGIN_INCOMPATIBLE,
        ),
    ):
        with pytest.raises(SimulationPreparationError) as exc_info:
            FakeBackendConfigurationValidator().validate(request)
        assert exc_info.value.detail.code == code
        assert exc_info.value.detail.category is category


@pytest.mark.parametrize(
    "epoch",
    [
        Epoch(value="2026-07-30T00:00:00", time_scale=TimeScale.TAI),
        Epoch(value="2016-12-31T23:59:60Z", time_scale=TimeScale.UTC),
    ],
)
def test_fake_validator_rejects_mixed_scales_and_leap_seconds(
    fake_request: SimulationRunRequest,
    epoch: Epoch,
) -> None:
    """Task 4 same-scale time semantics reject conversion and UTC leap seconds."""
    request = fake_request.model_copy(
        update={
            "time_range": fake_request.time_range.model_copy(update={"end": epoch}),
        }
    )

    with pytest.raises(SimulationPreparationError) as exc_info:
        FakeBackendConfigurationValidator().validate(request)

    assert exc_info.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE


# =============================👐Seperate👐=============================
# Deterministic state, attitude, and cancellation
# =============================👐Seperate👐=============================


def test_fake_backend_propagates_constant_velocity_and_identity_attitude(
    fake_manifest: SimulationExecutionManifest,
) -> None:
    """Ten SI seconds produce exact straight-line J2000 state and identity attitude."""
    runtime = FakeScienceBackendFactory().create(fake_manifest)
    runtime.initialize()
    outcome = runtime.propagate_to(utc("2026-07-30T00:00:10Z"), CancellationToken())
    truth = runtime.snapshot_truth()[0]
    attitude = runtime.snapshot_attitudes()[0]

    assert outcome is PropagationOutcome.REACHED_TARGET
    assert truth.cartesian_state.position_m == (7_000_000.0, 75_000.0, 0.0)
    assert truth.cartesian_state.velocity_mps == (0.0, 7_500.0, 0.0)
    assert truth.mass_kg == 500.0
    assert attitude.rotation_reference_to_body_wxyz == (1.0, 0.0, 0.0, 0.0)
    assert attitude.angular_velocity_body_wrt_reference_rad_s == (0.0, 0.0, 0.0)


def test_fake_backend_sorts_outputs_and_repeated_fresh_runtimes_match(
    fake_request_factory: Callable[..., SimulationRunRequest],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manifest order cannot affect stable output order or fresh-run determinism."""
    request = fake_request_factory(
        entities=(
            fake_spacecraft(entity_id="spacecraft-z", position_m=(2.0, 0.0, 0.0)),
            fake_spacecraft(entity_id="spacecraft-a", position_m=(1.0, 0.0, 0.0)),
        )
    )
    manifest = make_fake_manifest(request)
    attitude_entity_order: list[str] = []
    original_attitude_snapshot = fake_backend_module._attitude_snapshot

    def record_attitude_entity(
        state: fake_backend_module._EntityRuntimeState,
    ) -> AttitudeState:
        """Record the entity identity while preserving real snapshot behavior."""
        attitude_entity_order.append(state.entity_id)
        return original_attitude_snapshot(state)

    monkeypatch.setattr(
        fake_backend_module,
        "_attitude_snapshot",
        record_attitude_entity,
    )
    results = []
    for _ in range(2):
        runtime = FakeScienceBackendFactory().create(manifest)
        runtime.initialize()
        runtime.propagate_to(utc("2026-07-30T00:00:10Z"), CancellationToken())
        results.append(
            (
                runtime.snapshot_truth(),
                runtime.snapshot_attitudes(),
            )
        )

    assert tuple(state.entity_id for state in results[0][0]) == (
        "spacecraft-a",
        "spacecraft-z",
    )
    assert attitude_entity_order == [
        "spacecraft-a",
        "spacecraft-z",
        "spacecraft-a",
        "spacecraft-z",
    ]
    assert results[0] == results[1]


class CancelOnSecondProbe:
    """Request cancellation after the runtime has calculated but before it commits."""

    def __init__(self) -> None:
        self.reads = 0

    @property
    def is_cancelled(self) -> bool:
        """Return false once and true on all subsequent reads."""
        self.reads += 1
        return self.reads >= 2


def test_fake_backend_cancellation_does_not_partially_advance_entities(
    fake_request_factory: Callable[..., SimulationRunRequest],
) -> None:
    """A cancelled multi-entity propagation leaves one synchronized safe epoch."""
    request = fake_request_factory(
        entities=(
            fake_spacecraft(entity_id="spacecraft-z"),
            fake_spacecraft(entity_id="spacecraft-a"),
        )
    )
    runtime = FakeScienceBackendFactory().create(make_fake_manifest(request))
    runtime.initialize()
    before = runtime.snapshot_truth()

    outcome = runtime.propagate_to(
        utc("2026-07-30T00:00:10Z"),
        CancelOnSecondProbe(),
    )

    assert outcome is PropagationOutcome.CANCELLED
    assert runtime.current_epoch == utc("2026-07-30T00:00:00Z")
    assert runtime.snapshot_truth() == before


def test_fake_snapshots_do_not_expose_mutable_runtime_arrays(
    fake_manifest: SimulationExecutionManifest,
) -> None:
    """Every snapshot rebuilds independent frozen Core models and copied array views."""
    runtime = FakeScienceBackendFactory().create(fake_manifest)
    runtime.initialize()
    first = runtime.snapshot_truth()[0]
    mutable_position = first.cartesian_state.position_array()
    mutable_position[0] = -1.0
    second = runtime.snapshot_truth()[0]

    assert first is not second
    assert first.cartesian_state is not second.cartesian_state
    assert second.cartesian_state.position_m == (7_000_000.0, 0.0, 0.0)


# =============================👐Seperate👐=============================
# Exact impulsive maneuver and runtime lifecycle
# =============================👐Seperate👐=============================


def test_fake_backend_executes_j2000_impulse_without_changing_position_or_mass(
    fake_manifest: SimulationExecutionManifest,
) -> None:
    """An exact-current-epoch impulse returns independent frozen before/after snapshots."""
    runtime = FakeScienceBackendFactory().create(fake_manifest)
    runtime.initialize()

    execution = runtime.execute_impulsive_maneuver(prepared_impulse())

    assert execution.executed_epoch == runtime.current_epoch
    assert execution.actual_delta_v_j2000_mps == (1.0, -2.0, 0.5)
    assert execution.state_before.entity_id == execution.state_after.entity_id
    assert execution.state_before.epoch == execution.state_after.epoch
    assert (
        execution.state_before.cartesian_state.position_m
        == execution.state_after.cartesian_state.position_m
    )
    assert execution.state_before.cartesian_state.velocity_mps == (0.0, 7_500.0, 0.0)
    assert execution.state_after.cartesian_state.velocity_mps == (1.0, 7_498.0, 0.5)
    assert execution.state_before.mass_kg == execution.state_after.mass_kg == 500.0
    assert execution.state_before is not execution.state_after
    assert execution.state_before.cartesian_state is not execution.state_after.cartesian_state
    with pytest.raises(ValidationError):
        execution.state_after.mass_kg = 499.0


def test_fake_backend_maneuver_state_is_isolated_per_entity(
    fake_request_factory: Callable[..., SimulationRunRequest],
) -> None:
    """Maneuvering one spacecraft cannot mutate another entity's numerical arrays."""
    request = fake_request_factory(
        entities=(
            fake_spacecraft(
                entity_id="spacecraft-z",
                position_m=(8_000_000.0, 1.0, 2.0),
                velocity_mps=(3.0, 4.0, 5.0),
                mass_kg=600.0,
            ),
            fake_spacecraft(entity_id="spacecraft-a"),
        )
    )
    runtime = FakeScienceBackendFactory().create(make_fake_manifest(request))
    runtime.initialize()
    before_by_id = {state.entity_id: state for state in runtime.snapshot_truth()}

    runtime.execute_impulsive_maneuver(prepared_impulse(spacecraft_id="spacecraft-a"))
    after_by_id = {state.entity_id: state for state in runtime.snapshot_truth()}

    assert after_by_id["spacecraft-z"] == before_by_id["spacecraft-z"]
    assert after_by_id["spacecraft-a"].cartesian_state.velocity_mps == (1.0, 7_498.0, 0.5)
    assert runtime.current_epoch == before_by_id["spacecraft-z"].epoch


@pytest.mark.parametrize(
    ("entry", "expected_code"),
    [
        (
            prepared_impulse(
                maneuver=FiniteBurnManeuverSpec(
                    duration_s=1.0,
                    thrust_n=(1.0, 0.0, 0.0),
                    frame=FrameRef(kind=FrameKind.J2000),
                )
            ),
            "fake_backend.finite_burn_unsupported",
        ),
        (
            prepared_impulse(
                maneuver=fake_impulse(
                    frame=FrameRef(
                        kind=FrameKind.BODY,
                        owner_id="spacecraft-1",
                        convention="BODY_RH",
                        reference_epoch=utc("2026-07-30T00:00:00Z"),
                    )
                )
            ),
            "fake_backend.maneuver_frame_unsupported",
        ),
        (
            prepared_impulse(spacecraft_id="unknown-spacecraft"),
            "fake_backend.maneuver_entity_unknown",
        ),
    ],
)
def test_fake_backend_rejects_unsupported_or_mismatched_maneuvers(
    fake_manifest: SimulationExecutionManifest,
    entry: PreparedManeuverEntry,
    expected_code: str,
) -> None:
    """Direct runtime use cannot bypass finite/frame/entity/epoch constraints."""
    runtime = FakeScienceBackendFactory().create(fake_manifest)
    runtime.initialize()

    with pytest.raises(SimulationExecutionError) as exc_info:
        runtime.execute_impulsive_maneuver(entry)

    assert exc_info.value.detail.code == expected_code


@pytest.mark.parametrize(
    ("entry_epoch", "expected_category", "expected_code", "expected_context"),
    [
        (
            utc("2026-07-30T00:00:01Z"),
            ErrorCategory.OUT_OF_ORDER,
            "fake_backend.maneuver_epoch_mismatch",
            {
                "entry_epoch": {
                    "value": "2026-07-30T00:00:01Z",
                    "time_scale": "UTC",
                },
                "current_epoch": {
                    "value": "2026-07-30T00:00:00Z",
                    "time_scale": "UTC",
                },
            },
        ),
        (
            Epoch(
                value="2026-07-30T00:00:00",
                time_scale=TimeScale.TAI,
            ),
            ErrorCategory.PLUGIN_INCOMPATIBLE,
            "ENGINE_TIME_SCALE_MISMATCH",
            {"left_time_scale": "TAI", "right_time_scale": "UTC"},
        ),
        (
            utc("2016-12-31T23:59:60Z"),
            ErrorCategory.PLUGIN_INCOMPATIBLE,
            "ENGINE_TIME_LEAP_SECOND_UNSUPPORTED",
            {
                "epoch": "2016-12-31T23:59:60Z",
                "time_scale": "UTC",
            },
        ),
    ],
)
def test_fake_backend_rejects_incompatible_or_wrong_maneuver_epoch_without_mutation(
    fake_manifest: SimulationExecutionManifest,
    entry_epoch: Epoch,
    expected_category: ErrorCategory,
    expected_code: str,
    expected_context: dict[str, object],
) -> None:
    """Time incompatibility stays distinct from valid same-scale out-of-order input."""
    runtime = FakeScienceBackendFactory().create(fake_manifest)
    runtime.initialize()
    before = runtime.snapshot_truth()
    before_epoch = runtime.current_epoch

    with pytest.raises(SimulationExecutionError) as exc_info:
        runtime.execute_impulsive_maneuver(prepared_impulse(epoch=entry_epoch))

    assert exc_info.value.detail.category is expected_category
    assert exc_info.value.detail.code == expected_code
    assert exc_info.value.detail.context == expected_context
    assert runtime.snapshot_truth() == before
    assert runtime.current_epoch == before_epoch


def test_fake_backend_lifecycle_requires_one_initialize_and_open_operations(
    fake_manifest: SimulationExecutionManifest,
) -> None:
    """Initialize is single-use, operations require OPEN, and close is idempotent."""
    runtime = FakeScienceBackendFactory().create(fake_manifest)

    before_initialize_operations: tuple[Callable[[], object], ...] = (
        lambda: runtime.current_epoch,
        runtime.snapshot_truth,
        runtime.snapshot_attitudes,
        lambda: runtime.propagate_to(
            utc("2026-07-30T00:00:01Z"),
            CancellationToken(),
        ),
        lambda: runtime.execute_impulsive_maneuver(prepared_impulse()),
    )
    for operation in before_initialize_operations:
        with pytest.raises(SimulationExecutionError) as exc_info:
            operation()
        assert exc_info.value.detail.code == "fake_backend.runtime_not_initialized"

    runtime.initialize()
    with pytest.raises(SimulationExecutionError) as exc_info:
        runtime.initialize()
    assert exc_info.value.detail.code == "fake_backend.runtime_already_initialized"

    runtime.close()
    runtime.close()
    after_close_operations: tuple[Callable[[], object], ...] = (
        lambda: runtime.current_epoch,
        runtime.snapshot_truth,
        runtime.snapshot_attitudes,
        lambda: runtime.propagate_to(
            utc("2026-07-30T00:00:01Z"),
            CancellationToken(),
        ),
        lambda: runtime.execute_impulsive_maneuver(prepared_impulse()),
        runtime.initialize,
    )
    for operation in after_close_operations:
        with pytest.raises(SimulationExecutionError) as exc_info:
            operation()
        assert exc_info.value.detail.code == "fake_backend.runtime_closed"


def test_fake_backend_rejects_backward_propagation(
    fake_manifest: SimulationExecutionManifest,
) -> None:
    """The runtime never propagates backward from its synchronized current epoch."""
    runtime = FakeScienceBackendFactory().create(fake_manifest)
    runtime.initialize()
    runtime.propagate_to(utc("2026-07-30T00:00:10Z"), CancellationToken())

    with pytest.raises(SimulationExecutionError) as exc_info:
        runtime.propagate_to(utc("2026-07-30T00:00:09Z"), CancellationToken())

    assert exc_info.value.detail.category is ErrorCategory.OUT_OF_ORDER
    assert exc_info.value.detail.code == "fake_backend.propagation_backward"
