# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_delivery.py
创建者    : Sycamore
创建日期  : 2026-07-28
最后修改  : 2026-07-29
版本号    : v1.1.0

■ 用途说明:
  验证观测交付终态、守恒汇总及流式交付信封的严格不可变 Core 契约。

■ 主要函数功能:
  - make_delivery_record: 构造各终态矩阵行的有效交付记录
  - make_ideal_observation/make_reported_observation: 构造信封测试使用的观测载荷
  - 契约测试: 覆盖终态矩阵、时延、哈希、原因、守恒和信封血缘

■ 功能特性:
  ✓ 覆盖每种交付终态及误差管线拒绝谱系的合法与非法字段组合
  ✓ 覆盖严格时延、SHA-256、稳定原因码和时间尺度规则
  ✓ 覆盖汇总守恒以及流式信封的判别联合重验证

■ 待办事项:
  - [ ] 无

■ 更新日志:
  v1.1.0 (2026-07-29): 补齐 SENSOR_MISSED/QUALITY_REJECTED 非法谱系矩阵
  v1.0.0 (2026-07-28): 创建交付结果、汇总和流式信封契约测试

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import pytest
from pydantic import BaseModel, ValidationError
from sycasphere.core.delivery import (
    DeliveryOutcome,
    DeliverySummary,
    ObservationDeliveryRecord,
    StreamingObservationEnvelope,
)
from sycasphere.core.epoch import Epoch, TimeScale
from sycasphere.core.frames import FrameKind, FrameRef
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.observations import (
    IdealObservation,
    ObservationChannel,
    ObservationMeasurement,
    ReportedObservation,
)
from sycasphere.core.schema import SchemaVersion

# =============================👐Seperate👐=============================
# Delivery-contract fixtures
# =============================👐Seperate👐=============================
MEASUREMENT_EPOCH = Epoch(value="2026-07-28T00:00:00Z", time_scale=TimeScale.UTC)
DELIVERY_EPOCH = Epoch(value="2026-07-28T00:00:05Z", time_scale=TimeScale.UTC)
EARLIER_EPOCH = Epoch(value="2026-07-27T23:59:59Z", time_scale=TimeScale.UTC)
TAI_DELIVERY_EPOCH = Epoch(value="2026-07-28T00:00:05", time_scale=TimeScale.TAI)
SCHEMA_VERSION = SchemaVersion(major=1, minor=0)
PAYLOAD_SHA256 = "a" * 64

_REASON_BY_OUTCOME = {
    "GEOMETRY_REJECTED": "sycasphere.geometry/OCCLUDED",
    "SENSOR_MISSED": "sycasphere.error/SENSOR_MISSED",
    "QUALITY_REJECTED": "sycasphere.error/QUALITY_REJECTED",
    "LINK_DROPPED": "sycasphere.link/DROPPED",
    "DELIVERED": "sycasphere.delivery/DELIVERED",
}


def measurement_model_ref() -> ModelRef:
    """Return a valid immutable measurement-model reference."""
    return ModelRef(
        model_id="org.example/RA_DEC_V1",
        interface_version=SCHEMA_VERSION,
        configuration={},
    )


def error_model_ref() -> ModelRef:
    """Return a valid immutable error-model reference."""
    return ModelRef(
        model_id="org.example/GAUSSIAN_RA_DEC_V1",
        interface_version=SCHEMA_VERSION,
        configuration={},
    )


def make_measurement() -> ObservationMeasurement:
    """Return a valid J2000 right-ascension/declination measurement."""
    return ObservationMeasurement(
        measurement_type="ANGLES_RA_DEC",
        values=(1.0, 0.2),
        component_names=("right_ascension", "declination"),
        component_units=("rad", "rad"),
        frame=FrameRef(kind=FrameKind.J2000),
        qualifiers={},
    )


