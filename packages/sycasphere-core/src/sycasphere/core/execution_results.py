# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : execution_results.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  定义不可变、可序列化的仿真执行终态结果及其输出计数契约。

■ 主要函数功能:
  - SimulationOutputSummary: 保存各类科学输出的非负记录计数
  - SimulationExecutionResult: 保存完成或取消执行的终态结果

■ 功能特性:
  ✓ 严格区分完成和取消的终止详情
  ✓ 对嵌套公共模型进行快照和重新验证

■ 待办事项:
  - [ ] 无

■ 更新日志:
  v1.0.0 (2026-07-30): 初始版本

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sycasphere.core._validation import Sha256Hex, StrictNonNegativeInt, snapshot_model_input
from sycasphere.core.epoch import Epoch
from sycasphere.core.errors import ErrorCategory, ErrorDetail


# =============================👐Seperate👐=============================
# Simulation execution result contracts
# =============================👐Seperate👐=============================
class SimulationExecutionStatus(StrEnum):
    """Terminal outcome of a simulation execution with no execution failure result."""

    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class SimulationOutputSummary(BaseModel):
    """Counts of committed truth, attitude, and maneuver output records."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    truth_state_count: StrictNonNegativeInt = 0
    attitude_state_count: StrictNonNegativeInt = 0
    truth_maneuver_count: StrictNonNegativeInt = 0


class SimulationExecutionResult(BaseModel):
    """Immutable terminal result of one completed or cancelled simulation execution."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    manifest_content_hash: Sha256Hex
    status: SimulationExecutionStatus
    final_epoch: Epoch
    output_summary: SimulationOutputSummary
    termination_detail: ErrorDetail | None = None

    @field_validator("final_epoch", "output_summary", "termination_detail", mode="before")
    @classmethod
    def snapshot_result_models(cls, value: Any) -> Any:
        """Copy and revalidate nested public models at the result boundary."""
        if value is None:
            return None
        return snapshot_model_input(value)

    @model_validator(mode="after")
    def validate_status_detail(self) -> Self:
        """Enforce the terminal-status and termination-detail state matrix."""
        if self.status is SimulationExecutionStatus.COMPLETED:
            if self.termination_detail is not None:
                raise ValueError("COMPLETED result must not contain termination_detail")
            return self
        if self.termination_detail is None:
            raise ValueError("CANCELLED result requires termination_detail")
        if self.termination_detail.category is not ErrorCategory.CANCELLED:
            raise ValueError("CANCELLED result requires CANCELLED error category")
        if any(
            reference is not None
            for reference in (
                self.termination_detail.run_id,
                self.termination_detail.attempt_id,
                self.termination_detail.diagnostic_artifact_ref,
            )
        ):
            raise ValueError(
                "CANCELLED result termination_detail must not contain run_id, "
                "attempt_id, or diagnostic_artifact_ref"
            )
        return self
