# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : execution.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-31
版本号    : v1.1.0

■ 用途说明:
  执行后端中立、同步阻塞且可协作取消的批量 Truth 仿真。

■ 主要函数功能:
  - BatchRunner.run: 编排科学后端、事件组、批缓冲和输出生命周期。
  - _OutputBuffers: 有界聚合三种强类型科学输出并统计接收记录。

■ 功能特性:
  ✓ 保证同刻机动组原子执行及机动后采样
  ✓ 保证 runtime 关闭先于 sink 提交
  ✓ 保留首因结构化错误并隔离清理异常
  ✓ 批大小只改变 sink 调用粒度
  ✓ 重验证第三方 runtime 的时刻、科学快照和机动结果

■ 待办事项:
  - 无

■ 更新日志:
  v1.1.0 (2026-07-31): 加固 runtime 输出契约并在提交前验证完成结果。
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field

from sycasphere.core import (
    AttitudeState,
    Epoch,
    ErrorCategory,
    ErrorDetail,
    FrameKind,
    ManeuverTruthSource,
    OtherSpaceObjectDefinition,
    OutputProduct,
    PluginKind,
    ResolvedPluginRecord,
    SimulationExecutionManifest,
    SimulationExecutionResult,
    SimulationExecutionStatus,
    SimulationOutputSummary,
    SpacecraftDefinition,
    TruthManeuver,
    TruthState,
)
from sycasphere.engine.backend import (
    ManeuverExecution,
    PreparationTimeAdapter,
    PropagationOutcome,
    ScienceBackendRegistration,
    ScienceBackendRuntime,
    SimulationOutputSink,
)
from sycasphere.engine.cancellation import CancellationProbe
from sycasphere.engine.errors import (
    SimulationEngineError,
    SimulationExecutionError,
    make_error_detail,
)
from sycasphere.engine.registry import PluginRegistry
from sycasphere.engine.scheduling import iter_event_groups

# =============================👐Seperate👐=============================
# Typed per-run output buffers
# =============================👐Seperate👐=============================

_COMPONENT_REF = "sycasphere.engine.execution"


@dataclass(slots=True)
class _OutputBuffers:
    """Retain at most one configured batch per output channel."""

    batch_size: int
    sink: SimulationOutputSink
    truth_states: list[TruthState] = field(default_factory=list)
    attitude_states: list[AttitudeState] = field(default_factory=list)
    truth_maneuvers: list[TruthManeuver] = field(default_factory=list)
    truth_state_count: int = 0
    attitude_state_count: int = 0
    truth_maneuver_count: int = 0

    def accept_truth_states(self, records: tuple[TruthState, ...]) -> None:
        """Accept Truth records in order and flush each complete bounded batch."""
        for record in records:
            self.truth_states.append(record)
            self.truth_state_count += 1
            if len(self.truth_states) == self.batch_size:
                self._flush_truth_states()

    def accept_attitude_states(self, records: tuple[AttitudeState, ...]) -> None:
        """Accept attitude records in order and flush each complete bounded batch."""
        for record in records:
            self.attitude_states.append(record)
            self.attitude_state_count += 1
            if len(self.attitude_states) == self.batch_size:
                self._flush_attitude_states()

    def accept_truth_maneuver(self, record: TruthManeuver) -> None:
        """Accept one maneuver fact and flush a complete bounded batch."""
        self.truth_maneuvers.append(record)
        self.truth_maneuver_count += 1
        if len(self.truth_maneuvers) == self.batch_size:
            self._flush_truth_maneuvers()

    def flush_remaining(self, cancellation: CancellationProbe) -> bool:
        """Flush residual channels in order, checking cancellation before each write."""
        pending_flushes = (
            (self.truth_states, self._flush_truth_states),
            (self.attitude_states, self._flush_attitude_states),
            (self.truth_maneuvers, self._flush_truth_maneuvers),
        )
        for records, flush in pending_flushes:
            if not records:
                continue
            if cancellation.is_cancelled:
                return False
            flush()
        return True

    def summary(self) -> SimulationOutputSummary:
        """Return counts recorded when outputs entered their typed buffers."""
        return SimulationOutputSummary(
            truth_state_count=self.truth_state_count,
            attitude_state_count=self.attitude_state_count,
            truth_maneuver_count=self.truth_maneuver_count,
        )

    def _flush_truth_states(self) -> None:
        """Write and clear one nonempty immutable Truth batch."""
        if not self.truth_states:
            return
        batch = tuple(self.truth_states)
        self.sink.write_truth_states(batch)
        self.truth_states.clear()

    def _flush_attitude_states(self) -> None:
        """Write and clear one nonempty immutable attitude batch."""
        if not self.attitude_states:
            return
        batch = tuple(self.attitude_states)
        self.sink.write_attitude_states(batch)
        self.attitude_states.clear()

    def _flush_truth_maneuvers(self) -> None:
        """Write and clear one nonempty immutable maneuver batch."""
        if not self.truth_maneuvers:
            return
        batch = tuple(self.truth_maneuvers)
        self.sink.write_truth_maneuvers(batch)
        self.truth_maneuvers.clear()


