# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : sinks.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  提供后端中立的仿真输出 sink 生命周期和有界组合实现。

■ 主要函数功能:
  - NullOutputSink: 丢弃科学输出并维护严格生命周期。
  - InMemoryOutputSink: 在统一记录上限内保留不可变输出快照。
  - CompositeOutputSink: 按固定子 sink 顺序转发并清理部分失败。

■ 功能特性:
  ✓ 使用结构化执行错误报告非法状态和资源耗尽。
  ✓ 不提供跨 sink 的分布式原子提交保证。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from enum import StrEnum
from typing import cast

from sycasphere.core import (
    AttitudeState,
    ErrorCategory,
    ErrorDetail,
    SimulationExecutionManifest,
    SimulationOutputSummary,
    TruthManeuver,
    TruthState,
)
from sycasphere.engine.backend import SimulationOutputSink
from sycasphere.engine.errors import (
    SimulationEngineError,
    SimulationExecutionError,
    make_error_detail,
)

# =============================👐Seperate👐=============================
# Sink lifecycle status
# =============================👐Seperate👐=============================


class SinkStatus(StrEnum):
    """Lifecycle state of one single-use output sink."""

    NEW = "NEW"
    WRITING = "WRITING"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"


# =============================👐Seperate👐=============================
# Shared lifecycle and validation
# =============================👐Seperate👐=============================


def _validate_batch[OutputRecord: (TruthState, AttitudeState, TruthManeuver)](
    batch: object,
    expected_type: type[OutputRecord],
    channel: str,
) -> tuple[OutputRecord, ...]:
    """Require a nonempty built-in tuple whose elements have one exact Core type."""
    if (
        type(batch) is not tuple
        or not batch
        or any(type(record) is not expected_type for record in batch)
    ):
        raise SimulationExecutionError(
            make_error_detail(
                category=ErrorCategory.VALIDATION_ERROR,
                code="engine.sink.invalid_batch",
                message=(
                    f"{channel} batch must be a nonempty tuple of exact {expected_type.__name__}"
                ),
                component_ref="engine.output_sink",
                context={"channel": channel, "expected_type": expected_type.__name__},
            )
        )
    return cast(tuple[OutputRecord, ...], batch)


def _cleanup_detail(error: Exception, *, code: str) -> ErrorDetail:
    """Return a structured child failure detail without exposing unknown exceptions."""
    if isinstance(error, SimulationEngineError):
        return error.detail
    return make_error_detail(
        category=ErrorCategory.INTERNAL_ERROR,
        code=code,
        message="composite output sink child operation failed",
        component_ref="engine.composite_output_sink",
    )


