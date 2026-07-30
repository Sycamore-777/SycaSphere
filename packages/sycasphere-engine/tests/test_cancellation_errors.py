# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_cancellation_errors.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  验证 Engine 协作取消令牌和结构化公共异常的基础契约。

■ 主要函数功能:
  - test_cancellation_token_is_monotonic_and_thread_safe: 验证并发取消的单向线程安全语义。
  - test_engine_exception_exposes_only_structured_detail: 验证执行异常仅公开 ErrorDetail。

■ 功能特性:
  ✓ 覆盖取消令牌的初始状态和并发取消。
  ✓ 覆盖公共异常的结构化错误详情。

■ 待办事项:
  - [ ] 后续任务覆盖取消令牌在完整运行器中的协作行为。

■ 更新日志:
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from sycasphere.core import ErrorCategory, ErrorDetail
from sycasphere.engine.cancellation import CancellationProbe, CancellationToken
from sycasphere.engine.errors import SimulationExecutionError, make_error_detail

# =============================👐Seperate👐=============================
# Cancellation and public-error contracts
# =============================👐Seperate👐=============================


def test_cancellation_token_is_monotonic_and_thread_safe() -> None:
    """Concurrent cancellation permanently marks a token as cancelled."""
    token = CancellationToken()

    assert token.is_cancelled is False
    assert isinstance(token, CancellationProbe)
    with ThreadPoolExecutor(max_workers=4) as pool:
        tuple(pool.map(lambda _: token.cancel(), range(20)))
    assert token.is_cancelled is True


def test_engine_exception_exposes_only_structured_detail() -> None:
    """Execution errors expose their Core ErrorDetail and human message."""
    detail = ErrorDetail(
        category=ErrorCategory.NUMERICAL_FAILURE,
        code="backend.propagation_failed",
        message="propagation failed",
        retryable=False,
        component_ref="science-backend",
        context={"epoch": "2026-07-30T00:00:00Z"},
    )

    error = SimulationExecutionError(detail)

    assert error.detail is detail
    assert str(error) == "propagation failed"


def test_make_error_detail_uses_an_empty_context_by_default() -> None:
    """The Engine helper builds a Core error payload without shared context state."""
    detail = make_error_detail(
        category=ErrorCategory.CANCELLED,
        code="engine.cancelled",
        message="simulation was cancelled",
        component_ref="engine",
    )

    assert detail.context == {}
    assert detail.retryable is False
