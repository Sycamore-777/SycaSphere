# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_registry_backend.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  验证后端端口值对象和构造后不可变的显式科学后端注册表。

■ 主要函数功能:
  - test_registry_*: 验证精确解析、拒绝无效注册和构造后不可变性。
  - test_maneuver_execution_*: 验证后端返回的机动执行状态一致性。

■ 功能特性:
  ✓ 使用真实的类型化桩对象验证注册表不产生运行时副作用
  ✓ 验证缺失后端的稳定结构化错误

■ 待办事项:
  - [ ] 后续任务消费这些端口以实现准备和执行生命周期

■ 更新日志:
  v1.0.0 (2026-07-30): 创建后端注册表和端口测试

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from sycasphere.core import (
    CartesianState,
    Epoch,
    ErrorCategory,
    FrameKind,
    FrameRef,
    PluginKind,
    PluginManifest,
    PluginRef,
    ResourceRequirements,
    SchemaVersion,
    SimulationExecutionManifest,
    SimulationRunRequest,
    TimeScale,
    TruthState,
)
from sycasphere.engine.backend import (
    ManeuverExecution,
    ScienceBackendRegistration,
    ScienceBackendRuntime,
)
from sycasphere.engine.errors import SimulationPreparationError
from sycasphere.engine.registry import PluginRegistry

# =============================👐Seperate👐=============================
# Typed test doubles and fixtures
# =============================👐Seperate👐=============================


class StubValidator:
    """A configuration validator that exposes whether it was called."""

    def __init__(self) -> None:
        self.calls = 0

    def validate(self, request: SimulationRunRequest) -> None:
        self.calls += 1


class StubTimeAdapter:
    """A preparation-time adapter that rejects all unexpected use."""

    def compare(self, left: Epoch, right: Epoch) -> int:
        raise AssertionError("registry construction must not compare epochs")

    def seconds_between(self, start: Epoch, end: Epoch) -> float:
        raise AssertionError("registry construction must not compute durations")

    def add_seconds(self, epoch: Epoch, seconds: float) -> Epoch:
        raise AssertionError("registry construction must not add time")

    def same_instant(self, left: Epoch, right: Epoch) -> bool:
        raise AssertionError("registry construction must not compare instants")


class StubFactory:
    """A backend factory that rejects creation outside a run."""

    def __init__(self) -> None:
        self.create_calls = 0

    def create(self, manifest: SimulationExecutionManifest) -> ScienceBackendRuntime:
        self.create_calls += 1
        raise AssertionError("registry construction must not create runtime")


@pytest.fixture
def fake_registration() -> ScienceBackendRegistration:
    """Return an explicit, behavior-free registration for registry tests."""
    manifest = PluginManifest(
        ref=PluginRef(
            plugin_id="sycasphere.testing.stub",
            implementation_version="0.1.0",
            interface_version=SchemaVersion(major=1, minor=0),
        ),
        kind=PluginKind.SCIENCE_BACKEND,
        capabilities=("output.truth",),
        configuration_schema={},
        deterministic=True,
        resources=ResourceRequirements(),
    )
    return ScienceBackendRegistration(
        manifest=manifest,
        configuration_validator=StubValidator(),
        time_adapter=StubTimeAdapter(),
        factory=StubFactory(),
    )


def _truth_state(entity_id: str, epoch: Epoch) -> TruthState:
    """Build a minimal valid J2000 truth state for value-object tests."""
    return TruthState(
        entity_id=entity_id,
        cartesian_state=CartesianState(
            epoch=epoch,
            frame=FrameRef(kind=FrameKind.J2000),
            position_m=(1.0, 2.0, 3.0),
            velocity_mps=(4.0, 5.0, 6.0),
        ),
        mass_kg=1.0,
    )


# =============================👐Seperate👐=============================
# Immutable explicit-registry behavior
# =============================👐Seperate👐=============================


def test_registry_resolves_exact_backend_ref(
    fake_registration: ScienceBackendRegistration,
) -> None:
    """Registry returns the registration for its full plugin identity."""
    registry = PluginRegistry((fake_registration,))

    assert registry.resolve(fake_registration.manifest.ref) is fake_registration
    assert fake_registration.configuration_validator.calls == 0
    assert fake_registration.factory.create_calls == 0


def test_registry_rejects_duplicates_and_non_backend_manifest(
    fake_registration: ScienceBackendRegistration,
) -> None:
    """Registry accepts only one science-backend registration per exact reference."""
    with pytest.raises(ValueError, match="duplicate"):
        PluginRegistry((fake_registration, fake_registration))

    invalid = replace(
        fake_registration,
        manifest=fake_registration.manifest.model_copy(
            update={"kind": PluginKind.MEASUREMENT_MODEL}
        ),
    )
    with pytest.raises(ValueError, match="SCIENCE_BACKEND"):
        PluginRegistry((invalid,))


def test_registry_is_not_mutable_after_construction(
    fake_registration: ScienceBackendRegistration,
) -> None:
    """Registry exposes no registration mutation operation or writable state."""
    registry = PluginRegistry((fake_registration,))

    assert not hasattr(registry, "register")
    with pytest.raises(AttributeError):
        registry.registrations = ()


