# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_sinks.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-08-01
版本号    : v1.3.0

■ 用途说明:
  验证内置输出 sink 的严格生命周期、有界内存和组合故障清理语义。

■ 主要函数功能:
  - test_in_memory_sink_commits_bounded_records: 验证有界记录提交。
  - test_composite_commit_failure_preserves_first_error: 验证组合提交错误优先级。

■ 功能特性:
  ✓ 覆盖 NEW、WRITING、COMMITTED 和 ABORTED 状态转换。
  ✓ 覆盖精确批次类型、容量耗尽和组合 sink 固定顺序。
  ✓ 锁定 Sink 验证与容量错误的稳定详情。
  ✓ 锁定 Composite begin 回滚失败后的真实状态矩阵。
  ✓ 覆盖空 Composite Sink 的无效批次稳定错误详情。

■ 待办事项:
  - 无

■ 更新日志:
  v1.3.0 (2026-08-01): 覆盖空 Composite Sink 的无效批次稳定错误详情。
  v1.2.0 (2026-08-01): 锁定 Composite begin 回滚失败后的真实状态矩阵。
  v1.1.0 (2026-08-01): 锁定 Sink 验证与容量错误的稳定详情。
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import pytest
from sycasphere.core import (
    AttitudeState,
    CartesianState,
    Epoch,
    ErrorCategory,
    ErrorDetail,
    FrameKind,
    FrameRef,
    ManeuverTruthSource,
    SimulationExecutionManifest,
    SimulationOutputSummary,
    TimeScale,
    TruthManeuver,
    TruthState,
)
from sycasphere.engine.backend import SimulationOutputSink
from sycasphere.engine.errors import SimulationExecutionError
from sycasphere.engine.sinks import (
    CompositeOutputSink,
    InMemoryOutputSink,
    NullOutputSink,
    SinkStatus,
)

# =============================👐Seperate👐=============================
# Test fixtures and recording child sink
# =============================👐Seperate👐=============================


def make_manifest() -> SimulationExecutionManifest:
    """Return an opaque typed manifest because sinks never inspect its content."""
    return cast(SimulationExecutionManifest, object())


def make_epoch() -> Epoch:
    """Return the common epoch used by immutable scientific result fixtures."""
    return Epoch(value="2026-07-30T00:00:00Z", time_scale=TimeScale.UTC)


def make_truth_state() -> TruthState:
    """Return one valid J2000 truth state."""
    epoch = make_epoch()
    return TruthState(
        entity_id="spacecraft-1",
        cartesian_state=CartesianState(
            epoch=epoch,
            frame=FrameRef(kind=FrameKind.J2000),
            position_m=(7_000_000.0, 0.0, 0.0),
            velocity_mps=(0.0, 7_500.0, 0.0),
        ),
        mass_kg=500.0,
    )


def make_attitude_state() -> AttitudeState:
    """Return one valid J2000-to-body attitude state."""
    return AttitudeState(
        epoch=make_epoch(),
        reference_frame=FrameRef(kind=FrameKind.J2000),
        rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
    )


def make_truth_maneuver() -> TruthManeuver:
    """Return one valid executed maneuver fact."""
    state = make_truth_state()
    return TruthManeuver(
        maneuver_event_id="maneuver-1",
        source_kind=ManeuverTruthSource.COMMAND,
        source_id="command-1",
        entity_id=state.entity_id,
        scheduled_epoch=state.epoch,
        executed_epoch=state.epoch,
        actual_delta_v_j2000_mps=(0.0, 1.0, 0.0),
        state_before=state,
        state_after=state,
    )


def make_detail(code: str = "engine.test_failure") -> ErrorDetail:
    """Return a safe structured detail for aborts and injected failures."""
    return ErrorDetail(
        category=ErrorCategory.INTERNAL_ERROR,
        code=code,
        message=f"failure: {code}",
        retryable=False,
        component_ref="test-sink",
        context={},
    )


