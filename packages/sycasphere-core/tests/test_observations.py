# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_observations.py
创建者    : Sycamore
创建日期  : 2026-07-28
最后修改  : 2026-07-29
版本号    : v1.2.1

■ 用途说明:
  验证观测身份、事件、测量、有效残余协方差和独立 Ideal/Reported 载荷契约。

■ 主要函数功能:
  - 观测身份验证: 覆盖公开对象、tracklet 和未关联三种身份模式
  - 测量与事件验证: 覆盖标准及自定义载荷、嵌套重验证和不可变性
  - 协方差与观测通道验证: 覆盖严格数值、公差、判别联合和隐私边界

■ 功能特性:
  ✓ 覆盖标准测量的精确分量、单位、帧、范围和 qualifier 语义
  ✓ 覆盖公开主体实例旁路与内部真值身份隔离
  ✓ 覆盖有效残余协方差极值稳定性和 Ideal/Reported 独立模型

■ 待办事项:
  - [ ] 无

■ 更新日志:
  v1.2.1 (2026-07-29): 增加调用方严格 NumPy error-state 下的次正规 PSD 回归测试
  v1.2.0 (2026-07-29): 增加主体重验、严格积分时间和极值协方差回归测试
  v1.1.0 (2026-07-28): 增加协方差和 Ideal/Reported 通道契约测试
  v1.0.0 (2026-07-28): 创建观测身份、事件和测量载荷契约测试

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Mapping
from types import MappingProxyType

import numpy as np
import pytest
from pydantic import TypeAdapter, ValidationError
from sycasphere.core.epoch import Epoch, TimeScale
from sycasphere.core.frames import FrameKind, FrameRef
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.observations import (
    CustomMeasurementSchemaRef,
    GeometryStatus,
    IdealObservation,
    KnownObjectSubjectRef,
    MeasurementType,
    MeasurementUncertainty,
    Observation,
    ObservationChannel,
    ObservationEvent,
    ObservationMeasurement,
    ObservationSubjectRef,
    ReportedObservation,
    TrackletSubjectRef,
    UnassociatedSubjectRef,
)
from sycasphere.core.schema import SchemaVersion

# =============================👐Seperate👐=============================
# Observation-contract fixtures
# =============================👐Seperate👐=============================
EPOCH = Epoch(value="2026-07-28T00:00:00Z", time_scale=TimeScale.UTC)
SCHEMA_VERSION = SchemaVersion(major=1, minor=0)
J2000_FRAME = FrameRef(kind=FrameKind.J2000)
SENSOR_FRAME = FrameRef(
    kind=FrameKind.SENSOR,
    owner_id="sensor-1",
    convention="org.example/SENSOR_AXES_V1",
    reference_epoch=EPOCH,
)
BODY_FRAME = FrameRef(
    kind=FrameKind.BODY,
    owner_id="platform-1",
    convention="org.example/BODY_AXES_V1",
    reference_epoch=EPOCH,
)


class FloatSubclass(float):
    """Exercise strict semantic fields without changing general JSON compatibility."""


def measurement_model_ref() -> ModelRef:
    """Return a valid immutable measurement-model reference."""
    return ModelRef(
        model_id="org.example/RA_DEC_V1",
        interface_version=SCHEMA_VERSION,
        configuration={},
    )


def error_model_ref() -> ModelRef:
    """Return a valid immutable residual-error-model reference."""
    return ModelRef(
        model_id="org.example/GAUSSIAN_RA_DEC_V1",
        interface_version=SCHEMA_VERSION,
        configuration={},
    )


def ra_dec_data(**updates: object) -> dict[str, object]:
    """Return a valid standard RA/DEC payload with selected replacements."""
    data: dict[str, object] = {
        "measurement_type": "ANGLES_RA_DEC",
        "values": (1.0, 0.2),
        "component_names": ("right_ascension", "declination"),
        "component_units": ("rad", "rad"),
        "frame": J2000_FRAME,
        "qualifiers": {},
    }
    return {**data, **updates}