def test_registry_mapping_rejects_item_assignment_and_preserves_order(
    fake_registration: ScienceBackendRegistration,
) -> None:
    """The exposed mapping remains read-only and retains explicit insertion order."""
    second_registration = replace(
        fake_registration,
        manifest=fake_registration.manifest.model_copy(
            update={
                "ref": PluginRef(
                    plugin_id="sycasphere.testing.second-stub",
                    implementation_version="0.1.0",
                    interface_version=SchemaVersion(major=1, minor=0),
                )
            }
        ),
    )
    registry = PluginRegistry((fake_registration, second_registration))

    assert tuple(registry.registrations.values()) == (fake_registration, second_registration)
    with pytest.raises(TypeError):
        registry.registrations[fake_registration.manifest.ref] = fake_registration  # type: ignore[index]


def test_registry_reports_missing_exact_ref_as_structured_preparation_error(
    fake_registration: ScienceBackendRegistration,
) -> None:
    """A different implementation version is absent rather than loosely matched."""
    registry = PluginRegistry((fake_registration,))
    missing_ref = fake_registration.manifest.ref.model_copy(
        update={"implementation_version": "0.1.1"}
    )

    with pytest.raises(SimulationPreparationError) as exc_info:
        registry.resolve(missing_ref)

    assert exc_info.value.detail.category is ErrorCategory.PLUGIN_MISSING
    assert exc_info.value.detail.code == "plugin.backend_missing"
    assert exc_info.value.detail.context == {"plugin_ref": missing_ref.model_dump(mode="json")}


# =============================👐Seperate👐=============================
# Backend value-object validation
# =============================👐Seperate👐=============================


def test_maneuver_execution_requires_matching_state_lineage() -> None:
    """A maneuver execution cannot join snapshots for different entities."""
    epoch = Epoch(value="2026-07-30T00:00:00Z", time_scale=TimeScale.UTC)

    with pytest.raises(ValueError, match="same entity"):
        ManeuverExecution(
            executed_epoch=epoch,
            actual_delta_v_j2000_mps=(0.0, 0.0, 1.0),
            state_before=_truth_state("spacecraft.alpha", epoch),
            state_after=_truth_state("spacecraft.beta", epoch),
        )


def test_maneuver_execution_requires_states_at_execution_epoch() -> None:
    """A maneuver execution links both state snapshots to its execution epoch."""
    epoch = Epoch(value="2026-07-30T00:00:00Z", time_scale=TimeScale.UTC)
    other_epoch = Epoch(value="2026-07-30T00:00:01Z", time_scale=TimeScale.UTC)

    with pytest.raises(ValueError, match="state_after epoch"):
        ManeuverExecution(
            executed_epoch=epoch,
            actual_delta_v_j2000_mps=(0.0, 0.0, 1.0),
            state_before=_truth_state("spacecraft.alpha", epoch),
            state_after=_truth_state("spacecraft.alpha", other_epoch),
        )


def test_maneuver_execution_rejects_non_finite_or_non_float_delta_v() -> None:
    """A backend result exposes exactly three finite built-in float components."""
    epoch = Epoch(value="2026-07-30T00:00:00Z", time_scale=TimeScale.UTC)
    state = _truth_state("spacecraft.alpha", epoch)

    with pytest.raises(ValueError, match="finite built-in floats"):
        ManeuverExecution(
            executed_epoch=epoch,
            actual_delta_v_j2000_mps=(0.0, 0.0, float("nan")),
            state_before=state,
            state_after=state,
        )


def test_maneuver_execution_rejects_mutable_delta_v_list() -> None:
    """A frozen public value object must not retain a caller-owned mutable vector."""
    epoch = Epoch(value="2026-07-30T00:00:00Z", time_scale=TimeScale.UTC)
    state = _truth_state("spacecraft.alpha", epoch)

    with pytest.raises(ValueError, match="actual delta-v must be a tuple"):
        ManeuverExecution(
            executed_epoch=epoch,
            actual_delta_v_j2000_mps=[0.0, 0.0, 1.0],  # type: ignore[arg-type]
            state_before=state,
            state_after=state,
        )


def test_maneuver_execution_rejects_wrong_length_delta_v_tuple() -> None:
    """A backend result must expose exactly three delta-v components."""
    epoch = Epoch(value="2026-07-30T00:00:00Z", time_scale=TimeScale.UTC)
    state = _truth_state("spacecraft.alpha", epoch)

    with pytest.raises(ValueError, match="actual delta-v must contain three components"):
        ManeuverExecution(
            executed_epoch=epoch,
            actual_delta_v_j2000_mps=(0.0, 1.0),  # type: ignore[arg-type]
            state_before=state,
            state_after=state,
        )


def test_maneuver_execution_rejects_integer_delta_v_component() -> None:
    """A backend result rejects integer components at the strict float boundary."""
    epoch = Epoch(value="2026-07-30T00:00:00Z", time_scale=TimeScale.UTC)
    state = _truth_state("spacecraft.alpha", epoch)

    with pytest.raises(
        ValueError, match="actual delta-v components must be finite built-in floats"
    ):
        ManeuverExecution(
            executed_epoch=epoch,
            actual_delta_v_j2000_mps=(0.0, 0.0, 1),  # type: ignore[arg-type]
            state_before=state,
            state_after=state,
        )