class _LifecycleOutputSink:
    """Implement the shared single-use sink state machine."""

    _status: SinkStatus

    def __init__(self) -> None:
        self._status = SinkStatus.NEW

    @property
    def status(self) -> SinkStatus:
        """Return the current lifecycle state."""
        return self._status

    def _raise_invalid_state(self, operation: str) -> None:
        """Raise a stable execution error for a lifecycle transition violation."""
        raise SimulationExecutionError(
            make_error_detail(
                category=ErrorCategory.VALIDATION_ERROR,
                code="engine.sink.invalid_state",
                message=f"{operation} is not allowed in sink state {self._status.value}",
                component_ref="engine.output_sink",
                context={"operation": operation, "status": self._status.value},
            )
        )

    def _require_writing(self, operation: str) -> None:
        """Require the sole state in which output or finalization may occur."""
        if self._status is not SinkStatus.WRITING:
            self._raise_invalid_state(operation)

    def begin(self, manifest: SimulationExecutionManifest) -> None:
        """Begin one lifecycle from NEW."""
        if self._status is not SinkStatus.NEW:
            self._raise_invalid_state("begin")
        self._begin(manifest)
        self._status = SinkStatus.WRITING

    def write_truth_states(self, batch: tuple[TruthState, ...]) -> None:
        """Validate and write one truth-state batch."""
        self._require_writing("write_truth_states")
        validated = _validate_batch(batch, TruthState, "truth_states")
        self._write_truth_states(validated)

    def write_attitude_states(self, batch: tuple[AttitudeState, ...]) -> None:
        """Validate and write one attitude-state batch."""
        self._require_writing("write_attitude_states")
        validated = _validate_batch(batch, AttitudeState, "attitude_states")
        self._write_attitude_states(validated)

    def write_truth_maneuvers(self, batch: tuple[TruthManeuver, ...]) -> None:
        """Validate and write one truth-maneuver batch."""
        self._require_writing("write_truth_maneuvers")
        validated = _validate_batch(batch, TruthManeuver, "truth_maneuvers")
        self._write_truth_maneuvers(validated)

    def commit(self, summary: SimulationOutputSummary) -> None:
        """Commit exactly once, changing state only after successful completion."""
        self._require_writing("commit")
        self._commit(summary)
        self._status = SinkStatus.COMMITTED

    def abort(self, detail: ErrorDetail) -> None:
        """Abort once from WRITING and remain idempotent in ABORTED."""
        if self._status is SinkStatus.ABORTED:
            return
        self._require_writing("abort")
        self._abort(detail)
        self._status = SinkStatus.ABORTED

    def _begin(self, manifest: SimulationExecutionManifest) -> None:
        """Perform implementation-specific begin work."""

    def _write_truth_states(self, batch: tuple[TruthState, ...]) -> None:
        """Perform implementation-specific truth-state writing."""

    def _write_attitude_states(self, batch: tuple[AttitudeState, ...]) -> None:
        """Perform implementation-specific attitude-state writing."""

    def _write_truth_maneuvers(self, batch: tuple[TruthManeuver, ...]) -> None:
        """Perform implementation-specific truth-maneuver writing."""

    def _commit(self, summary: SimulationOutputSummary) -> None:
        """Perform implementation-specific commit work."""

    def _abort(self, detail: ErrorDetail) -> None:
        """Perform implementation-specific abort work."""


# =============================👐Seperate👐=============================
# Built-in output sinks
# =============================👐Seperate👐=============================


class NullOutputSink(_LifecycleOutputSink):
    """Discard validated output while tracking the sink lifecycle."""


class InMemoryOutputSink(NullOutputSink):
    """Retain a bounded number of output records in memory."""

    def __init__(self, max_records: int) -> None:
        if type(max_records) is not int or max_records <= 0:
            raise ValueError("max_records must be a positive built-in int")
        super().__init__()
        self._max_records = max_records
        self._truth_states: list[TruthState] = []
        self._attitude_states: list[AttitudeState] = []
        self._truth_maneuvers: list[TruthManeuver] = []

    @property
    def max_records(self) -> int:
        """Return the combined record limit across all output channels."""
        return self._max_records

    @property
    def truth_states(self) -> tuple[TruthState, ...]:
        """Return an immutable snapshot of retained truth states."""
        return tuple(self._truth_states)

    @property
    def attitude_states(self) -> tuple[AttitudeState, ...]:
        """Return an immutable snapshot of retained attitude states."""
        return tuple(self._attitude_states)

    @property
    def truth_maneuvers(self) -> tuple[TruthManeuver, ...]:
        """Return an immutable snapshot of retained truth maneuvers."""
        return tuple(self._truth_maneuvers)

    def _write_truth_states(self, batch: tuple[TruthState, ...]) -> None:
        """Retain a validated truth-state batch within the shared bound."""
        self._append_bounded(self._truth_states, batch)

    def _write_attitude_states(self, batch: tuple[AttitudeState, ...]) -> None:
        """Retain a validated attitude-state batch within the shared bound."""
        self._append_bounded(self._attitude_states, batch)

    def _write_truth_maneuvers(self, batch: tuple[TruthManeuver, ...]) -> None:
        """Retain a validated truth-maneuver batch within the shared bound."""
        self._append_bounded(self._truth_maneuvers, batch)

    def _append_bounded[OutputRecord: (TruthState, AttitudeState, TruthManeuver)](
        self,
        records: list[OutputRecord],
        batch: tuple[OutputRecord, ...],
    ) -> None:
        """Append a batch or atomically abort and discard all retained records."""
        retained_count = (
            len(self._truth_states) + len(self._attitude_states) + len(self._truth_maneuvers)
        )
        requested_count = retained_count + len(batch)
        if requested_count > self._max_records:
            self._clear()
            self._status = SinkStatus.ABORTED
            raise SimulationExecutionError(
                make_error_detail(
                    category=ErrorCategory.RESOURCE_EXHAUSTED,
                    code="engine.sink.memory_limit_exceeded",
                    message="in-memory output sink record capacity was exceeded",
                    component_ref="engine.in_memory_output_sink",
                    context={
                        "max_records": self._max_records,
                        "retained_count": retained_count,
                        "batch_count": len(batch),
                    },
                )
            )
        records.extend(batch)

    def _abort(self, detail: ErrorDetail) -> None:
        """Discard every uncommitted in-memory output record."""
        del detail
        self._clear()

    def _clear(self) -> None:
        """Clear all private mutable channel stores."""
        self._truth_states.clear()
        self._attitude_states.clear()
        self._truth_maneuvers.clear()


