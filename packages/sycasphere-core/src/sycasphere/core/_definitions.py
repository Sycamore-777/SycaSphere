# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : _definitions.py
创建者    : Sycamore
创建日期  : 2026-07-22
最后修改  : 2026-07-22
版本号    : v1.0.0

■ 用途说明:
  为 Core 内部定义对象集中提供身份、修订、标签和不可变 metadata 验证。

■ 主要函数功能:
  - _normalize_unique_strings: 规范化非空、唯一字符串序列。
  - _DefinitionBase: 保存定义对象共享字段并深度冻结 metadata。

■ 功能特性:
  ✓ 修订号使用严格正整数。
  ✓ 默认和显式 metadata 均深度冻结并稳定序列化。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-22): 创建 Core 私有共享定义验证。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    Strict,
    StringConstraints,
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

type DefinitionString = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1),
]
type Revision = Annotated[int, Strict(), Field(gt=0)]


def _normalize_unique_strings(value: Any, field_name: str) -> tuple[str, ...]:
    """Return stripped unique non-blank strings from a collection input."""
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError(f"{field_name} must be a collection of strings")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must contain only strings")

    normalized = tuple(item.strip() for item in value)
    if any(not item for item in normalized):
        raise ValueError(f"{field_name} must not contain blank values")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


# =============================👐Seperate👐==============================
# Private immutable definition base
# =============================👐Seperate👐==============================
class _DefinitionBase(BaseModel):
    """Shared immutable fields for versioned Core definition objects."""

    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)

    id: DefinitionString
    name: DefinitionString
    revision: Revision
    schema_version: SchemaVersion
    tags: frozenset[str] = Field(default_factory=frozenset)
    metadata: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: Any) -> tuple[str, ...]:
        """Validate user-search tags before freezing them as a set."""
        return _normalize_unique_strings(value, "tags")

    @field_serializer("tags", when_used="always")
    def serialize_tags(self, value: frozenset[str]) -> list[str]:
        """Serialize tags in deterministic lexical order."""
        return sorted(value)

    @field_validator("metadata", mode="before")
    @classmethod
    def normalize_metadata(cls, value: Any) -> dict[str, JsonValue]:
        """Validate finite public JSON metadata before Pydantic coercion."""
        return normalize_json_object(value)

    @field_validator("metadata")
    @classmethod
    def freeze_metadata(cls, value: Mapping[str, JsonValue]) -> Mapping[str, FrozenJsonValue]:
        """Store an alias-independent immutable metadata snapshot."""
        return freeze_json_object(value)

    @field_serializer("metadata", when_used="always")
    def serialize_metadata(self, value: Mapping[str, FrozenJsonValue]) -> dict[str, JsonValue]:
        """Serialize immutable metadata as ordinary JSON values."""
        return {key: thaw_json_value(nested) for key, nested in value.items()}
