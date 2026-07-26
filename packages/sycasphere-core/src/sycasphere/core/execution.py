# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : execution.py
创建者    : Sycamore
创建日期  : 2026-07-26
最后修改  : 2026-07-26
版本号    : v1.1.0

■ 用途说明:
  定义独立仿真引擎可直接验证、准备和执行的自包含不可变科学输入边界。

■ 主要函数功能:
  - ScienceBackendBinding: 绑定精确科学后端版本及有限 JSON 配置
  - SimulationRunRequest: 校验物理世界、调度、命令、采样和输出的闭合一致性
  - SimulationExecutionManifest.create: 冻结解析结果并计算确定性内容哈希

■ 功能特性:
  ✓ 嵌入完整 SimulationDefinition 并解析所有运行期科学引用
  ✓ 严格验证无符号随机种子、机动能力、时间范围和输出采样
  ✓ 生成排序稳定、可重验且不含运行生命周期状态的科学执行清单

■ 待办事项:
  - 无

■ 更新日志:
  v1.1.0 (2026-07-26): 增加不可变仿真执行清单、解析记录和完整性校验
  v1.0.0 (2026-07-26): 创建自包含仿真运行请求契约

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    Strict,
    StringConstraints,
    field_serializer,
    field_validator,
    model_validator,
)
from sycasphere.core._canonical import (
    CANONICALIZATION_VERSION,
    RANDOM_DERIVATION_VERSION,
    sha256_canonical_json,
)
from sycasphere.core._definitions import DefinitionString
from sycasphere.core._json import (
    FrozenJsonValue,
    freeze_json_object,
    normalize_json_object,
    thaw_json_value,
)
from sycasphere.core.entities import (
    GroundStationDefinition,
    OtherSpaceObjectDefinition,
    SpacecraftDefinition,
)
from sycasphere.core.epoch import Epoch, _is_strictly_before_same_scale
from sycasphere.core.maneuvers import (
    ManeuverCommand,
    ManeuverSpec,
    _validate_maneuver_binding,
)
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.plugins import PluginKind, PluginRef
from sycasphere.core.schedules import (
    ExplicitObservationSchedule,
    ObservationSchedule,
    OutputProduct,
    OutputSampling,
    PeriodicObservationSchedule,
    SimulationTimeRange,
)
from sycasphere.core.schema import SchemaVersion
from sycasphere.core.sensors import SensorDefinition
from sycasphere.core.simulations import ExternalDataRef, SimulationDefinition

type UInt64 = Annotated[
    int,
    Strict(),
    Field(ge=0, le=2**64 - 1),
]
type Sha256Hex = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$"),
]
type StrictNonNegativeInt = Annotated[
    int,
    Strict(),
    Field(ge=0),
]


def _snapshot_model_input(value: Any) -> Any:
    """Convert a Pydantic instance to ordinary Python data for boundary revalidation."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    return value


def _snapshot_model_collection(value: Any) -> Any:
    """Snapshot every Pydantic item in a supported collection input."""
    if isinstance(value, (frozenset, list, set, tuple)):
        return tuple(_snapshot_model_input(item) for item in value)
    return value


# =============================👐Seperate👐=============================
# Science backend and output requirements
# =============================👐Seperate👐=============================
class ScienceBackendBinding(BaseModel):
    """An exact science-backend implementation binding with immutable configuration."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_default=True,
        revalidate_instances="always",
    )

    ref: PluginRef
    configuration: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("configuration", mode="before")
    @classmethod
    def normalize_configuration(cls, value: Any) -> dict[str, JsonValue]:
        """Normalize supported JSON mappings and reject non-finite values."""
        return normalize_json_object(value)

    @field_validator("configuration")
    @classmethod
    def freeze_configuration(cls, value: Mapping[str, JsonValue]) -> Mapping[str, FrozenJsonValue]:
        """Store an alias-independent deeply immutable configuration snapshot."""
        return freeze_json_object(value)

    @field_serializer("configuration", when_used="always")
    def serialize_configuration(self, value: Mapping[str, FrozenJsonValue]) -> dict[str, JsonValue]:
        """Serialize the immutable configuration as ordinary JSON values."""
        return {key: thaw_json_value(nested) for key, nested in value.items()}


