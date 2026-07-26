# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : simulations.py
创建者    : Sycamore
创建日期  : 2026-07-26
最后修改  : 2026-07-26
版本号    : v1.0.0

■ 用途说明:
  定义后端中立、不可变的物理环境和可复用仿真世界输入契约。

■ 主要函数功能:
  - EnvironmentDefinition: 组合中心天体、环境模型和外部科学数据引用。
  - SimulationDefinition: 校验实体、传感器、同步初始状态和预设真值机动。

■ 功能特性:
  ✓ 保证仿真世界内的实体、传感器和预设机动标识全局唯一
  ✓ 约束 v1 同步初始状态和具备能力的航天器机动绑定

■ 待办事项:
  - [ ] 跨时间尺度的时序比较由 Engine prepare 阶段完成

■ 更新日志:
  v1.0.0 (2026-07-26): 创建物理环境与仿真定义契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sycasphere.core._definitions import DefinitionString, _DefinitionBase
from sycasphere.core.entities import (
    EntityDefinition,
    GroundStationDefinition,
    OtherSpaceObjectDefinition,
    SpacecraftDefinition,
)
from sycasphere.core.epoch import Epoch
from sycasphere.core.maneuvers import PlannedTruthManeuver, _validate_maneuver_binding
from sycasphere.core.model_refs import ModelRef


class CentralBody(StrEnum):
    """Celestial bodies supported by the v1 physical-world contract."""

    EARTH = "EARTH"


class ExternalDataRef(BaseModel):
    """An immutable, content-addressed external scientific data dependency."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    data_id: DefinitionString
    version: DefinitionString
    sha256: Annotated[
        str,
        StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$"),
    ]


def _require_unique_model_ids(model_refs: tuple[ModelRef, ...]) -> None:
    """Reject duplicate environment model identities."""
    if len(model_refs) != len({model_ref.model_id for model_ref in model_refs}):
        raise ValueError("model_refs must contain unique model_id values")


def _require_unique_data_ids(data_refs: tuple[ExternalDataRef, ...]) -> None:
    """Reject duplicate external scientific data identities."""
    if len(data_refs) != len({data_ref.data_id for data_ref in data_refs}):
        raise ValueError("external_data_refs must contain unique data_id values")


# =============================👐Seperate👐=============================
# Physical environment definition
# =============================👐Seperate👐=============================
class EnvironmentDefinition(_DefinitionBase):
    """Reusable Earth environment models and immutable external-data references."""

    central_body: CentralBody
    model_refs: tuple[ModelRef, ...] = ()
    external_data_refs: tuple[ExternalDataRef, ...] = ()

    @model_validator(mode="after")
    def validate_unique_references(self) -> EnvironmentDefinition:
        """Require each environment model and external data item to have one identity."""
        _require_unique_model_ids(self.model_refs)
        _require_unique_data_ids(self.external_data_refs)
        return self


def _collect_sensor_ids(entities: tuple[EntityDefinition, ...]) -> tuple[str, ...]:
    """Return all nested sensor identities from supported sensor-host entities."""
    return tuple(
        sensor.id
        for entity in entities
        if isinstance(entity, (SpacecraftDefinition, GroundStationDefinition))
        for sensor in entity.sensors
    )


# =============================👐Seperate👐=============================
# Reusable physical-world definition
# =============================👐Seperate👐=============================
class SimulationDefinition(_DefinitionBase):
    """An immutable physical world without mission roles or run-time controls."""

    synchronization_epoch: Epoch
    environment: EnvironmentDefinition
    entities: tuple[EntityDefinition, ...] = Field(min_length=1)
    planned_maneuvers: tuple[PlannedTruthManeuver, ...] = ()

    @model_validator(mode="after")
    def validate_world_consistency(self) -> SimulationDefinition:
        """Validate global identities, v1 synchronized states, and maneuver bindings."""
        ## -------------- step: validate entity and sensor identities ---------
        entity_ids = tuple(entity.id for entity in self.entities)
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("entities must contain unique entity id values")

        sensor_ids = _collect_sensor_ids(self.entities)
        if len(sensor_ids) != len(set(sensor_ids)):
            raise ValueError("sensors must contain globally unique sensor id values")
        if set(entity_ids).intersection(sensor_ids):
            raise ValueError("sensor id values must not equal entity id values")

        ## -------------- step: require synchronized propagated space objects ---------
        space_objects = tuple(
            entity
            for entity in self.entities
            if isinstance(entity, (SpacecraftDefinition, OtherSpaceObjectDefinition))
        )
        if not space_objects:
            raise ValueError("simulation must contain at least one space object")
        for space_object in space_objects:
            if space_object.initial_state.epoch != self.synchronization_epoch:
                raise ValueError(
                    "space object initial_state epoch must equal synchronization_epoch"
                )

        ## -------------- step: resolve and validate planned truth maneuvers ---------
        maneuver_ids = tuple(maneuver.maneuver_id for maneuver in self.planned_maneuvers)
        if len(maneuver_ids) != len(set(maneuver_ids)):
            raise ValueError("planned_maneuvers must contain unique maneuver_id values")

        entities_by_id = {entity.id: entity for entity in self.entities}
        for planned_maneuver in self.planned_maneuvers:
            target = entities_by_id.get(planned_maneuver.spacecraft_id)
            if not isinstance(target, SpacecraftDefinition):
                raise ValueError(
                    "planned maneuver spacecraft_id must reference an existing spacecraft"
                )
            _validate_maneuver_binding(
                planned_maneuver.maneuver,
                planned_maneuver.spacecraft_id,
                planned_maneuver.epoch,
                target.maneuver_capability,
            )
            if (
                planned_maneuver.epoch.time_scale is self.synchronization_epoch.time_scale
                and planned_maneuver.epoch.value < self.synchronization_epoch.value
            ):
                raise ValueError(
                    "planned maneuver epoch must not be earlier than synchronization_epoch"
                )

        return self
