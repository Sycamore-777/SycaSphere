# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : states.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.0.0

■ 用途说明:
  定义带显式时刻和参考系的不可变笛卡尔状态边界模型。

■ 主要函数功能:
  - CartesianState: 验证三维 SI 位置和速度状态向量。
  - position_array/velocity_array: 提供独立的 float64 数值计算数组。

■ 功能特性:
  ✓ 使用固定长度元组保存经过严格有限值验证的三维分量。
  ✓ 保持 JSON 边界数组与 NumPy 数值计算数组之间的隔离。

■ 更新日志:
  v1.0.0 (2026-07-20): 创建笛卡尔状态边界模型。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from typing import Annotated

import numpy as np
from numpy.typing import NDArray
from pydantic import AllowInfNan, BaseModel, ConfigDict, Strict, model_validator
from sycasphere.core.epoch import Epoch
from sycasphere.core.frames import CoordinateRepresentation, FrameRef

# =============================👐Seperate👐=============================
# Strict finite Cartesian-vector components
# =============================👐Seperate👐=============================
type FiniteComponent = Annotated[float, Strict(), AllowInfNan(False)]


# =============================👐Seperate👐=============================
# Immutable Cartesian state boundary model
# =============================👐Seperate👐=============================
class CartesianState(BaseModel):
    """An immutable three-dimensional position and velocity state in an explicit frame."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    epoch: Epoch
    frame: FrameRef
    position_m: tuple[FiniteComponent, FiniteComponent, FiniteComponent]
    velocity_mps: tuple[FiniteComponent, FiniteComponent, FiniteComponent]

    @model_validator(mode="after")
    def _validate_cartesian_frame_representation(self) -> CartesianState:
        """Require a Cartesian coordinate representation for Cartesian state components."""
        if self.frame.representation is not CoordinateRepresentation.CARTESIAN:
            raise ValueError("CartesianState requires a CARTESIAN frame representation")
        return self

    def position_array(self) -> NDArray[np.float64]:
        """Return an independent float64 position vector for numerical calculations."""
        return np.asarray(self.position_m, dtype=np.float64).copy()

    def velocity_array(self) -> NDArray[np.float64]:
        """Return an independent float64 velocity vector for numerical calculations."""
        return np.asarray(self.velocity_mps, dtype=np.float64).copy()
