# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : model_refs.py
创建者    : Sycamore
创建日期  : 2026-07-22
最后修改  : 2026-07-22
版本号    : v1.0.0

■ 用途说明:
  定义后端中立、仅数据化且深度不可变的科学子模型配置引用。

■ 主要函数功能:
  - ModelRef: 保存稳定模型 ID、接口模式版本和有限 JSON 配置。

■ 功能特性:
  ✓ 配置在输入边界复制并深度冻结。
  ✓ 序列化恢复普通 JSON 对象且不加载模型实现。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-22): 创建通用 ModelRef 契约。

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

type StableModelId = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1),
]


# =============================👐Seperate👐==============================
# Immutable scientific-model references
# =============================👐Seperate👐==============================
class ModelRef(BaseModel):
    """A data-only reference to a configured scientific submodel."""

    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)

    model_id: StableModelId
    interface_version: SchemaVersion
    configuration: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("configuration", mode="before")
    @classmethod
    def normalize_configuration(cls, value: Any) -> dict[str, JsonValue]:
        """Normalize a supported mapping and reject non-finite or private values."""
        return normalize_json_object(value)

    @field_validator("configuration")
    @classmethod
    def freeze_configuration(cls, value: Mapping[str, JsonValue]) -> Mapping[str, FrozenJsonValue]:
        """Store an alias-independent immutable configuration snapshot."""
        return freeze_json_object(value)

    @field_serializer("configuration", when_used="always")
    def serialize_configuration(self, value: Mapping[str, FrozenJsonValue]) -> dict[str, JsonValue]:
        """Serialize the immutable snapshot as ordinary JSON values."""
        return {key: thaw_json_value(nested) for key, nested in value.items()}