def az_el_data(**updates: object) -> dict[str, object]:
    """Return a valid standard azimuth/elevation payload."""
    data: dict[str, object] = {
        "measurement_type": "ANGLES_AZ_EL",
        "values": (1.0, 0.2),
        "component_names": ("azimuth", "elevation"),
        "component_units": ("rad", "rad"),
        "frame": SENSOR_FRAME,
        "qualifiers": {"angle_convention_id": "org.example/AZ_EL_V1"},
    }
    return {**data, **updates}


def range_data(**updates: object) -> dict[str, object]:
    """Return a valid one-way range payload."""
    data: dict[str, object] = {
        "measurement_type": "RANGE",
        "values": (1000.0,),
        "component_names": ("range",),
        "component_units": ("m",),
        "frame": None,
        "qualifiers": {"path_kind": "ONE_WAY"},
    }
    return {**data, **updates}


def range_rate_data(**updates: object) -> dict[str, object]:
    """Return a valid signed range-rate payload."""
    data: dict[str, object] = {
        "measurement_type": "RANGE_RATE",
        "values": (-10.0,),
        "component_names": ("range_rate",),
        "component_units": ("m/s",),
        "frame": None,
        "qualifiers": {
            "path_kind": "TWO_WAY",
            "sign_convention": "POSITIVE_RECEDING",
            "integration_interval_s": 1.0,
        },
    }
    return {**data, **updates}


def los_data(**updates: object) -> dict[str, object]:
    """Return a valid J2000 unit line-of-sight payload."""
    data: dict[str, object] = {
        "measurement_type": "LOS_UNIT_VECTOR",
        "values": (1.0, 0.0, 0.0),
        "component_names": ("los_x", "los_y", "los_z"),
        "component_units": ("1", "1", "1"),
        "frame": J2000_FRAME,
        "qualifiers": {},
    }
    return {**data, **updates}


def custom_data(**updates: object) -> dict[str, object]:
    """Return a valid custom pixel-centroid payload."""
    data: dict[str, object] = {
        "measurement_type": "CUSTOM",
        "values": (10.0, 20.0),
        "component_names": ("pixel_x", "pixel_y"),
        "component_units": ("pixel", "pixel"),
        "frame": None,
        "custom_type": "org.example/PIXEL_CENTROID_V1",
        "custom_schema_ref": {
            "schema_id": "org.example/PIXEL_CENTROID_SCHEMA",
            "schema_version": SCHEMA_VERSION,
            "sha256": "a" * 64,
        },
        "qualifiers": {"detector": "primary"},
    }
    return {**data, **updates}


def valid_ra_dec_measurement() -> ObservationMeasurement:
    """Return one valid RA/DEC measurement boundary model."""
    return ObservationMeasurement.model_validate(ra_dec_data())


def valid_ra_dec_uncertainty() -> MeasurementUncertainty:
    """Return one valid effective RA/DEC residual covariance."""
    return MeasurementUncertainty.from_standard_deviations(
        valid_ra_dec_measurement(),
        (2.0e-5, 3.0e-5),
    )


def make_ideal(**updates: object) -> IdealObservation:
    """Return one valid algorithm-visible ideal observation."""
    data: dict[str, object] = {
        "channel": "IDEAL",
        "observation_id": "ideal-observation-1",
        "event_id": "event-1",
        "measurement_epoch": EPOCH,
        "sensor_id": "sensor-1",
        "subject_ref": {"kind": "KNOWN_OBJECT", "object_id": "public-1"},
        "measurement_model_ref": measurement_model_ref(),
        "measurement": valid_ra_dec_measurement(),
    }
    return IdealObservation.model_validate({**data, **updates})


def make_reported(**updates: object) -> ReportedObservation:
    """Return one valid algorithm-visible reported observation."""
    data: dict[str, object] = {
        "channel": "REPORTED",
        "observation_id": "reported-observation-1",
        "event_id": "event-1",
        "measurement_epoch": EPOCH,
        "sensor_id": "sensor-1",
        "subject_ref": {"kind": "KNOWN_OBJECT", "object_id": "public-1"},
        "measurement_model_ref": measurement_model_ref(),
        "error_model_ref": error_model_ref(),
        "measurement": valid_ra_dec_measurement(),
        "uncertainty": valid_ra_dec_uncertainty(),
    }
    return ReportedObservation.model_validate({**data, **updates})


