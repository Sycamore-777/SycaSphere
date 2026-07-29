# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : delivery.py
创建者    : Sycamore
创建日期  : 2026-07-28
最后修改  : 2026-07-28
版本号    : v1.0.0

■ 用途说明:
  定义观测事件终态交付记录、守恒汇总和算法流式交付信封的不可变 Core 契约。

■ 主要函数功能:
  - ObservationDeliveryRecord: 校验交付终态矩阵、原因、载荷血缘和交付时刻
  - DeliverySummary: 校验非负终态计数及事件总数守恒
  - StreamingObservationEnvelope: 重验成功交付的 Ideal/Reported 观测及其时序血缘

■ 功能特性:
  ✓ 分离结构化交付事实与 Observation payload
  ✓ 固定几何拒绝原因并允许命名空间化扩展原因
  ✓ 保持流式信封最小且不引入乱序、重复或重传字段

■ 待办事项:
  - [ ] 无

■ 更新日志:
  v1.0.0 (2026-07-28): 创建观测交付终态、汇总和流式信封契约

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from sycasphere.core._definitions import DefinitionString
from sycasphere.core._validation import (
    Sha256Hex,
    StrictFiniteFloat,
    StrictNonNegativeInt,
    snapshot_model_input,
)
from sycasphere.core.epoch import Epoch, _is_strictly_before_same_scale
from sycasphere.core.observations import (
    IdealObservation,
    ObservationChannel,
    ReportedObservation,
)

# =============================👐Seperate👐=============================
# Stable delivery outcomes and reason-code vocabulary
# =============================👐Seperate👐=============================
_NAMESPACED_REASON_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]*(?:\.[A-Za-z0-9_.-]+)+/[A-Za-z0-9_.-]+$"
type _NamespacedReasonCode = Annotated[
    str,
    StringConstraints(strict=True, pattern=_NAMESPACED_REASON_PATTERN),
]

_GEOMETRY_REASONS = frozenset(
    {
        "sycasphere.geometry/OCCLUDED",
        "sycasphere.geometry/OUT_OF_FIELD_OF_VIEW",
        "sycasphere.geometry/INSUFFICIENT_ILLUMINATION",
        "sycasphere.geometry/POINTING_UNAVAILABLE",
    }
)


class DeliveryOutcome(StrEnum):
    """Terminal scientific delivery outcomes for one observation event."""

    GEOMETRY_REJECTED = "GEOMETRY_REJECTED"
    SENSOR_MISSED = "SENSOR_MISSED"
    QUALITY_REJECTED = "QUALITY_REJECTED"
    LINK_DROPPED = "LINK_DROPPED"
    DELIVERED = "DELIVERED"


def _require_delivery_timing(
    measurement_epoch: Epoch,
    delivery_epoch: Epoch,
) -> None:
    """Require directly comparable delivery timing without converting time scales."""
    if delivery_epoch.time_scale is not measurement_epoch.time_scale:
        raise ValueError("delivery_epoch TimeScale must match measurement_epoch")
    if _is_strictly_before_same_scale(delivery_epoch, measurement_epoch) is True:
        raise ValueError("delivery_epoch must not be earlier than measurement_epoch")


