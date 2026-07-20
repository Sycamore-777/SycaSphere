# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_plugins.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.1.0

■ 用途说明:
  验证后端中立插件标识、能力和资源声明契约。

■ 主要函数功能:
  - test_manifest_exposes_data_only_capability_contract: 验证完整清单和能力查询。
  - test_plugin_ref_rejects_non_semver_implementation_versions: 验证 SemVer 2.0 版本格式。

■ 功能特性:
  ✓ 覆盖插件清单、能力、版本兼容性和边界验证。
  ✓ 覆盖配置模式有限值、深度不可变性、输入别名隔离和确定性序列化。

■ 更新日志:
  v1.1.0 (2026-07-20): 覆盖共享有限 JSON 规则和能力规范排序输出。
  v1.0.1 (2026-07-20): 覆盖配置模式冻结、标识语法和 ASCII SemVer。
  v1.0.0 (2026-07-20): 创建插件清单契约测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from sycasphere.core import (
    PluginKind,
    PluginManifest,
    PluginRef,
    ResourceRequirements,
    SchemaVersion,
)

_ARABIC_INDIC_ONE = chr(0x0661)
_ARABIC_INDIC_TWO = chr(0x0662)
_ARABIC_INDIC_THREE = chr(0x0663)


# =============================👐Seperate👐==============================
# Plugin-manifest contract tests
# =============================👐Seperate👐==============================
def _complete_manifest() -> PluginManifest:
    return PluginManifest(
        ref=PluginRef(
            plugin_id="sycasphere.orekit",
            implementation_version="1.2.3-rc.1+build.42",
            interface_version=SchemaVersion(major=1, minor=2),
        ),
        kind=PluginKind.SCIENCE_BACKEND,
        capabilities=["propagation.numerical", "frames.j2000"],
        configuration_schema={
            "type": "object",
            "properties": {"step_size_s": {"type": "number", "minimum": 0}},
            "required": ["step_size_s"],
        },
        deterministic=True,
        resources=ResourceRequirements(requires_jdk=True, minimum_memory_mb=512),
    )


def test_manifest_exposes_data_only_capability_contract() -> None:
    manifest = _complete_manifest()

    assert manifest.ref.plugin_id == "sycasphere.orekit"
    assert manifest.ref.implementation_version == "1.2.3-rc.1+build.42"
    assert manifest.kind is PluginKind.SCIENCE_BACKEND
    assert manifest.capabilities == frozenset({"propagation.numerical", "frames.j2000"})
    assert manifest.configuration_schema["type"] == "object"
    assert manifest.deterministic
    assert manifest.resources == ResourceRequirements(requires_jdk=True, minimum_memory_mb=512)
    assert manifest.supports("propagation.numerical")
    assert not manifest.supports("measurements.range")


def test_manifest_deeply_freezes_configuration_schema() -> None:
    manifest = _complete_manifest()

    with pytest.raises(TypeError):
        manifest.configuration_schema["type"] = "array"
    with pytest.raises(TypeError):
        manifest.configuration_schema["properties"]["step_size_s"]["minimum"] = 1
    with pytest.raises(TypeError):
        manifest.configuration_schema["required"][0] = "other"


def test_manifest_isolated_from_configuration_schema_input_mutations() -> None:
    configuration_schema = {
        "type": "object",
        "properties": {"step_size_s": {"type": "number", "minimum": 0}},
        "required": ["step_size_s"],
    }
    manifest_data = _complete_manifest().model_dump(mode="python")
    manifest_data["configuration_schema"] = configuration_schema
    manifest = PluginManifest.model_validate(manifest_data)

    configuration_schema["properties"]["step_size_s"]["minimum"] = 1
    configuration_schema["required"].append("other")

    assert manifest.configuration_schema["properties"]["step_size_s"]["minimum"] == 0
    assert manifest.configuration_schema["required"] == ("step_size_s",)


def test_manifest_configuration_schema_json_dump_and_round_trip() -> None:
    manifest = _complete_manifest()

    serialized = manifest.model_dump(mode="json")
    restored = PluginManifest.model_validate(serialized)

    assert serialized["configuration_schema"]["required"] == ["step_size_s"]
    assert restored.model_dump(mode="json") == serialized


@pytest.mark.parametrize("invalid_value", [math.nan, math.inf, -math.inf])
def test_manifest_rejects_non_finite_configuration_schema_values(
    invalid_value: float,
) -> None:
    manifest_data = _complete_manifest().model_dump(mode="python")
    manifest_data["configuration_schema"] = {
        "properties": {"threshold": {"default": [invalid_value]}},
    }

    with pytest.raises(ValidationError):
        PluginManifest.model_validate(manifest_data)