class RecordingSink:
    """A complete child test double recording real sink lifecycle calls."""

    def __init__(
        self,
        name: str,
        events: list[str],
        *,
        failure_method: str | None = None,
        failure: SimulationExecutionError | None = None,
    ) -> None:
        self.name = name
        self.events = events
        self.failure_method = failure_method
        self.failure = failure
        self.status = SinkStatus.NEW

    def _record_or_fail(self, method: str) -> None:
        self.events.append(f"{self.name}.{method}")
        if self.failure_method == method:
            if self.failure is None:
                raise AssertionError("injected failure requires an exception")
            raise self.failure

    def begin(self, manifest: SimulationExecutionManifest) -> None:
        del manifest
        self._record_or_fail("begin")
        self.status = SinkStatus.WRITING

    def write_truth_states(self, batch: tuple[TruthState, ...]) -> None:
        del batch
        self._record_or_fail("write_truth_states")

    def write_attitude_states(self, batch: tuple[AttitudeState, ...]) -> None:
        del batch
        self._record_or_fail("write_attitude_states")

    def write_truth_maneuvers(self, batch: tuple[TruthManeuver, ...]) -> None:
        del batch
        self._record_or_fail("write_truth_maneuvers")

    def commit(self, summary: SimulationOutputSummary) -> None:
        del summary
        self._record_or_fail("commit")
        self.status = SinkStatus.COMMITTED

    def abort(self, detail: ErrorDetail) -> None:
        del detail
        self._record_or_fail("abort")
        self.status = SinkStatus.ABORTED


# =============================👐Seperate👐=============================
# Null and in-memory sink state machines
# =============================👐Seperate👐=============================


@pytest.mark.parametrize(
    "factory",
    [
        NullOutputSink,
        lambda: InMemoryOutputSink(max_records=3),
        lambda: CompositeOutputSink(()),
    ],
)
def test_sink_lifecycle_rejects_calls_outside_writing(
    factory: Callable[[], NullOutputSink | InMemoryOutputSink | CompositeOutputSink],
) -> None:
    """Only begin is legal in NEW and no operation is legal after commit."""
    sink = factory()
    manifest = make_manifest()
    truth_state = make_truth_state()
    summary = SimulationOutputSummary()

    assert sink.status is SinkStatus.NEW
    with pytest.raises(SimulationExecutionError) as caught:
        sink.write_truth_states((truth_state,))
    assert caught.value.detail.category is ErrorCategory.VALIDATION_ERROR
    assert caught.value.detail.code == "engine.sink.invalid_state"
    assert caught.value.detail.context == {
        "operation": "write_truth_states",
        "status": "NEW",
    }
    with pytest.raises(SimulationExecutionError, match="state"):
        sink.commit(summary)
    with pytest.raises(SimulationExecutionError, match="state"):
        sink.abort(make_detail())

    sink.begin(manifest)
    assert sink.status is SinkStatus.WRITING
    with pytest.raises(SimulationExecutionError, match="state"):
        sink.begin(manifest)
    sink.commit(summary)
    assert sink.status is SinkStatus.COMMITTED
    with pytest.raises(SimulationExecutionError, match="state"):
        sink.write_truth_states((truth_state,))
    with pytest.raises(SimulationExecutionError, match="state"):
        sink.commit(summary)
    with pytest.raises(SimulationExecutionError, match="state"):
        sink.abort(make_detail())


@pytest.mark.parametrize(
    "factory",
    [
        NullOutputSink,
        lambda: InMemoryOutputSink(max_records=3),
        lambda: CompositeOutputSink(()),
    ],
)
def test_abort_is_idempotent_only_after_abort(
    factory: Callable[[], NullOutputSink | InMemoryOutputSink | CompositeOutputSink],
) -> None:
    """An abort succeeds once from WRITING and is then idempotent."""
    sink = factory()
    detail = make_detail()
    sink.begin(make_manifest())

    sink.abort(detail)
    sink.abort(detail)

    assert sink.status is SinkStatus.ABORTED
    with pytest.raises(SimulationExecutionError, match="state"):
        sink.begin(make_manifest())
    with pytest.raises(SimulationExecutionError, match="state"):
        sink.commit(SimulationOutputSummary())


