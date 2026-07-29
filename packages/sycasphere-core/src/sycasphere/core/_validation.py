# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : _validation.py
创建者    : Sycamore
创建日期  : 2026-07-28
最后修改  : 2026-07-28
版本号    : v1.0.0

■ 用途说明:
  提供 Core 公共模型边界复用的严格标量、快照与浮点序列校验辅助函数。

■ 主要函数功能:
  - snapshot_model_input: 将 Pydantic 输入模型转换为独立的 Python 数据快照
  - snapshot_model_collection: 快照受支持集合中的 Pydantic 模型项
  - require_builtin_float_sequence: 拒绝数值强制转换并要求内置浮点序列

■ 功能特性:
  ✓ 集中严格有限浮点、非负整数和 SHA-256 十六进制类型别名
  ✓ 保持模型边界输入的重验证快照语义

■ 待办事项:
  - [ ] 无

■ 更新日志:
  v1.0.0 (2026-07-28): 初始版本，提取 Core 边界验证辅助函数

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import (
    AllowInfNan,
    BaseModel,
    Field,
    Strict,
    StringConstraints,
)

# =============================👐Seperate👐=============================
# Strict boundary validation helpers
# =============================👐Seperate👐=============================
type StrictFiniteFloat = Annotated[float, Strict(), AllowInfNan(False)]
type StrictNonNegativeInt = Annotated[int, Strict(), Field(ge=0)]
type Sha256Hex = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$"),
]


def snapshot_model_input(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    return value


def snapshot_model_collection(value: Any) -> Any:
    if isinstance(value, (frozenset, list, set, tuple)):
        return tuple(snapshot_model_input(item) for item in value)
    return value


def require_builtin_float_sequence(value: Any, field_name: str) -> Any:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be supplied as a list or tuple")
    if any(type(component) is not float for component in value):
        raise ValueError(f"{field_name} components must be built-in floats")
    return value