def make_ideal_observation(**updates: object) -> IdealObservation:
    """Return one valid algorithm-visible Ideal observation."""
    data: dict[str, object] = {
        "channel": "IDEAL",
        "observation_id": "ideal-1",
        "event_id": "event-1",
        "measurement_epoch": MEASUREMENT_EPOCH,
        "sensor_id": "sensor-1",
        "subject_ref": {"kind": "KNOWN_OBJECT", "object_id": "public-1"},
        "measurement_model_ref": measurement_model_ref(),
        "measurement": make_measurement(),
    }
    return IdealObservation.model_validate({**data, **updates})


def make_reported_observation(**updates: object) -> ReportedObservation:
    """Return one valid algorithm-visible Reported observation."""
    data: dict[str, object] = {
        "channel": "REPORTED",
        "observation_id": "reported-1",
        "event_id": "event-1",
        "measurement_epoch": MEASUREMENT_EPOCH,
        "sensor_id": "sensor-1",
        "subject_ref": {"kind": "KNOWN_OBJECT", "object_id": "public-1"},
        "measurement_model_ref": measurement_model_ref(),
        "error_model_ref": error_model_ref(),
        "measurement": make_measurement(),
        "uncertainty": None,
    }
    return ReportedObservation.model_validate({**data, **updates})


def make_delivery_record(**updates: object) -> ObservationDeliveryRecord:
    """Return one valid record, deriving its stable reason from the selected outcome."""
    outcome = str(updates.get("outcome", "DELIVERED"))
    data: dict[str, object] = {
        "event_id": "event-1",
        "selected_channel": "REPORTED",
        "outcome": outcome,
        "measurement_epoch": MEASUREMENT_EPOCH,
        "delivery_epoch": DELIVERY_EPOCH,
        "latency_s": 5.0,
        "ideal_observation_id": "ideal-1",
        "reported_observation_id": "reported-1",
        "observation_payload_sha256": PAYLOAD_SHA256,
        "reason_code": _REASON_BY_OUTCOME[outcome],
    }
    return ObservationDeliveryRecord.model_validate({**data, **updates})


# =============================👐Seperate👐=============================
# Exact terminal-state matrix
# =============================👐Seperate👐=============================
@pytest.mark.parametrize(
    ("outcome", "channel", "ideal_id", "reported_id", "delivered"),
    [
        ("GEOMETRY_REJECTED", "IDEAL", None, None, False),
        ("GEOMETRY_REJECTED", "REPORTED", None, None, False),
        ("SENSOR_MISSED", "REPORTED", "ideal-1", None, False),
        ("QUALITY_REJECTED", "REPORTED", "ideal-1", None, False),
        ("LINK_DROPPED", "IDEAL", "ideal-1", None, False),
        ("LINK_DROPPED", "REPORTED", "ideal-1", "reported-1", False),
        ("DELIVERED", "IDEAL", "ideal-1", None, True),
        ("DELIVERED", "REPORTED", "ideal-1", "reported-1", True),
    ],
)
def test_delivery_record_accepts_exact_terminal_state_matrix(
    outcome: str,
    channel: str,
    ideal_id: str | None,
    reported_id: str | None,
    delivered: bool,
) -> None:
    record = make_delivery_record(
        outcome=outcome,
        selected_channel=channel,
        ideal_observation_id=ideal_id,
        reported_observation_id=reported_id,
        delivery_epoch=DELIVERY_EPOCH if delivered else None,
        latency_s=5.0 if delivered else None,
        observation_payload_sha256=(
            PAYLOAD_SHA256 if outcome in {"LINK_DROPPED", "DELIVERED"} else None
        ),
    )

    assert (record.delivery_epoch is not None) is delivered