# =============================👐Seperate👐=============================
# Per-event terminal delivery record
# =============================👐Seperate👐=============================
class ObservationDeliveryRecord(BaseModel):
    """One immutable terminal outcome record for an observation event."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    event_id: DefinitionString
    selected_channel: ObservationChannel
    outcome: DeliveryOutcome
    measurement_epoch: Epoch
    delivery_epoch: Epoch | None
    latency_s: StrictFiniteFloat | None
    ideal_observation_id: DefinitionString | None
    reported_observation_id: DefinitionString | None
    observation_payload_sha256: Sha256Hex | None
    reason_code: _NamespacedReasonCode

    @field_validator("measurement_epoch", "delivery_epoch", mode="before")
    @classmethod
    def _snapshot_epoch(cls, value: Any) -> Any:
        """Detach and revalidate nested Epoch instances at the record boundary."""
        return snapshot_model_input(value)

    @field_validator("latency_s", mode="before")
    @classmethod
    def _require_strict_float_latency(cls, value: Any) -> Any:
        """Reject integer and coercible latency values before float validation."""
        if value is not None and type(value) is not float:
            raise ValueError("latency_s must be a built-in float")
        return value

    @model_validator(mode="after")
    def _validate_terminal_state(self) -> ObservationDeliveryRecord:
        """Apply the exact outcome/channel identity, hash, reason and timing matrix."""
        if self.outcome is DeliveryOutcome.GEOMETRY_REJECTED:
            self._validate_geometry_rejected()
        elif self.outcome in {
            DeliveryOutcome.SENSOR_MISSED,
            DeliveryOutcome.QUALITY_REJECTED,
        }:
            self._validate_error_pipeline_rejection()
        elif self.outcome is DeliveryOutcome.LINK_DROPPED:
            self._validate_payload_terminal(delivered=False)
        else:
            self._validate_payload_terminal(delivered=True)
        return self

    def _validate_geometry_rejected(self) -> None:
        """Require geometry rejection to precede every observation payload."""
        if (
            self.ideal_observation_id is not None
            or self.reported_observation_id is not None
            or self.observation_payload_sha256 is not None
        ):
            raise ValueError("GEOMETRY_REJECTED forbids observation IDs and payload hash")
        self._require_no_delivery_timing()
        if self.reason_code not in _GEOMETRY_REASONS:
            raise ValueError(
                "reason_code for GEOMETRY_REJECTED must identify an approved geometry status"
            )

    def _validate_error_pipeline_rejection(self) -> None:
        """Require a formed Ideal and no Reported after an error-pipeline rejection."""
        if self.selected_channel is not ObservationChannel.REPORTED:
            raise ValueError(f"{self.outcome.value} requires the REPORTED selected channel")
        if self.ideal_observation_id is None or self.reported_observation_id is not None:
            raise ValueError(f"{self.outcome.value} requires an Ideal ID and forbids a Reported ID")
        self._require_no_delivery_timing()

    def _validate_payload_terminal(self, *, delivered: bool) -> None:
        """Require lineage for the selected payload and exact link/delivery timing."""
        if self.ideal_observation_id is None:
            raise ValueError(f"{self.outcome.value} requires an Ideal observation ID")
        if self.selected_channel is ObservationChannel.IDEAL:
            if self.reported_observation_id is not None:
                raise ValueError(f"{self.outcome.value} on IDEAL forbids a Reported observation ID")
        elif self.reported_observation_id is None:
            raise ValueError(f"{self.outcome.value} on REPORTED requires a Reported observation ID")
        if self.observation_payload_sha256 is None:
            raise ValueError(f"{self.outcome.value} requires the selected payload hash")

        if delivered:
            if self.delivery_epoch is None or self.latency_s is None:
                raise ValueError("DELIVERED requires delivery_epoch and latency_s")
            if self.latency_s < 0.0:
                raise ValueError("DELIVERED latency_s must be nonnegative")
            _require_delivery_timing(self.measurement_epoch, self.delivery_epoch)
        else:
            self._require_no_delivery_timing()

    def _require_no_delivery_timing(self) -> None:
        """Forbid delivery timing on every outcome that did not reach the algorithm."""
        if self.delivery_epoch is not None or self.latency_s is not None:
            raise ValueError(
                "non-delivered outcomes forbid delivery timing (delivery_epoch and latency_s)"
            )


# =============================👐Seperate👐=============================
# Aggregate conservation and streaming delivery envelope
# =============================👐Seperate👐=============================
class DeliverySummary(BaseModel):
    """Conserved counts of all terminal observation delivery outcomes."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    total_events: StrictNonNegativeInt
    delivered: StrictNonNegativeInt
    geometry_rejected: StrictNonNegativeInt
    sensor_missed: StrictNonNegativeInt
    quality_rejected: StrictNonNegativeInt
    link_dropped: StrictNonNegativeInt

    @model_validator(mode="after")
    def _validate_event_conservation(self) -> DeliverySummary:
        """Require every event to contribute to exactly one terminal outcome count."""
        outcome_total = (
            self.delivered
            + self.geometry_rejected
            + self.sensor_missed
            + self.quality_rejected
            + self.link_dropped
        )
        if outcome_total != self.total_events:
            raise ValueError("delivery outcome counts must sum to total_events")
        return self


class StreamingObservationEnvelope(BaseModel):
    """A minimal successful-delivery envelope for one revalidated observation.

    Core cannot independently prove the DELIVERED outcome because the envelope
    intentionally contains no DeliveryRecord. Engine may construct this model only
    after the corresponding DELIVERED record passes its lineage checks.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    event_id: DefinitionString
    delivery_epoch: Epoch
    observation: Annotated[
        IdealObservation | ReportedObservation,
        Field(discriminator="channel"),
    ]

    @field_validator("delivery_epoch", mode="before")
    @classmethod
    def _snapshot_delivery_epoch(cls, value: Any) -> Any:
        """Detach and revalidate the delivery Epoch."""
        return snapshot_model_input(value)

    @field_validator("observation", mode="before")
    @classmethod
    def _snapshot_observation(cls, value: Any) -> Any:
        """Detach and revalidate the channel-discriminated Observation payload."""
        if isinstance(value, IdealObservation) and value.channel is not ObservationChannel.IDEAL:
            raise ValueError("IdealObservation channel discriminator is invalid")
        if (
            isinstance(value, ReportedObservation)
            and value.channel is not ObservationChannel.REPORTED
        ):
            raise ValueError("ReportedObservation channel discriminator is invalid")
        return snapshot_model_input(value)

    @model_validator(mode="after")
    def _validate_delivery_lineage(self) -> StreamingObservationEnvelope:
        """Keep event identity and delivery ordering aligned with the observation."""
        if self.event_id != self.observation.event_id:
            raise ValueError("envelope event_id must equal observation event_id")
        _require_delivery_timing(
            self.observation.measurement_epoch,
            self.delivery_epoch,
        )
        return self
