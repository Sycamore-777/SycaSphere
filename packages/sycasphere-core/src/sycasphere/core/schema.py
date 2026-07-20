# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : schema.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.0.0

■ 用途说明:
  定义 Core 公共数据模式的不可变兼容性版本契约。

■ 主要函数功能:
  - SchemaVersion.satisfies: 判断提供的模式版本是否满足所需版本。

■ 功能特性:
  ✓ 拒绝负数版本号。
  ✓ 以主版本相同且次版本不低于要求的规则判断兼容性。

■ 更新日志:
  v1.0.0 (2026-07-20): 创建模式版本契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, NonNegativeInt


# =============================👐Seperate👐==============================
# Schema-version contract
# =============================👐Seperate👐==============================
class SchemaVersion(BaseModel):
    """An immutable public schema version with forward-compatible minors."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    major: NonNegativeInt
    minor: NonNegativeInt

    def satisfies(self, required: SchemaVersion) -> bool:
        """Return whether this version is compatible with ``required``."""
        return self.major == required.major and self.minor >= required.minor