# =============================👐Seperate👐=============================
# Structured execution results and errors
# =============================👐Seperate👐=============================


def _cancelled_detail() -> ErrorDetail:
    """Build the stable public detail used by every normal cancellation path."""
    return make_error_detail(
        category=ErrorCategory.CANCELLED,
        code="engine.execution.cancelled",
        message="Simulation execution was cancelled.",
        component_ref=_COMPONENT_REF,
    )


def _unknown_execution_detail() -> ErrorDetail:
    """Convert an unknown implementation failure without exposing its payload."""
    return make_error_detail(
        category=ErrorCategory.INTERNAL_ERROR,
        code="engine.execution.internal_error",
        message="Simulation execution failed.",
        component_ref=_COMPONENT_REF,
    )


def _causal_detail(error: Exception) -> ErrorDetail:
    """Preserve an Engine detail or sanitize every other exception."""
    if isinstance(error, SimulationEngineError):
        return error.detail
    return _unknown_execution_detail()


def _result(
    manifest: SimulationExecutionManifest,
    *,
    status: SimulationExecutionStatus,
    final_epoch: Epoch,
    summary: SimulationOutputSummary,
    detail: ErrorDetail | None = None,
) -> SimulationExecutionResult:
    """Construct one immutable completed or cancelled result."""
    return SimulationExecutionResult(
        manifest_content_hash=manifest.content_hash,
        status=status,
        final_epoch=final_epoch,
        output_summary=summary,
        termination_detail=detail,
    )


