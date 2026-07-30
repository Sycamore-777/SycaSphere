# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : scheduling.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.1

■ 用途说明:
  提供后端中立的同时间尺度日历运算、闭区间惰性采样和确定性事件合并。

■ 主要函数功能:
  - SameScaleCalendarTimeAdapter: 使用整数日秒与 Decimal 小数执行轻量日历运算。
  - iter_sampling_epochs: 惰性生成包含起止边界的固定周期采样时刻。
  - iter_event_groups: 以有限前瞻合并产品采样和已准备机动。

■ 功能特性:
  ✓ 拒绝跨时间尺度运算、UTC 闰秒语法和非有限偏移。
  ✓ 保持 UTC Z 后缀以及 TAI/TT 无时区序列化。
  ✓ 同刻产品按枚举值排序，机动保持准备后的 order_index 顺序。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.1 (2026-07-30): 修复前导小数零精度并在首次产出前拒绝时间不兼容。
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_FLOOR, Decimal, InvalidOperation, localcontext
from typing import NoReturn

from sycasphere.core import (
    Epoch,
    ErrorCategory,
    OutputProduct,
    PreparedManeuverEntry,
    SamplingRule,
    SimulationExecutionManifest,
    SimulationTimeRange,
    TimeScale,
)
from sycasphere.engine.backend import PreparationTimeAdapter
from sycasphere.engine.errors import SimulationPreparationError, make_error_detail

# =============================👐Seperate👐=============================
# Exact normalized-calendar representation and errors
# =============================👐Seperate👐=============================

_CALENDAR_PATTERN = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
    r"(?P<fraction>\.\d+)?(?P<zone>Z)?$"
)
_SECONDS_PER_DAY = 86_400
_COMPONENT_REF = "sycasphere.engine.scheduling"


@dataclass(frozen=True, slots=True)
class _CalendarMoment:
    """Exact same-scale calendar components used only inside this adapter."""

    ordinal: int
    second_of_day: int
    fraction: Decimal


def _raise_time_error(
    *,
    code: str,
    message: str,
    context: dict[str, str] | None = None,
    category: ErrorCategory = ErrorCategory.VALIDATION_ERROR,
) -> NoReturn:
    """Raise one safe, structured preparation-time incompatibility."""
    raise SimulationPreparationError(
        make_error_detail(
            category=category,
            code=code,
            message=message,
            component_ref=_COMPONENT_REF,
            context={} if context is None else context,
        )
    )


def _require_same_scale(left: Epoch, right: Epoch) -> None:
    """Reject comparisons that require an external time-scale conversion."""
    if left.time_scale is not right.time_scale:
        _raise_time_error(
            code="ENGINE_TIME_SCALE_MISMATCH",
            message="same-scale calendar arithmetic cannot compare different time scales",
            category=ErrorCategory.PLUGIN_INCOMPATIBLE,
            context={
                "left_time_scale": left.time_scale.value,
                "right_time_scale": right.time_scale.value,
            },
        )


def _parse_calendar(epoch: Epoch) -> _CalendarMoment:
    """Parse a normalized Core Epoch into integer day/second and Decimal fraction."""
    match = _CALENDAR_PATTERN.fullmatch(epoch.value)
    if match is None:
        _raise_time_error(
            code="ENGINE_TIME_CALENDAR_INVALID",
            message="Epoch is not a normalized calendar value",
            context={"epoch": epoch.value, "time_scale": epoch.time_scale.value},
        )
    if match["second"] == "60":
        _raise_time_error(
            code="ENGINE_TIME_LEAP_SECOND_UNSUPPORTED",
            message="same-scale calendar arithmetic does not support a UTC leap second",
            category=ErrorCategory.PLUGIN_INCOMPATIBLE,
            context={"epoch": epoch.value, "time_scale": epoch.time_scale.value},
        )

    calendar_date = date.fromisoformat(match["date"])
    second_of_day = int(match["hour"]) * 3_600 + int(match["minute"]) * 60 + int(match["second"])
    fraction = Decimal(match["fraction"] or "0")
    return _CalendarMoment(
        ordinal=calendar_date.toordinal(),
        second_of_day=second_of_day,
        fraction=fraction,
    )


def _decimal_precision(*values: Decimal, integer_digits: int = 1) -> int:
    """Return sufficient local precision for exact finite additions and subtractions."""
    coefficient_digits = max((len(value.as_tuple().digits) for value in values), default=1)
    fractional_places = 0
    for value in values:
        exponent = value.as_tuple().exponent
        if isinstance(exponent, int):
            fractional_places = max(fractional_places, -exponent)
    return max(28, coefficient_digits, integer_digits + fractional_places) + 2


