# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : __init__.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  发布 Engine 兼容性测试使用的确定性 FakeBackend 公共入口。

■ 主要函数功能:
  - fake_backend_registration: 构造显式 FakeBackend 注册项。

■ 功能特性:
  ✓ 仅导出公开兼容性后端接口
  ✓ 不导入 Orekit、JPype 或 Java

■ 待办事项:
  - [ ] 无

■ 更新日志:
  v1.0.0 (2026-07-30): 创建公开测试后端命名空间

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from sycasphere.engine.testing.fake_backend import (
    FAKE_PLUGIN_MANIFEST,
    FakeBackendConfigurationValidator,
    FakeScienceBackendFactory,
    fake_backend_registration,
)

__all__ = [
    "FAKE_PLUGIN_MANIFEST",
    "FakeBackendConfigurationValidator",
    "FakeScienceBackendFactory",
    "fake_backend_registration",
]
