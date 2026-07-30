# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_execution_results.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  验证仿真执行结果契约的状态矩阵、严格计数和终止详情约束。

■ 主要函数功能:
  - test_completed_result_has_counts_and_no_termination_detail: 验证完成结果约束
  - test_cancelled_result_requires_cancelled_detail: 验证取消结果约束

■ 功能特性:
  ✓ 覆盖完成与取消执行状态
  ✓ 覆盖输出计数的严格非负整数边界

■ 待办事项:
  - [ ] 无

■ 更新日志:
  v1.0.0 (2026-07-30): 初始版本

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sycasphere.core import Epoch, ErrorCategory, ErrorDetail, TimeScale
from sycasphere.core.execution_results import (
    SimulationExecutionResult,
    SimulationExecutionStatus,
    SimulationOutputSummary,
)

# =============================👐Seperate👐=============================
# Simulation execution result contracts
# =============================👐Seperate👐=============================
EPOCH = Epoch(value="2026-07-30T00:00:10Z", time_scale=TimeScale.UTC)
CANCELLED = ErrorDetail(
    category=ErrorCategory.CANCELLED,
    code="engine.cancelled",
    message="simulation execution was cancelled",
    retryable=False,
    component_ref="engine",
    context={},
)


def test_completed_result_has_counts_and_no_termination_detail() -> None:
    result = SimulationExecutionResult(
        manifest_content_hash="a" * 64,
        status=SimulationExecutionStatus.COMPLETED,
        final_epoch=EPOCH,
        output_summary=SimulationOutputSummary(
            truth_state_count=2,
            attitude_state_count=2,
            truth_maneuver_count=1,
        ),
    )
    assert result.termination_detail is None

    with pytest.raises(ValidationError, match="COMPLETED"):
        SimulationExecutionResult(
            manifest_content_hash="a" * 64,
            status=SimulationExecutionStatus.COMPLETED,
            final_epoch=EPOCH,
            output_summary=SimulationOutputSummary(),
            termination_detail=CANCELLED,
        )


def test_cancelled_result_requires_cancelled_detail() -> None:
    result = SimulationExecutionResult(
        manifest_content_hash="a" * 64,
        status=SimulationExecutionStatus.CANCELLED,
        final_epoch=EPOCH,
        output_summary=SimulationOutputSummary(),
        termination_detail=CANCELLED,
    )
    assert result.termination_detail.category is ErrorCategory.CANCELLED

    with pytest.raises(ValidationError, match="CANCELLED"):
        SimulationExecutionResult.model_validate(
            {
                **result.model_dump(mode="python"),
                "termination_detail": None,
            }
        )

    with pytest.raises(ValidationError, match="CANCELLED"):
        SimulationExecutionResult(
            manifest_content_hash="a" * 64,
            status=SimulationExecutionStatus.CANCELLED,
            final_epoch=EPOCH,
            output_summary=SimulationOutputSummary(),
            termination_detail=CANCELLED.model_copy(
                update={"category": ErrorCategory.INTERNAL_ERROR}
            ),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_id", "run-001"),
        ("attempt_id", "attempt-001"),
        ("diagnostic_artifact_ref", "artifact://diagnostic-001"),
    ],
)
def test_cancelled_result_rejects_platform_references(
    field: str,
    value: str,
) -> None:
    with pytest.raises(ValidationError, match=field):
        SimulationExecutionResult(
            manifest_content_hash="a" * 64,
            status=SimulationExecutionStatus.CANCELLED,
            final_epoch=EPOCH,
            output_summary=SimulationOutputSummary(),
            termination_detail=CANCELLED.model_copy(update={field: value}),
        )


@pytest.mark.parametrize(
    "field",
    ["truth_state_count", "attitude_state_count", "truth_maneuver_count"],
)
def test_output_counts_reject_negative_and_coercible_values(field: str) -> None:
    with pytest.raises(ValidationError):
        SimulationOutputSummary(**{field: -1})
    with pytest.raises(ValidationError):
        SimulationOutputSummary(**{field: "1"})
