# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_public_api.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.0.0

■ 用途说明:
  锁定 SycaSphere Core 的公开导入契约和 Pydantic 模式。

■ 主要函数功能:
  - test_public_contract_exports_are_exact: 验证受审查的公开名称集合。
  - test_public_model_schemas_match_snapshot: 验证公开模型 JSON Schema 快照。

■ 功能特性:
  ✓ 公开 API 变更必须经测试审查。
  ✓ 模式快照使用确定性 JSON 比较。

■ 更新日志:
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
    "CartesianState",
    "CoordinateRepresentation",
    "EarthFixedFrameSpec",
    "EntityDefinition",
    "EntityType",
    "Epoch",
    "ErrorCategory",
    "ErrorDetail",
    "FrameKind",
    "FrameRef",
    "GeodeticLocation",
    "GroundStationDefinition",
    "ModelRef",
    "OtherSpaceObjectDefinition",
    "PluginKind",
    "PluginManifest",
    "PluginRef",
    "ReferenceEllipsoid",
    "ResourceRequirements",
    "RigidTransform",
    "SchemaVersion",
    "SensorAxes",
    "SensorDefinition",
    "SensorType",
    "SpaceObjectPhysicalProperties",
    "SpacecraftDefinition",
    "TimeScale",
}


def test_public_contract_exports_are_exact() -> None:
    """Only approved Task 2-6 Core contract names may be exported through ``__all__``."""
    assert set(core.__all__) == EXPECTED_PUBLIC_CONTRACTS


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
    )
    schemas = {model.__name__: model.model_json_schema() for model in models}
    schemas["EntityDefinition"] = TypeAdapter(core.EntityDefinition).json_schema()
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
