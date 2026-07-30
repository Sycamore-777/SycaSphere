# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : fake_backend.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  提供非科学、确定性的 Engine 科学后端兼容性实现。

■ 主要函数功能:
  - FakeBackendConfigurationValidator: 校验 FakeBackend 拥有的请求配置。
  - FakeScienceBackendFactory: 为每个 Manifest 创建隔离运行时。

■ 功能特性:
  ✓ 发布稳定的测试插件清单
  ✓ 使用每次运行私有的 NumPy float64 数组执行匀速传播
  ✓ 生成 J2000 Truth、WXYZ 单位姿态和质量不变脉冲快照
  ✓ 保持 Engine/Core 边界不依赖 Orekit、JPype 或 Java

■ 待办事项:
  - [ ] 无

■ 更新日志:
  v1.0.0 (2026-07-30): 实现 FakeBackend 配置校验和确定性单次运行时

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn

import numpy as np
from numpy.typing import NDArray
from pydantic import ValidationError
from sycasphere.core import (
    AttitudeState,
    CartesianState,
    Epoch,
    ErrorCategory,
    FiniteBurnManeuverSpec,
    FrameKind,
    FrameRef,
    GroundStationDefinition,
    ImpulsiveManeuverSpec,
    ManeuverCommand,
    ManeuverType,
    ModelRef,
    OtherSpaceObjectDefinition,
    OutputProduct,
    OutputRequirement,
    PlannedTruthManeuver,
    PluginKind,
    PluginManifest,
    PluginRef,
    PreparedManeuverEntry,
    ResolvedPluginRecord,
    ResourceRequirements,
    SchemaVersion,
    SimulationExecutionManifest,
    SimulationRunRequest,
    SpacecraftDefinition,
    TruthState,
)
from sycasphere.engine.backend import (
    ManeuverExecution,
    PropagationOutcome,
    ScienceBackendRegistration,
    ScienceBackendRuntime,
)
from sycasphere.engine.cancellation import CancellationProbe
from sycasphere.engine.errors import (
    SimulationExecutionError,
    SimulationPreparationError,
    make_error_detail,
)
from sycasphere.engine.scheduling import SameScaleCalendarTimeAdapter

# =============================👐Seperate👐=============================
# Stable public FakeBackend identity
# =============================👐Seperate👐=============================
_FAKE_BACKEND_ID = "sycasphere.testing.fake"
_FAKE_DYNAMICS_ID = "sycasphere.testing.constant-velocity"
_FAKE_ATTITUDE_ID = "sycasphere.testing.identity-attitude"
_FAKE_PROPULSION_ID = "sycasphere.testing.impulsive-propulsion"
_FAKE_INTERFACE_VERSION = SchemaVersion(major=1, minor=0)
_COMPONENT_REF = "sycasphere.engine.testing.fake_backend"

FAKE_PLUGIN_MANIFEST = PluginManifest(
    ref=PluginRef(
        plugin_id=_FAKE_BACKEND_ID,
        implementation_version="0.1.0",
        interface_version=_FAKE_INTERFACE_VERSION,
    ),
    kind=PluginKind.SCIENCE_BACKEND,
    capabilities=frozenset(
        {
            "attitude.identity-wxyz",
            "dynamics.constant-velocity",
            "frame.j2000",
            "maneuver.impulsive.j2000",
            "output.attitude",
            "output.truth",
            "time.same-scale",
        }
    ),
    configuration_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    deterministic=True,
    resources=ResourceRequirements(),
)


# =============================👐Seperate👐=============================
# Structured FakeBackend validation and execution errors
# =============================👐Seperate👐=============================
def _raise_preparation(
    code: str,
    message: str,
    *,
    context: dict[str, object] | None = None,
    category: ErrorCategory = ErrorCategory.PLUGIN_INCOMPATIBLE,
) -> NoReturn:
    """Raise one stable preparation error without implementation payloads."""
    raise SimulationPreparationError(
        make_error_detail(
            category=category,
            code=code,
            message=message,
            component_ref=_COMPONENT_REF,
            context={} if context is None else context,
        )
    )