@pytest.mark.parametrize("outcome", ["SENSOR_MISSED", "QUALITY_REJECTED"])
def test_error_pipeline_rejections_accept_optional_ideal_payload_hash(outcome: str) -> None:
    record = make_delivery_record(
        outcome=outcome,
        selected_channel="REPORTED",
        delivery_epoch=None,
        latency_s=None,
        reported_observation_id=None,
        observation_payload_sha256=PAYLOAD_SHA256,
    )

    assert record.observation_payload_sha256 == PAYLOAD_SHA256


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("ideal_observation_id", "ideal-1"),
        ("reported_observation_id", "reported-1"),
        ("observation_payload_sha256", PAYLOAD_SHA256),
    ],
)
def test_geometry_rejected_forbids_all_observation_lineage(
    field_name: str,
    value: str,
) -> None:
    lineage: dict[str, object] = {
        "ideal_observation_id": None,
        "reported_observation_id": None,
        "observation_payload_sha256": None,
    }
    lineage[field_name] = value

    with pytest.raises(ValidationError, match="GEOMETRY_REJECTED"):
        make_delivery_record(
            outcome="GEOMETRY_REJECTED",
            selected_channel="IDEAL",
            delivery_epoch=None,
            latency_s=None,
            **lineage,
        )


@pytest.mark.parametrize("outcome", ["SENSOR_MISSED", "QUALITY_REJECTED"])
def test_error_pipeline_rejections_require_reported_channel(outcome: str) -> None:
    with pytest.raises(ValidationError, match="REPORTED"):
        make_delivery_record(
            outcome=outcome,
            selected_channel="IDEAL",
            delivery_epoch=None,
            latency_s=None,
            reported_observation_id=None,
            observation_payload_sha256=None,
        )


@pytest.mark.parametrize("outcome", ["SENSOR_MISSED", "QUALITY_REJECTED"])
@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("ideal_observation_id", None),
        ("reported_observation_id", "reported-1"),
    ],
)
def test_error_pipeline_rejections_require_exact_observation_lineage(
    outcome: str,
    field_name: str,
    invalid_value: str | None,
) -> None:
    lineage: dict[str, object] = {
        "ideal_observation_id": "ideal-1",
        "reported_observation_id": None,
    }
    lineage[field_name] = invalid_value

    with pytest.raises(ValidationError, match=outcome):
        make_delivery_record(
            outcome=outcome,
            selected_channel="REPORTED",
            delivery_epoch=None,
            latency_s=None,
            observation_payload_sha256=None,
            **lineage,
        )


@pytest.mark.parametrize(
    ("channel", "field_name"),
    [
        ("IDEAL", "ideal_observation_id"),
        ("REPORTED", "reported_observation_id"),
        ("REPORTED", "delivery_epoch"),
        ("REPORTED", "latency_s"),
        ("REPORTED", "observation_payload_sha256"),
    ],
)
def test_delivered_requires_selected_payload_identity_timing_and_hash(
    channel: str,
    field_name: str,
) -> None:
    updates: dict[str, object] = {
        "selected_channel": channel,
        "reported_observation_id": None if channel == "IDEAL" else "reported-1",
        field_name: None,
    }

    with pytest.raises(ValidationError, match="DELIVERED"):
        make_delivery_record(**updates)


@pytest.mark.parametrize(
    "outcome",
    ["GEOMETRY_REJECTED", "SENSOR_MISSED", "QUALITY_REJECTED", "LINK_DROPPED"],
)
@pytest.mark.parametrize(
    ("field_name", "value"),
    [("delivery_epoch", DELIVERY_EPOCH), ("latency_s", 5.0)],
)
def test_non_delivered_outcomes_forbid_delivery_timing(
    outcome: str,
    field_name: str,
    value: Epoch | float,
) -> None:
    base_by_outcome: dict[str, dict[str, object]] = {
        "GEOMETRY_REJECTED": {
            "selected_channel": "IDEAL",
            "ideal_observation_id": None,
            "reported_observation_id": None,
            "observation_payload_sha256": None,
        },
        "SENSOR_MISSED": {
            "selected_channel": "REPORTED",
            "reported_observation_id": None,
            "observation_payload_sha256": None,
        },
        "QUALITY_REJECTED": {
            "selected_channel": "REPORTED",
            "reported_observation_id": None,
            "observation_payload_sha256": None,
        },
        "LINK_DROPPED": {
            "selected_channel": "REPORTED",
            "observation_payload_sha256": PAYLOAD_SHA256,
        },
    }
    updates = {
        "outcome": outcome,
        "delivery_epoch": None,
        "latency_s": None,
        **base_by_outcome[outcome],
        field_name: value,
    }

    with pytest.raises(ValidationError, match=r"delivery_epoch.*latency|delivery timing"):
        make_delivery_record(**updates)


