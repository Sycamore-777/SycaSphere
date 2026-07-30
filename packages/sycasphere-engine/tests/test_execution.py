# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_execution.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-31
版本号    : v1.2.0

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
  ✓ 覆盖多航天器同历元交错机动的逐实体状态连续性

■ 待办事项:
  - 无

■ 更新日志:
  v1.2.0 (2026-07-31): 增加多航天器交错机动链隔离回归覆盖。
  v1.1.0 (2026-07-31): 增加区间筛选和第三方 runtime 契约加固回归覆盖。
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
    CartesianState,
    CoordinateRepresentation,
    EarthFixedFrameSpec,
    Epoch,
    ErrorCategory,
    ErrorDetail,
    FrameKind,
    FrameRef,
    ManeuverCommand,
    ManeuverTruthSource,
    PlannedTruthManeuver,
    PluginKind,
    PluginRef,
    PreparedManeuverEntry,
    ResolvedPluginRecord,
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


def earth_fixed_frame() -> FrameRef:
    """Build one valid non-J2000 Cartesian frame for runtime-contract tests."""
    return FrameRef(
        kind=FrameKind.EARTH_FIXED,
        representation=CoordinateRepresentation.CARTESIAN,
        earth_fixed=EarthFixedFrameSpec(
            itrf_realization="ITRF2020",
            iers_conventions="IERS_2010",
            eop_data_id="test-eop",
        ),
    )


def truth_at_epoch(state: TruthState, epoch: Epoch) -> TruthState:
    """Copy one Truth snapshot to a caller-selected valid epoch."""
    cartesian = state.cartesian_state.model_copy(update={"epoch": epoch})
    return state.model_copy(update={"cartesian_state": cartesian})


def truth_in_frame(state: TruthState, frame: FrameRef) -> TruthState:
    """Copy one Truth snapshot to a caller-selected valid Cartesian frame."""
    cartesian = state.cartesian_state.model_copy(update={"frame": frame})
    return state.model_copy(update={"cartesian_state": cartesian})


class DerivedTruthState(TruthState):
    """Third-party subclass that must not cross the exact Core boundary."""


class DerivedAttitudeState(AttitudeState):
    """Third-party subclass that must not cross the exact Core boundary."""