def _raise_execution(
    code: str,
    message: str,
    *,
    context: dict[str, object] | None = None,
    category: ErrorCategory = ErrorCategory.VALIDATION_ERROR,
) -> NoReturn:
    """Raise one stable runtime error without numerical implementation payloads."""
    raise SimulationExecutionError(
        make_error_detail(
            category=category,
            code=code,
            message=message,
            component_ref=_COMPONENT_REF,
            context={} if context is None else context,
        )
    )


def _validate_model_ref(
    model_ref: ModelRef,
    *,
    expected_id: str,
    unsupported_code: str,
    entity_id: str,
) -> None:
    """Require an exact Fake model identity, interface version, and empty configuration."""
    if model_ref.model_id != expected_id or model_ref.interface_version != _FAKE_INTERFACE_VERSION:
        _raise_preparation(
            unsupported_code,
            "FakeBackend does not support the selected scientific model",
            context={
                "entity_id": entity_id,
                "model_id": model_ref.model_id,
                "interface_version": model_ref.interface_version.model_dump(mode="json"),
            },
        )
    if model_ref.configuration:
        _raise_preparation(
            "fake_backend.model_configuration_unsupported",
            "FakeBackend model configuration must be empty",
            context={"entity_id": entity_id, "model_id": model_ref.model_id},
        )


def _request_epochs(request: SimulationRunRequest) -> tuple[Epoch, ...]:
    """Collect every epoch whose same-scale calendar semantics FakeBackend consumes."""
    epochs = [
        request.simulation_definition.synchronization_epoch,
        request.time_range.start,
        request.time_range.end,
    ]
    epochs.extend(
        entity.initial_state.epoch
        for entity in request.simulation_definition.entities
        if isinstance(entity, (SpacecraftDefinition, OtherSpaceObjectDefinition))
    )
    epochs.extend(maneuver.epoch for maneuver in request.simulation_definition.planned_maneuvers)
    epochs.extend(command.epoch for command in request.command_timeline)
    return tuple(epochs)


def _source_event_id(entry: PlannedTruthManeuver | ManeuverCommand) -> str:
    """Return the stable source ID shared by planned and commanded maneuvers."""
    if isinstance(entry, PlannedTruthManeuver):
        return entry.maneuver_id
    return entry.command_id


def _validate_fake_maneuver(
    entry: PlannedTruthManeuver | ManeuverCommand,
    *,
    spacecraft_ids: frozenset[str],
) -> None:
    """Validate a planned or commanded source maneuver before runtime creation."""
    maneuver = entry.maneuver
    if isinstance(maneuver, FiniteBurnManeuverSpec):
        _raise_preparation(
            "fake_backend.finite_burn_unsupported",
            "FakeBackend supports only impulsive maneuvers",
            context={"event_id": _source_event_id(entry)},
        )
    if not isinstance(maneuver, ImpulsiveManeuverSpec):
        _raise_preparation(
            "fake_backend.maneuver_type_unsupported",
            "FakeBackend supports only Core impulsive maneuver specifications",
            context={"event_id": _source_event_id(entry)},
        )
    if maneuver.frame.kind is not FrameKind.J2000:
        _raise_preparation(
            "fake_backend.maneuver_frame_unsupported",
            "FakeBackend impulsive maneuvers must use J2000",
            category=ErrorCategory.UNSUPPORTED_FRAME,
            context={
                "event_id": _source_event_id(entry),
                "frame": maneuver.frame.kind.value,
            },
        )
    if entry.spacecraft_id not in spacecraft_ids:
        _raise_preparation(
            "fake_backend.maneuver_entity_unknown",
            "FakeBackend maneuver target must be a known spacecraft",
            context={"spacecraft_id": entry.spacecraft_id},
        )


