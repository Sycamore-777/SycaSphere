# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : execution.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

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

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field

from pydantic import ValidationError
from sycasphere.core import (
    AttitudeState,
    Epoch,
    ErrorCategory,
    ErrorDetail,
    ManeuverTruthSource,
    OutputProduct,
    PluginKind,
    ResolvedPluginRecord,
    SimulationExecutionManifest,
    SimulationExecutionResult,
    SimulationExecutionStatus,
    SimulationOutputSummary,
    TruthManeuver,
    TruthState,
)
from sycasphere.engine.backend import (
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
    except (AttributeError, TypeError, ValueError, ValidationError) as error:
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
            runtime = registration.factory.create(validated)
            runtime.initialize()
            if cancellation.is_cancelled:
                return cancel_active(runtime.current_epoch)

            ## -------------- step: begin output only after successful initialization ---------
            sink.begin(validated)
            sink_begun = True

            ## -------------- step: execute each same-epoch group as one atomic boundary ---------
            for group in iter_event_groups(validated, registration.time_adapter):
                if cancellation.is_cancelled:
                    return cancel_active(runtime.current_epoch)
                outcome = runtime.propagate_to(group.epoch, cancellation)
                if outcome is PropagationOutcome.CANCELLED:
                    return cancel_active(runtime.current_epoch)

                for entry in group.maneuvers:
                    physical = runtime.execute_impulsive_maneuver(entry)
                    buffers.accept_truth_maneuver(
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

                for product in group.sample_products:
                    if product is OutputProduct.TRUTH_STATE:
                        buffers.accept_truth_states(runtime.snapshot_truth())
                    elif product is OutputProduct.ATTITUDE_STATE:
                        buffers.accept_attitude_states(runtime.snapshot_attitudes())

                if cancellation.is_cancelled:
                    return cancel_active(runtime.current_epoch)

            ## -------------- step: flush, close, recheck cancellation, then commit ---------
            if cancellation.is_cancelled:
                return cancel_active(runtime.current_epoch)
            if not buffers.flush_remaining(cancellation):
                return cancel_active(runtime.current_epoch)
            if cancellation.is_cancelled:
                return cancel_active(runtime.current_epoch)
            final_epoch = runtime.current_epoch
            close_runtime_once()
            if cancellation.is_cancelled:
                return cancel_active(final_epoch)
            summary = buffers.summary()
            sink.commit(summary)
            return _result(
                validated,
                status=SimulationExecutionStatus.COMPLETED,
                final_epoch=final_epoch,
                summary=summary,
            )
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
