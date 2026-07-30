# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : __init__.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-30
版本号    : v1.4.0

■ 用途说明:
  提供 SycaSphere Core 纯领域契约包的公共版本、仿真输入、Truth、Observation 和 Delivery 契约。

■ 主要函数功能:
  - __version__: 声明当前 Core 分发包的版本。
  - SchemaVersion: 导出公共模式版本兼容性契约。
  - ErrorCategory 和 ErrorDetail: 导出公共结构化错误契约。
  - PluginKind、PluginRef 和 PluginManifest: 导出后端中立插件清单契约。
  - EntityDefinition 和 SensorDefinition: 导出实体、几何、模型引用与传感器契约。
  - SimulationDefinition 和 SimulationRunRequest: 导出可复用物理世界和一次运行输入。
  - SimulationExecutionManifest: 导出准备阶段生成的不可变科学输入清单。
  - TruthState、IdealObservation 和 ReportedObservation: 导出分离的科学数据层契约。
  - ObservationDeliveryRecord 和 DeliverySummary: 导出逐事件终态和交付汇总契约。

■ 功能特性:
  ✓ 提供稳定的公共导入接口。
  ✓ 发布后端中立的实体与传感器定义契约。
  ✓ 发布机动、调度、仿真输入和执行清单契约。
  ✓ 发布算法安全、可判别的 Truth、Observation 与 Delivery 契约。

■ 更新日志:
  v1.3.0 (2026-07-28): 导出 Truth、Observation 与 Delivery 契约。
  v1.2.0 (2026-07-26): 导出机动、调度、仿真输入和执行清单契约。
  v1.1.0 (2026-07-22): 导出实体、几何、模型引用与传感器契约。
  v1.0.0 (2026-07-20): 导出模式版本、结构化错误和插件清单契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from typing import Final

from sycasphere.core.attitudes import AttitudeState
from sycasphere.core.delivery import (
    DeliveryOutcome,
    DeliverySummary,
    ObservationDeliveryRecord,
    StreamingObservationEnvelope,
)
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
from sycasphere.core.execution_results import (
    SimulationExecutionResult,
    SimulationExecutionStatus,
    SimulationOutputSummary,
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
from sycasphere.core.observations import (
    CustomMeasurementSchemaRef,
    GeometryStatus,
    IdealObservation,
    KnownObjectSubjectRef,
    MeasurementType,
    MeasurementUncertainty,
    ObservationChannel,
    ObservationEvent,
    ObservationMeasurement,
    ObservationSubjectRef,
    ReportedObservation,
    TrackletSubjectRef,
    UnassociatedSubjectRef,
)
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
from sycasphere.core.truth import ManeuverTruthSource, TruthManeuver, TruthState

# =============================👐Seperate👐==============================
# Public package metadata and contracts
# =============================👐Seperate👐==============================
__version__: Final = "0.1.0"

__all__ = [
    "AttitudeState",
    "CartesianState",
    "CentralBody",
    "CoordinateRepresentation",
    "CustomMeasurementSchemaRef",
    "DeliveryOutcome",
    "DeliverySummary",
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
    "GeometryStatus",
    "GroundStationDefinition",
    "IdealObservation",
    "ImpulsiveManeuverSpec",
    "KnownObjectSubjectRef",
    "ManeuverCapability",
    "ManeuverCommand",
    "ManeuverSpec",
    "ManeuverTruthSource",
    "ManeuverType",
    "MeasurementType",
    "MeasurementUncertainty",
    "ModelRef",
    "ObservationChannel",
    "ObservationDeliveryRecord",
    "ObservationEvent",
    "ObservationMeasurement",
    "ObservationSchedule",
    "ObservationScheduleKind",
    "ObservationSubjectRef",
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
    "ReportedObservation",
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
    "SimulationExecutionResult",
    "SimulationExecutionStatus",
    "SimulationOutputSummary",
    "SimulationRunRequest",
    "SimulationTimeRange",
    "SpaceObjectPhysicalProperties",
    "SpacecraftDefinition",
    "StreamingObservationEnvelope",
    "TimeScale",
    "TrackletSubjectRef",
    "TruthManeuver",
    "TruthState",
    "UnassociatedSubjectRef",
]