def make_event(**updates: object) -> ObservationEvent:
    """Return one valid final observation-event fact."""
    data: dict[str, object] = {
        "event_id": "event-1",
        "schedule_id": "schedule-1",
        "measurement_epoch": EPOCH,
        "sensor_id": "sensor-1",
        "platform_id": "platform-1",
        "truth_target_entity_id": "truth-target-1",
        "public_subject_ref": {"kind": "KNOWN_OBJECT", "object_id": "public-1"},
        "measurement_model_ref": measurement_model_ref(),
        "measurement_type": "ANGLES_RA_DEC",
        "geometry_status": "VISIBLE",
    }
    return ObservationEvent.model_validate({**data, **updates})


# =============================👐Seperate👐=============================
# Algorithm-safe subject-reference tests
# =============================👐Seperate👐=============================
def test_subject_ref_union_supports_known_tracklet_and_unassociated_modes() -> None:
    adapter = TypeAdapter(ObservationSubjectRef)
    assert isinstance(
        adapter.validate_python({"kind": "KNOWN_OBJECT", "object_id": "public-1"}),
        KnownObjectSubjectRef,
    )
    assert isinstance(
        adapter.validate_python({"kind": "TRACKLET", "tracklet_id": "tracklet-1"}),
        TrackletSubjectRef,
    )
    assert isinstance(
        adapter.validate_python({"kind": "UNASSOCIATED"}),
        UnassociatedSubjectRef,
    )