class DerivedManeuverExecution(ManeuverExecution):
    """Third-party subclass that must not cross the exact Engine dataclass boundary."""


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
    initial_epoch_override: object | None = None
    outcome_override: object | None = None
    reach_without_propagating: bool = False
    cancel_after_target: bool = False
    truth_violation: str | None = None
    attitude_violation: str | None = None
    maneuver_violation: str | None = None
    corrupt_final_epoch_after_truth: bool = False
    close_calls: int = 0
    propagation_calls: int = 0
    maneuver_calls: int = 0
    _reported_epoch_override: object | None = field(default=None, init=False)

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
        if self._reported_epoch_override is not None:
            return cast(Epoch, self._reported_epoch_override)
        if self.initial_epoch_override is not None:
            return cast(Epoch, self.initial_epoch_override)
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
        if self.reach_without_propagating:
            return PropagationOutcome.REACHED_TARGET
        if self.cancel_after_target:
            overshoot = SameScaleCalendarTimeAdapter().add_seconds(target_epoch, 1.0)
            self.inner.propagate_to(overshoot, CancellationToken())
            return PropagationOutcome.CANCELLED
        if self.cancel_during_second_propagation and self.propagation_calls == 2:
            intermediate = SameScaleCalendarTimeAdapter().add_seconds(self.current_epoch, 5.0)
            outcome = self.inner.propagate_to(intermediate, CancellationToken())
            assert outcome is PropagationOutcome.REACHED_TARGET
            return PropagationOutcome.CANCELLED
        outcome = self.inner.propagate_to(target_epoch, cancellation)
        if self.outcome_override is not None:
            return cast(PropagationOutcome, self.outcome_override)
        return outcome

    def snapshot_truth(self) -> tuple[TruthState, ...]:
        """Record and optionally request cancellation after the final Truth snapshot."""
        self.events.append("runtime.snapshot_truth")
        self._fail("write_source")
        snapshots = self.inner.snapshot_truth()
        if self.truth_violation == "not_tuple":
            return cast(tuple[TruthState, ...], list(snapshots))
        if self.truth_violation == "missing":
            return ()
        if self.truth_violation == "duplicate":
            return (snapshots[0], snapshots[0])
        if self.truth_violation == "unstable_order":
            return tuple(reversed(snapshots))
        if self.truth_violation == "wrong_epoch":
            wrong_epoch = SameScaleCalendarTimeAdapter().add_seconds(self.inner.current_epoch, 1.0)
            return (truth_at_epoch(snapshots[0], wrong_epoch), *snapshots[1:])
        if self.truth_violation == "wrong_frame":
            return (truth_in_frame(snapshots[0], earth_fixed_frame()), *snapshots[1:])
        if self.truth_violation == "construct_bypassed":
            invalid = snapshots[0].model_copy(update={"mass_kg": -1.0})
            return (invalid, *snapshots[1:])
        if self.truth_violation == "subclass":
            derived = DerivedTruthState.model_validate(snapshots[0].model_dump(mode="python"))
            return (derived, *snapshots[1:])
        if (
            self.cancel_at_final_truth_snapshot
            and self.cancellation_token is not None
            and self.current_epoch == utc("2026-07-30T00:00:10Z")
        ):
            self.cancellation_token.cancel()
        if self.corrupt_final_epoch_after_truth and self.inner.current_epoch == utc(
            "2026-07-30T00:00:10Z"
        ):
            self._reported_epoch_override = utc("2026-07-30T00:00:09Z")
        return snapshots

    def snapshot_attitudes(self) -> tuple[AttitudeState, ...]:
        """Return wrapped stable attitudes."""
        self.events.append("runtime.snapshot_attitudes")
        snapshots = self.inner.snapshot_attitudes()
        if self.attitude_violation == "not_tuple":
            return cast(tuple[AttitudeState, ...], list(snapshots))
        if self.attitude_violation == "wrong_count":
            return ()
        if self.attitude_violation == "wrong_epoch":
            wrong_epoch = SameScaleCalendarTimeAdapter().add_seconds(self.inner.current_epoch, 1.0)
            return (
                snapshots[0].model_copy(update={"epoch": wrong_epoch}),
                *snapshots[1:],
            )
        if self.attitude_violation == "wrong_frame":
            return (
                snapshots[0].model_copy(update={"reference_frame": earth_fixed_frame()}),
                *snapshots[1:],
            )
        if self.attitude_violation == "construct_bypassed":
            invalid = snapshots[0].model_copy(
                update={"rotation_reference_to_body_wxyz": (2.0, 0.0, 0.0, 0.0)}
            )
            return (invalid, *snapshots[1:])
        if self.attitude_violation == "subclass":
            derived = DerivedAttitudeState.model_validate(snapshots[0].model_dump(mode="python"))
            return (derived, *snapshots[1:])
        return snapshots

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
        if self.maneuver_violation == "not_dataclass":
            return cast(ManeuverExecution, object())
        if self.maneuver_violation == "subclass":
            return DerivedManeuverExecution(
                executed_epoch=result.executed_epoch,
                actual_delta_v_j2000_mps=result.actual_delta_v_j2000_mps,
                state_before=result.state_before,
                state_after=result.state_after,
            )
        if self.maneuver_violation == "wrong_entity":
            before = result.state_before.model_copy(update={"entity_id": "spacecraft-other"})
            after = result.state_after.model_copy(update={"entity_id": "spacecraft-other"})
            return ManeuverExecution(
                executed_epoch=result.executed_epoch,
                actual_delta_v_j2000_mps=result.actual_delta_v_j2000_mps,
                state_before=before,
                state_after=after,
            )
        if self.maneuver_violation == "wrong_epoch":
            wrong_epoch = SameScaleCalendarTimeAdapter().add_seconds(result.executed_epoch, 1.0)
            return ManeuverExecution(
                executed_epoch=wrong_epoch,
                actual_delta_v_j2000_mps=result.actual_delta_v_j2000_mps,
                state_before=truth_at_epoch(result.state_before, wrong_epoch),
                state_after=truth_at_epoch(result.state_after, wrong_epoch),
            )
        if self.maneuver_violation == "wrong_frame":
            return ManeuverExecution(
                executed_epoch=result.executed_epoch,
                actual_delta_v_j2000_mps=result.actual_delta_v_j2000_mps,
                state_before=truth_in_frame(result.state_before, earth_fixed_frame()),
                state_after=truth_in_frame(result.state_after, earth_fixed_frame()),
            )
        if self.maneuver_violation == "broken_chain" and self.maneuver_calls == 2:
            broken_before = result.state_before.model_copy(
                update={
                    "cartesian_state": CartesianState(
                        epoch=result.state_before.epoch,
                        frame=result.state_before.cartesian_state.frame,
                        position_m=result.state_before.cartesian_state.position_m,
                        velocity_mps=(99.0, 99.0, 99.0),
                    )
                }
            )
            return ManeuverExecution(
                executed_epoch=result.executed_epoch,
                actual_delta_v_j2000_mps=result.actual_delta_v_j2000_mps,
                state_before=broken_before,
                state_after=result.state_after,
            )
        if self.maneuver_violation == "runtime_advanced":
            self._reported_epoch_override = SameScaleCalendarTimeAdapter().add_seconds(
                result.executed_epoch,
                1.0,
            )
        return result

    def close(self) -> None:
        """Record a single close attempt and optionally fail it."""
        self.events.append("runtime.close")
        self.close_calls += 1
        self._fail("close")
        self.inner.close()