class OutputRequirement(StrEnum):
    """Scientific and diagnostic products requested from one simulation run."""

    TRUTH = "TRUTH"
    ATTITUDE = "ATTITUDE"
    GEOMETRY = "GEOMETRY"
    IDEAL_OBSERVATIONS = "IDEAL_OBSERVATIONS"
    REPORTED_OBSERVATIONS = "REPORTED_OBSERVATIONS"
    DELIVERY_SUMMARY = "DELIVERY_SUMMARY"
    COMMAND_TRACE = "COMMAND_TRACE"
    DIAGNOSTICS = "DIAGNOSTICS"


_SAMPLING_REQUIREMENTS = {
    OutputProduct.TRUTH_STATE: OutputRequirement.TRUTH,
    OutputProduct.ATTITUDE_STATE: OutputRequirement.ATTITUDE,
    OutputProduct.DERIVED_GEOMETRY: OutputRequirement.GEOMETRY,
}


def _schedule_epochs(schedule: ObservationSchedule) -> tuple[Epoch, ...]:
    """Return every boundary or explicit epoch constrained by the request interval."""
    if isinstance(schedule, PeriodicObservationSchedule):
        return (schedule.start_epoch, schedule.end_epoch)
    if isinstance(schedule, ExplicitObservationSchedule):
        return schedule.epochs
    raise AssertionError("unsupported observation schedule")


def _require_epoch_in_closed_interval(
    epoch: Epoch,
    time_range: SimulationTimeRange,
) -> None:
    """Reject an epoch outside either comparable bound of a closed interval."""
    if _is_strictly_before_same_scale(epoch, time_range.start) is True:
        raise ValueError("observation schedule epoch must remain inside request interval")
    if _is_strictly_before_same_scale(time_range.end, epoch) is True:
        raise ValueError("observation schedule epoch must remain inside request interval")