@pytest.mark.parametrize("missing_field", ["ideal_observation_id", "reported_observation_id"])
def test_reported_link_drop_requires_both_observation_ids(missing_field: str) -> None:
    with pytest.raises(ValidationError, match="LINK_DROPPED"):
        make_delivery_record(
            outcome="LINK_DROPPED",
            selected_channel="REPORTED",
            delivery_epoch=None,
            latency_s=None,
            **{missing_field: None},
        )


@pytest.mark.parametrize("outcome", ["LINK_DROPPED", "DELIVERED"])
def test_ideal_terminal_payload_forbids_reported_observation_id(outcome: str) -> None:
    with pytest.raises(ValidationError, match=outcome):
        make_delivery_record(
            outcome=outcome,
            selected_channel="IDEAL",
            reported_observation_id="reported-1",
            delivery_epoch=DELIVERY_EPOCH if outcome == "DELIVERED" else None,
            latency_s=5.0 if outcome == "DELIVERED" else None,
        )


# =============================👐Seperate👐=============================
# Strict reason, hash, and delivery-time values
# =============================👐Seperate👐=============================
@pytest.mark.parametrize("latency_s", [-0.1, 5, math.nan])
def test_delivery_latency_is_a_finite_nonnegative_strict_float(
    latency_s: object,
) -> None:
    with pytest.raises(ValidationError, match="latency"):
        make_delivery_record(latency_s=latency_s)


@pytest.mark.parametrize("invalid_hash", ["a" * 63, "A" * 64, "g" * 64])
def test_payload_hash_is_exact_lowercase_sha256(invalid_hash: str) -> None:
    with pytest.raises(ValidationError, match="observation_payload_sha256"):
        make_delivery_record(observation_payload_sha256=invalid_hash)


@pytest.mark.parametrize(
    ("outcome", "reason_code"),
    [
        ("GEOMETRY_REJECTED", "free text"),
        ("GEOMETRY_REJECTED", "sycasphere.geometry/VISIBLE"),
        ("SENSOR_MISSED", "free text"),
        ("QUALITY_REJECTED", "sycasphere/QUALITY_REJECTED"),
        ("LINK_DROPPED", "sycasphere.link/"),
        ("DELIVERED", "sycasphere.delivery/DELIVERED/EXTRA"),
    ],
)
def test_delivery_reason_requires_an_approved_geometry_or_namespaced_machine_code(
    outcome: str,
    reason_code: str,
) -> None:
    updates: dict[str, object] = {
        "outcome": outcome,
        "reason_code": reason_code,
    }
    if outcome == "GEOMETRY_REJECTED":
        updates.update(
            selected_channel="IDEAL",
            ideal_observation_id=None,
            reported_observation_id=None,
            delivery_epoch=None,
            latency_s=None,
            observation_payload_sha256=None,
        )
    elif outcome in {"SENSOR_MISSED", "QUALITY_REJECTED"}:
        updates.update(
            reported_observation_id=None,
            delivery_epoch=None,
            latency_s=None,
            observation_payload_sha256=None,
        )
    elif outcome == "LINK_DROPPED":
        updates.update(delivery_epoch=None, latency_s=None)

    with pytest.raises(ValidationError, match="reason_code"):
        make_delivery_record(**updates)