def _validated_manifest(
    manifest: SimulationExecutionManifest,
) -> SimulationExecutionManifest:
    """Snapshot and revalidate the complete immutable run boundary."""
    try:
        return SimulationExecutionManifest.model_validate(manifest.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as error:
        del error
        raise SimulationExecutionError(
            make_error_detail(
                category=ErrorCategory.VALIDATION_ERROR,
                code="engine.execution.manifest_invalid",
                message="Simulation execution manifest failed integrity validation.",
                component_ref=_COMPONENT_REF,
                context={"validation_stage": "execution_manifest"},
            )
        ) from None


def _validate_backend_provenance(
    manifest: SimulationExecutionManifest,
    registration: ScienceBackendRegistration,
) -> None:
    """Require the resolved science-backend record to match source and registry binding."""
    source_binding = manifest.source_request.backend
    expected = ResolvedPluginRecord.create(
        component_id="science-backend",
        kind=PluginKind.SCIENCE_BACKEND,
        ref=registration.manifest.ref,
        configuration=source_binding.configuration,
    )
    actual = next(
        (
            record
            for record in manifest.resolved_plugins
            if record.component_id == "science-backend"
        ),
        None,
    )
    mismatch: str | None = None
    if actual is None:
        mismatch = "missing"
    elif actual.ref != expected.ref:
        mismatch = "ref"
    elif actual.kind is not expected.kind:
        mismatch = "kind"
    elif actual.configuration_hash != expected.configuration_hash:
        mismatch = "configuration"
    if mismatch is None:
        return
    raise SimulationExecutionError(
        make_error_detail(
            category=ErrorCategory.PLUGIN_INCOMPATIBLE,
            code="engine.execution.backend_provenance_mismatch",
            message="Resolved science backend provenance does not match the source binding.",
            component_ref=_COMPONENT_REF,
            context={
                "mismatch": mismatch,
                "expected_backend": expected.model_dump(mode="json"),
                "actual_backend": (None if actual is None else actual.model_dump(mode="json")),
            },
        )
    )


# =============================👐Seperate👐=============================
# Stateless synchronous batch runner
# =============================👐Seperate👐=============================


def _runtime_contract_error(
    *,
    code: str,
    message: str,
    validation_stage: str,
) -> SimulationExecutionError:
    """Build one sanitized backend contract violation."""
    return SimulationExecutionError(
        make_error_detail(
            category=ErrorCategory.PLUGIN_INCOMPATIBLE,
            code=code,
            message=message,
            component_ref=_COMPONENT_REF,
            context={"validation_stage": validation_stage},
        )
    )


def _snapshot_runtime_epoch(
    value: object,
    *,
    code: str = "engine.execution.runtime_epoch_invalid",
    validation_stage: str = "runtime_epoch",
) -> Epoch:
    """Require an exact Core Epoch and revalidate a detached snapshot."""
    try:
        if type(value) is not Epoch:
            raise TypeError
        return Epoch.model_validate(value.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError):
        raise _runtime_contract_error(
            code=code,
            message="Science backend returned an invalid runtime epoch.",
            validation_stage=validation_stage,
        ) from None


def _same_instant_or_error(
    adapter: PreparationTimeAdapter,
    left: Epoch,
    right: Epoch,
    *,
    code: str,
    message: str,
    validation_stage: str,
) -> None:
    """Require two validated epochs to denote the same instant."""
    if adapter.same_instant(left, right):
        return
    raise _runtime_contract_error(
        code=code,
        message=message,
        validation_stage=validation_stage,
    )


def _space_object_ids(manifest: SimulationExecutionManifest) -> tuple[str, ...]:
    """Return the stable propagated identity set every truth snapshot must describe."""
    return tuple(
        sorted(
            entity.id
            for entity in manifest.source_request.simulation_definition.entities
            if isinstance(entity, (SpacecraftDefinition, OtherSpaceObjectDefinition))
        )
    )


def _truth_snapshot_error() -> SimulationExecutionError:
    """Build the stable Truth boundary violation."""
    return _runtime_contract_error(
        code="engine.execution.truth_snapshot_invalid",
        message="Science backend returned an invalid Truth snapshot.",
        validation_stage="truth_snapshot",
    )


def _snapshot_truth_states(
    value: object,
    *,
    expected_epoch: Epoch,
    expected_entity_ids: tuple[str, ...],
    adapter: PreparationTimeAdapter,
) -> tuple[TruthState, ...]:
    """Revalidate one exact, complete, stable-order J2000 Truth snapshot."""
    try:
        if type(value) is not tuple:
            raise TypeError
        if any(type(record) is not TruthState for record in value):
            raise TypeError
        records = tuple(
            TruthState.model_validate(record.model_dump(mode="python")) for record in value
        )
    except (AttributeError, TypeError, ValueError):
        raise _truth_snapshot_error() from None

    if tuple(record.entity_id for record in records) != expected_entity_ids:
        raise _truth_snapshot_error()
    if any(record.cartesian_state.frame.kind is not FrameKind.J2000 for record in records):
        raise _truth_snapshot_error()
    if any(not adapter.same_instant(record.epoch, expected_epoch) for record in records):
        raise _truth_snapshot_error()
    return records


def _attitude_snapshot_error() -> SimulationExecutionError:
    """Build the stable attitude boundary violation."""
    return _runtime_contract_error(
        code="engine.execution.attitude_snapshot_invalid",
        message="Science backend returned an invalid attitude snapshot.",
        validation_stage="attitude_snapshot",
    )


def _snapshot_attitude_states(
    value: object,
    *,
    expected_epoch: Epoch,
    expected_count: int,
    adapter: PreparationTimeAdapter,
) -> tuple[AttitudeState, ...]:
    """Revalidate one exact, complete J2000 attitude snapshot."""
    try:
        if type(value) is not tuple:
            raise TypeError
        if any(type(record) is not AttitudeState for record in value):
            raise TypeError
        records = tuple(
            AttitudeState.model_validate(record.model_dump(mode="python")) for record in value
        )
    except (AttributeError, TypeError, ValueError):
        raise _attitude_snapshot_error() from None

    if len(records) != expected_count:
        raise _attitude_snapshot_error()
    if any(record.reference_frame.kind is not FrameKind.J2000 for record in records):
        raise _attitude_snapshot_error()
    if any(not adapter.same_instant(record.epoch, expected_epoch) for record in records):
        raise _attitude_snapshot_error()
    return records


def _maneuver_execution_error() -> SimulationExecutionError:
    """Build the stable physical maneuver boundary violation."""
    return _runtime_contract_error(
        code="engine.execution.maneuver_execution_invalid",
        message="Science backend returned an invalid maneuver execution.",
        validation_stage="maneuver_execution",
    )


def _snapshot_maneuver_execution(
    value: object,
    *,
    expected_entity_id: str,
    expected_epoch: Epoch,
    adapter: PreparationTimeAdapter,
) -> ManeuverExecution:
    """Rebuild and validate one exact physical maneuver response."""
    try:
        if type(value) is not ManeuverExecution:
            raise TypeError
        if type(value.executed_epoch) is not Epoch:
            raise TypeError
        if type(value.state_before) is not TruthState:
            raise TypeError
        if type(value.state_after) is not TruthState:
            raise TypeError
        executed_epoch = Epoch.model_validate(value.executed_epoch.model_dump(mode="python"))
        state_before = TruthState.model_validate(value.state_before.model_dump(mode="python"))
        state_after = TruthState.model_validate(value.state_after.model_dump(mode="python"))
        physical = ManeuverExecution(
            executed_epoch=executed_epoch,
            actual_delta_v_j2000_mps=value.actual_delta_v_j2000_mps,
            state_before=state_before,
            state_after=state_after,
        )
    except (AttributeError, TypeError, ValueError):
        raise _maneuver_execution_error() from None

    invalid = (
        physical.state_before.entity_id != expected_entity_id
        or physical.state_after.entity_id != expected_entity_id
        or physical.state_before.cartesian_state.frame.kind is not FrameKind.J2000
        or physical.state_after.cartesian_state.frame.kind is not FrameKind.J2000
        or not adapter.same_instant(physical.executed_epoch, expected_epoch)
        or not adapter.same_instant(physical.state_before.epoch, expected_epoch)
        or not adapter.same_instant(physical.state_after.epoch, expected_epoch)
    )
    if invalid:
        raise _maneuver_execution_error()
    return physical


class BatchRunner:
    """Execute independent manifests without retaining mutable scientific run state."""

    __slots__ = ("_batch_size", "_registry")

    def __init__(self, registry: PluginRegistry, *, batch_size: int) -> None:
        """Retain immutable execution dependencies and a strict bounded batch size."""
        if type(batch_size) is not int or batch_size <= 0:
            raise ValueError("batch_size must be a positive built-in int")
        self._registry = registry
        self._batch_size = batch_size

    def run(
        self,
        manifest: SimulationExecutionManifest,
        sink: SimulationOutputSink,
        cancellation: CancellationProbe,
    ) -> SimulationExecutionResult:
        """Run one manifest to completion, normal cancellation, or structured failure."""
        try:
            validated = _validated_manifest(manifest)
            empty_summary = SimulationOutputSummary()
            synchronization_epoch = (
                validated.source_request.simulation_definition.synchronization_epoch
            )
            if cancellation.is_cancelled:
                return _result(
                    validated,
                    status=SimulationExecutionStatus.CANCELLED,
                    final_epoch=synchronization_epoch,
                    summary=empty_summary,
                    detail=_cancelled_detail(),
                )
        except Exception as error:
            raise SimulationExecutionError(_causal_detail(error)) from None

        runtime: ScienceBackendRuntime | None = None
        close_attempted = False
        sink_begun = False
        buffers = _OutputBuffers(batch_size=self._batch_size, sink=sink)

        def close_runtime_once() -> None:
            """Attempt runtime cleanup no more than once."""
            nonlocal close_attempted
            if runtime is None or close_attempted:
                return
            close_attempted = True
            runtime.close()

        def cancel_active(final_epoch: Epoch) -> SimulationExecutionResult:
            """Best-effort clean active resources and preserve cancellation as the cause."""
            detail = _cancelled_detail()
            with suppress(Exception):
                close_runtime_once()
            if sink_begun:
                with suppress(Exception):
                    sink.abort(detail)
            return _result(
                validated,
                status=SimulationExecutionStatus.CANCELLED,
                final_epoch=final_epoch,
                summary=empty_summary,
                detail=detail,
            )

        try:
            ## -------------- step: resolve and initialize one isolated runtime ---------
            registration = self._registry.resolve(validated.source_request.backend.ref)
            _validate_backend_provenance(validated, registration)
            time_adapter = registration.time_adapter
            expected_entity_ids = _space_object_ids(validated)
            runtime = registration.factory.create(validated)
            runtime.initialize()
            initialized_epoch = _snapshot_runtime_epoch(runtime.current_epoch)
            _same_instant_or_error(
                time_adapter,
                initialized_epoch,
                synchronization_epoch,
                code="engine.execution.runtime_epoch_invalid",
                message="Science backend initialized at an invalid epoch.",
                validation_stage="initialized_epoch",
            )
            if cancellation.is_cancelled:
                return cancel_active(initialized_epoch)

            ## -------------- step: begin output only after successful initialization ---------
            sink.begin(validated)
            sink_begun = True

            ## -------------- step: execute each same-epoch group as one atomic boundary ---------
            for group in iter_event_groups(validated, registration.time_adapter):
                if cancellation.is_cancelled:
                    return cancel_active(_snapshot_runtime_epoch(runtime.current_epoch))
                previous_epoch = _snapshot_runtime_epoch(runtime.current_epoch)
                outcome = runtime.propagate_to(group.epoch, cancellation)
                if type(outcome) is not PropagationOutcome:
                    raise _runtime_contract_error(
                        code="engine.execution.propagation_outcome_invalid",
                        message="Science backend returned an invalid propagation outcome.",
                        validation_stage="propagation_outcome",
                    )
                reached_epoch = _snapshot_runtime_epoch(runtime.current_epoch)
                if outcome is PropagationOutcome.REACHED_TARGET:
                    _same_instant_or_error(
                        time_adapter,
                        reached_epoch,
                        group.epoch,
                        code="engine.execution.propagation_epoch_invalid",
                        message="Science backend did not reach the requested propagation epoch.",
                        validation_stage="propagation_epoch",
                    )
                else:
                    if (
                        time_adapter.compare(reached_epoch, previous_epoch) < 0
                        or time_adapter.compare(reached_epoch, group.epoch) > 0
                    ):
                        raise _runtime_contract_error(
                            code="engine.execution.cancellation_epoch_invalid",
                            message="Science backend returned an invalid cancellation safe point.",
                            validation_stage="cancellation_epoch",
                        )
                    return cancel_active(reached_epoch)

                maneuver_records: list[TruthManeuver] = []
                previous_state_after: TruthState | None = None
                for entry in group.maneuvers:
                    physical = _snapshot_maneuver_execution(
                        runtime.execute_impulsive_maneuver(entry),
                        expected_entity_id=entry.spacecraft_id,
                        expected_epoch=group.epoch,
                        adapter=time_adapter,
                    )
                    if (
                        previous_state_after is not None
                        and physical.state_before != previous_state_after
                    ):
                        raise _runtime_contract_error(
                            code="engine.execution.maneuver_chain_invalid",
                            message="Same-epoch maneuver state continuity is invalid.",
                            validation_stage="maneuver_chain",
                        )
                    maneuver_epoch = _snapshot_runtime_epoch(
                        runtime.current_epoch,
                        code="engine.execution.maneuver_runtime_epoch_invalid",
                        validation_stage="maneuver_runtime_epoch",
                    )
                    _same_instant_or_error(
                        time_adapter,
                        maneuver_epoch,
                        group.epoch,
                        code="engine.execution.maneuver_runtime_epoch_invalid",
                        message="Science backend advanced time while executing a maneuver.",
                        validation_stage="maneuver_runtime_epoch",
                    )
                    maneuver_records.append(
                        TruthManeuver(
                            maneuver_event_id=entry.event_id,
                            source_kind=ManeuverTruthSource(entry.source.value),
                            source_id=entry.event_id,
                            entity_id=entry.spacecraft_id,
                            scheduled_epoch=entry.epoch,
                            executed_epoch=physical.executed_epoch,
                            actual_delta_v_j2000_mps=physical.actual_delta_v_j2000_mps,
                            state_before=physical.state_before,
                            state_after=physical.state_after,
                        )
                    )
                    previous_state_after = physical.state_after

                truth_records: tuple[TruthState, ...] | None = None
                attitude_records: tuple[AttitudeState, ...] | None = None
                for product in group.sample_products:
                    if product is OutputProduct.TRUTH_STATE:
                        truth_records = _snapshot_truth_states(
                            runtime.snapshot_truth(),
                            expected_epoch=group.epoch,
                            expected_entity_ids=expected_entity_ids,
                            adapter=time_adapter,
                        )
                    elif product is OutputProduct.ATTITUDE_STATE:
                        attitude_records = _snapshot_attitude_states(
                            runtime.snapshot_attitudes(),
                            expected_epoch=group.epoch,
                            expected_count=len(expected_entity_ids),
                            adapter=time_adapter,
                        )
                for record in maneuver_records:
                    buffers.accept_truth_maneuver(record)
                if truth_records is not None:
                    buffers.accept_truth_states(truth_records)
                if attitude_records is not None:
                    buffers.accept_attitude_states(attitude_records)

                if cancellation.is_cancelled:
                    return cancel_active(_snapshot_runtime_epoch(runtime.current_epoch))

            ## -------------- step: flush, close, recheck cancellation, then commit ---------
            if cancellation.is_cancelled:
                return cancel_active(_snapshot_runtime_epoch(runtime.current_epoch))
            if not buffers.flush_remaining(cancellation):
                return cancel_active(_snapshot_runtime_epoch(runtime.current_epoch))
            if cancellation.is_cancelled:
                return cancel_active(_snapshot_runtime_epoch(runtime.current_epoch))
            final_epoch = _snapshot_runtime_epoch(
                runtime.current_epoch,
                code="engine.execution.final_epoch_invalid",
                validation_stage="final_epoch",
            )
            _same_instant_or_error(
                time_adapter,
                final_epoch,
                validated.source_request.time_range.end,
                code="engine.execution.final_epoch_invalid",
                message="Science backend completed at an invalid final epoch.",
                validation_stage="final_epoch",
            )
            close_runtime_once()
            if cancellation.is_cancelled:
                return cancel_active(final_epoch)
            summary = buffers.summary()
            completed_result = _result(
                validated,
                status=SimulationExecutionStatus.COMPLETED,
                final_epoch=final_epoch,
                summary=summary,
            )
            sink.commit(summary)
            return completed_result
        except Exception as error:
            ## -------------- step: preserve the first cause through best-effort cleanup ---------
            detail = _causal_detail(error)
            with suppress(Exception):
                close_runtime_once()
            if sink_begun:
                with suppress(Exception):
                    sink.abort(detail)
            raise SimulationExecutionError(detail) from None


__all__ = ["BatchRunner"]