def _serialize_calendar(moment: _CalendarMoment, time_scale: TimeScale) -> Epoch:
    """Serialize exact calendar components using the Core scale-specific grammar."""
    if not 1 <= moment.ordinal <= date.max.toordinal():
        _raise_time_error(
            code="ENGINE_TIME_CALENDAR_RANGE",
            message="calendar arithmetic exceeds the supported calendar range",
            context={"time_scale": time_scale.value},
        )

    calendar_date = date.fromordinal(moment.ordinal)
    hour, remaining_seconds = divmod(moment.second_of_day, 3_600)
    minute, second = divmod(remaining_seconds, 60)
    fraction_text = format(moment.fraction, "f").removeprefix("0").rstrip("0")
    if fraction_text == ".":
        fraction_text = ""
    zone = "Z" if time_scale is TimeScale.UTC else ""
    return Epoch(
        value=(
            f"{calendar_date:%Y-%m-%d}T{hour:02d}:{minute:02d}:{second:02d}{fraction_text}{zone}"
        ),
        time_scale=time_scale,
    )


# =============================👐Seperate👐=============================
# Public lightweight same-scale time adapter
# =============================👐Seperate👐=============================


class SameScaleCalendarTimeAdapter:
    """Perform exact calendar arithmetic without converting between time scales."""

    def compare(self, left: Epoch, right: Epoch) -> int:
        """Return -1, 0, or 1 for two supported epochs in the same time scale."""
        _require_same_scale(left, right)
        left_moment = _parse_calendar(left)
        right_moment = _parse_calendar(right)
        left_key = (
            left_moment.ordinal,
            left_moment.second_of_day,
            left_moment.fraction,
        )
        right_key = (
            right_moment.ordinal,
            right_moment.second_of_day,
            right_moment.fraction,
        )
        return (left_key > right_key) - (left_key < right_key)

    def seconds_between(self, start: Epoch, end: Epoch) -> float:
        """Return the finite SI-second difference between same-scale calendar values."""
        _require_same_scale(start, end)
        start_moment = _parse_calendar(start)
        end_moment = _parse_calendar(end)
        integer_seconds = (
            (end_moment.ordinal - start_moment.ordinal) * _SECONDS_PER_DAY
            + end_moment.second_of_day
            - start_moment.second_of_day
        )
        integer_digits = len(str(abs(integer_seconds))) if integer_seconds else 1
        with localcontext() as context:
            context.prec = _decimal_precision(
                start_moment.fraction,
                end_moment.fraction,
                integer_digits=integer_digits,
            )
            difference = Decimal(integer_seconds) + end_moment.fraction - start_moment.fraction
        return float(difference)

    def add_seconds(self, epoch: Epoch, seconds: float) -> Epoch:
        """Add a finite decimalized SI-second offset and preserve the epoch's scale syntax."""
        moment = _parse_calendar(epoch)
        if type(seconds) is not float or not math.isfinite(seconds):
            _raise_time_error(
                code="ENGINE_TIME_OFFSET_INVALID",
                message="calendar offset seconds must be a finite built-in float",
                context={"time_scale": epoch.time_scale.value},
            )
        try:
            offset = Decimal(str(seconds))
        except InvalidOperation:
            _raise_time_error(
                code="ENGINE_TIME_OFFSET_INVALID",
                message="calendar offset seconds must be finite",
                context={"time_scale": epoch.time_scale.value},
            )

        whole_offset = int(offset.to_integral_value(rounding=ROUND_FLOOR))
        fractional_offset = offset - Decimal(whole_offset)
        with localcontext() as context:
            context.prec = _decimal_precision(moment.fraction, fractional_offset)
            fraction_sum = moment.fraction + fractional_offset
            fraction_carry = int(fraction_sum.to_integral_value(rounding=ROUND_FLOOR))
            normalized_fraction = fraction_sum - Decimal(fraction_carry)

        accumulated_seconds = moment.second_of_day + whole_offset + fraction_carry
        day_offset, second_of_day = divmod(accumulated_seconds, _SECONDS_PER_DAY)
        return _serialize_calendar(
            _CalendarMoment(
                ordinal=moment.ordinal + day_offset,
                second_of_day=second_of_day,
                fraction=normalized_fraction,
            ),
            epoch.time_scale,
        )

    def same_instant(self, left: Epoch, right: Epoch) -> bool:
        """Return whether two supported same-scale values identify the same calendar instant."""
        return self.compare(left, right) == 0


