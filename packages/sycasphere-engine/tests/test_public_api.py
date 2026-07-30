# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_public_api.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  锁定 SycaSphere Engine v0.1 的精确根公共 API 与测试后端命名空间边界。

■ 主要函数功能:
  - test_engine_root_exports_exact_reviewed_api: 验证根导出集合与版本。
  - test_fake_backend_symbols_live_only_in_testing_namespace: 验证 Fake 仅从 testing 导入。

■ 功能特性:
  ✓ 使用精确集合防止意外扩大公共兼容面
  ✓ 保持测试后端与生产 Engine 根命名空间分离

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import sycasphere.engine
import sycasphere.engine.testing

# =============================👐Seperate👐=============================
# Exact reviewed Engine API
# =============================👐Seperate👐=============================
EXPECTED_ENGINE_EXPORTS = {
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
}
TESTING_ONLY_EXPORTS = {
    "FAKE_PLUGIN_MANIFEST",
    "FakeBackendConfigurationValidator",
    "FakeScienceBackendFactory",
    "fake_backend_registration",
}


def test_engine_root_exports_exact_reviewed_api() -> None:
    """The package root exposes exactly the reviewed Engine behavior contracts."""
    assert set(sycasphere.engine.__all__) == EXPECTED_ENGINE_EXPORTS
    assert sycasphere.engine.__version__ == "0.1.0"

    for public_name in EXPECTED_ENGINE_EXPORTS:
        assert getattr(sycasphere.engine, public_name) is not None


def test_fake_backend_symbols_live_only_in_testing_namespace() -> None:
    """Compatibility Fake symbols remain public only under sycasphere.engine.testing."""
    assert set(sycasphere.engine.testing.__all__) == TESTING_ONLY_EXPORTS

    for testing_name in TESTING_ONLY_EXPORTS:
        assert getattr(sycasphere.engine.testing, testing_name) is not None
        assert not hasattr(sycasphere.engine, testing_name)
