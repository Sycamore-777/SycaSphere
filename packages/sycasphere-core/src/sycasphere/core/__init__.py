# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : __init__.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-26
版本号    : v1.2.0

■ 用途说明:
  提供 SycaSphere Core 纯领域契约包的公共版本标识、实体、仿真输入和执行清单契约。

■ 主要函数功能:
  - __version__: 声明当前 Core 分发包的版本。
  - SchemaVersion: 导出公共模式版本兼容性契约。
  - ErrorCategory 和 ErrorDetail: 导出公共结构化错误契约。
  - PluginKind、PluginRef 和 PluginManifest: 导出后端中立插件清单契约。
  - EntityDefinition 和 SensorDefinition: 导出实体、几何、模型引用与传感器契约。
  - SimulationDefinition 和 SimulationRunRequest: 导出可复用物理世界和一次运行输入。
  - SimulationExecutionManifest: 导出准备阶段生成的不可变科学输入清单。

■ 功能特性:
  ✓ 提供稳定的公共导入接口。
  ✓ 发布后端中立的实体与传感器定义契约。
  ✓ 发布机动、调度、仿真输入和执行清单契约。

■ 更新日志:
  v1.2.0 (2026-07-26): 导出机动、调度、仿真输入和执行清单契约。
  v1.1.0 (2026-07-22): 导出实体、几何、模型引用与传感器契约。
  v1.0.0 (2026-07-20): 导出模式版本、结构化错误和插件清单契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from typing import Final

from sycasphere.core.entities import (
    EntityDefinition,
    EntityType,
    GroundStationDefinition,
    OtherSpaceObjectDefinition,
    SpacecraftDefinition,
    SpaceObjectPhysicalProperties,
)
from sycasphere.core.epoch import Epoch, TimeScale
from sycasphere.core.errors import ErrorCategory, ErrorDetail
from sycasphere.core.execution import (
    DerivedRandomStream,
    EventOrderingPolicy,
    OutputRequirement,
    PreparedManeuverEntry,
    PreparedManeuverSource,
    PreparedTimeline,
    ResolvedPluginRecord,
    ScienceBackendBinding,
    SimulationExecutionManifest,
    SimulationRunRequest,
)
from sycasphere.core.frames import (
    CoordinateRepresentation,
    EarthFixedFrameSpec,
    FrameKind,
    FrameRef,
    ReferenceEllipsoid,
)
from sycasphere.core.geometry import GeodeticLocation, RigidTransform, SensorAxes
from sycasphere.core.maneuvers import (
    FiniteBurnManeuverSpec,
    ImpulsiveManeuverSpec,
    ManeuverCapability,
    ManeuverCommand,
    ManeuverSpec,
    ManeuverType,
    PlannedTruthManeuver,
)
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.plugins import PluginKind, PluginManifest, PluginRef, ResourceRequirements
from sycasphere.core.schedules import (
    ExplicitObservationSchedule,
    ObservationSchedule,
    ObservationScheduleKind,
    OutputProduct,
    OutputSampling,
    PeriodicObservationSchedule,
    SamplingRule,
    SimulationTimeRange,
)
from sycasphere.core.schema import SchemaVersion
from sycasphere.core.sensors import SensorDefinition, SensorType
from sycasphere.core.simulations import (
    CentralBody,
    EnvironmentDefinition,
    ExternalDataRef,
    SimulationDefinition,
)
from sycasphere.core.states import CartesianState

# =============================👐Seperate👐==============================
# Public package metadata and contracts
# =============================👐Seperate👐==============================
__version__: Final = "0.1.0"

__all__ = [
    "CartesianState",
    "CentralBody",
    "CoordinateRepresentation",
    "DerivedRandomStream",
    "EarthFixedFrameSpec",
    "EntityDefinition",
    "EntityType",
    "EnvironmentDefinition",
    "Epoch",
    "ErrorCategory",
    "ErrorDetail",
    "EventOrderingPolicy",
    "ExplicitObservationSchedule",
    "ExternalDataRef",
    "FiniteBurnManeuverSpec",
    "FrameKind",
    "FrameRef",
    "GeodeticLocation",
    "GroundStationDefinition",
    "ImpulsiveManeuverSpec",
    "ManeuverCapability",
    "ManeuverCommand",
    "ManeuverSpec",
    "ManeuverType",
    "ModelRef",
    "ObservationSchedule",
    "ObservationScheduleKind",
    "OtherSpaceObjectDefinition",
    "OutputProduct",
    "OutputRequirement",
    "OutputSampling",
    "PeriodicObservationSchedule",
    "PlannedTruthManeuver",
    "PluginKind",
    "PluginManifest",
    "PluginRef",
    "PreparedManeuverEntry",
    "PreparedManeuverSource",
    "PreparedTimeline",
    "ReferenceEllipsoid",
    "ResolvedPluginRecord",
    "ResourceRequirements",
    "RigidTransform",
    "SamplingRule",
    "SchemaVersion",
    "ScienceBackendBinding",
    "SensorAxes",
    "SensorDefinition",
    "SensorType",
    "SimulationDefinition",
    "SimulationExecutionManifest",
    "SimulationRunRequest",
    "SimulationTimeRange",
    "SpaceObjectPhysicalProperties",
    "SpacecraftDefinition",
    "TimeScale",
]
