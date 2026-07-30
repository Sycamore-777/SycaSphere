# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : __init__.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.1.0

■ 用途说明:
  发布 SycaSphere Engine v0.1 经评审的后端中立批运行公共接口。

■ 主要函数功能:
  - __version__: 声明当前 Engine 分发包版本。
  - SimulationEngine: 准备并同步执行不可变仿真清单。

■ 功能特性:
  ✓ 精确导出批运行、插件、取消、后端端口、sink 与结构化异常
  ✓ 不从根命名空间导出测试专用 FakeBackend

■ 待办事项:
  - 无

■ 更新日志:
  v1.1.0 (2026-07-30): 发布 Engine v0.1 经评审的精确公共 API。
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from typing import Final

from sycasphere.engine.api import SimulationEngine
from sycasphere.engine.backend import (
    ManeuverExecution,
    PreparationTimeAdapter,
    PropagationOutcome,
    ScienceBackendFactory,
    ScienceBackendRegistration,
    ScienceBackendRuntime,
    SimulationOutputSink,
)
from sycasphere.engine.cancellation import CancellationProbe, CancellationToken
from sycasphere.engine.errors import (
    SimulationEngineError,
    SimulationExecutionError,
    SimulationPreparationError,
)
from sycasphere.engine.registry import PluginRegistry
from sycasphere.engine.sinks import CompositeOutputSink, InMemoryOutputSink, NullOutputSink

# =============================👐Seperate👐=============================
# Reviewed Engine v0.1 API and package metadata
# =============================👐Seperate👐=============================
__version__: Final = "0.1.0"

__all__ = [
    "CancellationProbe",
    "CancellationToken",
    "CompositeOutputSink",
    "InMemoryOutputSink",
    "ManeuverExecution",
    "NullOutputSink",
    "PluginRegistry",
    "PreparationTimeAdapter",
    "PropagationOutcome",
    "ScienceBackendFactory",
    "ScienceBackendRegistration",
    "ScienceBackendRuntime",
    "SimulationEngine",
    "SimulationEngineError",
    "SimulationExecutionError",
    "SimulationOutputSink",
    "SimulationPreparationError",
]
