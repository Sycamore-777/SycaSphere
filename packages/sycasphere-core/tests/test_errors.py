# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_errors.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.1.0

■ 用途说明:
  验证公共结构化错误负载的稳定序列化与安全诊断上下文。

■ 主要函数功能:
  - test_error_detail_serializes_to_stable_json_values: 验证机器可读错误序列化。
  - test_error_detail_rejects_non_json_context_values: 验证异常和回溯对象不会泄漏。

■ 功能特性:
  ✓ 覆盖错误引用、标识符约束、深度冻结和有限 JSON 上下文限制。

■ 待办事项:
  - 无

■ 更新日志:
  v1.1.0 (2026-07-20): 覆盖可选运行引用和安全、有限、深度不可变上下文。
  v1.0.0 (2026-07-20): 创建结构化错误契约测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math
from types import MappingProxyType, TracebackType

import pytest
from pydantic import ValidationError
from sycasphere.core import ErrorCategory, ErrorDetail

# =============================👐Seperate👐==============================
# Structured-error payload tests
# =============================👐Seperate👐==============================
EXPECTED_ERROR_CATEGORIES = {
    "VALIDATION_ERROR",
    "PLUGIN_MISSING",
    "PLUGIN_INCOMPATIBLE",
    "BACKEND_INITIALIZATION",
    "EXTERNAL_DATA",
    "UNSUPPORTED_FRAME",
    "UNSUPPORTED_MEASUREMENT",
    "UNAUTHORIZED_DATA_ACCESS",
    "OUT_OF_ORDER",
    "NUMERICAL_FAILURE",
    "RESOURCE_EXHAUSTED",
    "TIMEOUT",
    "CANCELLED",
    "INTERNAL_ERROR",
}


def _traceback_object() -> TracebackType:
    try:
        raise ValueError("traceback")
    except ValueError as error:
        assert error.__traceback__ is not None
        return error.__traceback__


def test_error_detail_serializes_to_stable_json_values() -> None:
    error = ErrorDetail(
        category=ErrorCategory.VALIDATION_ERROR,
        code="CORE.INVALID_FRAME",
        message="EARTH_FIXED requires earth-fixed metadata",
        retryable=False,
        component_ref="sycasphere.core.frames",
        context={"frame": "EARTH_FIXED"},
    )

    assert error.model_dump(mode="json") == {
        "category": "VALIDATION_ERROR",
        "code": "CORE.INVALID_FRAME",
        "message": "EARTH_FIXED requires earth-fixed metadata",
        "retryable": False,
        "component_ref": "sycasphere.core.frames",
        "context": {"frame": "EARTH_FIXED"},
        "run_id": None,
        "attempt_id": None,
        "diagnostic_artifact_ref": None,
    }


def test_error_detail_serializes_optional_operational_references() -> None:
    error = ErrorDetail(
        category=ErrorCategory.NUMERICAL_FAILURE,
        code="ENGINE.PROPAGATION_FAILURE",
        message="Propagation failed",
        retryable=True,
        component_ref="sycasphere.engine.propagator",
        context={},
        run_id="run-001",
        attempt_id="attempt-002",
        diagnostic_artifact_ref="artifact://diagnostics/run-001/attempt-002",
    )

    assert error.model_dump(mode="json") == {
        "category": "NUMERICAL_FAILURE",
        "code": "ENGINE.PROPAGATION_FAILURE",
        "message": "Propagation failed",
        "retryable": True,
        "component_ref": "sycasphere.engine.propagator",
        "context": {},
        "run_id": "run-001",
        "attempt_id": "attempt-002",
        "diagnostic_artifact_ref": "artifact://diagnostics/run-001/attempt-002",
    }


def test_error_category_exposes_exact_approved_values_without_aliases() -> None:
    assert set(ErrorCategory.__members__) == EXPECTED_ERROR_CATEGORIES
    assert {category.value for category in ErrorCategory} == EXPECTED_ERROR_CATEGORIES
    assert len(ErrorCategory.__members__) == len(ErrorCategory)
    assert not hasattr(ErrorCategory, "VALIDATION")
    assert not hasattr(ErrorCategory, "INTERNAL")


def test_error_detail_is_frozen() -> None:
    error = ErrorDetail(
        category=ErrorCategory.VALIDATION_ERROR,
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
            category=ErrorCategory.INTERNAL_ERROR,
            code="CORE.INTERNAL",
            message="An internal error occurred",
            retryable=False,
            component_ref="sycasphere.core",
            context={},
            traceback="private",
        )


