# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_canonical.py
创建者    : Sycamore
创建日期  : 2026-07-26
最后修改  : 2026-07-26
版本号    : v1.0.0

■ 用途说明:
  验证规范 JSON 序列化、哈希和随机种子派生契约。

■ 主要函数功能:
  - 测试规范 JSON 的排序、Unicode、有限数值和负零规则。
  - 测试哈希顺序无关性及 V1 随机种子派生。

■ 功能特性:
  ✓ 锁定 V1 规范 JSON 字节表示。
  ✓ 锁定 V1 随机种子已知向量。

■ 待办事项:
  - 无。

■ 更新日志:
  v1.0.0 (2026-07-26): 创建规范 JSON 与随机种子派生测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import pytest
from sycasphere.core._canonical import (
    canonical_json_bytes,
    derive_random_seed,
    sha256_canonical_json,
)
from sycasphere.core.schema import SchemaVersion


# =============================👐Seperate👐==============================
# Canonical JSON, hashing, and seed derivation tests
# =============================👐Seperate👐==============================
def test_canonical_json_sorts_keys_preserves_unicode_and_has_no_spaces() -> None:
    value = {"z": "轨道", "a": {"y": 2.0, "x": 1.0}}
    assert canonical_json_bytes(value) == ('{"a":{"x":1.0,"y":2.0},"z":"轨道"}'.encode())


def test_canonical_json_normalizes_negative_zero_recursively() -> None:
    assert canonical_json_bytes({"values": [-0.0, {"x": -0.0}]}) == (b'{"values":[0.0,{"x":0.0}]}')


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_canonical_json_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        canonical_json_bytes({"value": value})


def test_sha256_canonical_json_is_order_independent() -> None:
    assert sha256_canonical_json({"b": 2, "a": 1}) == sha256_canonical_json({"a": 1, "b": 2})


def test_seed_v1_has_a_locked_known_vector() -> None:
    seed = derive_random_seed(
        42,
        "sensor-1",
        "reported-noise",
        SchemaVersion(major=1, minor=0),
    )
    assert seed == 16_402_414_253_369_765_323


@pytest.mark.parametrize("master_seed", [-1, 2**64, True, 1.0])
def test_seed_derivation_rejects_values_outside_unsigned_64_bit(
    master_seed: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        derive_random_seed(
            master_seed,  # type: ignore[arg-type]
            "sensor-1",
            "reported-noise",
            SchemaVersion(major=1, minor=0),
        )