# =============================👐Seperate👐=============================
# Public preparation-time configuration validator
# =============================👐Seperate👐=============================
class FakeBackendConfigurationValidator:
    """Validate the exact configuration subset supported by FakeBackend."""

    def validate(self, request: SimulationRunRequest) -> None:
        """Validate one immutable request without creating runtime state."""
        ## -------------- step: require exact backend identity and empty binding ---------
        if request.backend.ref != FAKE_PLUGIN_MANIFEST.ref:
            _raise_preparation(
                "fake_backend.identity_unsupported",
                "request must select the exact FakeBackend implementation",
                context={"plugin_ref": request.backend.ref.model_dump(mode="json")},
            )
        if request.backend.configuration:
            _raise_preparation(
                "fake_backend.configuration_unsupported",
                "FakeBackend configuration must be empty",
            )

        ## -------------- step: reject orchestration inputs outside v0.1 scope ---------
        if request.observation_schedules:
            _raise_preparation(
                "fake_backend.observations_unsupported",
                "FakeBackend does not support observation schedules",
            )
        if request.link_models:
            _raise_preparation(
                "fake_backend.link_models_unsupported",
                "FakeBackend does not support link models",
            )
        environment = request.simulation_definition.environment
        if environment.model_refs:
            _raise_preparation(
                "fake_backend.environment_models_unsupported",
                "FakeBackend environment model references must be empty",
            )
        if environment.external_data_refs:
            _raise_preparation(
                "fake_backend.external_data_unsupported",
                "FakeBackend external data references must be empty",
            )

        ## -------------- step: require only paired Truth and optional attitude output ---------
        allowed_requirements = {
            OutputRequirement.TRUTH,
            OutputRequirement.ATTITUDE,
        }
        if (
            OutputRequirement.TRUTH not in request.output_requirements
            or not request.output_requirements.issubset(allowed_requirements)
        ):
            _raise_preparation(
                "fake_backend.output_unsupported",
                "FakeBackend requires Truth and supports only optional attitude output",
                context={"outputs": sorted(item.value for item in request.output_requirements)},
            )
        sampled_products = {rule.product for rule in request.output_sampling.rules}
        allowed_products = {
            OutputProduct.TRUTH_STATE,
            OutputProduct.ATTITUDE_STATE,
        }
        attitude_requested = OutputRequirement.ATTITUDE in request.output_requirements
        attitude_sampled = OutputProduct.ATTITUDE_STATE in sampled_products
        if (
            OutputProduct.TRUTH_STATE not in sampled_products
            or not sampled_products.issubset(allowed_products)
            or attitude_requested != attitude_sampled
        ):
            _raise_preparation(
                "fake_backend.output_unsupported",
                "FakeBackend sampling must contain Truth and pair attitude product and output",
                context={
                    "products": sorted(item.value for item in sampled_products),
                },
            )

        ## -------------- step: validate exact entity-owned models and J2000 states ---------
        spacecraft_ids: set[str] = set()
        for entity in request.simulation_definition.entities:
            if isinstance(entity, GroundStationDefinition):
                continue
            if not isinstance(entity, (SpacecraftDefinition, OtherSpaceObjectDefinition)):
                _raise_preparation(
                    "fake_backend.entity_unsupported",
                    "FakeBackend encountered an unsupported entity type",
                )
            if entity.initial_state.frame.kind is not FrameKind.J2000:
                _raise_preparation(
                    "fake_backend.frame_unsupported",
                    "FakeBackend space-object states must use J2000",
                    category=ErrorCategory.UNSUPPORTED_FRAME,
                    context={
                        "entity_id": entity.id,
                        "frame": entity.initial_state.frame.kind.value,
                    },
                )
            _validate_model_ref(
                entity.dynamics_model,
                expected_id=_FAKE_DYNAMICS_ID,
                unsupported_code="fake_backend.dynamics_model_unsupported",
                entity_id=entity.id,
            )
            _validate_model_ref(
                entity.attitude_model,
                expected_id=_FAKE_ATTITUDE_ID,
                unsupported_code="fake_backend.attitude_model_unsupported",
                entity_id=entity.id,
            )
            if not isinstance(entity, SpacecraftDefinition):
                continue
            spacecraft_ids.add(entity.id)
            capability = entity.maneuver_capability
            if capability is None:
                continue
            if capability.supported_types != frozenset({ManeuverType.IMPULSIVE}):
                _raise_preparation(
                    "fake_backend.finite_burn_unsupported",
                    "FakeBackend maneuver capability must be impulsive-only",
                    context={"entity_id": entity.id},
                )
            _validate_model_ref(
                capability.propulsion_model,
                expected_id=_FAKE_PROPULSION_ID,
                unsupported_code="fake_backend.propulsion_model_unsupported",
                entity_id=entity.id,
            )

        ## -------------- step: validate all source maneuvers and same-scale epochs ---------
        known_spacecraft_ids = frozenset(spacecraft_ids)
        for maneuver in request.simulation_definition.planned_maneuvers:
            _validate_fake_maneuver(maneuver, spacecraft_ids=known_spacecraft_ids)
        for command in request.command_timeline:
            _validate_fake_maneuver(command, spacecraft_ids=known_spacecraft_ids)

        time_adapter = SameScaleCalendarTimeAdapter()
        reference = request.simulation_definition.synchronization_epoch
        for epoch in _request_epochs(request):
            time_adapter.compare(reference, epoch)