# =============================👐Seperate👐=============================
# Self-contained simulation run input
# =============================👐Seperate👐=============================
class SimulationRunRequest(BaseModel):
    """A complete immutable input that an independent simulation engine can prepare."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: SchemaVersion
    simulation_definition: SimulationDefinition
    time_range: SimulationTimeRange
    output_sampling: OutputSampling
    observation_schedules: tuple[ObservationSchedule, ...] = ()
    command_timeline: tuple[ManeuverCommand, ...] = ()
    backend: ScienceBackendBinding
    link_models: tuple[ModelRef, ...] = ()
    random_seed: UInt64
    output_requirements: frozenset[OutputRequirement]

    @field_validator("random_seed", mode="before")
    @classmethod
    def validate_random_seed_type(cls, value: Any) -> int:
        """Require a built-in integer before applying the unsigned 64-bit bounds."""
        if type(value) is not int:
            raise ValueError("random_seed must be a built-in unsigned 64-bit integer")
        return value

    @field_validator("output_requirements", mode="before")
    @classmethod
    def normalize_output_requirements(cls, value: Any) -> tuple[OutputRequirement, ...]:
        """Reject empty or duplicate requirements before freezing them as a set."""
        if not isinstance(value, (frozenset, list, set, tuple)):
            raise ValueError("output_requirements must be a collection")

        try:
            normalized = tuple(OutputRequirement(item) for item in value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "output_requirements must contain valid output requirement values"
            ) from error
        if not normalized:
            raise ValueError("output_requirements must not be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("output_requirements must not contain duplicates")
        return normalized

    @field_serializer("output_requirements", when_used="always")
    def serialize_output_requirements(
        self,
        value: frozenset[OutputRequirement],
    ) -> list[str]:
        """Serialize requirements in deterministic enum-value order."""
        return [item.value for item in sorted(value, key=lambda item: item.value)]

    @model_validator(mode="after")
    def validate_request_consistency(self) -> Self:
        """Resolve all request-local identities once and enforce cross-boundary invariants."""
        ## -------------- step: build request-local lookup dictionaries ---------
        entities_by_id = {entity.id: entity for entity in self.simulation_definition.entities}
        sensors_by_id: dict[str, SensorDefinition] = {
            sensor.id: sensor
            for entity in self.simulation_definition.entities
            if isinstance(entity, (SpacecraftDefinition, GroundStationDefinition))
            for sensor in entity.sensors
        }
        link_models_by_id = {model.model_id: model for model in self.link_models}

        if len(link_models_by_id) != len(self.link_models):
            raise ValueError("link_models must contain unique model_id values")

        ## -------------- step: validate comparable request and schedule epochs ---------
        synchronization_epoch = self.simulation_definition.synchronization_epoch
        if _is_strictly_before_same_scale(self.time_range.start, synchronization_epoch) is True:
            raise ValueError("synchronization_epoch must not be after time_range start")

        schedule_ids = tuple(schedule.schedule_id for schedule in self.observation_schedules)
        if len(schedule_ids) != len(set(schedule_ids)):
            raise ValueError("observation_schedules must contain unique schedule_id values")

        for schedule in self.observation_schedules:
            for epoch in _schedule_epochs(schedule):
                _require_epoch_in_closed_interval(epoch, self.time_range)

            ## -------------- step: resolve schedule endpoints and models ---------
            sensor = sensors_by_id.get(schedule.sensor_id)
            if sensor is None:
                raise ValueError("observation schedule sensor_id must reference an existing sensor")

            target = entities_by_id.get(schedule.target_id)
            if target is None:
                raise ValueError("observation schedule target_id must reference an existing target")
            if not isinstance(
                target,
                (SpacecraftDefinition, OtherSpaceObjectDefinition),
            ):
                raise ValueError("observation schedule target must be a space object")

            measurement_ids = {model.model_id for model in sensor.measurement_models}
            if schedule.measurement_model_id not in measurement_ids:
                raise ValueError("measurement_model_id must belong to the selected sensor")

            error_profile_ids = {model.model_id for model in sensor.error_profiles}
            if (
                schedule.error_profile_id is not None
                and schedule.error_profile_id not in error_profile_ids
            ):
                raise ValueError("error_profile_id must belong to the selected sensor")

            if (
                schedule.link_model_id is not None
                and schedule.link_model_id not in link_models_by_id
            ):
                raise ValueError("link_model_id must reference a request link model")

        ## -------------- step: validate reported-observation error consistency ---------
        if OutputRequirement.REPORTED_OBSERVATIONS in self.output_requirements:
            for schedule in self.observation_schedules:
                if schedule.error_profile_id is None:
                    raise ValueError(
                        "REPORTED_OBSERVATIONS requires error_profile_id on every schedule"
                    )

        ## -------------- step: validate command identities and capabilities ---------
        command_ids = tuple(command.command_id for command in self.command_timeline)
        if len(command_ids) != len(set(command_ids)):
            raise ValueError("command_timeline must contain unique command_id values")
        planned_ids = {
            maneuver.maneuver_id for maneuver in self.simulation_definition.planned_maneuvers
        }
        if planned_ids.intersection(command_ids):
            raise ValueError("command_id values must not collide with planned maneuver IDs")

        for command in self.command_timeline:
            spacecraft = entities_by_id.get(command.spacecraft_id)
            if not isinstance(spacecraft, SpacecraftDefinition):
                raise ValueError("command spacecraft_id must reference an existing spacecraft")
            _validate_maneuver_binding(
                command.maneuver,
                command.spacecraft_id,
                command.epoch,
                spacecraft.maneuver_capability,
            )

        ## -------------- step: validate sampled-output equivalence ---------
        sampled_products = {rule.product for rule in self.output_sampling.rules}
        for product, requirement in _SAMPLING_REQUIREMENTS.items():
            has_sampling = product in sampled_products
            has_output = requirement in self.output_requirements
            if has_output and not has_sampling:
                raise ValueError(
                    f"{requirement.value} output requires {product.value} sampling rule"
                )
            if has_sampling and not has_output:
                raise ValueError(
                    f"{product.value} sampling rule requires {requirement.value} output"
                )

        return self


# =============================👐Seperate👐=============================
# Prepared timeline and resolved scientific inputs
# =============================👐Seperate👐=============================
class ResolvedPluginRecord(BaseModel):
    """One exact plugin implementation and configuration selected for execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    component_id: DefinitionString
    kind: PluginKind
    ref: PluginRef
    configuration_hash: Sha256Hex


