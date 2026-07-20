# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : epoch.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.1.0

■ 用途说明:
  定义带显式时间尺度的不可变 Epoch 边界模型，并规范化 UTC 字符串。

■ 主要函数功能:
  - _normalize_utc: 校验带时区 UTC 日历字符串并规范化为 Z 后缀。
  - _validate_unzoned_calendar: 校验 TAI 和 TT 的无时区日历字符串。

■ 功能特性:
  ✓ 统一通用映射输入的 UTC 偏移表示而不执行时间尺度转换。
  ✓ 仅以受限语法接受 Z 后缀闰秒字符串。

■ 更新日志:
  v1.1.0 (2026-07-20): 将公共字段改为 time_scale 并封装 UTC 日期边界溢出。
  v1.0.0 (2026-07-20): 创建带时间尺度的 Epoch 契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

# =============================👐Seperate👐==============================
# Time-scale and ISO-8601 validation helpers
# =============================👐Seperate👐==============================
_CALENDAR_PATTERN = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
    r"(?P<fraction>\.\d+)?$"
)
_UTC_PATTERN = re.compile(
    r"^(?P<calendar>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)"
    r"(?P<offset>Z|[+-]\d{2}:\d{2})$"
)
_UTC_LEAP_SECOND_PATTERN = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):60"
    r"(?P<fraction>\.\d+)?Z$"
)


class TimeScale(StrEnum):
    """Supported labels for an Epoch's declared time scale."""

    UTC = "UTC"
    TAI = "TAI"
    TT = "TT"


def _canonical_fraction(fraction: str | None) -> str:
    """Return a fractional-second suffix without unnecessary trailing zeros."""
    if fraction is None:
        return ""

    digits = fraction[1:].rstrip("0")
    return f".{digits}" if digits else ""


def _validate_calendar_components(value: str) -> re.Match[str]:
    """Validate a timezone-free ISO-8601 calendar value and return its match."""
    match = _CALENDAR_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("Epoch value must be an ISO-8601 calendar string")

    try:
        datetime.fromisoformat(value[:19])
    except ValueError as error:
        raise ValueError("Epoch value contains an invalid calendar date or time") from error

    return match


def _normalize_utc_leap_second(value: str) -> str | None:
    """Validate and canonicalize the syntactically permitted Z-suffixed leap second."""
    match = _UTC_LEAP_SECOND_PATTERN.fullmatch(value)
    if match is None:
        return None

    calendar_without_leap_second = f"{match['date']}T{match['hour']}:{match['minute']}:59"
    _validate_calendar_components(calendar_without_leap_second)
    return (
        f"{match['date']}T{match['hour']}:{match['minute']}:60"
        f"{_canonical_fraction(match['fraction'])}Z"
    )


def _normalize_utc(value: str) -> str:
    """Parse an aware ISO-8601 value and serialize the equivalent UTC value with ``Z``."""
    leap_second = _normalize_utc_leap_second(value)
    if leap_second is not None:
        return leap_second

    match = _UTC_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("UTC Epoch values must include Z or a numeric offset")

    calendar_match = _validate_calendar_components(match["calendar"])
    normalized_input = (
        f"{match['calendar']}{'+00:00' if match['offset'] == 'Z' else match['offset']}"
    )
    try:
        parsed = datetime.fromisoformat(normalized_input)
        utc_value = parsed.astimezone(UTC)
    except ValueError as error:
        raise ValueError("UTC Epoch value contains an invalid offset") from error
    except OverflowError as error:
        raise ValueError(
            "UTC Epoch offset normalization exceeds the supported date range"
        ) from error
    fraction = _canonical_fraction(calendar_match["fraction"])
    return f"{utc_value:%Y-%m-%dT%H:%M:%S}{fraction}Z"


def _validate_unzoned_calendar(value: str, scale: TimeScale) -> str:
    """Validate a TAI or TT calendar string without assigning any timezone semantics."""
    if scale is TimeScale.UTC:
        raise ValueError("UTC values must be validated as aware timestamps")

    match = _validate_calendar_components(value)
    if match["second"] == "60":
        raise ValueError(f"{scale.value} Epoch values do not support leap-second syntax")
    return f"{value[:19]}{_canonical_fraction(match['fraction'])}"


# =============================👐Seperate👐==============================
# Public immutable Epoch model
# =============================👐Seperate👐==============================
class Epoch(BaseModel):
    """An immutable calendar instant whose time scale is always explicit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str
    time_scale: TimeScale

    @model_validator(mode="before")
    @classmethod
    def _validate_value_for_scale(cls, data: Any) -> Any:
        """Canonicalize the supplied value according to its explicitly declared scale."""
        if not isinstance(data, Mapping):
            return data

        normalized_data = dict(data)
        value = normalized_data.get("value")
        scale = normalized_data.get("time_scale")
        if not isinstance(value, str) or not isinstance(scale, (str, TimeScale)):
            return normalized_data

        parsed_scale = TimeScale(scale)
        normalized = (
            _normalize_utc(value)
            if parsed_scale is TimeScale.UTC
            else _validate_unzoned_calendar(value, parsed_scale)
        )
        return {**normalized_data, "value": normalized}
