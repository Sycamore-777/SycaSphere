# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : execution.py
创建者    : Sycamore
创建日期  : 2026-07-26
最后修改  : 2026-07-26
版本号    : v1.0.0

■ 用途说明:
  定义独立仿真引擎可直接验证和执行的自包含、不可变运行输入边界。

■ 主要函数功能:
  - ScienceBackendBinding: 绑定精确科学后端版本及有限 JSON 配置
  - SimulationRunRequest: 校验物理世界、调度、命令、采样和输出的闭合一致性

■ 功能特性:
  ✓ 嵌入完整 SimulationDefinition 并解析所有运行期科学引用
  ✓ 严格验证无符号随机种子、机动能力、时间范围和输出采样

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-26): 创建自包含仿真运行请求契约

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    Strict,
    field_serializer,
    field_validator,
    model_validator,
)
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
from sycasphere.core.maneuvers import ManeuverCommand, _validate_maneuver_binding
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.plugins import PluginRef
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
from sycasphere.core.simulations import SimulationDefinition

type UInt64 = Annotated[
    int,
    Strict(),
    Field(ge=0, le=2**64 - 1),
]


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
