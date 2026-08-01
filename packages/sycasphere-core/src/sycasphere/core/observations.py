# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : observations.py
创建者    : Sycamore
创建日期  : 2026-07-28
最后修改  : 2026-08-01
版本号    : v1.3.1

■ 用途说明:
  定义算法安全的观测主体身份、事件、测量、有效残余协方差和 Ideal/Reported 载荷契约。

■ 主要函数功能:
  - ObservationMeasurement: 验证标准及自定义测量的数值、单位、帧和 qualifier 语义
  - ObservationEvent: 保存单次观测计划触发后的不可变内部科学事实
  - MeasurementUncertainty: 验证测量分量对应的有效残余误差协方差
  - IdealObservation/ReportedObservation: 分离算法可见的理想与报告观测通道

■ 功能特性:
  ✓ 分离内部真值目标身份与算法可见主体身份
  ✓ 重验公开主体实例并严格验证标准测量的原始 qualifier
  ✓ 数值稳定地验证协方差并隔离 Ideal/Reported 通道中的真值和实际误差
  ✓ 拒绝无法表示为有限浮点数的标准差派生方差
  ✓ 隔离标准差平方的十进制上下文并保留非有限值的严格验证语义

■ 待办事项:
  - [ ] 无

■ 更新日志:
  v1.3.1 (2026-08-01): 隔离标准差平方上下文并保留非有限标准差的严格验证错误。
  v1.3.0 (2026-08-01): 拒绝无法表示为有限浮点数的标准差派生方差。
  v1.2.1 (2026-07-29): 隔离协方差归一化的预期 underflow 数值状态
  v1.2.0 (2026-07-29): 加固主体重验、RANGE_RATE qualifier 和极值协方差校验
  v1.1.0 (2026-07-28): 增加有效残余协方差和独立 Ideal/Reported 观测模型
  v1.0.0 (2026-07-28): 创建观测身份、事件和测量载荷契约

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from decimal import Context, Decimal, DecimalException
from enum import StrEnum
from typing import Annotated, Any, Literal, cast

import numpy as np
from numpy.typing import NDArray
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    TypeAdapter,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)
from sycasphere.core._definitions import DefinitionString
from sycasphere.core._json import (
    FrozenJsonValue,
    freeze_json_object,
    normalize_json_object,
    thaw_json_value,
)
from sycasphere.core._validation import (
    Sha256Hex,
    StrictFiniteFloat,
    require_builtin_float_sequence,
    snapshot_model_input,
)
from sycasphere.core.epoch import Epoch
from sycasphere.core.frames import FrameKind, FrameRef
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.schema import SchemaVersion

# =============================👐Seperate👐=============================
# Stable identity and measurement enumerations
# =============================👐Seperate👐=============================
_NAMESPACED_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]*(?:\.[A-Za-z0-9_.-]+)+/[A-Za-z0-9_.-]+$"
_NAMESPACED_ID_REGEX = re.compile(_NAMESPACED_ID_PATTERN)

type NamespacedId = Annotated[
    str,
    StringConstraints(strict=True, pattern=_NAMESPACED_ID_PATTERN),
]
type MeasurementValues = tuple[StrictFiniteFloat, ...]
type CovarianceMatrix = tuple[tuple[StrictFiniteFloat, ...], ...]


_UNREPRESENTABLE_VARIANCE_MESSAGE = (
    "standard-deviation variance must be representable as a finite float"
)


def _square_standard_deviation(value: float) -> float:
    """Square one normalized decimal float and require faithful float representation."""
    try:
        operation_context = Context(prec=40, Emin=-999_999, Emax=999_999)
        decimal_value = Decimal(str(value))
        variance = float(operation_context.multiply(decimal_value, decimal_value))
    except (DecimalException, OverflowError, ValueError):
        raise ValueError(_UNREPRESENTABLE_VARIANCE_MESSAGE) from None
    if not math.isfinite(variance) or (value != 0.0 and variance == 0.0):
        raise ValueError(_UNREPRESENTABLE_VARIANCE_MESSAGE)
    return variance


def _require_standard_deviation_sequence(value: Any) -> Any:
    """Require nonnegative finite floats whose derived variances are representable."""
    values = require_builtin_float_sequence(value, "standard_deviations")
    if any(component < 0.0 for component in values):
        raise ValueError("standard_deviations must be nonnegative")
    for component in values:
        if math.isfinite(component):
            _square_standard_deviation(component)
    return values


