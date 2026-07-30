# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : errors.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  定义 Engine 边界使用的结构化公共异常和内部错误详情构造器。

■ 主要函数功能:
  - SimulationEngineError: 提供仅含 Core ErrorDetail 的公共异常基类。
  - make_error_detail: 统一构造安全、可序列化的 Core ErrorDetail。

■ 功能特性:
  ✓ 将准备期和执行期故障分为稳定的公共异常类型。
  ✓ 不将 Python、Java 或第三方异常负载放入公开错误详情。

■ 待办事项:
  - [ ] 后续任务在 Engine 边界转换具体后端异常。

■ 更新日志:
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sycasphere.core import ErrorCategory, ErrorDetail

# =============================👐Seperate👐=============================
# Public Engine exceptions
# =============================👐Seperate👐=============================


class SimulationEngineError(Exception):
    """Base exception exposing one structured Core error detail."""

    __slots__ = ("detail",)

    detail: ErrorDetail

    def __init__(self, detail: ErrorDetail) -> None:
        super().__init__(detail.message)
        self.detail = detail


class SimulationPreparationError(SimulationEngineError):
    """Raised when Engine preparation cannot produce a valid manifest."""

    __slots__ = ()


class SimulationExecutionError(SimulationEngineError):
    """Raised when Engine execution cannot complete normally or by cancellation."""

    __slots__ = ()


# =============================👐Seperate👐=============================
# Internal structured-error construction
# =============================👐Seperate👐=============================
def make_error_detail(
    *,
    category: ErrorCategory,
    code: str,
    message: str,
    component_ref: str,
    context: Mapping[str, Any] | None = None,
    retryable: bool = False,
) -> ErrorDetail:
    """Build an Engine-originated public error detail without exception payloads."""
    return ErrorDetail(
        category=category,
        code=code,
        message=message,
        retryable=retryable,
        component_ref=component_ref,
        context={} if context is None else context,
    )


__all__ = [
    "SimulationEngineError",
    "SimulationExecutionError",
    "SimulationPreparationError",
]
