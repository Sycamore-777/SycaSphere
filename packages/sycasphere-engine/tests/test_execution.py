# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_execution.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  验证公共 SimulationEngine 的批运行、取消、错误清理和确定性语义。

■ 主要函数功能:
  - test_engine_*: 验证批量 Truth、姿态与机动输出生命周期。
  - test_*cancellation*: 验证安全事件边界和同刻机动原子性。
  - test_*failure*: 验证首因错误、关闭与 abort 清理优先级。

■ 功能特性:
  ✓ 覆盖 FakeBackend 的端到端 prepare/run 路径
  ✓ 覆盖三通道批缓冲和批大小不变性
  ✓ 覆盖运行前、传播中和提交前取消
  ✓ 覆盖 factory、runtime 与 sink 故障清理

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import cast

import pytest
from conftest import fake_impulse, fake_spacecraft, make_fake_request, utc
from sycasphere.core import (
    AttitudeState,
    Epoch,
    ErrorCategory,
    ErrorDetail,
    ManeuverCommand,
    ManeuverTruthSource,
    PlannedTruthManeuver,
    PreparedManeuverEntry,
    SimulationExecutionManifest,
    SimulationExecutionStatus,
    SimulationOutputSummary,
    SimulationRunRequest,
    TruthManeuver,
    TruthState,
)
from sycasphere.engine.api import SimulationEngine
from sycasphere.engine.backend import (
    ManeuverExecution,
    PropagationOutcome,
    ScienceBackendFactory,
    ScienceBackendRegistration,
    ScienceBackendRuntime,
)
from sycasphere.engine.cancellation import CancellationProbe, CancellationToken
from sycasphere.engine.errors import SimulationExecutionError
from sycasphere.engine.registry import PluginRegistry
from sycasphere.engine.scheduling import SameScaleCalendarTimeAdapter
from sycasphere.engine.sinks import InMemoryOutputSink, SinkStatus
from sycasphere.engine.testing import fake_backend_registration

# =============================👐Seperate👐=============================
# Recording execution doubles
# =============================👐Seperate👐=============================


def execution_detail(code: str) -> ErrorDetail:
    """Build one stable causal detail for lifecycle-failure tests."""
    return ErrorDetail(
        category=ErrorCategory.NUMERICAL_FAILURE,
        code=code,
        message="recording execution failure",
        retryable=False,
        component_ref="test.recording_component",
        context={"safe": "value"},
    )