@pytest.mark.parametrize(
    "data",
    [
        {"kind": "KNOWN_OBJECT", "object_id": "   "},
        {"kind": "TRACKLET", "tracklet_id": ""},
        {"kind": "UNASSOCIATED", "truth_target_entity_id": "truth-target-1"},
        {"kind": "UNKNOWN"},
    ],
)
def test_subject_refs_reject_blank_unknown_or_truth_leaking_fields(
    data: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(ObservationSubjectRef).validate_python(data)


def test_known_subject_revalidates_tampered_instance_at_public_boundaries() -> None:
    subject = KnownObjectSubjectRef(object_id="public-1")
    object.__setattr__(subject, "object_id", "")

    with pytest.raises(ValidationError, match="object_id"):
        KnownObjectSubjectRef.model_validate(subject)
    with pytest.raises(ValidationError, match="object_id"):
        TypeAdapter(ObservationSubjectRef).validate_python(subject)


def test_tracklet_subject_revalidates_constructed_instance_at_public_boundaries() -> None:
    subject = TrackletSubjectRef.model_construct(
        kind="TRACKLET",
        tracklet_id="",
    )

    with pytest.raises(ValidationError, match="tracklet_id"):
        TrackletSubjectRef.model_validate(subject)
    with pytest.raises(ValidationError, match="tracklet_id"):
        TypeAdapter(ObservationSubjectRef).validate_python(subject)


def test_unassociated_subject_revalidates_copied_extra_at_public_boundaries() -> None:
    subject = UnassociatedSubjectRef().model_copy(
        update={"truth_target_entity_id": "truth-target-1"}
    )

    assert subject.kind == "UNASSOCIATED"
    with pytest.raises(ValidationError, match="truth_target_entity_id"):
        UnassociatedSubjectRef.model_validate(subject)
    with pytest.raises(ValidationError, match="truth_target_entity_id"):
        TypeAdapter(ObservationSubjectRef).validate_python(subject)


# =============================👐Seperate👐=============================
# Self-describing measurement tests
# =============================👐Seperate👐=============================
def test_ra_dec_measurement_is_strict_self_describing_j2000() -> None:
    measurement = ObservationMeasurement(
        measurement_type="ANGLES_RA_DEC",
        values=(1.0, 0.2),
        component_names=("right_ascension", "declination"),
        component_units=("rad", "rad"),
        frame=FrameRef(kind=FrameKind.J2000),
        qualifiers={},
    )

    assert measurement.values == (1.0, 0.2)


@pytest.mark.parametrize(
    "data",
    [
        ra_dec_data(values=(2.0 * math.pi, 0.0)),
        ra_dec_data(values=(0.0, math.pi)),
        ra_dec_data(component_units=("deg", "deg")),
        ra_dec_data(frame=None),
        range_data(values=(-1.0,)),
        los_data(values=(1.0, 1.0, 0.0)),
        range_data(qualifiers={"path_kind": "ROUND_TRIP"}),
    ],
)
def test_standard_measurements_reject_invalid_values_and_semantics(
    data: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ObservationMeasurement.model_validate(data)


def test_custom_measurement_requires_exact_schema_reference() -> None:
    measurement = ObservationMeasurement(
        measurement_type="CUSTOM",
        values=(10.0, 20.0),
        component_names=("pixel_x", "pixel_y"),
        component_units=("pixel", "pixel"),
        frame=None,
        custom_type="org.example/PIXEL_CENTROID_V1",
        custom_schema_ref=CustomMeasurementSchemaRef(
            schema_id="org.example/PIXEL_CENTROID_SCHEMA",
            schema_version=SchemaVersion(major=1, minor=0),
            sha256="a" * 64,
        ),
        qualifiers={"detector": "primary"},
    )

    assert measurement.custom_schema_ref is not None
    assert measurement.custom_schema_ref.sha256 == "a" * 64


@pytest.mark.parametrize(
    ("data", "expected_type"),
    [
        (ra_dec_data(values=(0.0, -math.pi / 2.0)), MeasurementType.ANGLES_RA_DEC),
        (az_el_data(), MeasurementType.ANGLES_AZ_EL),
        (az_el_data(frame=BODY_FRAME), MeasurementType.ANGLES_AZ_EL),
        (range_data(), MeasurementType.RANGE),
        (
            range_data(qualifiers={"path_kind": "TWO_WAY"}),
            MeasurementType.RANGE,
        ),
        (range_rate_data(), MeasurementType.RANGE_RATE),
        (
            range_rate_data(
                qualifiers={
                    "path_kind": "ONE_WAY",
                    "sign_convention": "POSITIVE_CLOSING",
                    "integration_interval_s": 0.25,
                }
            ),
            MeasurementType.RANGE_RATE,
        ),
        (los_data(), MeasurementType.LOS_UNIT_VECTOR),
        (
            los_data(values=(0.0, 0.6, 0.8), frame=SENSOR_FRAME),
            MeasurementType.LOS_UNIT_VECTOR,
        ),
    ],
)
def test_standard_measurements_accept_exact_valid_contracts(
    data: dict[str, object],
    expected_type: MeasurementType,
) -> None:
    measurement = ObservationMeasurement.model_validate(data)

    assert measurement.measurement_type is expected_type


@pytest.mark.parametrize(
    "data",
    [
        ra_dec_data(values=(1, 0.2)),
        ra_dec_data(values=(True, 0.2)),
        ra_dec_data(values=(math.nan, 0.2)),
        ra_dec_data(values=(math.inf, 0.2)),
        ra_dec_data(values=(1.0,)),
        ra_dec_data(component_names=("ra", "dec")),
        ra_dec_data(frame=SENSOR_FRAME),
        ra_dec_data(qualifiers={"unexpected": "value"}),
        az_el_data(values=(2.0 * math.pi, 0.0)),
        az_el_data(values=(0.0, math.pi)),
        az_el_data(component_names=("azimuth", "altitude")),
        az_el_data(frame=J2000_FRAME),
        az_el_data(qualifiers={"angle_convention_id": "not-namespaced"}),
        range_data(component_names=("distance",)),
        range_data(component_units=("km",)),
        range_data(frame=J2000_FRAME),
        range_data(qualifiers={"path_kind": "ONE_WAY", "extra": True}),
        range_rate_data(values=(0,)),
        range_rate_data(component_units=("km/s",)),
        range_rate_data(
            qualifiers={
                "path_kind": "ONE_WAY",
                "sign_convention": "POSITIVE_RECEDING",
                "integration_interval_s": 0.0,
            }
        ),
        range_rate_data(
            qualifiers={
                "path_kind": "ONE_WAY",
                "sign_convention": "POSITIVE_RECEDING",
                "integration_interval_s": 1,
            }
        ),
        los_data(values=(1.0, 0.0)),
        los_data(frame=BODY_FRAME),
        los_data(qualifiers={"axis": "boresight"}),
        ra_dec_data(custom_type="org.example/RA_DEC"),
        range_data(custom_schema_ref=custom_data()["custom_schema_ref"]),
        ra_dec_data(unknown_field=True),
    ],
)
def test_standard_measurements_reject_shape_frame_qualifier_and_custom_field_errors(
    data: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ObservationMeasurement.model_validate(data)


@pytest.mark.parametrize(
    "integration_interval_s",
    [FloatSubclass(1.0), np.float64(1.0)],
)
def test_range_rate_rejects_non_builtin_integration_interval_float(
    integration_interval_s: object,
) -> None:
    with pytest.raises(ValidationError, match="integration_interval_s"):
        ObservationMeasurement.model_validate(
            range_rate_data(
                qualifiers={
                    "path_kind": "TWO_WAY",
                    "sign_convention": "POSITIVE_RECEDING",
                    "integration_interval_s": integration_interval_s,
                }
            )
        )


def test_custom_qualifiers_preserve_general_json_float_semantics() -> None:
    measurement = ObservationMeasurement.model_validate(
        custom_data(
            qualifiers={
                "float_subclass": FloatSubclass(1.0),
                "numpy_float": np.float64(2.0),
            }
        )
    )

    assert measurement.qualifiers == {
        "float_subclass": 1.0,
        "numpy_float": 2.0,
    }
    assert type(measurement.qualifiers["float_subclass"]) is float
    assert type(measurement.qualifiers["numpy_float"]) is float


@pytest.mark.parametrize(
    "data",
    [
        custom_data(custom_type=None),
        custom_data(custom_type="PIXEL_CENTROID"),
        custom_data(custom_type=" org.example/PIXEL_CENTROID_V1"),
        custom_data(custom_schema_ref=None),
        custom_data(
            custom_schema_ref={
                "schema_id": "PIXEL_SCHEMA",
                "schema_version": SCHEMA_VERSION,
                "sha256": "a" * 64,
            }
        ),
        custom_data(
            custom_schema_ref={
                "schema_id": "org.example/PIXEL_SCHEMA",
                "schema_version": SCHEMA_VERSION,
                "sha256": "A" * 64,
            }
        ),
        custom_data(values=(10.0, math.nan)),
        custom_data(values=(10.0, False)),
        custom_data(unknown_field=True),
    ],
)
def test_custom_measurements_reject_invalid_identity_schema_numeric_and_extra_fields(
    data: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ObservationMeasurement.model_validate(data)


def test_qualifiers_are_deeply_frozen_snapshots_and_serialize_as_json() -> None:
    source = {"detector": {"channels": ["primary", "backup"]}}
    measurement = ObservationMeasurement.model_validate(custom_data(qualifiers=source))

    source["detector"]["channels"].append("mutated")
    assert isinstance(measurement.qualifiers, MappingProxyType)
    detector = measurement.qualifiers["detector"]
    assert isinstance(detector, Mapping)
    assert detector["channels"] == ("primary", "backup")
    with pytest.raises(TypeError):
        measurement.qualifiers["other"] = "value"
    assert measurement.model_dump(mode="json")["qualifiers"] == {
        "detector": {"channels": ["primary", "backup"]}
    }


def test_measurement_revalidates_constructed_nested_frame_and_schema_ref() -> None:
    malformed_frame = FrameRef.model_construct(kind=FrameKind.SENSOR)
    malformed_schema = CustomMeasurementSchemaRef.model_construct(
        schema_id="org.example/PIXEL_SCHEMA",
        schema_version=SchemaVersion.model_construct(major=-1, minor=0),
        sha256="not-a-hash",
    )

    with pytest.raises(ValidationError):
        ObservationMeasurement.model_validate(az_el_data(frame=malformed_frame))
    with pytest.raises(ValidationError):
        ObservationMeasurement.model_validate(custom_data(custom_schema_ref=malformed_schema))


def test_measurement_round_trips_as_exact_json_contract() -> None:
    measurement = ObservationMeasurement.model_validate(
        custom_data(qualifiers={"detector": {"channels": ["primary"]}})
    )

    assert ObservationMeasurement.model_validate_json(measurement.model_dump_json()) == measurement


# =============================👐Seperate👐=============================
# Final immutable observation-event tests
# =============================👐Seperate👐=============================
def test_observation_event_is_a_final_geometry_fact_with_internal_and_public_identity() -> None:
    event = make_event(
        geometry_status="OCCLUDED",
        public_subject_ref={"kind": "UNASSOCIATED"},
    )

    assert event.truth_target_entity_id == "truth-target-1"
    assert event.public_subject_ref.kind == "UNASSOCIATED"
    with pytest.raises(ValidationError):
        event.geometry_status = GeometryStatus.VISIBLE


def test_event_schema_has_no_pending_geometry_state() -> None:
    schema = ObservationEvent.model_json_schema()
    geometry_schema = schema["$defs"]["GeometryStatus"]

    assert "PENDING" not in geometry_schema["enum"]


@pytest.mark.parametrize(
    "updates",
    [
        {"event_id": "   "},
        {"schedule_id": ""},
        {"sensor_id": " "},
        {"platform_id": " "},
        {"truth_target_entity_id": " "},
        {"unknown_field": True},
    ],
)
def test_observation_event_rejects_blank_ids_and_unknown_fields(
    updates: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        make_event(**updates)


def test_observation_event_revalidates_constructed_subject_and_model_refs() -> None:
    malformed_subject = KnownObjectSubjectRef.model_construct(
        kind="KNOWN_OBJECT",
        object_id="",
    )
    malformed_model = ModelRef.model_construct(
        model_id="",
        interface_version=SchemaVersion.model_construct(major=-1, minor=0),
        configuration={},
    )

    with pytest.raises(ValidationError):
        make_event(public_subject_ref=malformed_subject)
    with pytest.raises(ValidationError):
        make_event(measurement_model_ref=malformed_model)


def test_observation_event_snapshots_nested_models_and_round_trips() -> None:
    event = make_event()

    assert ObservationEvent.model_validate_json(event.model_dump_json()) == event


# =============================👐Seperate👐=============================
# Effective residual covariance tests
# =============================👐Seperate👐=============================
def test_uncertainty_factory_normalizes_standard_deviations_to_covariance() -> None:
    measurement = valid_ra_dec_measurement()
    uncertainty = MeasurementUncertainty.from_standard_deviations(
        measurement,
        (2.0e-5, 3.0e-5),
    )

    assert uncertainty.component_names == measurement.component_names
    assert uncertainty.component_units == measurement.component_units
    assert uncertainty.covariance == (
        (4.0e-10, 0.0),
        (0.0, 9.0e-10),
    )


@pytest.mark.parametrize(
    "covariance",
    [
        (),
        ((1.0,),),
        ((1.0, 0.0), (0.0,)),
        ((1, 0.0), (0.0, 1.0)),
        ((1.0, math.nan), (math.nan, 1.0)),
        ((1.0, 0.1), (0.2, 1.0)),
        ((1.0, 2.0), (2.0, 1.0)),
        ((-1.0, 0.0), (0.0, 1.0)),
    ],
)
def test_uncertainty_rejects_invalid_covariance(covariance: object) -> None:
    with pytest.raises(ValidationError):
        MeasurementUncertainty(
            semantics="EFFECTIVE_RESIDUAL_ERROR_COVARIANCE_V1",
            component_names=("right_ascension", "declination"),
            component_units=("rad", "rad"),
            covariance=covariance,
        )


@pytest.mark.parametrize(
    "standard_deviations",
    [
        (-1.0, 1.0),
        (1, 1.0),
        (True, 1.0),
        (math.nan, 1.0),
        (math.inf, 1.0),
        (1.0,),
    ],
)
def test_uncertainty_factory_requires_strict_nonnegative_standard_deviations(
    standard_deviations: object,
) -> None:
    with pytest.raises(ValidationError):
        MeasurementUncertainty.from_standard_deviations(
            valid_ra_dec_measurement(),
            standard_deviations,
        )


def test_uncertainty_factory_accepts_zero_standard_deviation() -> None:
    uncertainty = MeasurementUncertainty.from_standard_deviations(
        valid_ra_dec_measurement(),
        (0.0, 0.0),
    )

    assert uncertainty.covariance == ((0.0, 0.0), (0.0, 0.0))


def test_uncertainty_covariance_is_an_alias_independent_immutable_snapshot() -> None:
    source = [[1.0, 0.0], [0.0, 4.0]]
    uncertainty = MeasurementUncertainty(
        semantics="EFFECTIVE_RESIDUAL_ERROR_COVARIANCE_V1",
        component_names=("right_ascension", "declination"),
        component_units=("rad", "rad"),
        covariance=source,
    )

    source[0][0] = 99.0
    source.append([0.0, 0.0])

    assert uncertainty.covariance == ((1.0, 0.0), (0.0, 4.0))
    with pytest.raises(ValidationError):
        uncertainty.covariance = ((9.0, 0.0), (0.0, 9.0))


def test_uncertainty_covariance_array_is_an_independent_float64_copy() -> None:
    uncertainty = valid_ra_dec_uncertainty()

    first = uncertainty.covariance_array()
    first[0, 0] = 99.0
    second = uncertainty.covariance_array()

    assert first.dtype == np.float64
    assert second.dtype == np.float64
    assert second[0, 0] == pytest.approx(4.0e-10)


@pytest.mark.parametrize(
    ("off_diagonal_delta", "is_valid"),
    [
        (0.999e-12, True),
        (1.001e-12, False),
    ],
)
def test_uncertainty_symmetry_uses_the_approved_tolerance_boundary(
    off_diagonal_delta: float,
    is_valid: bool,
) -> None:
    data = {
        "semantics": "EFFECTIVE_RESIDUAL_ERROR_COVARIANCE_V1",
        "component_names": ("right_ascension", "declination"),
        "component_units": ("rad", "rad"),
        "covariance": (
            (1.0, off_diagonal_delta),
            (0.0, 1.0),
        ),
    }

    if is_valid:
        MeasurementUncertainty.model_validate(data)
    else:
        with pytest.raises(ValidationError, match="symmetric"):
            MeasurementUncertainty.model_validate(data)


@pytest.mark.parametrize(
    ("off_diagonal", "is_valid"),
    [
        (1.0 + 0.5e-12, True),
        (1.0 + 2.0e-12, False),
    ],
)
def test_uncertainty_psd_uses_the_approved_eigenvalue_tolerance_boundary(
    off_diagonal: float,
    is_valid: bool,
) -> None:
    data = {
        "semantics": "EFFECTIVE_RESIDUAL_ERROR_COVARIANCE_V1",
        "component_names": ("right_ascension", "declination"),
        "component_units": ("rad", "rad"),
        "covariance": (
            (1.0, off_diagonal),
            (off_diagonal, 1.0),
        ),
    }

    if is_valid:
        MeasurementUncertainty.model_validate(data)
    else:
        with pytest.raises(ValidationError, match="positive semidefinite"):
            MeasurementUncertainty.model_validate(data)


def test_uncertainty_rejects_extreme_finite_non_psd_covariance_without_warning() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        with pytest.raises(ValidationError, match="positive semidefinite"):
            MeasurementUncertainty(
                semantics="EFFECTIVE_RESIDUAL_ERROR_COVARIANCE_V1",
                component_names=("right_ascension", "declination"),
                component_units=("rad", "rad"),
                covariance=((1.0e308, 1.0e308), (1.0e308, 0.0)),
            )


def test_uncertainty_accepts_extreme_finite_psd_covariance_without_warning() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        uncertainty = MeasurementUncertainty(
            semantics="EFFECTIVE_RESIDUAL_ERROR_COVARIANCE_V1",
            component_names=("right_ascension", "declination"),
            component_units=("rad", "rad"),
            covariance=((1.0e308, 0.0), (0.0, 1.0e308)),
        )

    assert uncertainty.covariance == ((1.0e308, 0.0), (0.0, 1.0e308))


def test_uncertainty_accepts_subnormal_psd_with_strict_numpy_errstate() -> None:
    covariance = ((1.0e308, 0.0), (0.0, 5.0e-324))

    with np.errstate(all="raise"):
        uncertainty = MeasurementUncertainty(
            semantics="EFFECTIVE_RESIDUAL_ERROR_COVARIANCE_V1",
            component_names=("right_ascension", "declination"),
            component_units=("rad", "rad"),
            covariance=covariance,
        )

    assert uncertainty.covariance == covariance


def test_uncertainty_factory_revalidates_a_copied_invalid_measurement() -> None:
    malformed = valid_ra_dec_measurement().model_copy(update={"component_units": ("deg", "deg")})

    with pytest.raises(ValidationError):
        MeasurementUncertainty.from_standard_deviations(
            malformed,
            (1.0, 1.0),
        )


# =============================👐Seperate👐=============================
# Algorithm-visible Ideal/Reported channel tests
# =============================👐Seperate👐=============================
def test_ideal_and_reported_are_separate_discriminated_models() -> None:
    ideal = make_ideal()
    reported = make_reported()
    adapter = TypeAdapter(Observation)

    assert ideal.channel is ObservationChannel.IDEAL
    assert reported.channel is ObservationChannel.REPORTED
    assert ideal.event_id == reported.event_id
    assert ideal.observation_id != reported.observation_id
    assert adapter.validate_python(ideal.model_dump(mode="json")) == ideal
    assert adapter.validate_python(reported.model_dump(mode="json")) == reported


def test_observation_union_schema_uses_the_channel_discriminator() -> None:
    schema = TypeAdapter(Observation).json_schema()

    assert schema["discriminator"]["propertyName"] == "channel"
    assert set(schema["discriminator"]["mapping"]) == {"IDEAL", "REPORTED"}


def test_algorithm_visible_observation_schemas_exclude_truth_and_realized_errors() -> None:
    forbidden = {
        "truth_target_entity_id",
        "truth_state",
        "actual_error",
        "noise_sample",
        "true_bias",
        "truth_residual",
    }

    assert forbidden.isdisjoint(IdealObservation.model_fields)
    assert forbidden.isdisjoint(ReportedObservation.model_fields)


def test_ideal_and_reported_forbid_truth_and_realized_noise_extras() -> None:
    with pytest.raises(ValidationError, match="truth_target_entity_id"):
        make_ideal(truth_target_entity_id="truth-target-1")
    with pytest.raises(ValidationError, match="noise_sample"):
        make_reported(noise_sample=(1.0, 2.0))


def test_reported_uncertainty_must_match_measurement_components() -> None:
    with pytest.raises(ValidationError, match="uncertainty"):
        make_reported(
            uncertainty=MeasurementUncertainty(
                semantics="EFFECTIVE_RESIDUAL_ERROR_COVARIANCE_V1",
                component_names=("range",),
                component_units=("m",),
                covariance=((1.0,),),
            )
        )


def test_explicit_zero_uncertainty_differs_from_unknown_uncertainty() -> None:
    zero = MeasurementUncertainty.from_standard_deviations(
        valid_ra_dec_measurement(),
        (0.0, 0.0),
    )

    with_zero = make_reported(uncertainty=zero)
    unknown = make_reported(uncertainty=None)

    assert with_zero.uncertainty is not None
    assert with_zero.uncertainty.covariance == ((0.0, 0.0), (0.0, 0.0))
    assert unknown.uncertainty is None
    assert with_zero != unknown


def test_observations_revalidate_copied_invalid_nested_models() -> None:
    malformed_subject = KnownObjectSubjectRef(object_id="public-1").model_copy(
        update={"object_id": ""}
    )
    malformed_model = measurement_model_ref().model_copy(update={"model_id": ""})
    malformed_measurement = valid_ra_dec_measurement().model_copy(
        update={"component_units": ("deg", "deg")}
    )
    malformed_uncertainty = valid_ra_dec_uncertainty().model_copy(
        update={"covariance": ((-1.0, 0.0), (0.0, 1.0))}
    )

    with pytest.raises(ValidationError):
        make_ideal(subject_ref=malformed_subject)
    with pytest.raises(ValidationError):
        make_ideal(measurement_model_ref=malformed_model)
    with pytest.raises(ValidationError):
        make_reported(error_model_ref=malformed_model)
    with pytest.raises(ValidationError):
        make_reported(measurement=malformed_measurement)
    with pytest.raises(ValidationError):
        make_reported(uncertainty=malformed_uncertainty)


def test_observations_are_frozen_and_round_trip_as_json() -> None:
    ideal = make_ideal()
    reported = make_reported()

    with pytest.raises(ValidationError):
        ideal.event_id = "event-2"
    with pytest.raises(ValidationError):
        reported.event_id = "event-2"
    assert IdealObservation.model_validate_json(ideal.model_dump_json()) == ideal
    assert ReportedObservation.model_validate_json(reported.model_dump_json()) == reported
