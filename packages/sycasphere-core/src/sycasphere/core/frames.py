# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : frames.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.0.0

■ 用途说明:
  定义不泄漏科学后端实现的公共坐标系引用和坐标表示契约。

■ 主要函数功能:
  - EarthFixedFrameSpec: 声明地固帧所需的 ITRF、IERS 和 EOP 来源元数据。
  - FrameRef: 验证公共帧、坐标表示和局部帧构造元数据的有效组合。

■ 功能特性:
  ✓ 提供六种稳定的公共帧语义。
  ✓ 区分地固帧与 WGS84 参考椭球。
  ✓ 保持公共帧引用和元数据不可变。

■ 更新日志:
  v1.0.0 (2026-07-20): 创建公共坐标系引用契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sycasphere.core.epoch import Epoch


# =============================👐Seperate👐==============================
# Public frame and coordinate-representation enumerations
# =============================👐Seperate👐==============================
class FrameKind(StrEnum):
    """Stable public frame semantics that a backend adapter may implement."""

    J2000 = "J2000"
    EARTH_FIXED = "EARTH_FIXED"
    LVLH = "LVLH"
    VVLH = "VVLH"
    BODY = "BODY"
    SENSOR = "SENSOR"


class CoordinateRepresentation(StrEnum):
    """Coordinate representations supported by public frame references."""

    CARTESIAN = "CARTESIAN"
    GEODETIC = "GEODETIC"


class ReferenceEllipsoid(StrEnum):
    """Reference ellipsoids used only with compatible coordinate representations."""

    WGS84 = "WGS84"


# =============================👐Seperate👐==============================
# Immutable public frame metadata
# =============================👐Seperate👐==============================
class EarthFixedFrameSpec(BaseModel):
    """Explicit provenance required to interpret an Earth-fixed coordinate frame."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    itrf_realization: Annotated[str, Field(min_length=1)]
    iers_conventions: Annotated[str, Field(min_length=1)]
    eop_data_id: Annotated[str, Field(min_length=1)]


class FrameRef(BaseModel):
    """An immutable public frame reference without scientific-backend implementation types."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: FrameKind
    representation: CoordinateRepresentation = CoordinateRepresentation.CARTESIAN
    earth_fixed: EarthFixedFrameSpec | None = None
    ellipsoid: ReferenceEllipsoid | None = None
    owner_id: Annotated[str | None, Field(min_length=1)] = None
    convention: Annotated[str | None, Field(min_length=1)] = None
    reference_epoch: Epoch | None = None

    @model_validator(mode="after")
    def _validate_metadata_combination(self) -> FrameRef:
        """Reject metadata that does not belong to the selected public frame semantic."""
        local_kinds = {FrameKind.LVLH, FrameKind.VVLH, FrameKind.BODY, FrameKind.SENSOR}

        if self.kind is FrameKind.J2000:
            if self.representation is not CoordinateRepresentation.CARTESIAN:
                raise ValueError("J2000 supports only CARTESIAN representation")
            if any(
                value is not None
                for value in (
                    self.earth_fixed,
                    self.ellipsoid,
                    self.owner_id,
                    self.convention,
                    self.reference_epoch,
                )
            ):
                raise ValueError("J2000 does not accept Earth-fixed or local-frame metadata")
            return self

        if self.kind is FrameKind.EARTH_FIXED:
            if self.earth_fixed is None:
                raise ValueError("EARTH_FIXED requires ITRF, IERS, and EOP metadata")
            if any(
                value is not None
                for value in (self.owner_id, self.convention, self.reference_epoch)
            ):
                raise ValueError("EARTH_FIXED does not accept local-frame metadata")
            if self.representation is CoordinateRepresentation.GEODETIC:
                if self.ellipsoid is not ReferenceEllipsoid.WGS84:
                    raise ValueError("GEODETIC EARTH_FIXED references require ellipsoid WGS84")
            elif self.ellipsoid is not None:
                raise ValueError("CARTESIAN EARTH_FIXED references do not accept an ellipsoid")
            return self

        if self.kind in local_kinds:
            if self.representation is not CoordinateRepresentation.CARTESIAN:
                raise ValueError("local frames support only CARTESIAN representation")
            if any(
                value is None for value in (self.owner_id, self.convention, self.reference_epoch)
            ):
                raise ValueError("local frames require owner_id, convention, and reference_epoch")
            if self.earth_fixed is not None or self.ellipsoid is not None:
                raise ValueError("local frames do not accept Earth-fixed metadata")
            return self

        raise ValueError("unsupported public frame kind")