class CompositeOutputSink(NullOutputSink):
    """Forward output to ordered children without claiming cross-sink atomicity."""

    def __init__(self, sinks: tuple[SimulationOutputSink, ...]) -> None:
        if type(sinks) is not tuple:
            raise ValueError("sinks must be a tuple")
        if len({id(sink) for sink in sinks}) != len(sinks):
            raise ValueError("duplicate child sink identity is not allowed")
        super().__init__()
        self._sinks = sinks
        self._child_statuses = (SinkStatus.NEW,) * len(sinks)

    @property
    def sinks(self) -> tuple[SimulationOutputSink, ...]:
        """Return the fixed child tuple in forwarding order."""
        return self._sinks

    def _set_child_status(self, index: int, status: SinkStatus) -> None:
        """Replace one child lifecycle marker without mutable sequence state."""
        self._child_statuses = (
            *self._child_statuses[:index],
            status,
            *self._child_statuses[index + 1 :],
        )

    def _begin(self, manifest: SimulationExecutionManifest) -> None:
        """Begin children in order and reverse successful begins on failure."""
        for index, sink in enumerate(self._sinks):
            try:
                sink.begin(manifest)
            except Exception as error:
                detail = _cleanup_detail(error, code="engine.sink.child_begin_failed")
                self._abort_writing_children(detail, indices=range(index - 1, -1, -1))
                raise
            self._set_child_status(index, SinkStatus.WRITING)

    def _write_truth_states(self, batch: tuple[TruthState, ...]) -> None:
        """Forward a validated truth-state batch in constructor order."""
        for sink in self._sinks:
            sink.write_truth_states(batch)

    def _write_attitude_states(self, batch: tuple[AttitudeState, ...]) -> None:
        """Forward a validated attitude-state batch in constructor order."""
        for sink in self._sinks:
            sink.write_attitude_states(batch)

    def _write_truth_maneuvers(self, batch: tuple[TruthManeuver, ...]) -> None:
        """Forward a validated truth-maneuver batch in constructor order."""
        for sink in self._sinks:
            sink.write_truth_maneuvers(batch)

    def _commit(self, summary: SimulationOutputSummary) -> None:
        """Commit in order and abort only children not successfully committed."""
        for index, sink in enumerate(self._sinks):
            try:
                sink.commit(summary)
            except Exception as error:
                detail = _cleanup_detail(error, code="engine.sink.child_commit_failed")
                self._abort_writing_children(
                    detail,
                    indices=range(len(self._sinks) - 1, -1, -1),
                )
                raise
            self._set_child_status(index, SinkStatus.COMMITTED)

    def _abort(self, detail: ErrorDetail) -> None:
        """Best-effort abort all still-writing children in reverse begin order."""
        first_error = self._abort_writing_children(
            detail,
            indices=range(len(self._sinks) - 1, -1, -1),
        )
        if first_error is not None:
            raise first_error

    def _abort_writing_children(
        self,
        detail: ErrorDetail,
        *,
        indices: range,
    ) -> Exception | None:
        """Abort selected WRITING children while preserving the first cleanup error."""
        first_error: Exception | None = None
        for index in indices:
            if self._child_statuses[index] is not SinkStatus.WRITING:
                continue
            try:
                self._sinks[index].abort(detail)
            except Exception as error:
                if first_error is None:
                    first_error = error
            else:
                self._set_child_status(index, SinkStatus.ABORTED)
        return first_error


__all__ = [
    "CompositeOutputSink",
    "InMemoryOutputSink",
    "NullOutputSink",
    "SinkStatus",
]