# =============================👐Seperate👐=============================
# Lazy sampling and deterministic event merge
# =============================👐Seperate👐=============================


@dataclass(frozen=True, slots=True)
class ScheduledEventGroup:
    """All prepared maneuvers and requested products due at one exact epoch."""

    epoch: Epoch
    maneuvers: tuple[PreparedManeuverEntry, ...]
    sample_products: tuple[OutputProduct, ...]


def iter_sampling_epochs(
    time_range: SimulationTimeRange,
    rule: SamplingRule,
    time_adapter: PreparationTimeAdapter,
) -> Iterator[Epoch]:
    """Yield a lazy closed-interval cadence, forcing the end exactly once."""
    ## -------------- step: validate both boundaries before exposing the start ---------
    time_adapter.compare(time_range.start, time_range.end)
    current = time_range.start
    yield current

    while not time_adapter.same_instant(current, time_range.end):
        ## -------------- step: calculate and validate the next cadence epoch ---------
        candidate = time_adapter.add_seconds(current, rule.interval_s)
        if time_adapter.compare(candidate, current) <= 0:
            _raise_time_error(
                code="ENGINE_SAMPLING_DID_NOT_ADVANCE",
                message="sampling time adapter must advance for a positive interval",
                context={"product": rule.product.value},
            )

        ## -------------- step: emit an interior cadence or the exact final bound ---------
        relative_to_end = time_adapter.compare(candidate, time_range.end)
        if relative_to_end < 0:
            current = candidate
            yield current
            continue
        yield time_range.end
        return


def _minimum_epoch(
    candidates: Iterator[Epoch],
    time_adapter: PreparationTimeAdapter,
) -> Epoch:
    """Select the earliest epoch from a small set of current look-ahead values."""
    earliest = next(candidates)
    for candidate in candidates:
        if time_adapter.compare(candidate, earliest) < 0:
            earliest = candidate
    return earliest


def iter_event_groups(
    manifest: SimulationExecutionManifest,
    time_adapter: PreparationTimeAdapter,
) -> Iterator[ScheduledEventGroup]:
    """Lazily merge one look-ahead per sampler with one prepared-maneuver cursor."""
    time_range = manifest.source_request.time_range
    ## -------------- step: validate even a manifest with no scheduled events ---------
    time_adapter.compare(time_range.start, time_range.end)
    rules = tuple(
        sorted(
            manifest.prepared_timeline.output_sampling.rules,
            key=lambda rule: rule.product.value,
        )
    )
    samplers = tuple(iter(iter_sampling_epochs(time_range, rule, time_adapter)) for rule in rules)
    sample_lookaheads: list[Epoch | None] = [next(sampler, None) for sampler in samplers]
    maneuvers = manifest.prepared_timeline.maneuvers
    maneuver_cursor = 0

    while maneuver_cursor < len(maneuvers) or any(epoch is not None for epoch in sample_lookaheads):
        ## -------------- step: select the next epoch from bounded look-ahead state ---------
        candidate_epochs = [epoch for epoch in sample_lookaheads if epoch is not None]
        if maneuver_cursor < len(maneuvers):
            candidate_epochs.append(maneuvers[maneuver_cursor].epoch)
        event_epoch = _minimum_epoch(iter(candidate_epochs), time_adapter)

        ## -------------- step: consume equal maneuvers in prepared order ---------
        group_maneuvers: list[PreparedManeuverEntry] = []
        while maneuver_cursor < len(maneuvers) and time_adapter.same_instant(
            maneuvers[maneuver_cursor].epoch,
            event_epoch,
        ):
            group_maneuvers.append(maneuvers[maneuver_cursor])
            maneuver_cursor += 1

        ## -------------- step: consume and advance every due product sampler ---------
        group_products: list[OutputProduct] = []
        for index, rule in enumerate(rules):
            lookahead = sample_lookaheads[index]
            if lookahead is not None and time_adapter.same_instant(lookahead, event_epoch):
                group_products.append(rule.product)
                sample_lookaheads[index] = next(samplers[index], None)

        yield ScheduledEventGroup(
            epoch=event_epoch,
            maneuvers=tuple(group_maneuvers),
            sample_products=tuple(group_products),
        )


__all__ = [
    "SameScaleCalendarTimeAdapter",
    "ScheduledEventGroup",
    "iter_event_groups",
    "iter_sampling_epochs",
]