@dataclass
class RecordingRuntime:
    """Wrap a real FakeBackend runtime while recording and injecting lifecycle behavior."""

    inner: ScienceBackendRuntime
    events: list[str]
    failure_at: str | None = None
    failure_detail: ErrorDetail | None = None
    cancellation_token: CancellationToken | None = None
    cancel_after_first_maneuver: bool = False
    cancel_at_final_truth_snapshot: bool = False
    cancel_during_second_propagation: bool = False
    close_calls: int = 0
    propagation_calls: int = 0
    maneuver_calls: int = 0

    def _fail(self, operation: str) -> None:
        """Raise the configured structured or unknown failure at one operation."""
        if self.failure_at != operation:
            return
        if self.failure_detail is not None:
            raise SimulationExecutionError(self.failure_detail)
        raise RuntimeError("JavaError traceback: forbidden implementation detail")

    @property
    def current_epoch(self) -> Epoch:
        """Return the wrapped runtime epoch."""
        return self.inner.current_epoch

    def initialize(self) -> None:
        """Record and optionally fail initialization."""
        self.events.append("runtime.initialize")
        self._fail("initialize")
        self.inner.initialize()

    def propagate_to(
        self,
        target_epoch: Epoch,
        cancellation: CancellationProbe,
    ) -> PropagationOutcome:
        """Record propagation and optionally stop at a synchronized intermediate epoch."""
        self.events.append("runtime.propagate")
        self.propagation_calls += 1
        self._fail("propagate")
        if self.cancel_during_second_propagation and self.propagation_calls == 2:
            intermediate = SameScaleCalendarTimeAdapter().add_seconds(self.current_epoch, 5.0)
            outcome = self.inner.propagate_to(intermediate, CancellationToken())
            assert outcome is PropagationOutcome.REACHED_TARGET
            return PropagationOutcome.CANCELLED
        return self.inner.propagate_to(target_epoch, cancellation)

    def snapshot_truth(self) -> tuple[TruthState, ...]:
        """Record and optionally request cancellation after the final Truth snapshot."""
        self.events.append("runtime.snapshot_truth")
        self._fail("write_source")
        snapshots = self.inner.snapshot_truth()
        if (
            self.cancel_at_final_truth_snapshot
            and self.cancellation_token is not None
            and self.current_epoch == utc("2026-07-30T00:00:10Z")
        ):
            self.cancellation_token.cancel()
        return snapshots

    def snapshot_attitudes(self) -> tuple[AttitudeState, ...]:
        """Return wrapped stable attitudes."""
        self.events.append("runtime.snapshot_attitudes")
        return self.inner.snapshot_attitudes()

    def execute_impulsive_maneuver(
        self,
        entry: PreparedManeuverEntry,
    ) -> ManeuverExecution:
        """Record maneuvers and optionally cancel after the first same-epoch impulse."""
        self.events.append(f"runtime.maneuver:{entry.event_id}")
        self.maneuver_calls += 1
        result = self.inner.execute_impulsive_maneuver(entry)
        if (
            self.cancel_after_first_maneuver
            and self.maneuver_calls == 1
            and self.cancellation_token is not None
        ):
            self.cancellation_token.cancel()
        return result

    def close(self) -> None:
        """Record a single close attempt and optionally fail it."""
        self.events.append("runtime.close")
        self.close_calls += 1
        self._fail("close")
        self.inner.close()


@dataclass
class RecordingFactory:
    """Create recording runtime wrappers or fail before runtime construction."""

    inner: ScienceBackendFactory
    events: list[str]
    runtime_options: dict[str, object] = field(default_factory=dict)
    failure_detail: ErrorDetail | None = None
    create_calls: int = 0
    runtime: RecordingRuntime | None = None

    def create(self, manifest: SimulationExecutionManifest) -> ScienceBackendRuntime:
        """Record factory use and return one independently wrapped Fake runtime."""
        self.events.append("factory.create")
        self.create_calls += 1
        if self.failure_detail is not None:
            raise SimulationExecutionError(self.failure_detail)
        self.runtime = RecordingRuntime(
            inner=self.inner.create(manifest),
            events=self.events,
            **self.runtime_options,
        )
        return self.runtime


@dataclass
class RecordingSink:
    """Record all sink calls while retaining uncommitted batches for assertions."""

    events: list[str]
    failure_at: str | None = None
    failure_detail: ErrorDetail | None = None
    abort_also_fails: bool = False
    truth_states: list[TruthState] = field(default_factory=list)
    attitude_states: list[AttitudeState] = field(default_factory=list)
    truth_maneuvers: list[TruthManeuver] = field(default_factory=list)
    truth_batch_sizes: list[int] = field(default_factory=list)
    attitude_batch_sizes: list[int] = field(default_factory=list)
    maneuver_batch_sizes: list[int] = field(default_factory=list)
    abort_calls: int = 0
    commit_calls: int = 0

    def _fail(self, operation: str) -> None:
        """Raise one configured structured failure."""
        if self.failure_at != operation:
            return
        detail = self.failure_detail or execution_detail(f"test.{operation}_failed")
        raise SimulationExecutionError(detail)

    def begin(self, manifest: SimulationExecutionManifest) -> None:
        """Record begin without mutating the manifest."""
        del manifest
        self.events.append("sink.begin")
        self._fail("begin")

    def write_truth_states(self, batch: tuple[TruthState, ...]) -> None:
        """Record one immutable Truth batch."""
        self.events.append("sink.write_truth")
        self._fail("write")
        self.truth_batch_sizes.append(len(batch))
        self.truth_states.extend(batch)

    def write_attitude_states(self, batch: tuple[AttitudeState, ...]) -> None:
        """Record one immutable attitude batch."""
        self.events.append("sink.write_attitude")
        self._fail("write")
        self.attitude_batch_sizes.append(len(batch))
        self.attitude_states.extend(batch)

    def write_truth_maneuvers(self, batch: tuple[TruthManeuver, ...]) -> None:
        """Record one immutable maneuver batch."""
        self.events.append("sink.write_maneuver")
        self._fail("write")
        self.maneuver_batch_sizes.append(len(batch))
        self.truth_maneuvers.extend(batch)

    def commit(self, summary: SimulationOutputSummary) -> None:
        """Record commit and optionally fail before success."""
        del summary
        self.events.append("sink.commit")
        self.commit_calls += 1
        self._fail("commit")

    def abort(self, detail: ErrorDetail) -> None:
        """Record best-effort abort and optionally fail during cleanup."""
        del detail
        self.events.append("sink.abort")
        self.abort_calls += 1
        if self.abort_also_fails:
            raise RuntimeError("abort traceback: cleanup detail must remain private")


