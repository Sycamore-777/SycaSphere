# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : entities.py
创建者    : Sycamore
创建日期  : 2026-07-22
最后修改  : 2026-07-22
版本号    : v1.0.0

■ 用途说明:
  定义航天器、其他空间对象和地面站的物理实体层级与传感器组合关系。

■ 主要函数功能:
  - SpaceObjectPhysicalProperties: 验证空间对象 SI 物理参数。
  - EntityDefinition: 以 entity_type 判别三个具体实体模型。

■ 功能特性:
  ✓ 传感器只嵌套在航天器或地面站内。
  ✓ 实体保存物理能力但拒绝固定任务角色。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-22): 创建物理实体定义层级。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    AllowInfNan,
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    field_serializer,
    field_validator,
)
from sycasphere.core._definitions import (
    DefinitionString,
    _DefinitionBase,
    _normalize_unique_strings,
)
from sycasphere.core.geometry import GeodeticLocation
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.sensors import SensorDefinition
from sycasphere.core.states import CartesianState

type PositiveFiniteFloat = Annotated[
    float,
    Strict(),
    AllowInfNan(False),
    Field(gt=0.0),
]
type NonNegativeFiniteFloat = Annotated[
    float,
    Strict(),
    AllowInfNan(False),
    Field(ge=0.0),
]


def _require_unique_sensor_ids(
    values: tuple[SensorDefinition, ...],
) -> tuple[SensorDefinition, ...]:
    """Reject duplicate sensor IDs within one parent entity."""
    identifiers = tuple(value.id for value in values)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("sensors must contain unique id values")
    return values


def _require_unique_model_ids(values: tuple[ModelRef, ...]) -> tuple[ModelRef, ...]:
    """Reject duplicate model IDs within one entity model collection."""
    identifiers = tuple(value.model_id for value in values)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("environment_models must contain unique model_id values")
    return values


# =============================👐Seperate👐==============================
# Shared entity metadata and physical properties
# =============================👐Seperate👐==============================
class EntityType(StrEnum):
    """Supported physical entity kinds."""

    SPACECRAFT = "SPACECRAFT"
    OTHER_SPACE_OBJECT = "OTHER_SPACE_OBJECT"
    GROUND_STATION = "GROUND_STATION"


class SpaceObjectPhysicalProperties(BaseModel):
    """Validated SI physical parameters for a propagated space object."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mass_kg: PositiveFiniteFloat
    cross_section_area_m2: PositiveFiniteFloat
    drag_coefficient: NonNegativeFiniteFloat | None = None
    solar_radiation_pressure_coefficient: NonNegativeFiniteFloat | None = None

    @field_validator(
        "mass_kg",
        "cross_section_area_m2",
        "drag_coefficient",
        "solar_radiation_pressure_coefficient",
        mode="before",
    )
    @classmethod
    def validate_builtin_float(cls, value: Any) -> Any:
        """Reject numeric coercion while preserving optional coefficient values."""
        if value is not None and type(value) is not float:
            raise ValueError("physical properties must be built-in floats")
        return value


class _EntityDefinitionBase(_DefinitionBase):
    """Shared immutable identity and non-controlling metadata for physical entities."""

    capabilities: frozenset[str] = Field(default_factory=frozenset)

    @field_validator("capabilities", mode="before")
    @classmethod
    def normalize_capabilities(cls, value: Any) -> tuple[str, ...]:
        """Validate searchable capabilities before freezing them as a set."""
        return _normalize_unique_strings(value, "capabilities")

    @field_serializer("capabilities", when_used="always")
    def serialize_capabilities(self, value: frozenset[str]) -> list[str]:
        """Serialize capabilities in deterministic lexical order."""
        return sorted(value)


# =============================👐Seperate👐==============================
# Concrete entity definitions and discriminated public union
# =============================👐Seperate👐==============================
class SpacecraftDefinition(_EntityDefinitionBase):
    """A propagated spacecraft that may host sensor child components."""

    entity_type: Literal[EntityType.SPACECRAFT] = EntityType.SPACECRAFT
    initial_state: CartesianState
    physical_properties: SpaceObjectPhysicalProperties
    dynamics_model: ModelRef
    attitude_model: ModelRef
    sensors: tuple[SensorDefinition, ...] = ()

    @field_validator("sensors")
    @classmethod
    def validate_unique_sensor_ids(
        cls, value: tuple[SensorDefinition, ...]
    ) -> tuple[SensorDefinition, ...]:
        """Require unique sensor identities within this spacecraft."""
        return _require_unique_sensor_ids(value)


class OtherSpaceObjectDefinition(_EntityDefinitionBase):
    """A propagated non-spacecraft object that cannot host sensors."""

    entity_type: Literal[EntityType.OTHER_SPACE_OBJECT] = EntityType.OTHER_SPACE_OBJECT
    initial_state: CartesianState
    physical_properties: SpaceObjectPhysicalProperties
    dynamics_model: ModelRef
    attitude_model: ModelRef


class GroundStationDefinition(_EntityDefinitionBase):
    """A WGS84 ground site that may host sensor child components."""

    entity_type: Literal[EntityType.GROUND_STATION] = EntityType.GROUND_STATION
    location: GeodeticLocation
    body_axes_convention: DefinitionString
    environment_models: tuple[ModelRef, ...] = ()
    availability_model: ModelRef | None = None
    sensors: tuple[SensorDefinition, ...] = ()

    @field_validator("environment_models")
    @classmethod
    def validate_unique_environment_model_ids(
        cls, value: tuple[ModelRef, ...]
    ) -> tuple[ModelRef, ...]:
        """Require unique environment model identities within this station."""
        return _require_unique_model_ids(value)

    @field_validator("sensors")
    @classmethod
    def validate_unique_sensor_ids(
        cls, value: tuple[SensorDefinition, ...]
    ) -> tuple[SensorDefinition, ...]:
        """Require unique sensor identities within this station."""
        return _require_unique_sensor_ids(value)


type EntityDefinition = Annotated[
    SpacecraftDefinition | OtherSpaceObjectDefinition | GroundStationDefinition,
    Field(discriminator="entity_type"),
]