@pytest.mark.parametrize(
    ("method_name", "valid_item"),
    [
        ("write_truth_states", make_truth_state()),
        ("write_attitude_states", make_attitude_state()),
        ("write_truth_maneuvers", make_truth_maneuver()),
    ],
)
@pytest.mark.parametrize(
    "factory",
    [
        NullOutputSink,
        lambda: InMemoryOutputSink(max_records=10),
        lambda: CompositeOutputSink(()),
    ],
)
def test_writes_require_nonempty_exact_tuples(
    factory: Callable[[], NullOutputSink | InMemoryOutputSink | CompositeOutputSink],
    method_name: str,
    valid_item: TruthState | AttitudeState | TruthManeuver,
) -> None:
    """All channels reject lists, empty tuples, and values of a different Core type."""
    sink = factory()
    sink.begin(make_manifest())
    write = cast(Callable[[Any], None], getattr(sink, method_name))
    expected_channel = method_name.removeprefix("write_")
    expected_type = type(valid_item).__name__

    for invalid_batch in ([], (), (object(),)):
        with pytest.raises(SimulationExecutionError) as caught:
            write(invalid_batch)
        assert caught.value.detail.category is ErrorCategory.VALIDATION_ERROR
        assert caught.value.detail.code == "engine.sink.invalid_batch"
        assert caught.value.detail.context == {
            "channel": expected_channel,
            "expected_type": expected_type,
        }
        assert sink.status is SinkStatus.WRITING

    write((valid_item,))


def test_writes_reject_subclasses_of_core_elements() -> None:
    """Boundary writes accept each exact Core class rather than its subclasses."""

    class DerivedTruthState(TruthState):
        pass

    derived = DerivedTruthState.model_validate(make_truth_state().model_dump(mode="python"))
    sink = InMemoryOutputSink(max_records=1)
    sink.begin(make_manifest())

    with pytest.raises(SimulationExecutionError) as caught:
        sink.write_truth_states((derived,))

    assert caught.value.detail.category is ErrorCategory.VALIDATION_ERROR
    assert sink.truth_states == ()


def test_in_memory_sink_commits_bounded_records() -> None:
    """A successful commit retains immutable tuple snapshots."""
    manifest = make_manifest()
    truth_state = make_truth_state()
    sink = InMemoryOutputSink(max_records=3)
    sink.begin(manifest)
    sink.write_truth_states((truth_state,))
    sink.commit(SimulationOutputSummary(truth_state_count=1))
    assert sink.truth_states == (truth_state,)
    assert sink.status is SinkStatus.COMMITTED

    with pytest.raises(SimulationExecutionError, match="state"):
        sink.write_truth_states((truth_state,))


def test_in_memory_sink_retains_all_three_output_channels() -> None:
    """The bound applies to the combined count while each channel has a tuple snapshot."""
    truth_state = make_truth_state()
    attitude_state = make_attitude_state()
    truth_maneuver = make_truth_maneuver()
    sink = InMemoryOutputSink(max_records=3)
    sink.begin(make_manifest())

    sink.write_truth_states((truth_state,))
    first_snapshot = sink.truth_states
    sink.write_attitude_states((attitude_state,))
    sink.write_truth_maneuvers((truth_maneuver,))

    assert first_snapshot == (truth_state,)
    assert sink.truth_states == (truth_state,)
    assert sink.attitude_states == (attitude_state,)
    assert sink.truth_maneuvers == (truth_maneuver,)


