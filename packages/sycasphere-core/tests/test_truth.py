# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_truth.py
创建者    : Sycamore
创建日期  : 2026-07-28
最后修改  : 2026-07-28
版本号    : v1.0.0

■ 用途说明:
  验证不可变真值状态快照和真实机动结果的边界契约。

■ 主要函数功能:
  - 真值状态验证: 覆盖历元、姿态、质量和序列化约束
  - 真值机动验证: 覆盖来源、时序、坐标系、状态谱系和质量约束

■ 功能特性:
  ✓ 覆盖 J2000 实际 Δv 和机动前后快照
  ✓ 覆盖嵌套模型重验证和 JSON 往返

■ 待办事项:
  - [ ] 无

■ 更新日志:
  v1.0.0 (2026-07-28): 创建真值状态与真实机动契约测试

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from sycasphere.core.attitudes import AttitudeState
from sycasphere.core.epoch import Epoch, TimeScale
from sycasphere.core.frames import EarthFixedFrameSpec, FrameKind, FrameRef
from sycasphere.core.states import CartesianState
from sycasphere.core.truth import ManeuverTruthSource, TruthManeuver, TruthState

# =============================👐Seperate👐=============================
# Truth-contract fixtures
# =============================👐Seperate👐=============================
EPOCH = Epoch(value="2026-07-28T00:00:00Z", time_scale=TimeScale.UTC)
OTHER_EPOCH = Epoch(value="2026-07-28T00:01:00Z", time_scale=TimeScale.UTC)
TAI_EPOCH = Epoch(value="2026-07-28T00:01:00", time_scale=TimeScale.TAI)
EARLIER_EPOCH = Epoch(value="2026-07-27T23:59:59Z", time_scale=TimeScale.UTC)


def make_cartesian_state(
    *,
    epoch: Epoch = EPOCH,
    frame: FrameRef | None = None,
    velocity: tuple[float, float, float] = (0.0, 7_500.0, 0.0),
) -> CartesianState:
    """Return a valid J2000 Cartesian truth-state component."""
    return CartesianState(
        epoch=epoch,
        frame=frame or FrameRef(kind=FrameKind.J2000),
        position_m=(7_000_000.0, 0.0, 0.0),
        velocity_mps=velocity,
    )


def make_truth_state(
    *,
    entity_id: str = "spacecraft-1",
    epoch: Epoch = EPOCH,
    frame: FrameRef | None = None,
    velocity: tuple[float, float, float] = (0.0, 7_500.0, 0.0),
    mass_kg: float | None = None,
    attitude_epoch: Epoch | None = None,
) -> TruthState:
    """Return a valid truth-state snapshot with an optional identity attitude."""
    return TruthState(
        entity_id=entity_id,
        cartesian_state=make_cartesian_state(epoch=epoch, frame=frame, velocity=velocity),
        attitude_state=(
            AttitudeState(
                epoch=attitude_epoch or epoch,
                reference_frame=FrameRef(kind=FrameKind.J2000),
                rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
            )
            if attitude_epoch is not None
            else None
        ),
        mass_kg=mass_kg,
    )


def valid_earth_fixed_frame() -> FrameRef:
    """Return a valid Cartesian Earth-fixed frame for mismatch validation."""
    return FrameRef(
        kind=FrameKind.EARTH_FIXED,
        earth_fixed=EarthFixedFrameSpec(
            itrf_realization="ITRF2020",
            iers_conventions="IERS_2010",
            eop_data_id="iers-bulletin-a:2026-07-28",
        ),
    )


def valid_truth_maneuver_data() -> dict[str, object]:
    """Return valid true-maneuver inputs with equal pre- and post-event states."""
    state = make_truth_state(mass_kg=500.0)
    return {
        "maneuver_event_id": "truth-maneuver-1",
        "source_kind": ManeuverTruthSource.COMMAND,
        "source_id": "command-1",
        "entity_id": "spacecraft-1",
        "scheduled_epoch": EPOCH,
        "executed_epoch": EPOCH,
        "actual_delta_v_j2000_mps": (0.0, 1.0, 0.0),
        "state_before": state,
        "state_after": state,
    }


# =============================👐Seperate👐=============================
# Truth-state contract tests
# =============================👐Seperate👐=============================
def test_truth_state_uses_cartesian_epoch_without_serialized_duplicate() -> None:
    state = make_truth_state()

    assert state.epoch == EPOCH
    assert "epoch" not in state.model_dump(mode="json")


def test_truth_state_requires_matching_attitude_epoch() -> None:
    with pytest.raises(ValidationError, match="epoch"):
        make_truth_state(attitude_epoch=OTHER_EPOCH)


@pytest.mark.parametrize("mass", [0.0, -1.0, 1, math.nan])
def test_truth_state_rejects_invalid_mass(mass: object) -> None:
    with pytest.raises(ValidationError):
        TruthState(
            entity_id="spacecraft-1",
            cartesian_state=make_cartesian_state(),
            mass_kg=mass,
        )


