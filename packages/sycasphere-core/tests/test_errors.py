# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_errors.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.0.0

■ 用途说明:
  验证公共结构化错误负载的稳定序列化与安全诊断上下文。

■ 主要函数功能:
  - test_error_detail_serializes_to_stable_json_values: 验证机器可读错误序列化。
  - test_error_detail_rejects_non_json_context_values: 验证异常和回溯对象不会泄漏。

■ 功能特性:
  ✓ 覆盖错误类别、冻结行为和 JSON 上下文限制。

■ 更新日志:
  v1.0.0 (2026-07-20): 创建结构化错误契约测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from types import TracebackType

import pytest
from pydantic import ValidationError
from sycasphere.core import ErrorCategory, ErrorDetail


# =============================👐Seperate👐==============================
# Structured-error payload tests
# =============================👐Seperate👐==============================
def _traceback_object() -> TracebackType:
    try:
        raise ValueError("traceback")
    except ValueError as error:
        assert error.__traceback__ is not None
        return error.__traceback__


def test_error_detail_serializes_to_stable_json_values() -> None:
    error = ErrorDetail(
        category=ErrorCategory.VALIDATION,
        code="CORE.INVALID_FRAME",
        message="EARTH_FIXED requires earth-fixed metadata",
        retryable=False,
        component_ref="sycasphere.core.frames",
        context={"frame": "EARTH_FIXED"},
    )

    assert error.model_dump(mode="json") == {
        "category": "VALIDATION",
        "code": "CORE.INVALID_FRAME",
        "message": "EARTH_FIXED requires earth-fixed metadata",
        "retryable": False,
        "component_ref": "sycasphere.core.frames",
        "context": {"frame": "EARTH_FIXED"},
    }


def test_error_detail_is_frozen() -> None:
    error = ErrorDetail(
        category=ErrorCategory.VALIDATION,
        code="CORE.INVALID_FRAME",
        message="EARTH_FIXED requires earth-fixed metadata",
        retryable=False,
        component_ref="sycasphere.core.frames",
        context={"frame": "EARTH_FIXED"},
    )

    with pytest.raises(ValidationError):
        error.code = "CORE.OTHER"


def test_error_detail_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ErrorDetail(
            category=ErrorCategory.INTERNAL,
            code="CORE.INTERNAL",
            message="An internal error occurred",
            retryable=False,
            component_ref="sycasphere.core",
            context={},
            traceback="private",
        )


@pytest.mark.parametrize("context_value", [ValueError("private"), _traceback_object()])
def test_error_detail_rejects_non_json_context_values(context_value: object) -> None:
    with pytest.raises(ValidationError):
        ErrorDetail(
            category=ErrorCategory.INTERNAL,
            code="CORE.INTERNAL",
            message="An internal error occurred",
            retryable=False,
            component_ref="sycasphere.core",
            context={"private": context_value},
        )