# =============================👐Seperate👐=============================
# Private per-run numerical state and lifecycle
# =============================👐Seperate👐=============================
@dataclass(slots=True)
class _EntityRuntimeState:
    """One runtime-owned mutable state with no array reference exposed publicly."""

    entity_id: str
    position_m: NDArray[np.float64]
    velocity_mps: NDArray[np.float64]
    mass_kg: float
    epoch: Epoch


class _RuntimeLifecycle(StrEnum):
    """Private single-use runtime lifecycle."""

    NEW = "NEW"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


def _vector_tuple(array: NDArray[np.float64]) -> tuple[float, float, float]:
    """Copy one validated numerical vector into a strict built-in-float tuple."""
    return (float(array[0]), float(array[1]), float(array[2]))


def _truth_snapshot(state: _EntityRuntimeState) -> TruthState:
    """Reconstruct one independent immutable Core Truth snapshot."""
    return TruthState(
        entity_id=state.entity_id,
        cartesian_state=CartesianState(
            epoch=state.epoch,
            frame=FrameRef(kind=FrameKind.J2000),
            position_m=_vector_tuple(state.position_m),
            velocity_mps=_vector_tuple(state.velocity_mps),
        ),
        mass_kg=float(state.mass_kg),
    )


def _attitude_snapshot(state: _EntityRuntimeState) -> AttitudeState:
    """Reconstruct the exact identity reference-to-BODY attitude."""
    return AttitudeState(
        epoch=state.epoch,
        reference_frame=FrameRef(kind=FrameKind.J2000),
        rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
        angular_velocity_body_wrt_reference_rad_s=(0.0, 0.0, 0.0),
    )