def test_truth_state_is_frozen_and_revalidates_constructed_cartesian_state() -> None:
    malformed_cartesian = CartesianState.model_construct(
        epoch=EPOCH,
        frame=FrameRef.model_construct(kind=FrameKind.SENSOR),
        position_m=(7_000_000.0, 0.0, 0.0),
        velocity_mps=(0.0, 7_500.0, 0.0),
    )

    with pytest.raises(ValidationError):
        TruthState(entity_id="spacecraft-1", cartesian_state=malformed_cartesian)

    state = make_truth_state()
    with pytest.raises(ValidationError):
        state.entity_id = "spacecraft-2"


# =============================👐Seperate👐=============================
# Truth-maneuver contract tests
# =============================👐Seperate👐=============================
def test_truth_maneuver_records_actual_j2000_jump_and_mass_loss() -> None:
    before = make_truth_state(velocity=(0.0, 7_500.0, 0.0), mass_kg=500.0)
    after = make_truth_state(velocity=(0.0, 7_501.0, 0.0), mass_kg=499.9)
    event = TruthManeuver(
        maneuver_event_id="truth-maneuver-1",
        source_kind="COMMAND",
        source_id="command-1",
        entity_id="spacecraft-1",
        scheduled_epoch=EPOCH,
        executed_epoch=EPOCH,
        actual_delta_v_j2000_mps=(0.0, 1.0, 0.0),
        state_before=before,
        state_after=after,
    )

    assert event.source_kind is ManeuverTruthSource.COMMAND
    assert event.state_after.mass_kg == 499.9


def test_truth_maneuver_rejects_entity_epoch_frame_and_mass_mismatches() -> None:
    valid = valid_truth_maneuver_data()
    invalid_cases = (
        {"state_after": make_truth_state(entity_id="other")},
        {"state_after": make_truth_state(epoch=OTHER_EPOCH)},
        {"state_after": make_truth_state(frame=valid_earth_fixed_frame())},
        {
            "state_before": make_truth_state(mass_kg=500.0),
            "state_after": make_truth_state(mass_kg=501.0),
        },
    )

    for update in invalid_cases:
        with pytest.raises(ValidationError):
            TruthManeuver.model_validate({**valid, **update})


@pytest.mark.parametrize("source_kind", [ManeuverTruthSource.PLANNED, ManeuverTruthSource.COMMAND])
def test_truth_maneuver_accepts_planned_and_command_sources(
    source_kind: ManeuverTruthSource,
) -> None:
    event = TruthManeuver.model_validate(
        {**valid_truth_maneuver_data(), "source_kind": source_kind}
    )

    assert event.source_kind is source_kind


def test_truth_maneuver_requires_nonblank_source_id() -> None:
    with pytest.raises(ValidationError):
        TruthManeuver.model_validate({**valid_truth_maneuver_data(), "source_id": "   "})


def test_truth_maneuver_rejects_executed_epoch_before_scheduled_in_same_scale() -> None:
    with pytest.raises(ValidationError, match="executed_epoch"):
        TruthManeuver.model_validate(
            {
                **valid_truth_maneuver_data(),
                "scheduled_epoch": EPOCH,
                "executed_epoch": EARLIER_EPOCH,
                "state_before": make_truth_state(epoch=EARLIER_EPOCH),
                "state_after": make_truth_state(epoch=EARLIER_EPOCH),
            }
        )


def test_truth_maneuver_keeps_cross_time_scale_ordering_structurally_valid() -> None:
    event = TruthManeuver.model_validate(
        {
            **valid_truth_maneuver_data(),
            "scheduled_epoch": TAI_EPOCH,
            "executed_epoch": EPOCH,
        }
    )

    assert event.executed_epoch.time_scale is TimeScale.UTC
    assert event.scheduled_epoch.time_scale is TimeScale.TAI


@pytest.mark.parametrize(
    "actual_delta_v_j2000_mps",
    [(0, 1.0, 0.0), (math.nan, 1.0, 0.0)],
)
def test_truth_maneuver_rejects_non_strict_or_nonfinite_actual_delta_v(
    actual_delta_v_j2000_mps: object,
) -> None:
    with pytest.raises(ValidationError):
        TruthManeuver.model_validate(
            {
                **valid_truth_maneuver_data(),
                "actual_delta_v_j2000_mps": actual_delta_v_j2000_mps,
            }
        )


def test_truth_maneuver_is_frozen_and_revalidates_constructed_states() -> None:
    malformed_state = TruthState.model_construct(
        entity_id="",
        cartesian_state=make_cartesian_state(),
        attitude_state=None,
        mass_kg=None,
    )

    with pytest.raises(ValidationError):
        TruthManeuver.model_validate(
            {**valid_truth_maneuver_data(), "state_before": malformed_state}
        )

    event = TruthManeuver.model_validate(valid_truth_maneuver_data())
    with pytest.raises(ValidationError):
        event.source_id = "other-command"


def test_truth_models_round_trip_as_exact_json_contracts() -> None:
    state = make_truth_state(mass_kg=500.0)
    maneuver = TruthManeuver.model_validate(valid_truth_maneuver_data())

    assert TruthState.model_validate_json(state.model_dump_json()) == state
    assert TruthManeuver.model_validate_json(maneuver.model_dump_json()) == maneuver
