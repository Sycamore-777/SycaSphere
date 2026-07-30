# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : api.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  提供 SycaSphere Engine v0.1 的同步公共准备与批运行门面。

■ 主要函数功能:
  - SimulationEngine.prepare: 将完整运行请求准备为不可变执行清单。
  - SimulationEngine.run: 通过无状态批运行器执行已准备清单。

■ 功能特性:
  ✓ 构造后复用同一不可变显式插件注册表
  ✓ 严格验证非科学批大小参数
  ✓ 不保存跨运行的可变科学状态

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from sycasphere.core import (
    SimulationExecutionManifest,
    SimulationExecutionResult,
    SimulationRunRequest,
)
from sycasphere.engine.backend import SimulationOutputSink
from sycasphere.engine.cancellation import CancellationProbe
from sycasphere.engine.execution import BatchRunner
from sycasphere.engine.preparation import ManifestPreparer
from sycasphere.engine.registry import PluginRegistry

# =============================👐Seperate👐=============================
# Public synchronous Engine facade
# =============================👐Seperate👐=============================


class SimulationEngine:
    """Prepare and execute independent backend-neutral simulation manifests."""

    __slots__ = ("_preparer", "_runner")

    def __init__(self, plugin_registry: PluginRegistry, *, batch_size: int = 256) -> None:
        """Bind one immutable registry and strict positive output batch size."""
        if type(batch_size) is not int or batch_size <= 0:
            raise ValueError("batch_size must be a positive built-in int")
        self._preparer = ManifestPreparer(plugin_registry)
        self._runner = BatchRunner(plugin_registry, batch_size=batch_size)

    def prepare(self, request: SimulationRunRequest) -> SimulationExecutionManifest:
        """Prepare one complete request without creating a backend runtime."""
        return self._preparer.prepare(request)

    def run(
        self,
        manifest: SimulationExecutionManifest,
        sink: SimulationOutputSink,
        cancellation: CancellationProbe,
    ) -> SimulationExecutionResult:
        """Execute one prepared manifest through a single-use output sink."""
        return self._runner.run(manifest, sink, cancellation)


__all__ = ["SimulationEngine"]