type StandardDeviations = Annotated[
    tuple[StrictFiniteFloat, ...],
    BeforeValidator(_require_standard_deviation_sequence),
]


class MeasurementType(StrEnum):
    """Stable measurement payload types supported by the Core boundary."""

    ANGLES_RA_DEC = "ANGLES_RA_DEC"
    ANGLES_AZ_EL = "ANGLES_AZ_EL"
    RANGE = "RANGE"
    RANGE_RATE = "RANGE_RATE"
    LOS_UNIT_VECTOR = "LOS_UNIT_VECTOR"
    CUSTOM = "CUSTOM"


class GeometryStatus(StrEnum):
    """Final geometry outcomes for an allocated observation event."""

    VISIBLE = "VISIBLE"
    OCCLUDED = "OCCLUDED"
    OUT_OF_FIELD_OF_VIEW = "OUT_OF_FIELD_OF_VIEW"
    INSUFFICIENT_ILLUMINATION = "INSUFFICIENT_ILLUMINATION"
    POINTING_UNAVAILABLE = "POINTING_UNAVAILABLE"


class ObservationChannel(StrEnum):
    """Algorithm-visible observation channels."""

    IDEAL = "IDEAL"
    REPORTED = "REPORTED"


# =============================👐Seperate👐=============================
# Algorithm-safe public subject identity
# =============================👐Seperate👐=============================
class KnownObjectSubjectRef(BaseModel):
    """Reference an explicitly authorized public object identity."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    kind: Literal["KNOWN_OBJECT"] = "KNOWN_OBJECT"
    object_id: DefinitionString


class TrackletSubjectRef(BaseModel):
    """Reference a public tracklet without asserting its truth identity."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    kind: Literal["TRACKLET"] = "TRACKLET"
    tracklet_id: DefinitionString


class UnassociatedSubjectRef(BaseModel):
    """Represent a detection without inventing a public target identity."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    kind: Literal["UNASSOCIATED"] = "UNASSOCIATED"


type ObservationSubjectRef = Annotated[
    KnownObjectSubjectRef | TrackletSubjectRef | UnassociatedSubjectRef,
    Field(discriminator="kind"),
]


# =============================👐Seperate👐=============================
# Self-describing measurement payloads
# =============================👐Seperate👐=============================
class CustomMeasurementSchemaRef(BaseModel):
    """A location-independent exact schema identity for one custom measurement type."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    schema_id: NamespacedId
    schema_version: SchemaVersion
    sha256: Sha256Hex

    @field_validator("schema_version", mode="before")
    @classmethod
    def _snapshot_schema_version(cls, value: Any) -> Any:
        """Revalidate and detach an input schema-version model."""
        return snapshot_model_input(value)