class _FakeScienceBackendRuntime:
    """Mutable numerical runtime isolated to one immutable manifest snapshot."""

    def __init__(self, manifest: SimulationExecutionManifest) -> None:
        self._manifest = manifest
        self._lifecycle = _RuntimeLifecycle.NEW
        self._states: dict[str, _EntityRuntimeState] = {}
        self._spacecraft_ids = frozenset(
            entity.id
            for entity in manifest.source_request.simulation_definition.entities
            if isinstance(entity, SpacecraftDefinition)
        )
        self._time_adapter = SameScaleCalendarTimeAdapter()

    def _require_open(self) -> None:
        """Reject operations outside the initialized and not-closed state."""
        if self._lifecycle is _RuntimeLifecycle.CLOSED:
            _raise_execution(
                "fake_backend.runtime_closed",
                "FakeBackend runtime is closed",
            )
        if self._lifecycle is not _RuntimeLifecycle.OPEN:
            _raise_execution(
                "fake_backend.runtime_not_initialized",
                "FakeBackend runtime is not initialized",
            )

    @property
    def current_epoch(self) -> Epoch:
        """Return the common synchronized epoch for all propagated entities."""
        self._require_open()
        epochs = {state.epoch for state in self._states.values()}
        if len(epochs) != 1:
            _raise_execution(
                "fake_backend.runtime_unsynchronized",
                "FakeBackend entities do not share one current epoch",
                category=ErrorCategory.INTERNAL_ERROR,
            )
        return next(iter(epochs))

    def initialize(self) -> None:
        """Initialize exactly once from independent arrays in the manifest snapshot."""
        if self._lifecycle is _RuntimeLifecycle.CLOSED:
            _raise_execution(
                "fake_backend.runtime_closed",
                "FakeBackend runtime is closed",
            )
        if self._lifecycle is _RuntimeLifecycle.OPEN:
            _raise_execution(
                "fake_backend.runtime_already_initialized",
                "FakeBackend runtime was already initialized",
            )

        states: dict[str, _EntityRuntimeState] = {}
        for entity in self._manifest.source_request.simulation_definition.entities:
            if not isinstance(entity, (SpacecraftDefinition, OtherSpaceObjectDefinition)):
                continue
            states[entity.id] = _EntityRuntimeState(
                entity_id=entity.id,
                position_m=entity.initial_state.position_array(),
                velocity_mps=entity.initial_state.velocity_array(),
                mass_kg=float(entity.physical_properties.mass_kg),
                epoch=entity.initial_state.epoch,
            )
        self._states = states
        self._lifecycle = _RuntimeLifecycle.OPEN

    def propagate_to(
        self,
        target_epoch: Epoch,
        cancellation: CancellationProbe,
    ) -> PropagationOutcome:
        """Atomically apply constant velocity to every entity or leave all unchanged."""
        self._require_open()
        current_epoch = self.current_epoch
        try:
            order = self._time_adapter.compare(target_epoch, current_epoch)
        except SimulationPreparationError as error:
            raise SimulationExecutionError(error.detail) from None
        if order < 0:
            _raise_execution(
                "fake_backend.propagation_backward",
                "FakeBackend cannot propagate backward",
                category=ErrorCategory.OUT_OF_ORDER,
                context={
                    "current_epoch": current_epoch.model_dump(mode="json"),
                    "target_epoch": target_epoch.model_dump(mode="json"),
                },
            )
        if cancellation.is_cancelled:
            return PropagationOutcome.CANCELLED
        if order == 0:
            return PropagationOutcome.REACHED_TARGET

        try:
            delta_t_s = self._time_adapter.seconds_between(current_epoch, target_epoch)
        except SimulationPreparationError as error:
            raise SimulationExecutionError(error.detail) from None
        candidates = {
            entity_id: state.position_m + state.velocity_mps * np.float64(delta_t_s)
            for entity_id, state in self._states.items()
        }
        if any(
            candidate.shape != (3,)
            or candidate.dtype != np.dtype(np.float64)
            or not bool(np.all(np.isfinite(candidate)))
            for candidate in candidates.values()
        ):
            _raise_execution(
                "fake_backend.propagation_non_finite",
                "FakeBackend propagation produced a non-finite state",
                category=ErrorCategory.NUMERICAL_FAILURE,
            )
        if cancellation.is_cancelled:
            return PropagationOutcome.CANCELLED

        for entity_id, candidate in candidates.items():
            state = self._states[entity_id]
            state.position_m = candidate.copy()
            state.epoch = target_epoch
        return PropagationOutcome.REACHED_TARGET

    def snapshot_truth(self) -> tuple[TruthState, ...]:
        """Return fresh Truth snapshots sorted by stable entity ID."""
        self._require_open()
        return tuple(_truth_snapshot(self._states[entity_id]) for entity_id in sorted(self._states))

    def snapshot_attitudes(self) -> tuple[AttitudeState, ...]:
        """Return fresh identity-attitude snapshots sorted by stable entity ID."""
        self._require_open()
        return tuple(
            _attitude_snapshot(self._states[entity_id]) for entity_id in sorted(self._states)
        )

    def execute_impulsive_maneuver(
        self,
        entry: PreparedManeuverEntry,
    ) -> ManeuverExecution:
        """Apply one exact-current-epoch J2000 impulse without changing mass."""
        self._require_open()
        maneuver = entry.maneuver
        if isinstance(maneuver, FiniteBurnManeuverSpec):
            _raise_execution(
                "fake_backend.finite_burn_unsupported",
                "FakeBackend supports only impulsive maneuvers",
            )
        if not isinstance(maneuver, ImpulsiveManeuverSpec):
            _raise_execution(
                "fake_backend.maneuver_type_unsupported",
                "FakeBackend supports only Core impulsive maneuver specifications",
            )
        if maneuver.frame.kind is not FrameKind.J2000:
            _raise_execution(
                "fake_backend.maneuver_frame_unsupported",
                "FakeBackend impulses must use J2000",
                category=ErrorCategory.UNSUPPORTED_FRAME,
            )
        if entry.spacecraft_id not in self._spacecraft_ids:
            _raise_execution(
                "fake_backend.maneuver_entity_unknown",
                "FakeBackend maneuver target is not a known spacecraft",
                context={"spacecraft_id": entry.spacecraft_id},
            )
        state = self._states[entry.spacecraft_id]
        try:
            same_epoch = self._time_adapter.same_instant(entry.epoch, self.current_epoch)
        except SimulationPreparationError as error:
            raise SimulationExecutionError(error.detail) from None
        if not same_epoch:
            _raise_execution(
                "fake_backend.maneuver_epoch_mismatch",
                "FakeBackend impulse epoch must equal the current epoch",
                category=ErrorCategory.OUT_OF_ORDER,
                context={
                    "entry_epoch": entry.epoch.model_dump(mode="json"),
                    "current_epoch": self.current_epoch.model_dump(mode="json"),
                },
            )

        before = _truth_snapshot(state)
        delta_v = np.asarray(maneuver.delta_v_mps, dtype=np.float64).copy()
        candidate_velocity = state.velocity_mps + delta_v
        if not bool(np.all(np.isfinite(candidate_velocity))):
            _raise_execution(
                "fake_backend.maneuver_non_finite",
                "FakeBackend impulse produced a non-finite velocity",
                category=ErrorCategory.NUMERICAL_FAILURE,
            )
        state.velocity_mps = candidate_velocity.copy()
        after = _truth_snapshot(state)
        return ManeuverExecution(
            executed_epoch=state.epoch,
            actual_delta_v_j2000_mps=_vector_tuple(delta_v),
            state_before=before,
            state_after=after,
        )

    def close(self) -> None:
        """Idempotently release all per-run numerical arrays."""
        if self._lifecycle is _RuntimeLifecycle.CLOSED:
            return
        self._states.clear()
        self._lifecycle = _RuntimeLifecycle.CLOSED


