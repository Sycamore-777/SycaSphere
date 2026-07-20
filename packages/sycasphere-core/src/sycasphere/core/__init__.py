# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : __init__.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.0.0

■ 用途说明:
  提供 SycaSphere Core 纯领域契约包的公共版本标识和基础契约。

■ 主要函数功能:
  - __version__: 声明当前 Core 分发包的版本。
  - SchemaVersion: 导出公共模式版本兼容性契约。
  - ErrorCategory 和 ErrorDetail: 导出公共结构化错误契约。

■ 功能特性:
  ✓ 提供稳定的公共导入接口。

■ 更新日志:
  v1.0.0 (2026-07-20): 导出模式版本和结构化错误契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from typing import Final

from sycasphere.core.epoch import Epoch, TimeScale
from sycasphere.core.errors import ErrorCategory, ErrorDetail
from sycasphere.core.schema import SchemaVersion

# =============================👐Seperate👐==============================
# Public package metadata and contracts
# =============================👐Seperate👐==============================
__version__: Final = "0.1.0"

__all__ = [
    "Epoch",
    "ErrorCategory",
    "ErrorDetail",
    "SchemaVersion",
    "TimeScale",
    "__version__",
]
