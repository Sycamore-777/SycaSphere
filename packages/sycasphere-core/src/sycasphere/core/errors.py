# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : errors.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.0.0

■ 用途说明:
  定义 Core 公共边界使用的结构化错误类别和可安全序列化的错误负载。

■ 主要函数功能:
  - ErrorCategory: 声明稳定的错误类别值。
  - ErrorDetail: 承载机器可读错误代码、用户消息和 JSON 诊断上下文。

■ 功能特性:
  ✓ 拒绝未知字段和非 JSON 诊断上下文值。
  ✓ 不承载 Python/Java 异常或堆栈跟踪对象。

■ 更新日志:
  v1.0.0 (2026-07-20): 创建结构化错误契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, JsonValue


# =============================👐Seperate👐==============================
# Public error categories
# =============================👐Seperate👐==============================
class ErrorCategory(StrEnum):
    """Stable categories for public SycaSphere error payloads."""

    VALIDATION = "VALIDATION"
    PLUGIN_MISSING = "PLUGIN_MISSING"
    PLUGIN_INCOMPATIBLE = "PLUGIN_INCOMPATIBLE"
    BACKEND_INITIALIZATION = "BACKEND_INITIALIZATION"
    EXTERNAL_DATA = "EXTERNAL_DATA"
    UNSUPPORTED_FRAME = "UNSUPPORTED_FRAME"
    UNSUPPORTED_MEASUREMENT = "UNSUPPORTED_MEASUREMENT"
    NUMERICAL_FAILURE = "NUMERICAL_FAILURE"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    INTERNAL = "INTERNAL"


# =============================👐Seperate👐==============================
# Public error-detail payload
# =============================👐Seperate👐==============================
class ErrorDetail(BaseModel):
    """An immutable, JSON-safe payload for errors crossing public boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: ErrorCategory
    code: str
    message: str
    retryable: bool
    component_ref: str
    context: dict[str, JsonValue]