def recording_registration(
    *,
    runtime_options: dict[str, object] | None = None,
    factory_failure: ErrorDetail | None = None,
) -> tuple[ScienceBackendRegistration, RecordingFactory, list[str]]:
    """Return one Fake registration with a recording factory/runtime boundary."""
    events: list[str] = []
    base = fake_backend_registration()
    factory = RecordingFactory(
        inner=base.factory,
        events=events,
        runtime_options={} if runtime_options is None else runtime_options,
        failure_detail=factory_failure,
    )
    return replace(base, factory=factory), factory, events


def engine_for(
    registration: ScienceBackendRegistration,
    *,
    batch_size: int = 2,
) -> SimulationEngine:
    """Construct the public facade from one explicit immutable registration."""
    return SimulationEngine(PluginRegistry((registration,)), batch_size=batch_size)


def maneuver_request() -> SimulationRunRequest:
    """Build one run with PLANNED then COMMAND impulses at the final sample epoch."""
    epoch = utc("2026-07-30T00:00:10Z")
    return make_fake_request(
        planned_maneuvers=(
            PlannedTruthManeuver(
                maneuver_id="planned-final",
                spacecraft_id="spacecraft-1",
                epoch=epoch,
                maneuver=fake_impulse(delta_v_mps=(1.0, 0.0, 0.0)),
            ),
        ),
        commands=(
            ManeuverCommand(
                command_id="command-final",
                spacecraft_id="spacecraft-1",
                epoch=epoch,
                maneuver=fake_impulse(delta_v_mps=(0.0, 2.0, 0.0)),
            ),
        ),
    )