def test_in_memory_limit_aborts_and_clears() -> None:
    """Capacity exhaustion atomically clears all uncommitted channel records."""
    manifest = make_manifest()
    truth_state = make_truth_state()
    sink = InMemoryOutputSink(max_records=1)
    sink.begin(manifest)
    with pytest.raises(SimulationExecutionError) as caught:
        sink.write_truth_states((truth_state, truth_state))
    assert caught.value.detail.category is ErrorCategory.RESOURCE_EXHAUSTED
    assert caught.value.detail.code == "engine.sink.memory_limit_exceeded"
    assert caught.value.detail.context == {
        "max_records": 1,
        "retained_count": 0,
        "batch_count": 2,
    }
    assert sink.truth_states == ()
    assert sink.status is SinkStatus.ABORTED


def test_in_memory_limit_counts_records_across_channels() -> None:
    """Overflow on a later channel clears records previously held in other channels."""
    sink = InMemoryOutputSink(max_records=2)
    sink.begin(make_manifest())
    sink.write_truth_states((make_truth_state(),))
    sink.write_attitude_states((make_attitude_state(),))

    with pytest.raises(SimulationExecutionError) as caught:
        sink.write_truth_maneuvers((make_truth_maneuver(),))

    assert caught.value.detail.category is ErrorCategory.RESOURCE_EXHAUSTED
    assert sink.truth_states == ()
    assert sink.attitude_states == ()
    assert sink.truth_maneuvers == ()
    assert sink.status is SinkStatus.ABORTED


@pytest.mark.parametrize("max_records", [0, -1, True, "10"])
def test_in_memory_sink_requires_positive_builtin_int(max_records: object) -> None:
    """Capacity configuration rejects nonpositive and coercible integer values."""
    with pytest.raises(ValueError, match="max_records"):
        InMemoryOutputSink(max_records=cast(Any, max_records))


def test_in_memory_abort_clears_records() -> None:
    """Explicit abort discards every retained uncommitted record."""
    sink = InMemoryOutputSink(max_records=3)
    sink.begin(make_manifest())
    sink.write_truth_states((make_truth_state(),))
    sink.write_attitude_states((make_attitude_state(),))
    sink.write_truth_maneuvers((make_truth_maneuver(),))

    sink.abort(make_detail())

    assert sink.truth_states == ()
    assert sink.attitude_states == ()
    assert sink.truth_maneuvers == ()
    assert sink.status is SinkStatus.ABORTED


# =============================👐Seperate👐=============================
# Composite ordering, rollback, and failure precedence
# =============================👐Seperate👐=============================


def test_composite_forwards_begin_writes_and_commit_in_constructor_order() -> None:
    """Successful lifecycle calls visit every child in stable constructor order."""
    events: list[str] = []
    children = tuple(RecordingSink(str(index), events) for index in range(1, 4))
    sink = CompositeOutputSink(cast(tuple[SimulationOutputSink, ...], children))
    truth_state = make_truth_state()
    attitude_state = make_attitude_state()
    truth_maneuver = make_truth_maneuver()

    sink.begin(make_manifest())
    sink.write_truth_states((truth_state,))
    sink.write_attitude_states((attitude_state,))
    sink.write_truth_maneuvers((truth_maneuver,))
    sink.commit(
        SimulationOutputSummary(
            truth_state_count=1,
            attitude_state_count=1,
            truth_maneuver_count=1,
        )
    )

    assert events == [
        "1.begin",
        "2.begin",
        "3.begin",
        "1.write_truth_states",
        "2.write_truth_states",
        "3.write_truth_states",
        "1.write_attitude_states",
        "2.write_attitude_states",
        "3.write_attitude_states",
        "1.write_truth_maneuvers",
        "2.write_truth_maneuvers",
        "3.write_truth_maneuvers",
        "1.commit",
        "2.commit",
        "3.commit",
    ]
    assert sink.status is SinkStatus.COMMITTED