# =============================👐Seperate👐=============================
# Public factory and registration
# =============================👐Seperate👐=============================
class FakeScienceBackendFactory:
    """Create a fresh deterministic FakeBackend runtime for one manifest."""

    def create(self, manifest: SimulationExecutionManifest) -> ScienceBackendRuntime:
        """Create one isolated runtime from an immutable manifest snapshot."""
        try:
            snapshot = SimulationExecutionManifest.model_validate(
                manifest.model_dump(mode="python")
            )
        except ValidationError:
            _raise_preparation(
                "fake_backend.manifest_invalid",
                "FakeBackend manifest failed integrity validation",
                category=ErrorCategory.VALIDATION_ERROR,
                context={"validation_stage": "manifest_integrity"},
            )
        FakeBackendConfigurationValidator().validate(snapshot.source_request)
        expected_backend = ResolvedPluginRecord.create(
            component_id="science-backend",
            kind=PluginKind.SCIENCE_BACKEND,
            ref=FAKE_PLUGIN_MANIFEST.ref,
            configuration={},
        )
        if snapshot.resolved_plugins != (expected_backend,):
            _raise_preparation(
                "fake_backend.manifest_backend_mismatch",
                "FakeBackend manifest must lock exactly its public backend identity",
            )
        if snapshot.resolved_external_data:
            _raise_preparation(
                "fake_backend.external_data_unsupported",
                "FakeBackend manifest external data must be empty",
            )
        if snapshot.derived_random_streams:
            _raise_preparation(
                "fake_backend.random_streams_unsupported",
                "FakeBackend manifest random streams must be empty",
            )
        return _FakeScienceBackendRuntime(snapshot)


def fake_backend_registration() -> ScienceBackendRegistration:
    """Return the complete explicit FakeBackend registration."""
    return ScienceBackendRegistration(
        manifest=FAKE_PLUGIN_MANIFEST,
        configuration_validator=FakeBackendConfigurationValidator(),
        time_adapter=SameScaleCalendarTimeAdapter(),
        factory=FakeScienceBackendFactory(),
    )


__all__ = [
    "FAKE_PLUGIN_MANIFEST",
    "FakeBackendConfigurationValidator",
    "FakeScienceBackendFactory",
    "fake_backend_registration",
]