def serialized_records(
    sink: InMemoryOutputSink,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Serialize all retained channels without relying on object identity."""
    return (
        tuple(record.model_dump_json() for record in sink.truth_states),
        tuple(record.model_dump_json() for record in sink.attitude_states),
        tuple(record.model_dump_json() for record in sink.truth_maneuvers),
    )


# =============================👐Seperate👐=============================
# Completed execution and deterministic batching
# =============================👐Seperate👐=============================


def test_engine_runs_fake_backend_to_committed_truth(fake_request: SimulationRunRequest) -> None:
    """A prepared FakeBackend run commits all requested Truth records."""
    engine = engine_for(fake_backend_registration(), batch_size=2)
    manifest = engine.prepare(fake_request)
    sink = InMemoryOutputSink(max_records=100)

    result = engine.run(manifest, sink, CancellationToken())

    assert result.status is SimulationExecutionStatus.COMPLETED
    assert result.final_epoch == fake_request.time_range.end
    assert sink.status is SinkStatus.COMMITTED
    assert result.output_summary.truth_state_count == len(sink.truth_states)
    assert sink.truth_states[-1].epoch == fake_request.time_range.end


def test_engine_emits_post_maneuver_truth_with_exact_provenance_and_chaining() -> None:
    """Equal-epoch maneuvers retain source order and ordinary Truth sees both impulses."""
    engine = engine_for(fake_backend_registration(), batch_size=2)
    request = maneuver_request()
    sink = InMemoryOutputSink(max_records=100)

    result = engine.run(engine.prepare(request), sink, CancellationToken())

    assert result.status is SimulationExecutionStatus.COMPLETED
    assert tuple(item.source_kind for item in sink.truth_maneuvers) == (
        ManeuverTruthSource.PLANNED,
        ManeuverTruthSource.COMMAND,
    )
    assert tuple(item.maneuver_event_id for item in sink.truth_maneuvers) == (
        "planned-final",
        "command-final",
    )
    assert tuple(item.source_id for item in sink.truth_maneuvers) == (
        "planned-final",
        "command-final",
    )
    assert sink.truth_maneuvers[1].state_before == sink.truth_maneuvers[0].state_after
    assert sink.truth_states[-1].cartesian_state.velocity_mps == (1.0, 7_502.0, 0.0)
    assert sink.truth_states[-1] == sink.truth_maneuvers[-1].state_after


def test_buffers_flush_at_the_configured_limit_without_reordering() -> None:
    """Each output channel flushes bounded tuples while preserving source order."""
    request = make_fake_request(
        entities=(
            fake_spacecraft(entity_id="spacecraft-a"),
            fake_spacecraft(entity_id="spacecraft-b"),
        ),
    )
    registration, _, events = recording_registration()
    engine = engine_for(registration, batch_size=2)
    sink = RecordingSink(events)

    result = engine.run(engine.prepare(request), sink, CancellationToken())

    assert result.output_summary.truth_state_count == 4
    assert result.output_summary.attitude_state_count == 4
    assert sink.truth_batch_sizes == [2, 2]
    assert sink.attitude_batch_sizes == [2, 2]
    assert [state.entity_id for state in sink.truth_states] == [
        "spacecraft-a",
        "spacecraft-b",
        "spacecraft-a",
        "spacecraft-b",
    ]


def test_batch_size_does_not_change_outputs_or_result_summary() -> None:
    """Batch size changes sink call granularity but not scientific records."""
    request = maneuver_request()
    records: list[
        tuple[tuple[TruthState, ...], tuple[AttitudeState, ...], tuple[TruthManeuver, ...]]
    ] = []
    summaries: list[SimulationOutputSummary] = []
    for batch_size in (1, 2, 1024):
        engine = engine_for(fake_backend_registration(), batch_size=batch_size)
        manifest = engine.prepare(request)
        sink = InMemoryOutputSink(max_records=100)
        result = engine.run(manifest, sink, CancellationToken())
        records.append((sink.truth_states, sink.attitude_states, sink.truth_maneuvers))
        summaries.append(result.output_summary)

    assert records[0] == records[1] == records[2]
    assert summaries[0] == summaries[1] == summaries[2]


def test_repeated_engine_instances_produce_identical_serialized_outputs() -> None:
    """Fresh registries, engines, tokens and sinks serialize byte-identical results."""
    request = maneuver_request()

    def execute_once() -> tuple[str, str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]]:
        engine = engine_for(fake_backend_registration(), batch_size=2)
        manifest = engine.prepare(request)
        sink = InMemoryOutputSink(max_records=100)
        result = engine.run(manifest, sink, CancellationToken())
        return manifest.model_dump_json(), result.model_dump_json(), serialized_records(sink)

    assert execute_once() == execute_once()


@pytest.mark.parametrize("batch_size", [True, False, 0, -1, 1.0, "2"])
def test_engine_requires_a_positive_builtin_integer_batch_size(batch_size: object) -> None:
    """The non-scientific batching parameter rejects bools and coercible values."""
    with pytest.raises(ValueError, match="batch_size"):
        SimulationEngine(
            PluginRegistry((fake_backend_registration(),)),
            batch_size=cast(int, batch_size),
        )


# =============================👐Seperate👐=============================
# Cooperative cancellation boundaries
# =============================👐Seperate👐=============================


def test_cancelled_before_run_touches_no_factory_runtime_or_sink() -> None:
    """A pre-cancelled run returns at synchronization without starting resources."""
    registration, factory, events = recording_registration()
    engine = engine_for(registration)
    manifest = engine.prepare(make_fake_request())
    sink = RecordingSink(events)
    token = CancellationToken()
    token.cancel()

    result = engine.run(manifest, sink, token)

    assert result.status is SimulationExecutionStatus.CANCELLED
    assert result.final_epoch == manifest.source_request.simulation_definition.synchronization_epoch
    assert result.output_summary == SimulationOutputSummary()
    assert result.termination_detail is not None
    assert result.termination_detail.category is ErrorCategory.CANCELLED
    assert factory.create_calls == 0
    assert events == []


def test_propagation_cancellation_aborts_once_closes_once_and_uses_runtime_epoch() -> None:
    """A backend safe-point cancellation reports its synchronized intermediate epoch."""
    registration, factory, events = recording_registration(
        runtime_options={"cancel_during_second_propagation": True}
    )
    engine = engine_for(registration)
    sink = RecordingSink(events)

    result = engine.run(engine.prepare(make_fake_request()), sink, CancellationToken())

    assert result.status is SimulationExecutionStatus.CANCELLED
    assert result.final_epoch == utc("2026-07-30T00:00:05Z")
    assert sink.abort_calls == 1
    assert sink.commit_calls == 0
    assert factory.runtime is not None
    assert factory.runtime.close_calls == 1


def test_cancellation_after_last_group_aborts_instead_of_committing() -> None:
    """Cancellation requested by the final group is observed before commit."""
    token = CancellationToken()
    registration, factory, events = recording_registration(
        runtime_options={
            "cancellation_token": token,
            "cancel_at_final_truth_snapshot": True,
        }
    )
    engine = engine_for(registration)
    sink = RecordingSink(events)

    result = engine.run(engine.prepare(make_fake_request()), sink, token)

    assert result.status is SimulationExecutionStatus.CANCELLED
    assert result.final_epoch == utc("2026-07-30T00:00:10Z")
    assert sink.commit_calls == 0
    assert sink.abort_calls == 1
    assert factory.runtime is not None
    assert factory.runtime.close_calls == 1


def test_same_epoch_maneuver_group_is_atomic_before_cancellation() -> None:
    """Cancellation after the first impulse cannot split an equal-epoch maneuver group."""
    token = CancellationToken()
    registration, factory, events = recording_registration(
        runtime_options={
            "cancellation_token": token,
            "cancel_after_first_maneuver": True,
        }
    )
    engine = engine_for(registration, batch_size=2)
    sink = RecordingSink(events)

    result = engine.run(engine.prepare(maneuver_request()), sink, token)

    assert result.status is SimulationExecutionStatus.CANCELLED
    assert factory.runtime is not None
    assert factory.runtime.maneuver_calls == 2
    assert [item.maneuver_event_id for item in sink.truth_maneuvers] == [
        "planned-final",
        "command-final",
    ]
    assert sink.truth_states[-1].cartesian_state.velocity_mps == (1.0, 7_502.0, 0.0)
    assert result.output_summary.truth_maneuver_count == 2


# =============================👐Seperate👐=============================
# Failure precedence and resource cleanup
# =============================👐Seperate👐=============================


def test_factory_failure_never_touches_runtime_or_sink() -> None:
    """Factory construction is the first runtime boundary and precedes sink begin."""
    causal = execution_detail("test.factory_failed")
    registration, factory, events = recording_registration(factory_failure=causal)
    engine = engine_for(registration)
    sink = RecordingSink(events)

    with pytest.raises(SimulationExecutionError) as exc_info:
        engine.run(engine.prepare(make_fake_request()), sink, CancellationToken())

    assert exc_info.value.detail == causal
    assert factory.create_calls == 1
    assert factory.runtime is None
    assert events == ["factory.create"]


def test_initialize_failure_closes_once_without_touching_sink_and_preserves_cause() -> None:
    """Initialization failure closes the created runtime but never begins the sink."""
    causal = execution_detail("test.initialize_failed")
    registration, factory, events = recording_registration(
        runtime_options={
            "failure_at": "initialize",
            "failure_detail": causal,
        }
    )
    engine = engine_for(registration)
    sink = RecordingSink(events)

    with pytest.raises(SimulationExecutionError) as exc_info:
        engine.run(engine.prepare(make_fake_request()), sink, CancellationToken())

    assert exc_info.value.detail == causal
    assert factory.runtime is not None
    assert factory.runtime.close_calls == 1
    assert "sink.begin" not in events
    assert "sink.abort" not in events


def test_sink_begin_failure_closes_once_but_does_not_abort_unstarted_sink() -> None:
    """A failed begin is not an active sink lifecycle and must not be aborted."""
    causal = execution_detail("test.begin_failed")
    registration, factory, events = recording_registration()
    engine = engine_for(registration)
    sink = RecordingSink(events, failure_at="begin", failure_detail=causal)

    with pytest.raises(SimulationExecutionError) as exc_info:
        engine.run(engine.prepare(make_fake_request()), sink, CancellationToken())

    assert exc_info.value.detail == causal
    assert factory.runtime is not None
    assert factory.runtime.close_calls == 1
    assert sink.abort_calls == 0


@pytest.mark.parametrize("failure_at", ["write", "commit"])
def test_sink_failure_aborts_once_and_preserves_the_first_cause(failure_at: str) -> None:
    """Write and commit failures remain primary when abort cleanup also fails."""
    causal = execution_detail(f"test.{failure_at}_failed")
    registration, factory, events = recording_registration()
    engine = engine_for(registration)
    sink = RecordingSink(
        events,
        failure_at=failure_at,
        failure_detail=causal,
        abort_also_fails=True,
    )

    with pytest.raises(SimulationExecutionError) as exc_info:
        engine.run(engine.prepare(make_fake_request()), sink, CancellationToken())

    assert exc_info.value.detail == causal
    assert factory.runtime is not None
    assert factory.runtime.close_calls == 1
    assert sink.abort_calls == 1


def test_runtime_close_failure_prevents_commit_and_aborts_once() -> None:
    """Runtime cleanup succeeds before commit or becomes the primary execution failure."""
    causal = execution_detail("test.close_failed")
    registration, factory, events = recording_registration(
        runtime_options={
            "failure_at": "close",
            "failure_detail": causal,
        }
    )
    engine = engine_for(registration)
    sink = RecordingSink(events)

    with pytest.raises(SimulationExecutionError) as exc_info:
        engine.run(engine.prepare(make_fake_request()), sink, CancellationToken())

    assert exc_info.value.detail == causal
    assert factory.runtime is not None
    assert factory.runtime.close_calls == 1
    assert sink.abort_calls == 1
    assert sink.commit_calls == 0


def test_runtime_closes_before_sink_commit() -> None:
    """Successful output publication happens only after backend resources close."""
    registration, factory, events = recording_registration()
    engine = engine_for(registration)
    sink = RecordingSink(events)

    result = engine.run(engine.prepare(make_fake_request()), sink, CancellationToken())

    assert result.status is SimulationExecutionStatus.COMPLETED
    assert factory.runtime is not None
    assert factory.runtime.close_calls == 1
    assert events.index("runtime.close") < events.index("sink.commit")


def test_unknown_exception_is_sanitized_without_traceback_or_language_objects() -> None:
    """Unknown backend exceptions become a stable public detail with safe context only."""
    registration, factory, events = recording_registration(
        runtime_options={"failure_at": "initialize"}
    )
    engine = engine_for(registration)

    with pytest.raises(SimulationExecutionError) as exc_info:
        engine.run(
            engine.prepare(make_fake_request()),
            RecordingSink(events),
            CancellationToken(),
        )

    serialized = exc_info.value.detail.model_dump_json().lower()
    assert exc_info.value.detail.category is ErrorCategory.INTERNAL_ERROR
    assert "javaerror" not in serialized
    assert "traceback" not in serialized
    assert factory.runtime is not None
    assert factory.runtime.close_calls == 1
