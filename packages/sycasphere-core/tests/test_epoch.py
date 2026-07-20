# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_epoch.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.0.0

■ 用途说明:
  验证带显式时间尺度的不可变 Epoch 边界契约与字符串规范化。

■ 主要函数功能:
  - UTC 规范化: 验证带时区 UTC 输入统一持久化为 Z。
  - 时间尺度验证: 验证 UTC、TAI 与 TT 的时区语义和日历语法。

■ 功能特性:
  ✓ 覆盖 UTC 偏移归一化、闰秒语法和 JSON 往返。
  ✓ 覆盖不可变模型和额外字段拒绝。

■ 更新日志:
  v1.0.0 (2026-07-20): 创建 Epoch 契约测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sycasphere.core import Epoch, TimeScale


# =============================👐Seperate👐==============================
# Epoch contract tests
# =============================👐Seperate👐==============================
@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("2026-07-20T10:00:00Z", "2026-07-20T10:00:00Z"),
        ("2026-07-20T18:00:00+08:00", "2026-07-20T10:00:00Z"),
        ("2026-07-20T10:00:00.125+00:00", "2026-07-20T10:00:00.125Z"),
        ("2026-07-20T10:00:00.125000Z", "2026-07-20T10:00:00.125Z"),
    ],
)
def test_utc_is_normalized_to_z(raw: str, canonical: str) -> None:
    assert Epoch(value=raw, scale=TimeScale.UTC).value == canonical


def test_utc_rejects_timezone_free_calendar_string() -> None:
    with pytest.raises(ValidationError):
        Epoch(value="2026-07-20T10:00:00", scale=TimeScale.UTC)


@pytest.mark.parametrize("scale", [TimeScale.TAI, TimeScale.TT])
def test_non_utc_scales_accept_timezone_free_calendar_strings(scale: TimeScale) -> None:
    epoch = Epoch(value="2026-07-20T10:00:00.125000", scale=scale)

    assert epoch.value == "2026-07-20T10:00:00.125"


@pytest.mark.parametrize("scale", [TimeScale.TAI, TimeScale.TT])
@pytest.mark.parametrize(
    "value",
    ["2026-07-20T10:00:00Z", "2026-07-20T10:00:00+08:00"],
)
def test_non_utc_scales_reject_timezone_designators(scale: TimeScale, value: str) -> None:
    with pytest.raises(ValidationError):
        Epoch(value=value, scale=scale)


def test_epoch_is_frozen_and_rejects_extra_fields() -> None:
    epoch = Epoch(value="2026-07-20T10:00:00Z", scale=TimeScale.UTC)

    with pytest.raises(ValidationError):
        epoch.value = "2026-07-20T11:00:00Z"
    with pytest.raises(ValidationError):
        Epoch(
            value="2026-07-20T10:00:00Z",
            scale=TimeScale.UTC,
            source="test",
        )


def test_utc_accepts_z_suffixed_leap_second_without_time_conversion() -> None:
    epoch = Epoch(value="2026-12-31T23:59:60Z", scale=TimeScale.UTC)

    assert epoch.value == "2026-12-31T23:59:60Z"


def test_utc_rejects_offset_form_leap_second() -> None:
    with pytest.raises(ValidationError):
        Epoch(value="2026-12-31T23:59:60+00:00", scale=TimeScale.UTC)


@pytest.mark.parametrize(
    "value",
    ["2026-02-29T10:00:00Z", "2026-07-20T10:00:61Z", "2026-13-01T10:00:00Z"],
)
def test_utc_rejects_invalid_calendar_values(value: str) -> None:
    with pytest.raises(ValidationError):
        Epoch(value=value, scale=TimeScale.UTC)


def test_epoch_json_round_trip_preserves_normalized_value_and_scale() -> None:
    epoch = Epoch(value="2026-07-20T18:00:00.125000+08:00", scale=TimeScale.UTC)

    assert Epoch.model_validate_json(epoch.model_dump_json()) == epoch
