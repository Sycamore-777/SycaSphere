# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_schema.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.0.0

■ 用途说明:
  验证公共模式版本兼容性与不可变性契约。

■ 主要函数功能:
  - test_schema_version_accepts_same_major_and_newer_minor: 验证向后兼容的次版本规则。
  - test_schema_version_rejects_different_major: 验证主版本不兼容规则。

■ 功能特性:
  ✓ 覆盖模式版本验证、兼容性和冻结行为。

■ 更新日志:
  v1.0.0 (2026-07-20): 创建模式版本契约测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sycasphere.core import SchemaVersion


# =============================👐Seperate👐==============================
# Schema-version compatibility tests
# =============================👐Seperate👐==============================
def test_schema_version_accepts_same_major_and_newer_minor() -> None:
    required = SchemaVersion(major=1, minor=1)
    provided = SchemaVersion(major=1, minor=3)

    assert provided.satisfies(required)


def test_schema_version_rejects_different_major() -> None:
    required = SchemaVersion(major=1, minor=0)
    provided = SchemaVersion(major=2, minor=0)

    assert not provided.satisfies(required)


@pytest.mark.parametrize(("major", "minor"), [(-1, 0), (0, -1)])
def test_schema_version_rejects_negative_components(major: int, minor: int) -> None:
    with pytest.raises(ValidationError):
        SchemaVersion(major=major, minor=minor)


def test_schema_version_is_frozen() -> None:
    schema_version = SchemaVersion(major=1, minor=0)

    with pytest.raises(ValidationError):
        schema_version.minor = 1