@pytest.mark.parametrize(
    "outcome",
    ["SENSOR_MISSED", "QUALITY_REJECTED", "LINK_DROPPED", "DELIVERED"],
)
def test_non_geometry_outcomes_accept_extension_namespaced_reason_codes(
    outcome: str,
) -> None:
    updates: dict[str, object] = {
        "outcome": outcome,
        "reason_code": f"org.example/{outcome}_PLUGIN_V1",
    }
    if outcome in {"SENSOR_MISSED", "QUALITY_REJECTED"}:
        updates.update(
            reported_observation_id=None,
            delivery_epoch=None,
            latency_s=None,
            observation_payload_sha256=None,
        )
    elif outcome == "LINK_DROPPED":
        updates.update(delivery_epoch=None, latency_s=None)

    record = make_delivery_record(**updates)

    assert record.reason_code == f"org.example/{outcome}_PLUGIN_V1"


@pytest.mark.parametrize(
    "reason_code",
    [
        "sycasphere.geometry/OCCLUDED",
        "sycasphere.geometry/OUT_OF_FIELD_OF_VIEW",
        "sycasphere.geometry/INSUFFICIENT_ILLUMINATION",
        "sycasphere.geometry/POINTING_UNAVAILABLE",
    ],
)
def test_geometry_rejected_accepts_each_stable_geometry_reason(reason_code: str) -> None:
    record = make_delivery_record(
        outcome="GEOMETRY_REJECTED",
        selected_channel="IDEAL",
        ideal_observation_id=None,
        reported_observation_id=None,
        delivery_epoch=None,
        latency_s=None,
        observation_payload_sha256=None,
        reason_code=reason_code,
    )

    assert record.reason_code == reason_code


@pytest.mark.parametrize(
    "delivery_epoch",
    [TAI_DELIVERY_EPOCH, EARLIER_EPOCH],
)
def test_delivery_epoch_matches_measurement_scale_and_is_not_earlier(
    delivery_epoch: Epoch,
) -> None:
    with pytest.raises(ValidationError, match=r"TimeScale|earlier"):
        make_delivery_record(delivery_epoch=delivery_epoch)


# =============================👐Seperate👐=============================
# Summary conservation and streaming envelope
# =============================👐Seperate👐=============================
def test_delivery_summary_counts_must_conserve_total_events() -> None:
    summary = DeliverySummary(
        total_events=5,
        delivered=1,
        geometry_rejected=1,
        sensor_missed=1,
        quality_rejected=1,
        link_dropped=1,
    )
    assert summary.total_events == 5

    with pytest.raises(ValidationError, match="sum"):
        DeliverySummary(
            total_events=6,
            delivered=summary.delivered,
            geometry_rejected=summary.geometry_rejected,
            sensor_missed=summary.sensor_missed,
            quality_rejected=summary.quality_rejected,
            link_dropped=summary.link_dropped,
        )


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [("total_events", -1), ("delivered", -1), ("link_dropped", 1.0)],
)
def test_delivery_summary_counts_are_strict_nonnegative_integers(
    field_name: str,
    invalid_value: object,
) -> None:
    data: dict[str, object] = {
        "total_events": 0,
        "delivered": 0,
        "geometry_rejected": 0,
        "sensor_missed": 0,
        "quality_rejected": 0,
        "link_dropped": 0,
        field_name: invalid_value,
    }

    with pytest.raises(ValidationError, match=field_name):
        DeliverySummary.model_validate(data)


@pytest.mark.parametrize(
    "observation",
    [make_ideal_observation(), make_reported_observation()],
)
def test_streaming_envelope_wraps_matching_delivered_observation(
    observation: IdealObservation | ReportedObservation,
) -> None:
    envelope = StreamingObservationEnvelope(
        event_id=observation.event_id,
        delivery_epoch=DELIVERY_EPOCH,
        observation=observation,
    )

    assert envelope.observation.channel is observation.channel
    assert envelope.observation is not observation


def test_streaming_envelope_rejects_event_id_mismatch() -> None:
    observation = make_reported_observation()

    with pytest.raises(ValidationError, match="event_id"):
        StreamingObservationEnvelope(
            event_id="other",
            delivery_epoch=DELIVERY_EPOCH,
            observation=observation,
        )


