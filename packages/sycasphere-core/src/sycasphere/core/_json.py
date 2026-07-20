# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : _json.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.0.0

■ 用途说明:
  为 Core 公共边界集中提供有限、深度不可变且可往返的 JSON 值处理。

■ 主要函数功能:
  - normalize_json_object: 校验任意映射和序列并生成普通 JSON 验证输入。
  - freeze_json_object: 深度复制并冻结 JSON 对象。
  - thaw_json_value: 将冻结值还原为普通字典和列表以供序列化。

■ 功能特性:
  ✓ 在任意嵌套深度拒绝非有限浮点数、异常、回溯和非 JSON 值。
  ✓ 通过有序映射副本和不可变序列消除输入别名及哈希顺序差异。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-20): 创建共享有限不可变 JSON 工具。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from types import MappingProxyType, TracebackType
from typing import Any, cast

from pydantic import JsonValue

# =============================👐Seperate👐==============================
# Recursive finite immutable JSON values
# =============================👐Seperate👐==============================
type FrozenJsonScalar = bool | float | int | str | None
type FrozenJsonValue = (
    FrozenJsonScalar | Mapping[str, FrozenJsonValue] | tuple[FrozenJsonValue, ...]
)


def _normalized_reserved_key(key: str) -> str:
    """Normalize a JSON object key only for reserved-key comparisons."""
    return key.strip().casefold().replace("-", "_")


def freeze_json_value(
    value: Any,
    *,
    reserved_keys: frozenset[str] = frozenset(),
) -> FrozenJsonValue:
    """Validate, copy, and recursively freeze one JSON-compatible value."""
    if isinstance(value, (BaseException, TracebackType)):
        raise ValueError("Python exception and traceback objects are not public JSON values")

    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return str(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON floating-point values must be finite")
        return float(value)

    if isinstance(value, Mapping):
        items: list[tuple[str, Any]] = []
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            if _normalized_reserved_key(key) in reserved_keys:
                raise ValueError(f"JSON object key {key!r} is reserved for private diagnostics")
            items.append((key, nested_value))

        return MappingProxyType(
            {
                key: freeze_json_value(nested_value, reserved_keys=reserved_keys)
                for key, nested_value in sorted(items, key=lambda item: item[0])
            }
        )

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(freeze_json_value(item, reserved_keys=reserved_keys) for item in value)

    raise ValueError(f"value of type {type(value).__name__} is not JSON-compatible")


def freeze_json_object(
    value: Any,
    *,
    reserved_keys: frozenset[str] = frozenset(),
) -> Mapping[str, FrozenJsonValue]:
    """Validate and deeply freeze a top-level JSON object."""
    frozen = freeze_json_value(value, reserved_keys=reserved_keys)
    if not isinstance(frozen, Mapping):
        raise ValueError("value must be a JSON object")
    return frozen


def thaw_json_value(value: FrozenJsonValue) -> JsonValue:
    """Return ordinary JSON dictionaries and lists for public serialization."""
    if isinstance(value, Mapping):
        return {key: thaw_json_value(nested_value) for key, nested_value in value.items()}
    if isinstance(value, tuple):
        return [thaw_json_value(item) for item in value]
    return value


def normalize_json_object(
    value: Any,
    *,
    reserved_keys: frozenset[str] = frozenset(),
) -> dict[str, JsonValue]:
    """Return a validated ordinary object suitable for Pydantic's JSON field validation."""
    normalized = thaw_json_value(freeze_json_object(value, reserved_keys=reserved_keys))
    return cast(dict[str, JsonValue], normalized)