def test_composite_begin_failure_aborts_successful_children_in_reverse_order() -> None:
    """A failed begin reverses only children whose begin already succeeded."""
    events: list[str] = []
    failure = SimulationExecutionError(make_detail("engine.child_begin_failed"))
    children = (
        RecordingSink("1", events),
        RecordingSink("2", events),
        RecordingSink("3", events, failure_method="begin", failure=failure),
        RecordingSink("4", events),
    )
    sink = CompositeOutputSink(cast(tuple[SimulationOutputSink, ...], children))

    with pytest.raises(SimulationExecutionError) as caught:
        sink.begin(make_manifest())

    assert caught.value is failure
    assert events == ["1.begin", "2.begin", "3.begin", "2.abort", "1.abort"]
    assert children[0].status is SinkStatus.ABORTED
    assert children[1].status is SinkStatus.ABORTED
    assert children[2].status is SinkStatus.NEW
    assert children[3].status is SinkStatus.NEW


def test_composite_begin_failure_preserves_error_when_rollback_also_fails() -> None:
    """A rollback failure cannot replace the begin failure that caused cleanup."""
    events: list[str] = []
    rollback_failure = SimulationExecutionError(make_detail("engine.child_abort_failed"))
    begin_failure = SimulationExecutionError(make_detail("engine.child_begin_failed"))
    children = (
        RecordingSink(
            "1",
            events,
            failure_method="abort",
            failure=rollback_failure,
        ),
        RecordingSink("2", events, failure_method="begin", failure=begin_failure),
        RecordingSink("3", events),
    )
    sink = CompositeOutputSink(cast(tuple[SimulationOutputSink, ...], children))

    with pytest.raises(SimulationExecutionError) as caught:
        sink.begin(make_manifest())

    assert caught.value is begin_failure
    assert events == ["1.begin", "2.begin", "1.abort"]
    assert children[0].status is SinkStatus.WRITING
    assert children[1].status is SinkStatus.NEW
    assert children[2].status is SinkStatus.NEW
    assert sink.status is SinkStatus.NEW


def test_composite_rejects_duplicate_child_identity() -> None:
    """The same mutable sink instance cannot receive a lifecycle twice."""
    child = NullOutputSink()

    with pytest.raises(ValueError, match="duplicate"):
        CompositeOutputSink((child, child))


def test_composite_commit_failure_preserves_first_error() -> None:
    """Commit cleanup skips committed children and retains its first causal exception."""
    events: list[str] = []
    commit_failure = SimulationExecutionError(make_detail("engine.child_commit_failed"))
    abort_failure = SimulationExecutionError(make_detail("engine.child_abort_failed"))
    children = (
        RecordingSink("1", events),
        RecordingSink("2", events, failure_method="commit", failure=commit_failure),
        RecordingSink("3", events, failure_method="abort", failure=abort_failure),
    )
    sink = CompositeOutputSink(cast(tuple[SimulationOutputSink, ...], children))
    sink.begin(make_manifest())
    events.clear()

    with pytest.raises(SimulationExecutionError) as caught:
        sink.commit(SimulationOutputSummary())

    assert caught.value is commit_failure
    assert events == ["1.commit", "2.commit", "3.abort", "2.abort"]
    assert children[0].status is SinkStatus.COMMITTED
    assert children[1].status is SinkStatus.ABORTED
    assert children[2].status is SinkStatus.WRITING
    assert sink.status is SinkStatus.WRITING


def test_composite_commit_failure_never_aborts_already_committed_children() -> None:
    """Partial commit is reported honestly rather than pretending cross-sink rollback."""
    events: list[str] = []
    failure = SimulationExecutionError(make_detail("engine.child_commit_failed"))
    children = (
        RecordingSink("1", events),
        RecordingSink("2", events),
        RecordingSink("3", events, failure_method="commit", failure=failure),
    )
    sink = CompositeOutputSink(cast(tuple[SimulationOutputSink, ...], children))
    sink.begin(make_manifest())
    events.clear()

    with pytest.raises(SimulationExecutionError):
        sink.commit(SimulationOutputSummary())

    assert events == ["1.commit", "2.commit", "3.commit", "3.abort"]
    assert children[0].status is SinkStatus.COMMITTED
    assert children[1].status is SinkStatus.COMMITTED
    assert children[2].status is SinkStatus.ABORTED
