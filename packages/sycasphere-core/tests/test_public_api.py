# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_public_api.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-30
版本号    : v1.3.0

■ 用途说明:
  锁定 SycaSphere Core 的公开导入契约和 Pydantic 模式。

■ 主要函数功能:
  - test_public_contract_exports_are_exact: 验证受审查的公开名称集合。
  - test_public_model_schemas_match_snapshot: 验证公开模型 JSON Schema 快照。
  - test_discriminated_public_schemas_expose_discriminators: 验证判别联合的稳定键。

■ 功能特性:
  ✓ 公开 API 变更必须经测试审查。
  ✓ 模式快照使用确定性 JSON 比较。
  ✓ 运行输入与执行清单公开契约受到审查。
  ✓ Truth、Observation 与 Delivery 公开模式受到泄漏和判别器审查。

■ 更新日志:
  v1.2.0 (2026-07-28): 覆盖 Truth、Observation 与 Delivery 公开契约。
  v1.1.0 (2026-07-26): 覆盖仿真输入和执行清单公开契约。
  v1.0.0 (2026-07-20): 新增公开 API 和模式快照测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sycasphere.core as core
from pydantic import BaseModel, TypeAdapter

# =============================👐Seperate👐=============================
# Public Core contract tests
# =============================👐Seperate👐=============================
EXPECTED_PUBLIC_CONTRACTS = {
    "AttitudeState",
    "CartesianState",
    "CentralBody",
    "CoordinateRepresentation",
    "CustomMeasurementSchemaRef",
    "DerivedRandomStream",
    "DeliveryOutcome",
    "DeliverySummary",
    "EarthFixedFrameSpec",
    "EntityDefinition",
    "EntityType",
    "EnvironmentDefinition",
    "Epoch",
    "ErrorCategory",
    "ErrorDetail",
    "EventOrderingPolicy",
    "ExplicitObservationSchedule",
    "ExternalDataRef",
    "FiniteBurnManeuverSpec",
    "FrameKind",
    "FrameRef",
    "GeodeticLocation",
    "GeometryStatus",
    "GroundStationDefinition",
    "IdealObservation",
    "ImpulsiveManeuverSpec",
    "KnownObjectSubjectRef",
    "ManeuverCapability",
    "ManeuverCommand",
    "ManeuverSpec",
    "ManeuverTruthSource",
    "ManeuverType",
    "MeasurementType",
    "MeasurementUncertainty",
    "ModelRef",
    "ObservationChannel",
    "ObservationDeliveryRecord",
    "ObservationEvent",
    "ObservationMeasurement",
    "ObservationSchedule",
    "ObservationScheduleKind",
    "ObservationSubjectRef",
    "OtherSpaceObjectDefinition",
    "OutputProduct",
    "OutputRequirement",
    "OutputSampling",
    "PeriodicObservationSchedule",
    "PlannedTruthManeuver",
    "PluginKind",
    "PluginManifest",
    "PluginRef",
    "PreparedManeuverEntry",
    "PreparedManeuverSource",
    "PreparedTimeline",
    "ReferenceEllipsoid",
    "ReportedObservation",
    "ResolvedPluginRecord",
    "ResourceRequirements",
    "RigidTransform",
    "SamplingRule",
    "SchemaVersion",
    "ScienceBackendBinding",
    "SensorAxes",
    "SensorDefinition",
    "SensorType",
    "SimulationDefinition",
    "SimulationExecutionManifest",
    "SimulationExecutionResult",
    "SimulationExecutionStatus",
    "SimulationOutputSummary",
    "SimulationRunRequest",
    "SimulationTimeRange",
    "SpaceObjectPhysicalProperties",
    "SpacecraftDefinition",
    "StreamingObservationEnvelope",
    "TimeScale",
    "TrackletSubjectRef",
    "TruthManeuver",
    "TruthState",
    "UnassociatedSubjectRef",
}


def test_public_contract_exports_are_exact() -> None:
    """Only approved Task 1-6 Core contract names may be exported through ``__all__``."""
    assert set(core.__all__) == EXPECTED_PUBLIC_CONTRACTS


def test_sensor_schema_requires_at_least_one_measurement_model() -> None:
    """Published SensorDefinition schema must reject an empty model collection."""
    schema = core.SensorDefinition.model_json_schema()

    assert schema["properties"]["measurement_models"]["minItems"] == 1