class ObservationMeasurement(BaseModel):
    """An immutable, strict, self-describing standard or custom measurement."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    measurement_type: MeasurementType
    values: MeasurementValues
    component_names: tuple[str, ...]
    component_units: tuple[str, ...]
    frame: FrameRef | None
    custom_type: NamespacedId | None = None
    custom_schema_ref: CustomMeasurementSchemaRef | None = None
    qualifiers: Mapping[str, JsonValue]

    @field_validator("values", mode="before")
    @classmethod
    def _require_builtin_float_values(cls, value: Any) -> Any:
        """Reject integer, boolean and coercible measurement values."""
        return require_builtin_float_sequence(value, "values")

    @field_validator("frame", "custom_schema_ref", mode="before")
    @classmethod
    def _snapshot_nested_model(cls, value: Any) -> Any:
        """Snapshot nested boundary records so all their validation reruns."""
        return snapshot_model_input(value)

    @field_validator("qualifiers", mode="before")
    @classmethod
    def _normalize_qualifiers(
        cls,
        value: Any,
        info: ValidationInfo,
    ) -> dict[str, JsonValue]:
        """Normalize supported JSON inputs before Pydantic field validation."""
        if (
            info.data.get("measurement_type") is MeasurementType.RANGE_RATE
            and isinstance(value, Mapping)
            and "integration_interval_s" in value
            and type(value["integration_interval_s"]) is not float
        ):
            raise ValueError("integration_interval_s must be a built-in float")
        return normalize_json_object(value)

    @field_validator("qualifiers")
    @classmethod
    def _freeze_qualifiers(
        cls,
        value: Mapping[str, JsonValue],
    ) -> Mapping[str, FrozenJsonValue]:
        """Store an alias-independent deeply immutable qualifier snapshot."""
        return freeze_json_object(value)

    @field_serializer("qualifiers", when_used="always")
    def _serialize_qualifiers(
        self,
        value: Mapping[str, FrozenJsonValue],
    ) -> dict[str, JsonValue]:
        """Restore ordinary JSON objects and arrays at serialization boundaries."""
        return cast(dict[str, JsonValue], thaw_json_value(value))

    @model_validator(mode="after")
    def _validate_measurement_semantics(self) -> ObservationMeasurement:
        """Dispatch exact standard semantics or the custom-schema identity contract."""
        validators = {
            MeasurementType.ANGLES_RA_DEC: self._validate_ra_dec,
            MeasurementType.ANGLES_AZ_EL: self._validate_az_el,
            MeasurementType.RANGE: self._validate_range,
            MeasurementType.RANGE_RATE: self._validate_range_rate,
            MeasurementType.LOS_UNIT_VECTOR: self._validate_los,
            MeasurementType.CUSTOM: self._validate_custom,
        }
        validators[self.measurement_type]()
        return self

    def _require_standard_shape(
        self,
        *,
        component_names: tuple[str, ...],
        component_units: tuple[str, ...],
        qualifier_keys: frozenset[str],
    ) -> None:
        """Require exact standard component metadata and qualifier key sets."""
        if self.component_names != component_names:
            raise ValueError("component_names do not match the standard measurement contract")
        if self.component_units != component_units:
            raise ValueError("component_units do not match the standard measurement contract")
        if frozenset(self.qualifiers) != qualifier_keys:
            raise ValueError("qualifier keys do not match the standard measurement contract")
        if self.custom_type is not None or self.custom_schema_ref is not None:
            raise ValueError("standard measurements do not accept custom schema fields")

    def _validate_ra_dec(self) -> None:
        """Validate one atomic right-ascension/declination measurement."""
        self._require_standard_shape(
            component_names=("right_ascension", "declination"),
            component_units=("rad", "rad"),
            qualifier_keys=frozenset(),
        )
        if self.frame is None or self.frame.kind is not FrameKind.J2000:
            raise ValueError("ANGLES_RA_DEC requires a J2000 frame")
        if len(self.values) != 2:
            raise ValueError("ANGLES_RA_DEC requires two values")
        right_ascension, declination = self.values
        if not 0.0 <= right_ascension < 2.0 * math.pi:
            raise ValueError("right ascension must be in [0, 2*pi)")
        if not -math.pi / 2.0 <= declination <= math.pi / 2.0:
            raise ValueError("declination must be in [-pi/2, pi/2]")

    def _validate_az_el(self) -> None:
        """Validate azimuth/elevation values and their explicit axes convention."""
        self._require_standard_shape(
            component_names=("azimuth", "elevation"),
            component_units=("rad", "rad"),
            qualifier_keys=frozenset({"angle_convention_id"}),
        )
        if self.frame is None or self.frame.kind not in {FrameKind.SENSOR, FrameKind.BODY}:
            raise ValueError("ANGLES_AZ_EL requires a SENSOR or BODY frame")
        if len(self.values) != 2:
            raise ValueError("ANGLES_AZ_EL requires two values")
        azimuth, elevation = self.values
        if not 0.0 <= azimuth < 2.0 * math.pi:
            raise ValueError("azimuth must be in [0, 2*pi)")
        if not -math.pi / 2.0 <= elevation <= math.pi / 2.0:
            raise ValueError("elevation must be in [-pi/2, pi/2]")
        angle_convention_id = self.qualifiers["angle_convention_id"]
        if not isinstance(angle_convention_id, str) or (
            _NAMESPACED_ID_REGEX.fullmatch(angle_convention_id) is None
        ):
            raise ValueError("angle_convention_id must be a namespaced stable ID")

    def _validate_range(self) -> None:
        """Validate a non-negative one-way or two-way range scalar."""
        self._require_standard_shape(
            component_names=("range",),
            component_units=("m",),
            qualifier_keys=frozenset({"path_kind"}),
        )
        if self.frame is not None:
            raise ValueError("RANGE does not accept a frame")
        if len(self.values) != 1 or self.values[0] < 0.0:
            raise ValueError("RANGE requires one non-negative value")
        if self.qualifiers["path_kind"] not in {"ONE_WAY", "TWO_WAY"}:
            raise ValueError("RANGE path_kind must be ONE_WAY or TWO_WAY")

    def _validate_range_rate(self) -> None:
        """Validate a signed finite range-rate scalar and integration semantics."""
        self._require_standard_shape(
            component_names=("range_rate",),
            component_units=("m/s",),
            qualifier_keys=frozenset({"path_kind", "sign_convention", "integration_interval_s"}),
        )
        if self.frame is not None:
            raise ValueError("RANGE_RATE does not accept a frame")
        if len(self.values) != 1:
            raise ValueError("RANGE_RATE requires one value")
        if self.qualifiers["path_kind"] not in {"ONE_WAY", "TWO_WAY"}:
            raise ValueError("RANGE_RATE path_kind must be ONE_WAY or TWO_WAY")
        if self.qualifiers["sign_convention"] not in {
            "POSITIVE_RECEDING",
            "POSITIVE_CLOSING",
        }:
            raise ValueError("RANGE_RATE sign_convention is unsupported")
        integration_interval_s = self.qualifiers["integration_interval_s"]
        if (
            type(integration_interval_s) is not float
            or not math.isfinite(integration_interval_s)
            or integration_interval_s <= 0.0
        ):
            raise ValueError("integration_interval_s must be a finite positive float")

    def _validate_los(self) -> None:
        """Validate a J2000 or sensor-frame three-dimensional unit LOS vector."""
        self._require_standard_shape(
            component_names=("los_x", "los_y", "los_z"),
            component_units=("1", "1", "1"),
            qualifier_keys=frozenset(),
        )
        if self.frame is None or self.frame.kind not in {FrameKind.J2000, FrameKind.SENSOR}:
            raise ValueError("LOS_UNIT_VECTOR requires a J2000 or SENSOR frame")
        if len(self.values) != 3:
            raise ValueError("LOS_UNIT_VECTOR requires three values")
        norm = math.sqrt(sum(component * component for component in self.values))
        if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("LOS_UNIT_VECTOR norm must equal one within 1e-9")

    def _validate_custom(self) -> None:
        """Require exact custom type and schema identities without guessing payload shape."""
        if self.custom_type is None or self.custom_schema_ref is None:
            raise ValueError("CUSTOM measurements require custom_type and custom_schema_ref")


# =============================👐Seperate👐=============================
# Effective residual measurement covariance
# =============================👐Seperate👐=============================
class MeasurementUncertainty(BaseModel):
    """An immutable declared covariance for reported-minus-ideal residual error."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    semantics: Literal["EFFECTIVE_RESIDUAL_ERROR_COVARIANCE_V1"]
    component_names: tuple[str, ...]
    component_units: tuple[str, ...]
    covariance: CovarianceMatrix

    @field_validator("covariance", mode="before")
    @classmethod
    def _snapshot_covariance_rows(cls, value: Any) -> Any:
        """Detach mutable row inputs and require built-in floating-point entries."""
        if not isinstance(value, (list, tuple)):
            raise ValueError("covariance must be supplied as nested lists or tuples")
        rows: list[tuple[Any, ...]] = []
        for row in value:
            if not isinstance(row, (list, tuple)):
                raise ValueError("covariance rows must be supplied as lists or tuples")
            if any(type(component) is not float for component in row):
                raise ValueError("covariance entries must be built-in floats")
            rows.append(tuple(row))
        return tuple(rows)

    @model_validator(mode="after")
    def _validate_covariance_semantics(self) -> MeasurementUncertainty:
        """Require exact dimension, symmetry and positive-semidefinite semantics."""
        dimension = len(self.covariance)
        if dimension == 0:
            raise ValueError("covariance must not be empty")
        if any(len(row) != dimension for row in self.covariance):
            raise ValueError("covariance must be square")
        if len(self.component_names) != dimension or len(self.component_units) != dimension:
            raise ValueError("covariance dimension must match component_names and component_units")
        if any(self.covariance[index][index] < 0.0 for index in range(dimension)):
            raise ValueError("covariance diagonal entries must be nonnegative")

        scale = max(
            1.0,
            max(abs(value) for row in self.covariance for value in row),
        )
        tolerance = 1e-12 * scale
        normalized_tolerance = tolerance / scale
        with np.errstate(under="ignore"):
            normalized_matrix = self.covariance_array() / scale
            if not np.allclose(
                normalized_matrix,
                normalized_matrix.T,
                rtol=0.0,
                atol=normalized_tolerance,
            ):
                raise ValueError("covariance must be symmetric within the approved tolerance")
            symmetric_matrix = (normalized_matrix + normalized_matrix.T) / 2.0
            eigenvalues = np.linalg.eigvalsh(symmetric_matrix)
            if not np.all(np.isfinite(eigenvalues)):
                raise ValueError("covariance eigenvalues must be finite")
            if float(eigenvalues[0]) < -normalized_tolerance:
                raise ValueError(
                    "covariance must be positive semidefinite within the approved tolerance"
                )
        return self

    @classmethod
    def from_standard_deviations(
        cls,
        measurement: ObservationMeasurement,
        standard_deviations: Sequence[float],
    ) -> MeasurementUncertainty:
        """Normalize strict component standard deviations to diagonal covariance."""
        validated_measurement = ObservationMeasurement.model_validate(
            snapshot_model_input(measurement)
        )
        deviations: tuple[float, ...] = TypeAdapter(StandardDeviations).validate_python(
            standard_deviations
        )
        covariance = tuple(
            tuple(
                _square_standard_deviation(deviation) if row_index == column_index else 0.0
                for column_index, deviation in enumerate(deviations)
            )
            for row_index in range(len(deviations))
        )
        return cls(
            semantics="EFFECTIVE_RESIDUAL_ERROR_COVARIANCE_V1",
            component_names=validated_measurement.component_names,
            component_units=validated_measurement.component_units,
            covariance=covariance,
        )

    def covariance_array(self) -> NDArray[np.float64]:
        """Return an independent float64 covariance array for numerical work."""
        return np.asarray(self.covariance, dtype=np.float64).copy()