def test_manifest_serializes_capabilities_in_canonical_sorted_order() -> None:
    first_data = _complete_manifest().model_dump(mode="python")
    second_data = _complete_manifest().model_dump(mode="python")
    first_data["capabilities"] = ["propagation.numerical", "frames.j2000"]
    second_data["capabilities"] = ["frames.j2000", "propagation.numerical"]

    first = PluginManifest.model_validate(first_data)
    second = PluginManifest.model_validate(second_data)

    expected = ["frames.j2000", "propagation.numerical"]
    assert first.model_dump(mode="json")["capabilities"] == expected
    assert second.model_dump(mode="json")["capabilities"] == expected
    assert first.model_dump_json() == second.model_dump_json()


def test_manifest_json_schema_describes_configuration_schema() -> None:
    schema = PluginManifest.model_json_schema()

    assert schema["properties"]["configuration_schema"]["type"] == "object"


def test_manifest_uses_schema_version_for_interface_compatibility() -> None:
    manifest = _complete_manifest()

    assert manifest.is_interface_compatible_with(SchemaVersion(major=1, minor=1))
    assert not manifest.is_interface_compatible_with(SchemaVersion(major=2, minor=0))


def test_plugin_kind_exposes_only_approved_first_version_kinds() -> None:
    assert {kind.value for kind in PluginKind} == {
        "SCIENCE_BACKEND",
        "MEASUREMENT_MODEL",
        "ERROR_MODEL",
        "LINK_MODEL",
    }


@pytest.mark.parametrize(
    "capabilities",
    [
        [],
        ["propagation.numerical", "propagation.numerical"],
        [""],
        ["propagation. numerical"],
        ["Propagation.numerical"],
        ["propagation..numerical"],
        ["propagation_"],
        ["-propagation"],
    ],
)
def test_manifest_rejects_empty_duplicate_or_invalid_capabilities(
    capabilities: list[str],
) -> None:
    manifest_data = _complete_manifest().model_dump(mode="python")
    manifest_data["capabilities"] = capabilities

    with pytest.raises(ValidationError):
        PluginManifest.model_validate(manifest_data)


@pytest.mark.parametrize(
    "plugin_id",
    ["", "Sycasphere.orekit", "sycasphere.orekit ", "sycasphere..orekit", "sycasphere-"],
)
def test_plugin_ref_rejects_invalid_stable_plugin_ids(plugin_id: str) -> None:
    with pytest.raises(ValidationError):
        PluginRef(
            plugin_id=plugin_id,
            implementation_version="1.2.3",
            interface_version=SchemaVersion(major=1, minor=0),
        )


@pytest.mark.parametrize(
    "identifier",
    ["sycasphere", "sycasphere.orekit", "sycasphere_orekit", "sycasphere-orekit"],
)
def test_plugin_ref_accepts_single_and_explicitly_separated_identifiers(identifier: str) -> None:
    ref = PluginRef(
        plugin_id=identifier,
        implementation_version="1.2.3",
        interface_version=SchemaVersion(major=1, minor=0),
    )

    assert ref.plugin_id == identifier


def test_manifest_accepts_single_capability_identifier() -> None:
    manifest_data = _complete_manifest().model_dump(mode="python")
    manifest_data["capabilities"] = ["propagation"]

    manifest = PluginManifest.model_validate(manifest_data)

    assert manifest.supports("propagation")


@pytest.mark.parametrize(
    "implementation_version",
    [
        "1.2",
        "v1.2.3",
        "01.2.3",
        "1.02.3",
        "1.2.03",
        "1.2.3-01",
        "1.2.3+",
        "1" + _ARABIC_INDIC_TWO + ".3",
        "1.2" + _ARABIC_INDIC_THREE + ".3",
        "1.2.3-rc." + _ARABIC_INDIC_ONE,
    ],
)
def test_plugin_ref_rejects_non_semver_implementation_versions(
    implementation_version: str,
) -> None:
    with pytest.raises(ValidationError):
        PluginRef(
            plugin_id="sycasphere.orekit",
            implementation_version=implementation_version,
            interface_version=SchemaVersion(major=1, minor=0),
        )


@pytest.mark.parametrize(
    "model_type, data",
    [
        (
            PluginRef,
            {
                "plugin_id": "sycasphere.orekit",
                "implementation_version": "1.2.3",
                "interface_version": {"major": 1, "minor": 0},
                "python_import_path": "private.module",
            },
        ),
        (
            ResourceRequirements,
            {"requires_network": False, "loader": "private.module"},
        ),
        (
            PluginManifest,
            {
                "ref": {
                    "plugin_id": "sycasphere.orekit",
                    "implementation_version": "1.2.3",
                    "interface_version": {"major": 1, "minor": 0},
                },
                "kind": "SCIENCE_BACKEND",
                "capabilities": ["propagation.numerical"],
                "configuration_schema": {},
                "deterministic": True,
                "resources": {},
                "loader": "private.module",
            },
        ),
    ],
)
def test_plugin_contracts_reject_unknown_fields(
    model_type: type[PluginManifest] | type[PluginRef] | type[ResourceRequirements],
    data: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        model_type.model_validate(data)


def test_plugin_manifest_is_frozen() -> None:
    manifest = _complete_manifest()

    with pytest.raises(ValidationError):
        manifest.deterministic = False