class DerivedRandomStream(BaseModel):
    """One deterministic random stream derived for a stable component purpose."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    component_id: DefinitionString
    purpose: DefinitionString
    interface_version: SchemaVersion
    derived_seed: UInt64


class PreparedManeuverSource(StrEnum):
    """Origin of one maneuver in the prepared event timeline."""

    PLANNED = "PLANNED"
    COMMAND = "COMMAND"


class PreparedManeuverEntry(BaseModel):
    """One engine-ordered planned or commanded maneuver."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    order_index: StrictNonNegativeInt
    source: PreparedManeuverSource
    event_id: DefinitionString
    spacecraft_id: DefinitionString
    epoch: Epoch
    maneuver: ManeuverSpec


class EventOrderingPolicy(StrEnum):
    """Versioned event-ordering rules frozen into an execution manifest."""

    POST_MANEUVER_OBSERVATION_V1 = "POST_MANEUVER_OBSERVATION_V1"


class PreparedTimeline(BaseModel):
    """Compact, validated event and sampling inputs produced during preparation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    maneuvers: tuple[PreparedManeuverEntry, ...] = ()
    observation_schedules: tuple[ObservationSchedule, ...] = ()
    output_sampling: OutputSampling

    @field_validator("maneuvers", "observation_schedules", mode="before")
    @classmethod
    def snapshot_timeline_records(cls, value: Any) -> Any:
        """Revalidate copied nested records instead of trusting Pydantic instances."""
        return _snapshot_model_collection(value)

    @field_validator("output_sampling", mode="before")
    @classmethod
    def snapshot_output_sampling(cls, value: Any) -> Any:
        """Copy and revalidate prepared sampling rules at the timeline boundary."""
        return _snapshot_model_input(value)

    @field_validator("observation_schedules")
    @classmethod
    def order_observation_schedules(
        cls,
        value: tuple[ObservationSchedule, ...],
    ) -> tuple[ObservationSchedule, ...]:
        """Serialize prepared schedules in stable schedule-ID order."""
        return tuple(sorted(value, key=lambda item: item.schedule_id))

    @model_validator(mode="after")
    def validate_timeline_identities(self) -> Self:
        """Require exact maneuver ordering and unique event and schedule identities."""
        order_indices = tuple(entry.order_index for entry in self.maneuvers)
        if order_indices != tuple(range(len(self.maneuvers))):
            raise ValueError("maneuver order_index values must be exactly 0..n-1")

        event_ids = tuple(entry.event_id for entry in self.maneuvers)
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("maneuvers must contain unique event_id values")

        schedule_ids = tuple(schedule.schedule_id for schedule in self.observation_schedules)
        if len(schedule_ids) != len(set(schedule_ids)):
            raise ValueError("observation_schedules must contain unique schedule_id values")
        return self


# =============================👐Seperate👐=============================
# Immutable simulation execution manifest
# =============================👐Seperate👐=============================
class SimulationExecutionManifest(BaseModel):
    """Deterministic, immutable scientific execution inputs produced by prepare."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: SchemaVersion
    source_request: SimulationRunRequest
    source_request_hash: Sha256Hex
    simulation_definition_hash: Sha256Hex
    resolved_plugins: tuple[ResolvedPluginRecord, ...]
    resolved_external_data: tuple[ExternalDataRef, ...]
    derived_random_streams: tuple[DerivedRandomStream, ...]
    random_derivation_version: Literal["SYCASPHERE_SEED_V1"]
    prepared_timeline: PreparedTimeline
    event_ordering_policy: Literal[EventOrderingPolicy.POST_MANEUVER_OBSERVATION_V1]
    expected_outputs: frozenset[OutputRequirement]
    canonicalization_version: Literal["SYCASPHERE_CANONICAL_JSON_V1"]
    content_hash: Sha256Hex

    @field_validator("schema_version", "source_request", "prepared_timeline", mode="before")
    @classmethod
    def snapshot_manifest_models(cls, value: Any) -> Any:
        """Copy and revalidate trusted model instances at the manifest boundary."""
        return _snapshot_model_input(value)

    @field_validator(
        "resolved_plugins",
        "resolved_external_data",
        "derived_random_streams",
        mode="before",
    )
    @classmethod
    def snapshot_manifest_records(cls, value: Any) -> Any:
        """Copy and revalidate every resolved or derived nested record."""
        return _snapshot_model_collection(value)

    @field_validator("resolved_plugins")
    @classmethod
    def order_resolved_plugins(
        cls,
        value: tuple[ResolvedPluginRecord, ...],
    ) -> tuple[ResolvedPluginRecord, ...]:
        """Order resolved plugins by stable component identity."""
        return tuple(sorted(value, key=lambda item: item.component_id))

    @field_validator("resolved_external_data")
    @classmethod
    def order_resolved_external_data(
        cls,
        value: tuple[ExternalDataRef, ...],
    ) -> tuple[ExternalDataRef, ...]:
        """Order resolved scientific data by exact identity, version, and digest."""
        return tuple(
            sorted(
                value,
                key=lambda item: (item.data_id, item.version, item.sha256),
            )
        )

    @field_validator("derived_random_streams")
    @classmethod
    def order_derived_random_streams(
        cls,
        value: tuple[DerivedRandomStream, ...],
    ) -> tuple[DerivedRandomStream, ...]:
        """Order derived streams by component and purpose."""
        return tuple(
            sorted(
                value,
                key=lambda item: (item.component_id, item.purpose),
            )
        )

    @field_validator("expected_outputs", mode="before")
    @classmethod
    def normalize_expected_outputs(cls, value: Any) -> tuple[OutputRequirement, ...]:
        """Reject empty or duplicate expected outputs before freezing."""
        return SimulationRunRequest.normalize_output_requirements(value)

    @field_serializer("expected_outputs", when_used="always")
    def serialize_expected_outputs(
        self,
        value: frozenset[OutputRequirement],
    ) -> list[str]:
        """Serialize expected outputs in deterministic enum-value order."""
        return [item.value for item in sorted(value, key=lambda item: item.value)]

    @model_validator(mode="after")
    def validate_manifest_integrity(self) -> Self:
        """Recalculate scientific-input hashes and reject semantic tampering."""
        ## -------------- step: validate resolved and derived identities ---------
        plugin_ids = tuple(record.component_id for record in self.resolved_plugins)
        if len(plugin_ids) != len(set(plugin_ids)):
            raise ValueError("resolved_plugins must contain unique component_id values")

        data_ids = tuple(record.data_id for record in self.resolved_external_data)
        if len(data_ids) != len(set(data_ids)):
            raise ValueError("resolved_external_data must contain unique data_id values")

        stream_ids = tuple(
            (record.component_id, record.purpose) for record in self.derived_random_streams
        )
        if len(stream_ids) != len(set(stream_ids)):
            raise ValueError(
                "derived_random_streams must contain unique component_id and purpose pairs"
            )

        ## -------------- step: validate prepared/source equivalence ---------
        if self.expected_outputs != self.source_request.output_requirements:
            raise ValueError("expected_outputs must equal source_request output_requirements")
        if self.prepared_timeline.output_sampling != self.source_request.output_sampling:
            raise ValueError("prepared output_sampling must equal source_request output_sampling")

        source_schedule_ids = {
            schedule.schedule_id for schedule in self.source_request.observation_schedules
        }
        prepared_schedule_ids = {
            schedule.schedule_id for schedule in self.prepared_timeline.observation_schedules
        }
        if prepared_schedule_ids != source_schedule_ids:
            raise ValueError(
                "prepared observation schedule_id set must equal source_request schedule_id set"
            )

        ## -------------- step: recalculate all manifest hashes ---------
        expected_source_hash = sha256_canonical_json(self.source_request)
        if self.source_request_hash != expected_source_hash:
            raise ValueError("source_request_hash does not match source_request")

        expected_definition_hash = sha256_canonical_json(self.source_request.simulation_definition)
        if self.simulation_definition_hash != expected_definition_hash:
            raise ValueError("simulation_definition_hash does not match simulation_definition")

        expected_content_hash = sha256_canonical_json(
            self.model_dump(mode="json", exclude={"content_hash"})
        )
        if self.content_hash != expected_content_hash:
            raise ValueError("content_hash does not match manifest payload")
        return self

    @classmethod
    def create(
        cls,
        *,
        schema_version: SchemaVersion,
        source_request: SimulationRunRequest,
        resolved_plugins: tuple[ResolvedPluginRecord, ...],
        resolved_external_data: tuple[ExternalDataRef, ...],
        derived_random_streams: tuple[DerivedRandomStream, ...],
        prepared_timeline: PreparedTimeline,
    ) -> SimulationExecutionManifest:
        """Create a validated manifest from alias-independent scientific snapshots."""
        ## -------------- step: revalidate all supplied model instances ---------
        validated_schema_version = SchemaVersion.model_validate(
            _snapshot_model_input(schema_version)
        )
        validated_source = SimulationRunRequest.model_validate(
            _snapshot_model_input(source_request)
        )
        validated_plugins = tuple(
            ResolvedPluginRecord.model_validate(_snapshot_model_input(item))
            for item in resolved_plugins
        )
        validated_data = tuple(
            ExternalDataRef.model_validate(_snapshot_model_input(item))
            for item in resolved_external_data
        )
        validated_streams = tuple(
            DerivedRandomStream.model_validate(_snapshot_model_input(item))
            for item in derived_random_streams
        )
        validated_timeline = PreparedTimeline.model_validate(
            _snapshot_model_input(prepared_timeline)
        )

        ## -------------- step: order resolved scientific records ---------
        ordered_plugins = tuple(sorted(validated_plugins, key=lambda item: item.component_id))
        ordered_data = tuple(
            sorted(
                validated_data,
                key=lambda item: (item.data_id, item.version, item.sha256),
            )
        )
        ordered_streams = tuple(
            sorted(
                validated_streams,
                key=lambda item: (item.component_id, item.purpose),
            )
        )

        ## -------------- step: hash the source and content payload ---------
        source_hash = sha256_canonical_json(validated_source)
        definition_hash = sha256_canonical_json(validated_source.simulation_definition)
        payload: dict[str, Any] = {
            "schema_version": validated_schema_version,
            "source_request": validated_source,
            "source_request_hash": source_hash,
            "simulation_definition_hash": definition_hash,
            "resolved_plugins": ordered_plugins,
            "resolved_external_data": ordered_data,
            "derived_random_streams": ordered_streams,
            "random_derivation_version": RANDOM_DERIVATION_VERSION,
            "prepared_timeline": validated_timeline,
            "event_ordering_policy": (EventOrderingPolicy.POST_MANEUVER_OBSERVATION_V1),
            "expected_outputs": sorted(
                validated_source.output_requirements,
                key=lambda item: item.value,
            ),
            "canonicalization_version": CANONICALIZATION_VERSION,
        }
        payload["content_hash"] = sha256_canonical_json(payload)
        return cls.model_validate(payload)