# =============================👐Seperate👐=============================
# Immutable observation-event fact
# =============================👐Seperate👐=============================
class ObservationEvent(BaseModel):
    """One immutable final geometry fact for a single schedule occurrence."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    event_id: DefinitionString
    schedule_id: DefinitionString
    measurement_epoch: Epoch
    sensor_id: DefinitionString
    platform_id: DefinitionString
    truth_target_entity_id: DefinitionString
    public_subject_ref: ObservationSubjectRef
    measurement_model_ref: ModelRef
    measurement_type: MeasurementType
    geometry_status: GeometryStatus

    @field_validator(
        "measurement_epoch",
        "public_subject_ref",
        "measurement_model_ref",
        mode="before",
    )
    @classmethod
    def _snapshot_nested_model(cls, value: Any) -> Any:
        """Snapshot nested records so malformed constructed instances are revalidated."""
        return snapshot_model_input(value)


# =============================👐Seperate👐=============================
# Algorithm-visible Ideal and Reported observation channels
# =============================👐Seperate👐=============================
class IdealObservation(BaseModel):
    """An immutable error-free observation visible to authorized algorithms."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    channel: Literal[ObservationChannel.IDEAL] = ObservationChannel.IDEAL
    observation_id: DefinitionString
    event_id: DefinitionString
    measurement_epoch: Epoch
    sensor_id: DefinitionString
    subject_ref: ObservationSubjectRef
    measurement_model_ref: ModelRef
    measurement: ObservationMeasurement

    @field_validator(
        "measurement_epoch",
        "subject_ref",
        "measurement_model_ref",
        "measurement",
        mode="before",
    )
    @classmethod
    def _snapshot_nested_model(cls, value: Any) -> Any:
        """Detach and revalidate every nested public boundary model."""
        return snapshot_model_input(value)