def _public_model_schemas() -> dict[str, dict[str, Any]]:
    """Return JSON Schemas for the reviewed public Pydantic model surface."""
    models: tuple[type[BaseModel], ...] = (
        core.SchemaVersion,
        core.ErrorDetail,
        core.Epoch,
        core.EarthFixedFrameSpec,
        core.FrameRef,
        core.CartesianState,
        core.PluginRef,
        core.ResourceRequirements,
        core.PluginManifest,
        core.ModelRef,
        core.RigidTransform,
        core.SensorAxes,
        core.GeodeticLocation,
        core.SensorDefinition,
        core.SpaceObjectPhysicalProperties,
        core.SpacecraftDefinition,
        core.OtherSpaceObjectDefinition,
        core.GroundStationDefinition,
        core.ExternalDataRef,
        core.EnvironmentDefinition,
        core.SimulationDefinition,
        core.ManeuverCapability,
        core.ImpulsiveManeuverSpec,
        core.FiniteBurnManeuverSpec,
        core.PlannedTruthManeuver,
        core.ManeuverCommand,
        core.SimulationTimeRange,
        core.SamplingRule,
        core.OutputSampling,
        core.PeriodicObservationSchedule,
        core.ExplicitObservationSchedule,
        core.ScienceBackendBinding,
        core.SimulationRunRequest,
        core.ResolvedPluginRecord,
        core.DerivedRandomStream,
        core.PreparedManeuverEntry,
        core.PreparedTimeline,
        core.SimulationExecutionManifest,
        core.SimulationOutputSummary,
        core.SimulationExecutionResult,
        core.AttitudeState,
        core.TruthState,
        core.TruthManeuver,
        core.KnownObjectSubjectRef,
        core.TrackletSubjectRef,
        core.UnassociatedSubjectRef,
        core.CustomMeasurementSchemaRef,
        core.ObservationMeasurement,
        core.MeasurementUncertainty,
        core.ObservationEvent,
        core.IdealObservation,
        core.ReportedObservation,
        core.ObservationDeliveryRecord,
        core.DeliverySummary,
        core.StreamingObservationEnvelope,
    )
    schemas = {model.__name__: model.model_json_schema() for model in models}
    schemas["SimulationExecutionStatus"] = TypeAdapter(core.SimulationExecutionStatus).json_schema()
    schemas["EntityDefinition"] = TypeAdapter(core.EntityDefinition).json_schema()
    schemas["ManeuverSpec"] = TypeAdapter(core.ManeuverSpec).json_schema()
    schemas["ObservationSchedule"] = TypeAdapter(core.ObservationSchedule).json_schema()
    schemas["ObservationSubjectRef"] = TypeAdapter(core.ObservationSubjectRef).json_schema()
    return schemas


def _serialized_public_model_schemas() -> str:
    """Return a stable UTF-8 text representation for the reviewed model schemas."""
    return (
        json.dumps(
            _public_model_schemas(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def test_public_model_schemas_match_snapshot() -> None:
    """Reviewed model JSON Schemas must match the deterministic UTF-8 snapshot."""
    snapshot_path = Path(__file__).parent / "snapshots" / "core-schemas.json"
    expected_text = snapshot_path.read_text(encoding="utf-8")

    assert json.loads(expected_text) == _public_model_schemas()
    assert expected_text == _serialized_public_model_schemas()


def test_execution_status_enum_schema_is_snapshotted() -> None:
    """The standalone terminal-status enum remains in the reviewed public schema set."""
    schema = _public_model_schemas()["SimulationExecutionStatus"]

    assert schema["enum"] == ["COMPLETED", "CANCELLED"]


def test_discriminated_public_schemas_expose_discriminators() -> None:
    """Published unions must retain their stable public discriminator properties."""
    schemas = _public_model_schemas()

    assert schemas["ManeuverSpec"]["discriminator"]["propertyName"] == "maneuver_type"
    assert schemas["ObservationSchedule"]["discriminator"]["propertyName"] == "schedule_type"
    assert schemas["ObservationSubjectRef"]["discriminator"]["propertyName"] == "kind"
    assert (
        schemas["StreamingObservationEnvelope"]["properties"]["observation"]["discriminator"][
            "propertyName"
        ]
        == "channel"
    )


def test_algorithm_visible_schemas_exclude_truth_and_realized_errors() -> None:
    """Ideal/Reported schemas must not expose Truth identity or realized error samples."""
    schemas = _public_model_schemas()
    forbidden_properties = {
        "truth_target_entity_id",
        "truth_state",
        "actual_error",
        "noise_sample",
        "true_bias",
        "truth_residual",
    }

    assert forbidden_properties.isdisjoint(schemas["IdealObservation"]["properties"])
    assert forbidden_properties.isdisjoint(schemas["ReportedObservation"]["properties"])


def test_execution_manifest_excludes_runtime_lifecycle_fields() -> None:
    """The immutable manifest contains scientific inputs, not runtime state or results."""
    fields = set(core.SimulationExecutionManifest.model_fields)

    assert fields.isdisjoint(
        {
            "prepared_at",
            "started_at",
            "ended_at",
            "status",
            "error",
            "output_hashes",
            "output_path",
            "runtime_command_journal",
        }
    )