@pytest.mark.parametrize("delivery_epoch", [EARLIER_EPOCH, TAI_DELIVERY_EPOCH])
def test_streaming_envelope_rejects_earlier_or_cross_scale_delivery(
    delivery_epoch: Epoch,
) -> None:
    observation = make_reported_observation()

    with pytest.raises(ValidationError, match=r"earlier|TimeScale"):
        StreamingObservationEnvelope(
            event_id=observation.event_id,
            delivery_epoch=delivery_epoch,
            observation=observation,
        )


def test_streaming_envelope_revalidates_copied_observation_discriminator() -> None:
    invalid = make_reported_observation().model_copy(update={"channel": "IDEAL"})

    with pytest.raises(ValidationError, match=r"channel|ReportedObservation"):
        StreamingObservationEnvelope(
            event_id=invalid.event_id,
            delivery_epoch=DELIVERY_EPOCH,
            observation=invalid,
        )


def test_streaming_envelope_schema_excludes_deferred_delivery_metadata() -> None:
    assert set(StreamingObservationEnvelope.model_fields) == {
        "event_id",
        "delivery_epoch",
        "observation",
    }

    with pytest.raises(ValidationError, match="sequence_number"):
        StreamingObservationEnvelope(
            event_id="event-1",
            delivery_epoch=DELIVERY_EPOCH,
            observation=make_reported_observation(),
            sequence_number=1,
        )


# =============================👐Seperate👐=============================
# Immutable boundary and serialization behavior
# =============================👐Seperate👐=============================
@pytest.mark.parametrize(
    "model_type",
    [
        ObservationDeliveryRecord,
        DeliverySummary,
        StreamingObservationEnvelope,
    ],
)
def test_delivery_models_are_frozen_extra_forbid_and_revalidate_instances(
    model_type: type[BaseModel],
) -> None:
    assert model_type.model_config["frozen"] is True
    assert model_type.model_config["extra"] == "forbid"
    assert model_type.model_config["revalidate_instances"] == "always"


def test_delivery_models_are_frozen_and_round_trip_as_json() -> None:
    record = make_delivery_record()
    summary = DeliverySummary(
        total_events=1,
        delivered=1,
        geometry_rejected=0,
        sensor_missed=0,
        quality_rejected=0,
        link_dropped=0,
    )
    envelope = StreamingObservationEnvelope(
        event_id="event-1",
        delivery_epoch=DELIVERY_EPOCH,
        observation=make_reported_observation(),
    )

    with pytest.raises(ValidationError):
        record.event_id = "event-2"
    with pytest.raises(ValidationError):
        summary.total_events = 2
    with pytest.raises(ValidationError):
        envelope.event_id = "event-2"
    assert ObservationDeliveryRecord.model_validate_json(record.model_dump_json()) == record
    assert DeliverySummary.model_validate_json(summary.model_dump_json()) == summary
    assert StreamingObservationEnvelope.model_validate_json(envelope.model_dump_json()) == envelope


def test_delivery_boundaries_revalidate_copied_invalid_nested_models() -> None:
    malformed_epoch = MEASUREMENT_EPOCH.model_copy(update={"value": "not-an-epoch"})
    malformed_observation = make_reported_observation().model_copy(update={"event_id": ""})

    with pytest.raises(ValidationError, match="Epoch"):
        make_delivery_record(measurement_epoch=malformed_epoch)
    with pytest.raises(ValidationError, match="event_id"):
        StreamingObservationEnvelope(
            event_id="event-1",
            delivery_epoch=DELIVERY_EPOCH,
            observation=malformed_observation,
        )


def test_delivery_enums_expose_only_approved_stable_values() -> None:
    assert [outcome.value for outcome in DeliveryOutcome] == [
        "GEOMETRY_REJECTED",
        "SENSOR_MISSED",
        "QUALITY_REJECTED",
        "LINK_DROPPED",
        "DELIVERED",
    ]
    assert ObservationChannel.IDEAL.value == "IDEAL"
    assert ObservationChannel.REPORTED.value == "REPORTED"
