# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : _canonical.py
创建者    : Sycamore
创建日期  : 2026-07-26
最后修改  : 2026-07-26
版本号    : v1.0.0

■ 用途说明:
  为可重复执行输入提供私有的规范 JSON、SHA-256 哈希和随机种子派生。

■ 主要函数功能:
  - canonical_json_bytes: 生成稳定的 UTF-8 规范 JSON 字节。
  - sha256_canonical_json: 计算规范 JSON 的 SHA-256 十六进制摘要。
  - derive_random_seed: 从主种子和组件标识派生确定性无符号 64 位种子。

■ 功能特性:
  ✓ 递归拒绝非 JSON 兼容值和非有限浮点数。
  ✓ 递归将负零标准化为正零。
  ✓ 以版本化载荷派生可重复随机种子。

■ 待办事项:
  - 无。

■ 更新日志:
  v1.0.0 (2026-07-26): 创建 V1 规范 JSON、哈希和种子派生实现。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Final

from pydantic import BaseModel, JsonValue
from sycasphere.core.schema import SchemaVersion

# =============================👐Seperate👐==============================
# Canonical JSON and deterministic seed derivation
# =============================👐Seperate👐==============================
CANONICALIZATION_VERSION: Final[str] = "SYCASPHERE_CANONICAL_JSON_V1"
RANDOM_DERIVATION_VERSION: Final[str] = "SYCASPHERE_SEED_V1"
_UINT64_MAX: Final[int] = 2**64 - 1


def _normalize_canonical_value(value: Any) -> JsonValue:
    """Return a recursively validated JSON value with canonical negative zeros."""
    if isinstance(value, BaseModel):
        return _normalize_canonical_value(value.model_dump(mode="json"))
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON floating-point values must be finite")
        return 0.0 if value == 0.0 else value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("canonical JSON object keys must be strings")
        return {key: _normalize_canonical_value(nested) for key, nested in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_canonical_value(item) for item in value]
    raise ValueError(f"value of type {type(value).__name__} is not JSON-compatible")


def canonical_json_bytes(value: BaseModel | JsonValue) -> bytes:
    """Serialize a JSON-compatible value to stable UTF-8 canonical JSON bytes."""
    normalized = _normalize_canonical_value(value)
    return json.dumps(
        normalized,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_canonical_json(value: BaseModel | JsonValue) -> str:
    """Return the SHA-256 hexadecimal digest of a canonical JSON value."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def derive_random_seed(
    master_seed: int,
    component_id: str,
    purpose: str,
    interface_version: SchemaVersion,
) -> int:
    """Derive a deterministic unsigned 64-bit seed for one component purpose."""
    if type(master_seed) is not int:
        raise TypeError("master_seed must be a built-in integer")
    if not 0 <= master_seed <= _UINT64_MAX:
        raise ValueError("master_seed must be an unsigned 64-bit integer")
    if not component_id.strip() or not purpose.strip():
        raise ValueError("component_id and purpose must not be blank")
    payload: JsonValue = [
        master_seed,
        component_id,
        purpose,
        interface_version.model_dump(mode="json"),
    ]
    digest = hashlib.sha256(canonical_json_bytes(payload)).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)
