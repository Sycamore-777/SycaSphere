# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : plugins.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.1.0

■ 用途说明:
  定义后端中立、仅数据化且深度不可变的插件标识、能力和资源声明契约。

■ 主要函数功能:
  - PluginManifest.supports: 查询声明的稳定能力标识。
  - PluginManifest.is_interface_compatible_with: 判断接口模式版本兼容性。

■ 功能特性:
  ✓ 验证稳定插件标识、能力标识和 SemVer 2.0 实现版本。
  ✓ 冻结有限配置模式嵌套映射和序列，防止输入别名修改。
  ✓ 规范排序能力数组以获得确定性公共序列化。
  ✓ 不导入、加载或初始化任何插件实现。

■ 更新日志:
  v1.1.0 (2026-07-20): 复用共享有限 JSON 工具并规范排序能力序列化。
  v1.0.1 (2026-07-20): 深度冻结配置模式并扩展稳定标识语法。
  v1.0.0 (2026-07-20): 创建插件身份和能力清单契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
    NonNegativeInt,
    field_serializer,
    field_validator,
)
from sycasphere.core._json import (
    FrozenJsonValue,
    freeze_json_object,
    normalize_json_object,
    thaw_json_value,
)
from sycasphere.core.schema import SchemaVersion

# =============================👐Seperate👐==============================
# Stable plugin-identifier validation
# =============================👐Seperate👐==============================
_SEGMENTED_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_SEMVER_PRERELEASE_IDENTIFIER = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
_SEMVER_BUILD_IDENTIFIER = r"[0-9A-Za-z-]+"
_SEMVER_PATTERN = re.compile(
    rf"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    rf"(?:-{_SEMVER_PRERELEASE_IDENTIFIER}(?:\.{_SEMVER_PRERELEASE_IDENTIFIER})*)?"
    rf"(?:\+{_SEMVER_BUILD_IDENTIFIER}(?:\.{_SEMVER_BUILD_IDENTIFIER})*)?$"
)


def _validate_segmented_identifier(value: str, field_name: str) -> str:
    """Return a lowercase ASCII identifier with optional explicit segment separators."""
    if not _SEGMENTED_IDENTIFIER_PATTERN.fullmatch(value):
        msg = (
            f"{field_name} must contain lowercase ASCII alphanumeric segments separated by "
            "'.', '_', or '-', for example 'sycasphere.orekit'"
        )
        raise ValueError(msg)
    return value


# =============================👐Seperate👐==============================
# Data-only plugin manifest contracts
# =============================👐Seperate👐==============================
class PluginKind(StrEnum):
    """First-version plugin kinds the engine may select by declared capability."""

    SCIENCE_BACKEND = "SCIENCE_BACKEND"
    MEASUREMENT_MODEL = "MEASUREMENT_MODEL"
    ERROR_MODEL = "ERROR_MODEL"
    LINK_MODEL = "LINK_MODEL"


class PluginRef(BaseModel):
    """Immutable identity and public interface version for a plugin implementation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plugin_id: str
    implementation_version: str
    interface_version: SchemaVersion

    @field_validator("plugin_id")
    @classmethod
    def validate_plugin_id(cls, value: str) -> str:
        """Require a stable, lowercase ASCII plugin identifier."""
        return _validate_segmented_identifier(value, "plugin_id")

    @field_validator("implementation_version")
    @classmethod
    def validate_implementation_version(cls, value: str) -> str:
        """Require a canonical SemVer 2.0 implementation version."""
        if not _SEMVER_PATTERN.fullmatch(value):
            raise ValueError("implementation_version must be a canonical SemVer 2.0 version")
        return value


class ResourceRequirements(BaseModel):
    """Resource requirements inspectable without importing a plugin implementation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requires_jdk: bool = False
    requires_network: bool = False
    minimum_memory_mb: NonNegativeInt | None = None


class PluginManifest(BaseModel):
    """Immutable, data-only declaration used to select compatible plugin capabilities."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ref: PluginRef
    kind: PluginKind
    capabilities: frozenset[str]
    configuration_schema: Mapping[str, JsonValue]
    deterministic: bool
    resources: ResourceRequirements

    @field_validator("configuration_schema", mode="before")
    @classmethod
    def normalize_configuration_schema(cls, value: Any) -> dict[str, JsonValue]:
        """Normalize supported mappings and reject non-finite or non-JSON values."""
        return normalize_json_object(value)

    @field_validator("configuration_schema")
    @classmethod
    def freeze_configuration_schema(
        cls, value: Mapping[str, JsonValue]
    ) -> Mapping[str, FrozenJsonValue]:
        """Store an immutable, alias-independent configuration-schema snapshot."""
        return freeze_json_object(value)

    @field_serializer("configuration_schema", when_used="always")
    def serialize_configuration_schema(
        self, value: Mapping[str, FrozenJsonValue]
    ) -> dict[str, JsonValue]:
        """Serialize the immutable snapshot as ordinary JSON objects and arrays."""
        return {key: thaw_json_value(nested_value) for key, nested_value in value.items()}

    @field_serializer("capabilities", when_used="always")
    def serialize_capabilities(self, value: frozenset[str]) -> list[str]:
        """Serialize capabilities as a canonical sorted JSON array."""
        return sorted(value)

    @field_validator("capabilities", mode="before")
    @classmethod
    def validate_capabilities_before_freezing(cls, value: Any) -> tuple[str, ...]:
        """Reject malformed or duplicate capabilities before Pydantic creates a frozenset."""
        if not isinstance(value, (frozenset, list, set, tuple)):
            raise ValueError("capabilities must be a collection of stable capability identifiers")

        capabilities = tuple(value)
        if not capabilities:
            raise ValueError("capabilities must not be empty")
        if not all(isinstance(capability, str) for capability in capabilities):
            raise ValueError("capabilities must contain only strings")
        if len(capabilities) != len(set(capabilities)):
            raise ValueError("capabilities must not contain duplicates")

        for capability in capabilities:
            _validate_segmented_identifier(capability, "capability")
        return capabilities

    def supports(self, capability: str) -> bool:
        """Return whether this manifest declares the requested stable capability."""
        return capability in self.capabilities

    def is_interface_compatible_with(self, required: SchemaVersion) -> bool:
        """Return whether this manifest's interface version satisfies ``required``."""
        return self.ref.interface_version.satisfies(required)