@pytest.mark.parametrize("field_name", ["code", "component_ref"])
@pytest.mark.parametrize("value", ["", "  ", "not a machine identifier", ".leading"])
def test_error_detail_rejects_invalid_machine_identifiers(field_name: str, value: str) -> None:
    data = {
        "category": ErrorCategory.INTERNAL_ERROR,
        "code": "CORE.INTERNAL",
        "message": "An internal error occurred",
        "retryable": False,
        "component_ref": "sycasphere.core",
        "context": {},
    }
    data[field_name] = value

    with pytest.raises(ValidationError):
        ErrorDetail.model_validate(data)


def test_error_detail_trims_machine_identifiers() -> None:
    error = ErrorDetail(
        category=ErrorCategory.INTERNAL_ERROR,
        code=" CORE.INTERNAL ",
        message="An internal error occurred",
        retryable=False,
        component_ref=" sycasphere.core ",
        context={},
    )

    assert error.code == "CORE.INTERNAL"
    assert error.component_ref == "sycasphere.core"


@pytest.mark.parametrize(
    "field_name",
    ["run_id", "attempt_id", "diagnostic_artifact_ref"],
)
def test_error_detail_optional_references_reject_blank_values(field_name: str) -> None:
    data = {
        "category": ErrorCategory.INTERNAL_ERROR,
        "code": "CORE.INTERNAL",
        "message": "An internal error occurred",
        "retryable": False,
        "component_ref": "sycasphere.core",
        "context": {},
        field_name: " \t ",
    }

    with pytest.raises(ValidationError):
        ErrorDetail.model_validate(data)


@pytest.mark.parametrize("context_value", [ValueError("private"), _traceback_object()])
def test_error_detail_rejects_non_json_context_values(context_value: object) -> None:
    with pytest.raises(ValidationError):
        ErrorDetail(
            category=ErrorCategory.INTERNAL_ERROR,
            code="CORE.INTERNAL",
            message="An internal error occurred",
            retryable=False,
            component_ref="sycasphere.core",
            context={"private": context_value},
        )


@pytest.mark.parametrize("invalid_value", [math.nan, math.inf, -math.inf])
def test_error_detail_rejects_non_finite_context_at_any_depth(invalid_value: float) -> None:
    with pytest.raises(ValidationError):
        ErrorDetail(
            category=ErrorCategory.NUMERICAL_FAILURE,
            code="CORE.NON_FINITE",
            message="A non-finite diagnostic value was produced",
            retryable=False,
            component_ref="sycasphere.core",
            context={"outer": [{"value": invalid_value}]},
        )


@pytest.mark.parametrize(
    "reserved_key",
    ["exception", "exception_type", "traceback", "stack_trace", "stacktrace"],
)
def test_error_detail_rejects_reserved_exception_payload_keys(reserved_key: str) -> None:
    with pytest.raises(ValidationError):
        ErrorDetail(
            category=ErrorCategory.INTERNAL_ERROR,
            code="CORE.INTERNAL",
            message="An internal error occurred",
            retryable=False,
            component_ref="sycasphere.core",
            context={"nested": {reserved_key: "private diagnostic data"}},
        )


def test_error_detail_deeply_freezes_and_isolates_context() -> None:
    nested_values = [1, {"label": "original"}]
    context = {"nested": nested_values}
    error = ErrorDetail(
        category=ErrorCategory.INTERNAL_ERROR,
        code="CORE.INTERNAL",
        message="An internal error occurred",
        retryable=False,
        component_ref="sycasphere.core",
        context=context,
    )

    nested_values.append(2)
    nested_values[1]["label"] = "mutated"

    assert error.context["nested"] == (1, MappingProxyType({"label": "original"}))
    with pytest.raises(TypeError):
        error.context["new"] = "value"
    with pytest.raises(TypeError):
        error.context["nested"][1]["label"] = "changed"


def test_error_detail_accepts_mapping_input_and_round_trips_as_normal_json() -> None:
    context = MappingProxyType({"details": MappingProxyType({"samples": (1, 2, 3)})})
    error = ErrorDetail(
        category=ErrorCategory.INTERNAL_ERROR,
        code="CORE.INTERNAL",
        message="An internal error occurred",
        retryable=False,
        component_ref="sycasphere.core",
        context=context,
    )

    serialized = error.model_dump(mode="json")

    assert serialized["context"] == {"details": {"samples": [1, 2, 3]}}
    assert (
        ErrorDetail.model_validate_json(error.model_dump_json()).model_dump(mode="json")
        == serialized
    )
