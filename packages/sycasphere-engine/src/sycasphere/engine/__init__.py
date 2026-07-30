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
  定义 SycaSphere Engine 分发包的最小公共包元数据。

■ 主要函数功能:
  - __version__: 声明当前 Engine 分发包版本。

■ 功能特性:
  ✓ 提供版本标识而不提前导出尚未实现的运行时 API。

■ 待办事项:
  - [ ] 后续任务在稳定后导出 Engine 公共运行时接口。

■ 更新日志:
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from typing import Final

# =============================👐Seperate👐=============================
# Public package metadata
# =============================👐Seperate👐=============================
__version__: Final = "0.1.0"

__all__ = ["__version__"]
