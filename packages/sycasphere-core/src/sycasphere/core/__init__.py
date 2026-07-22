# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : __init__.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-22
版本号    : v1.1.0

■ 用途说明:
  提供 SycaSphere Core 纯领域契约包的公共版本标识、实体与传感器契约。

■ 主要函数功能:
  - __version__: 声明当前 Core 分发包的版本。
  - SchemaVersion: 导出公共模式版本兼容性契约。
  - ErrorCategory 和 ErrorDetail: 导出公共结构化错误契约。
  - PluginKind、PluginRef 和 PluginManifest: 导出后端中立插件清单契约。
  - EntityDefinition 和 SensorDefinition: 导出实体、几何、模型引用与传感器契约。

■ 功能特性:
  ✓ 提供稳定的公共导入接口。
  ✓ 发布后端中立的实体与传感器定义契约。

■ 更新日志:
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
from sycasphere.core.frames import (
    CoordinateRepresentation,
    EarthFixedFrameSpec,
    FrameKind,
    FrameRef,
    ReferenceEllipsoid,
)
from sycasphere.core.geometry import GeodeticLocation, RigidTransform, SensorAxes
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.plugins import PluginKind, PluginManifest, PluginRef, ResourceRequirements
from sycasphere.core.schema import SchemaVersion
from sycasphere.core.sensors import SensorDefinition, SensorType
from sycasphere.core.states import CartesianState

# =============================👐Seperate👐==============================
# Public package metadata and contracts
# =============================👐Seperate👐==============================
__version__: Final = "0.1.0"

__all__ = [
    "CartesianState",
    "CoordinateRepresentation",
    "EarthFixedFrameSpec",
    "EntityDefinition",
    "EntityType",
    "Epoch",
    "ErrorCategory",
    "ErrorDetail",
    "FrameKind",
    "FrameRef",
    "GeodeticLocation",
    "GroundStationDefinition",
    "ModelRef",
    "OtherSpaceObjectDefinition",
    "PluginKind",
    "PluginManifest",
    "PluginRef",
    "ReferenceEllipsoid",
    "ResourceRequirements",
    "RigidTransform",
    "SchemaVersion",
    "SensorAxes",
    "SensorDefinition",
    "SensorType",
    "SpaceObjectPhysicalProperties",
    "SpacecraftDefinition",
    "TimeScale",
]