class ThrowingCancellationProbe:
    """Raise an unknown implementation exception when the Engine reads cancellation."""

    @property
    def is_cancelled(self) -> bool:
        """Fail before returning a cancellation state."""
        raise RuntimeError("Python traceback JavaObject: forbidden probe payload")


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
    cancel_after_truth_write: CancellationToken | None = None
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
        if self.cancel_after_truth_write is not None:
            self.cancel_after_truth_write.cancel()

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


def interleaved_maneuver_request() -> SimulationRunRequest:
    """Build A1, B1, A2, B2 impulses at one shared final epoch."""
    epoch = utc("2026-07-30T00:00:10Z")
    return make_fake_request(
        entities=(
            fake_spacecraft(
                entity_id="spacecraft-a",
                position_m=(7_000_000.0, 0.0, 0.0),
                velocity_mps=(0.0, 7_500.0, 0.0),
            ),
            fake_spacecraft(
                entity_id="spacecraft-b",
                position_m=(7_100_000.0, 0.0, 0.0),
                velocity_mps=(0.0, 7_600.0, 0.0),
            ),
        ),
        planned_maneuvers=(
            PlannedTruthManeuver(
                maneuver_id="a1",
                spacecraft_id="spacecraft-a",
                epoch=epoch,
                maneuver=fake_impulse(delta_v_mps=(1.0, 0.0, 0.0)),
            ),
            PlannedTruthManeuver(
                maneuver_id="b1",
                spacecraft_id="spacecraft-b",
                epoch=epoch,
                maneuver=fake_impulse(delta_v_mps=(0.0, 1.0, 0.0)),
            ),
        ),
        commands=(
            ManeuverCommand(
                command_id="a2",
                spacecraft_id="spacecraft-a",
                epoch=epoch,
                maneuver=fake_impulse(delta_v_mps=(2.0, 0.0, 0.0)),
            ),
            ManeuverCommand(
                command_id="b2",
                spacecraft_id="spacecraft-b",
                epoch=epoch,
                maneuver=fake_impulse(delta_v_mps=(0.0, 2.0, 0.0)),
            ),
        ),
        include_attitude=False,
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


def manifest_with_backend_records(
    manifest: SimulationExecutionManifest,
    records: tuple[ResolvedPluginRecord, ...],
) -> SimulationExecutionManifest:
    """Rebuild one self-hashed manifest with caller-selected public plugin provenance."""
    return SimulationExecutionManifest.create(
        schema_version=manifest.schema_version,
        source_request=manifest.source_request,
        resolved_plugins=records,
        resolved_external_data=manifest.resolved_external_data,
        derived_random_streams=manifest.derived_random_streams,
        prepared_timeline=manifest.prepared_timeline,
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


def test_engine_isolates_interleaved_same_epoch_maneuver_chains_by_entity() -> None:
    """A1, B1, A2, B2 remain ordered while A and B chain independently."""
    engine = engine_for(fake_backend_registration(), batch_size=2)
    sink = InMemoryOutputSink(max_records=100)

    result = engine.run(
        engine.prepare(interleaved_maneuver_request()),
        sink,
        CancellationToken(),
    )

    maneuvers = sink.truth_maneuvers
    assert result.status is SimulationExecutionStatus.COMPLETED
    assert result.output_summary.truth_maneuver_count == 4
    assert tuple(item.maneuver_event_id for item in maneuvers) == ("a1", "b1", "a2", "b2")
    assert tuple(item.entity_id for item in maneuvers) == (
        "spacecraft-a",
        "spacecraft-b",
        "spacecraft-a",
        "spacecraft-b",
    )
    assert maneuvers[0].state_after != maneuvers[1].state_before
    assert maneuvers[2].state_before == maneuvers[0].state_after
    assert maneuvers[3].state_before == maneuvers[1].state_after
    final_truth = {item.entity_id: item for item in sink.truth_states[-2:]}
    assert final_truth["spacecraft-a"].cartesian_state.velocity_mps == (3.0, 7_500.0, 0.0)
    assert final_truth["spacecraft-b"].cartesian_state.velocity_mps == (0.0, 7_603.0, 0.0)


def test_engine_executes_prestart_planned_and_closed_interval_events_only() -> None:
    """Prestart Truth changes start state while filtered provenance remains in the Manifest."""
    synchronization_epoch = utc("2026-07-30T00:00:00Z")
    start = utc("2026-07-30T00:00:05Z")
    end = utc("2026-07-30T00:00:10Z")

    def planned(event_id: str, epoch: Epoch, delta_v: tuple[float, float, float]):
        return PlannedTruthManeuver(
            maneuver_id=event_id,
            spacecraft_id="spacecraft-1",
            epoch=epoch,
            maneuver=fake_impulse(delta_v_mps=delta_v),
        )

    def command(event_id: str, epoch: Epoch, delta_v: tuple[float, float, float]):
        return ManeuverCommand(
            command_id=event_id,
            spacecraft_id="spacecraft-1",
            epoch=epoch,
            maneuver=fake_impulse(delta_v_mps=delta_v),
        )

    request = make_fake_request(
        planned_maneuvers=(
            planned("planned-sync", synchronization_epoch, (1.0, 0.0, 0.0)),
            planned("planned-prestart", utc("2026-07-30T00:00:02Z"), (2.0, 0.0, 0.0)),
            planned("planned-start", start, (3.0, 0.0, 0.0)),
            planned("planned-end", end, (5.0, 0.0, 0.0)),
            planned("planned-after-end", utc("2026-07-30T00:00:11Z"), (50.0, 0.0, 0.0)),
        ),
        commands=(
            command(
                "command-prestart",
                utc("2026-07-30T00:00:03Z"),
                (100.0, 0.0, 0.0),
            ),
            command("command-start", start, (0.0, 4.0, 0.0)),
            command("command-end", end, (0.0, 6.0, 0.0)),
            command(
                "command-after-end",
                utc("2026-07-30T00:00:11Z"),
                (0.0, 60.0, 0.0),
            ),
        ),
    )
    request = SimulationRunRequest.model_validate(
        request.model_copy(
            update={
                "time_range": request.time_range.model_copy(update={"start": start, "end": end})
            }
        ).model_dump(mode="python")
    )
    engine = engine_for(fake_backend_registration(), batch_size=2)
    manifest = engine.prepare(request)
    sink = InMemoryOutputSink(max_records=100)

    result = engine.run(manifest, sink, CancellationToken())

    assert tuple(entry.event_id for entry in manifest.prepared_timeline.maneuvers) == (
        "planned-sync",
        "planned-prestart",
        "command-prestart",
        "planned-start",
        "command-start",
        "planned-end",
        "command-end",
        "planned-after-end",
        "command-after-end",
    )
    assert tuple(item.maneuver_event_id for item in sink.truth_maneuvers) == (
        "planned-sync",
        "planned-prestart",
        "planned-start",
        "command-start",
        "planned-end",
        "command-end",
    )
    assert tuple(state.epoch for state in sink.truth_states) == (start, end)
    assert sink.truth_states[0].cartesian_state.velocity_mps == (6.0, 7_504.0, 0.0)
    assert sink.truth_states[1].cartesian_state.velocity_mps == (11.0, 7_510.0, 0.0)
    assert result.final_epoch == end


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


def test_throwing_initial_cancellation_probe_is_sanitized_before_resource_creation() -> None:
    """An unknown preflight probe failure cannot leak its language-level payload."""
    registration, factory, events = recording_registration()
    engine = engine_for(registration)
    manifest = engine.prepare(make_fake_request())

    with pytest.raises(SimulationExecutionError) as exc_info:
        engine.run(manifest, RecordingSink(events), ThrowingCancellationProbe())

    serialized = exc_info.value.detail.model_dump_json().lower()
    assert exc_info.value.detail.category is ErrorCategory.INTERNAL_ERROR
    assert factory.create_calls == 0
    assert events == []
    assert "python" not in serialized
    assert "traceback" not in serialized
    assert "javaobject" not in serialized


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
    assert result.output_summary == SimulationOutputSummary()
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
    assert result.output_summary == SimulationOutputSummary()
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
    assert result.output_summary == SimulationOutputSummary()


def test_final_residual_flush_stops_between_channels_when_a_write_cancels() -> None:
    """Final residual writes recheck cancellation without interrupting event groups."""
    token = CancellationToken()
    registration, factory, events = recording_registration()
    engine = engine_for(registration, batch_size=1024)
    sink = RecordingSink(events, cancel_after_truth_write=token)

    result = engine.run(engine.prepare(make_fake_request()), sink, token)

    assert result.status is SimulationExecutionStatus.CANCELLED
    assert sink.truth_states
    assert sink.attitude_states == []
    assert "sink.write_truth" in events
    assert "sink.write_attitude" not in events
    assert result.output_summary == SimulationOutputSummary()
    assert sink.commit_calls == 0
    assert sink.abort_calls == 1
    assert factory.runtime is not None
    assert factory.runtime.close_calls == 1


@pytest.mark.parametrize("mismatch", ["missing", "ref", "kind", "configuration"])
def test_run_rejects_mismatched_backend_provenance_before_factory(
    mismatch: str,
) -> None:
    """A self-hashed manifest must bind its source backend to exact resolved provenance."""
    registration, factory, events = recording_registration()
    engine = engine_for(registration)
    manifest = engine.prepare(make_fake_request())
    source_binding = manifest.source_request.backend
    if mismatch == "missing":
        records: tuple[ResolvedPluginRecord, ...] = ()
    else:
        ref = source_binding.ref
        kind = PluginKind.SCIENCE_BACKEND
        configuration = source_binding.configuration
        if mismatch == "ref":
            ref = PluginRef(
                plugin_id="user.example.mismatched-backend",
                implementation_version=ref.implementation_version,
                interface_version=ref.interface_version,
            )
        elif mismatch == "kind":
            kind = PluginKind.MEASUREMENT_MODEL
        elif mismatch == "configuration":
            configuration = {"unexpected": "configuration"}
        records = (
            ResolvedPluginRecord.create(
                component_id="science-backend",
                kind=kind,
                ref=ref,
                configuration=configuration,
            ),
        )
    mismatched = manifest_with_backend_records(manifest, records)

    with pytest.raises(SimulationExecutionError) as exc_info:
        engine.run(mismatched, RecordingSink(events), CancellationToken())

    assert exc_info.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE
    assert exc_info.value.detail.code == "engine.execution.backend_provenance_mismatch"
    assert exc_info.value.detail.context["mismatch"] == mismatch
    assert factory.create_calls == 0
    assert events == []


# =============================👐Seperate👐=============================
# Untrusted runtime contract validation
# =============================👐Seperate👐=============================


def test_run_rejects_invalid_initialized_epoch_before_sink_begin() -> None:
    """The initialized runtime epoch must be an exact, revalidated Core Epoch at sync."""
    registration, factory, events = recording_registration(
        runtime_options={"initial_epoch_override": object()}
    )
    sink = RecordingSink(events)

    with pytest.raises(SimulationExecutionError) as captured:
        engine_for(registration).run(
            engine_for(registration).prepare(make_fake_request()),
            sink,
            CancellationToken(),
        )

    assert captured.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE
    assert captured.value.detail.code == "engine.execution.runtime_epoch_invalid"
    assert factory.runtime is not None
    assert factory.runtime.close_calls == 1
    assert sink.abort_calls == 0
    assert sink.commit_calls == 0
    assert "sink.begin" not in events


@pytest.mark.parametrize(
    ("runtime_options", "expected_code"),
    (
        (
            {"outcome_override": "REACHED_TARGET"},
            "engine.execution.propagation_outcome_invalid",
        ),
        (
            {"reach_without_propagating": True},
            "engine.execution.propagation_epoch_invalid",
        ),
        (
            {"cancel_after_target": True},
            "engine.execution.cancellation_epoch_invalid",
        ),
    ),
)
def test_run_validates_propagation_outcome_and_safe_epoch(
    runtime_options: dict[str, object],
    expected_code: str,
) -> None:
    """Propagation results must be exact and synchronized at a valid safe point."""
    registration, factory, events = recording_registration(runtime_options=runtime_options)
    engine = engine_for(registration)
    sink = RecordingSink(events)

    with pytest.raises(SimulationExecutionError) as captured:
        engine.run(engine.prepare(make_fake_request()), sink, CancellationToken())

    assert captured.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE
    assert captured.value.detail.code == expected_code
    assert factory.runtime is not None
    assert factory.runtime.close_calls == 1
    assert sink.abort_calls == 1
    assert sink.commit_calls == 0


@pytest.mark.parametrize(
    "violation",
    (
        "not_tuple",
        "missing",
        "duplicate",
        "unstable_order",
        "wrong_epoch",
        "wrong_frame",
        "construct_bypassed",
        "subclass",
    ),
)
def test_run_revalidates_exact_complete_truth_snapshots(violation: str) -> None:
    """Truth snapshots are exact Core tuples covering every propagated entity in ID order."""
    request = make_fake_request(
        entities=(
            fake_spacecraft(entity_id="spacecraft-b"),
            fake_spacecraft(entity_id="spacecraft-a"),
        )
    )
    registration, factory, events = recording_registration(
        runtime_options={"truth_violation": violation}
    )
    engine = engine_for(registration)
    sink = RecordingSink(events)

    with pytest.raises(SimulationExecutionError) as captured:
        engine.run(engine.prepare(request), sink, CancellationToken())

    assert captured.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE
    assert captured.value.detail.code == "engine.execution.truth_snapshot_invalid"
    assert factory.runtime is not None
    assert factory.runtime.close_calls == 1
    assert sink.abort_calls == 1
    assert sink.commit_calls == 0


@pytest.mark.parametrize(
    "violation",
    (
        "not_tuple",
        "wrong_count",
        "wrong_epoch",
        "wrong_frame",
        "construct_bypassed",
        "subclass",
    ),
)
def test_run_revalidates_exact_attitude_snapshots(violation: str) -> None:
    """Attitude snapshots are exact Core tuples with one J2000 record per space object."""
    request = make_fake_request(
        entities=(
            fake_spacecraft(entity_id="spacecraft-b"),
            fake_spacecraft(entity_id="spacecraft-a"),
        )
    )
    registration, factory, events = recording_registration(
        runtime_options={"attitude_violation": violation}
    )
    engine = engine_for(registration)
    sink = RecordingSink(events)

    with pytest.raises(SimulationExecutionError) as captured:
        engine.run(engine.prepare(request), sink, CancellationToken())

    assert captured.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE
    assert captured.value.detail.code == "engine.execution.attitude_snapshot_invalid"
    assert factory.runtime is not None
    assert factory.runtime.close_calls == 1
    assert sink.abort_calls == 1
    assert sink.commit_calls == 0


def test_run_validates_all_same_group_samples_before_any_sink_write() -> None:
    """A bad attitude cannot expose valid same-group Truth through a size-one buffer."""
    registration, _, events = recording_registration(
        runtime_options={"attitude_violation": "wrong_frame"}
    )
    engine = engine_for(registration, batch_size=1)
    sink = RecordingSink(events)

    with pytest.raises(SimulationExecutionError) as captured:
        engine.run(engine.prepare(make_fake_request()), sink, CancellationToken())

    assert captured.value.detail.code == "engine.execution.attitude_snapshot_invalid"
    assert "sink.write_truth" not in events
    assert "sink.write_attitude" not in events
    assert sink.abort_calls == 1
    assert sink.commit_calls == 0


@pytest.mark.parametrize(
    ("violation", "expected_code"),
    (
        ("not_dataclass", "engine.execution.maneuver_execution_invalid"),
        ("subclass", "engine.execution.maneuver_execution_invalid"),
        ("wrong_entity", "engine.execution.maneuver_execution_invalid"),
        ("wrong_epoch", "engine.execution.maneuver_execution_invalid"),
        ("wrong_frame", "engine.execution.maneuver_execution_invalid"),
        ("broken_chain", "engine.execution.maneuver_chain_invalid"),
        ("runtime_advanced", "engine.execution.maneuver_runtime_epoch_invalid"),
    ),
)
def test_run_revalidates_maneuver_execution_and_same_epoch_chain(
    violation: str,
    expected_code: str,
) -> None:
    """Physical maneuver results are exact, targeted, J2000, chained, and epoch-stationary."""
    registration, factory, events = recording_registration(
        runtime_options={"maneuver_violation": violation}
    )
    engine = engine_for(registration)
    sink = RecordingSink(events)

    with pytest.raises(SimulationExecutionError) as captured:
        engine.run(engine.prepare(maneuver_request()), sink, CancellationToken())

    assert captured.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE
    assert captured.value.detail.code == expected_code
    assert factory.runtime is not None
    assert factory.runtime.close_calls == 1
    assert sink.abort_calls == 1
    assert sink.commit_calls == 0


def test_completed_result_is_validated_before_sink_commit() -> None:
    """A runtime that corrupts its final epoch after output cannot commit."""
    registration, factory, events = recording_registration(
        runtime_options={"corrupt_final_epoch_after_truth": True}
    )
    engine = engine_for(registration)
    sink = RecordingSink(events)

    with pytest.raises(SimulationExecutionError) as captured:
        engine.run(engine.prepare(make_fake_request()), sink, CancellationToken())

    assert captured.value.detail.category is ErrorCategory.PLUGIN_INCOMPATIBLE
    assert captured.value.detail.code == "engine.execution.final_epoch_invalid"
    assert factory.runtime is not None
    assert factory.runtime.close_calls == 1
    assert sink.abort_calls == 1
    assert sink.commit_calls == 0


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
