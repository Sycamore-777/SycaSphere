# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : readme_fake_run.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  作为 Engine README FakeBackend 批运行示例的可执行单一来源。

■ 主要函数功能:
  - main: 准备并执行有限时间、有限内存的确定性 FakeBackend 示例。

■ 功能特性:
  ✓ 使用 FakeBackend 三个精确稳定模型 ID
  ✓ 通过有界内存 sink 打印轻量执行结果计数

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

# README_EXAMPLE_START
from sycasphere.core import (
    CartesianState,
    CentralBody,
    EnvironmentDefinition,
    Epoch,
    FrameKind,
    FrameRef,
    ImpulsiveManeuverSpec,
    ManeuverCapability,
    ManeuverCommand,
    ManeuverType,
    ModelRef,
    OutputProduct,
    OutputRequirement,
    OutputSampling,
    PluginRef,
    SamplingRule,
    SchemaVersion,
    ScienceBackendBinding,
    SimulationDefinition,
    SimulationRunRequest,
    SimulationTimeRange,
    SpacecraftDefinition,
    SpaceObjectPhysicalProperties,
    TimeScale,
)
from sycasphere.engine import (
    CancellationToken,
    InMemoryOutputSink,
    PluginRegistry,
    SimulationEngine,
)
from sycasphere.engine.testing import fake_backend_registration


def main() -> None:
    """Run one bounded deterministic compatibility simulation."""
    version = SchemaVersion(major=1, minor=0)
    start = Epoch(value="2026-07-30T00:00:00Z", time_scale=TimeScale.UTC)

    def fake_model(model_id: str) -> ModelRef:
        return ModelRef(
            model_id=model_id,
            interface_version=version,
            configuration={},
        )

    spacecraft = SpacecraftDefinition(
        id="spacecraft-1",
        name="Fake spacecraft",
        revision=1,
        schema_version=version,
        initial_state=CartesianState(
            epoch=start,
            frame=FrameRef(kind=FrameKind.J2000),
            position_m=(7_000_000.0, 0.0, 0.0),
            velocity_mps=(0.0, 7_500.0, 0.0),
        ),
        physical_properties=SpaceObjectPhysicalProperties(
            mass_kg=500.0,
            cross_section_area_m2=10.0,
        ),
        dynamics_model=fake_model("sycasphere.testing.constant-velocity"),
        attitude_model=fake_model("sycasphere.testing.identity-attitude"),
        maneuver_capability=ManeuverCapability(
            supported_types=frozenset({ManeuverType.IMPULSIVE}),
            propulsion_model=fake_model("sycasphere.testing.impulsive-propulsion"),
        ),
    )
    request = SimulationRunRequest(
        schema_version=version,
        simulation_definition=SimulationDefinition(
            id="readme-fake-run",
            name="README FakeBackend run",
            revision=1,
            schema_version=version,
            synchronization_epoch=start,
            environment=EnvironmentDefinition(
                id="fake-earth",
                name="Fake Earth",
                revision=1,
                schema_version=version,
                central_body=CentralBody.EARTH,
            ),
            entities=(spacecraft,),
        ),
        time_range=SimulationTimeRange(
            start=start,
            end=Epoch(value="2026-07-30T00:00:10Z", time_scale=TimeScale.UTC),
        ),
        output_sampling=OutputSampling(
            rules=(
                SamplingRule(product=OutputProduct.TRUTH_STATE, interval_s=5.0),
                SamplingRule(product=OutputProduct.ATTITUDE_STATE, interval_s=5.0),
            )
        ),
        command_timeline=(
            ManeuverCommand(
                command_id="readme-impulse",
                spacecraft_id="spacecraft-1",
                epoch=Epoch(value="2026-07-30T00:00:05Z", time_scale=TimeScale.UTC),
                maneuver=ImpulsiveManeuverSpec(
                    delta_v_mps=(1.0, 0.0, 0.0),
                    frame=FrameRef(kind=FrameKind.J2000),
                ),
            ),
        ),
        backend=ScienceBackendBinding(
            ref=PluginRef(
                plugin_id="sycasphere.testing.fake",
                implementation_version="0.1.0",
                interface_version=version,
            ),
            configuration={},
        ),
        random_seed=20260730,
        output_requirements=frozenset(
            {
                OutputRequirement.TRUTH,
                OutputRequirement.ATTITUDE,
            }
        ),
    )

    registry = PluginRegistry((fake_backend_registration(),))
    engine = SimulationEngine(registry)
    manifest = engine.prepare(request)
    sink = InMemoryOutputSink(max_records=32)
    result = engine.run(manifest, sink, CancellationToken())

    print(f"Truth states: {result.output_summary.truth_state_count}")
    print(f"Attitude states: {result.output_summary.attitude_state_count}")
    print(f"Truth maneuvers: {result.output_summary.truth_maneuver_count}")


if __name__ == "__main__":
    main()
# README_EXAMPLE_END