class ReportedObservation(BaseModel):
    """An immutable algorithm-safe observation after the declared error model."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )

    channel: Literal[ObservationChannel.REPORTED] = ObservationChannel.REPORTED
    observation_id: DefinitionString
    event_id: DefinitionString
    measurement_epoch: Epoch
    sensor_id: DefinitionString
    subject_ref: ObservationSubjectRef
    measurement_model_ref: ModelRef
    error_model_ref: ModelRef
    measurement: ObservationMeasurement
    uncertainty: MeasurementUncertainty | None = None

    @field_validator(
        "measurement_epoch",
        "subject_ref",
        "measurement_model_ref",
        "error_model_ref",
        "measurement",
        "uncertainty",
        mode="before",
    )
    @classmethod
    def _snapshot_nested_model(cls, value: Any) -> Any:
        """Detach and revalidate every nested public boundary model."""
        return snapshot_model_input(value)

    @model_validator(mode="after")
    def _validate_uncertainty_components(self) -> ReportedObservation:
        """Keep declared covariance component order and units aligned to measurement."""
        if self.uncertainty is not None and (
            self.uncertainty.component_names != self.measurement.component_names
            or self.uncertainty.component_units != self.measurement.component_units
        ):
            raise ValueError(
                "uncertainty component_names and component_units must match measurement"
            )
        return self


type Observation = Annotated[
    IdealObservation | ReportedObservation,
    Field(discriminator="channel"),
]
