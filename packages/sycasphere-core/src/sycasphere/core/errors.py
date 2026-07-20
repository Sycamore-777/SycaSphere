# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : errors.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.1.0

■ 用途说明:
  定义 Core 公共边界使用的结构化错误类别和可安全序列化的错误负载。

■ 主要函数功能:
  - ErrorCategory: 声明稳定的错误类别值。
  - ErrorDetail: 承载机器可读错误代码、可选运行引用和安全 JSON 诊断上下文。

■ 功能特性:
  ✓ 拒绝未知字段、非有限 JSON 值和保留的异常诊断键。
  ✓ 深度冻结上下文且不承载 Python/Java 异常或堆栈跟踪对象。

■ 待办事项:
  - 无

■ 更新日志:
  v1.1.0 (2026-07-20): 增加可选运行引用、稳定标识约束和深度不可变有限上下文。
  v1.0.0 (2026-07-20): 创建结构化错误契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
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

type MachineIdentifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9._:/-]*[A-Za-z0-9])?$",
    ),
]
type NonBlankReference = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
_RESERVED_EXCEPTION_CONTEXT_KEYS = frozenset(
    {
        "__traceback__",
        "exception",
        "exception_message",
        "exception_type",
        "java_exception",
        "python_exception",
        "stack_trace",
        "stacktrace",
        "traceback",
    }
)


# =============================👐Seperate👐==============================
# Public error categories
# =============================👐Seperate👐==============================
class ErrorCategory(StrEnum):
    """Stable categories for public SycaSphere error payloads."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    PLUGIN_MISSING = "PLUGIN_MISSING"
    PLUGIN_INCOMPATIBLE = "PLUGIN_INCOMPATIBLE"
    BACKEND_INITIALIZATION = "BACKEND_INITIALIZATION"
    EXTERNAL_DATA = "EXTERNAL_DATA"
    UNSUPPORTED_FRAME = "UNSUPPORTED_FRAME"
    UNSUPPORTED_MEASUREMENT = "UNSUPPORTED_MEASUREMENT"
    UNAUTHORIZED_DATA_ACCESS = "UNAUTHORIZED_DATA_ACCESS"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    NUMERICAL_FAILURE = "NUMERICAL_FAILURE"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# =============================👐Seperate👐==============================
# Public error-detail payload
# =============================👐Seperate👐==============================
class ErrorDetail(BaseModel):
    """An immutable, JSON-safe payload for errors crossing public boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: ErrorCategory
    code: MachineIdentifier
    message: str
    retryable: bool
    component_ref: MachineIdentifier
    context: Mapping[str, JsonValue]
    run_id: NonBlankReference | None = None
    attempt_id: NonBlankReference | None = None
    diagnostic_artifact_ref: NonBlankReference | None = None

    @field_validator("context", mode="before")
    @classmethod
    def normalize_context(cls, value: Any) -> dict[str, JsonValue]:
        """Normalize all supported mappings and reject private diagnostic payloads."""
        return normalize_json_object(value, reserved_keys=_RESERVED_EXCEPTION_CONTEXT_KEYS)

    @field_validator("context")
    @classmethod
    def freeze_context(cls, value: Mapping[str, JsonValue]) -> Mapping[str, FrozenJsonValue]:
        """Store an immutable, alias-independent diagnostic context snapshot."""
        return freeze_json_object(value, reserved_keys=_RESERVED_EXCEPTION_CONTEXT_KEYS)

    @field_serializer("context", when_used="always")
    def serialize_context(self, value: Mapping[str, FrozenJsonValue]) -> dict[str, JsonValue]:
        """Serialize the immutable context as ordinary JSON objects and arrays."""
        return {key: thaw_json_value(nested_value) for key, nested_value in value.items()}
