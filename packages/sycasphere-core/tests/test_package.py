# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_package.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.0.0

■ 用途说明:
  验证 Core 分发包公开其语义化版本号。

■ 主要函数功能:
  - test_core_package_exposes_version: 验证导入后可读取包版本。

■ 功能特性:
  ✓ 验证 Core 包的基础导入契约。

■ 更新日志:
  v1.0.0 (2026-07-20): 创建 Core 包烟雾测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations


# =============================👐Seperate👐=============================
# Core package smoke test
# =============================👐Seperate👐=============================
def test_core_package_exposes_version() -> None:
    import sycasphere.core

    assert sycasphere.core.__version__ == "0.1.0"
