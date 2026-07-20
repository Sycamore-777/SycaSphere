# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_frames.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.1.0

■ 用途说明:
  验证公共坐标系引用的允许组合、不变量和不可变性。

■ 主要函数功能:
  - 帧契约验证: 验证公共帧、地固元数据和局部帧构造要求。
  - 表示验证: 验证笛卡尔与大地坐标表示的适用范围。

■ 功能特性:
  ✓ 覆盖公共帧种类和后端泄漏防护。
  ✓ 覆盖帧元数据组合、非空规范化和模型不可变性。

■ 更新日志:
  v1.1.0 (2026-07-20): 覆盖必需元数据规范化和全部无关元数据分支。
  v1.0.0 (2026-07-20): 创建公共帧引用契约测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sycasphere.core import (
    CoordinateRepresentation,
    EarthFixedFrameSpec,
    Epoch,
    FrameKind,
    FrameRef,
    ReferenceEllipsoid,
    TimeScale,
)

# =============================👐Seperate👐==============================
# Public frame-reference contract tests
# =============================👐Seperate👐==============================
_REFERENCE_EPOCH = Epoch(value="2026-07-20T10:00:00Z", time_scale=TimeScale.UTC)
_EARTH_FIXED_SPEC = EarthFixedFrameSpec(
    itrf_realization="ITRF2020",
    iers_conventions="IERS_2010",
    eop_data_id="iers-bulletin-a:2026-07-20",
)


def test_frame_kind_contains_only_the_six_approved_public_values() -> None:
    assert {kind.value for kind in FrameKind} == {
        "J2000",
        "EARTH_FIXED",
        "LVLH",
        "VVLH",
        "BODY",
        "SENSOR",
    }


def test_j2000_defaults_to_cartesian_representation() -> None:
    frame = FrameRef(kind=FrameKind.J2000)

    assert frame.representation is CoordinateRepresentation.CARTESIAN


def test_earth_fixed_accepts_explicit_provenance_metadata() -> None:
    frame = FrameRef(
        kind=FrameKind.EARTH_FIXED,
        representation=CoordinateRepresentation.CARTESIAN,
        earth_fixed=_EARTH_FIXED_SPEC,
    )

    assert frame.earth_fixed == _EARTH_FIXED_SPEC


def test_sensor_accepts_required_local_frame_metadata() -> None:
    frame = FrameRef(
        kind=FrameKind.SENSOR,
        owner_id="sensor-1",
        convention="sensor-boresight-rh",
        reference_epoch=_REFERENCE_EPOCH,
    )

    assert frame.owner_id == "sensor-1"
    assert frame.reference_epoch == _REFERENCE_EPOCH


@pytest.mark.parametrize("kind", ["WGS84", "GCRF"])
def test_unknown_public_frame_kind_is_rejected(kind: str) -> None:
    with pytest.raises(ValidationError):
        FrameRef(kind=kind)


def test_earth_fixed_requires_all_provenance_metadata() -> None:
    with pytest.raises(ValidationError):
        FrameRef(kind=FrameKind.EARTH_FIXED)


@pytest.mark.parametrize(
    "field_name",
    ["itrf_realization", "iers_conventions", "eop_data_id"],
)
def test_earth_fixed_provenance_rejects_blank_required_values(field_name: str) -> None:
    metadata = _EARTH_FIXED_SPEC.model_dump()
    metadata[field_name] = ""

    with pytest.raises(ValidationError):
        EarthFixedFrameSpec(**metadata)


@pytest.mark.parametrize(
    "field_name",
    ["itrf_realization", "iers_conventions", "eop_data_id"],
)
def test_earth_fixed_provenance_rejects_whitespace_only_values(field_name: str) -> None:
    metadata = _EARTH_FIXED_SPEC.model_dump()
    metadata[field_name] = " \t "

    with pytest.raises(ValidationError):
        EarthFixedFrameSpec(**metadata)


def test_earth_fixed_provenance_trims_surrounding_whitespace() -> None:
    spec = EarthFixedFrameSpec(
        itrf_realization=" ITRF2020 ",
        iers_conventions=" IERS_2010 ",
        eop_data_id=" iers-bulletin-a:2026-07-20 ",
    )

    assert spec == _EARTH_FIXED_SPEC


@pytest.mark.parametrize(
    "metadata",
    [
        {"earth_fixed": _EARTH_FIXED_SPEC},
        {"ellipsoid": ReferenceEllipsoid.WGS84},
        {"owner_id": "spacecraft-1"},
        {"convention": "inertial"},
        {"reference_epoch": _REFERENCE_EPOCH},
    ],
)
def test_j2000_rejects_irrelevant_metadata(metadata: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        FrameRef(kind=FrameKind.J2000, **metadata)


@pytest.mark.parametrize("kind", [FrameKind.J2000, FrameKind.LVLH, FrameKind.VVLH])
def test_geodetic_representation_is_rejected_outside_earth_fixed(kind: FrameKind) -> None:
    metadata: dict[str, object] = {}
    if kind in {FrameKind.LVLH, FrameKind.VVLH}:
        metadata = {
            "owner_id": "spacecraft-1",
            "convention": "local-rh",
            "reference_epoch": _REFERENCE_EPOCH,
        }

    with pytest.raises(ValidationError):
        FrameRef(
            kind=kind,
            representation=CoordinateRepresentation.GEODETIC,
            **metadata,
        )


@pytest.mark.parametrize("kind", [FrameKind.BODY, FrameKind.SENSOR])
def test_remaining_local_frames_reject_geodetic_representation(kind: FrameKind) -> None:
    with pytest.raises(ValidationError):
        FrameRef(
            kind=kind,
            representation=CoordinateRepresentation.GEODETIC,
            owner_id="spacecraft-1",
            convention="local-rh",
            reference_epoch=_REFERENCE_EPOCH,
        )


def test_geodetic_earth_fixed_requires_wgs84_ellipsoid() -> None:
    with pytest.raises(ValidationError):
        FrameRef(
            kind=FrameKind.EARTH_FIXED,
            representation=CoordinateRepresentation.GEODETIC,
            earth_fixed=_EARTH_FIXED_SPEC,
        )


def test_geodetic_earth_fixed_accepts_wgs84_ellipsoid() -> None:
    frame = FrameRef(
        kind=FrameKind.EARTH_FIXED,
        representation=CoordinateRepresentation.GEODETIC,
        ellipsoid=ReferenceEllipsoid.WGS84,
        earth_fixed=_EARTH_FIXED_SPEC,
    )

    assert frame.ellipsoid is ReferenceEllipsoid.WGS84


def test_cartesian_earth_fixed_rejects_irrelevant_ellipsoid() -> None:
    with pytest.raises(ValidationError):
        FrameRef(
            kind=FrameKind.EARTH_FIXED,
            representation=CoordinateRepresentation.CARTESIAN,
            earth_fixed=_EARTH_FIXED_SPEC,
            ellipsoid=ReferenceEllipsoid.WGS84,
        )


@pytest.mark.parametrize(
    "metadata",
    [
        {"owner_id": "spacecraft-1"},
        {"convention": "earth-fixed"},
        {"reference_epoch": _REFERENCE_EPOCH},
    ],
)
def test_earth_fixed_rejects_each_irrelevant_local_metadata_field(
    metadata: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        FrameRef(kind=FrameKind.EARTH_FIXED, earth_fixed=_EARTH_FIXED_SPEC, **metadata)


@pytest.mark.parametrize(
    "kind",
    [FrameKind.LVLH, FrameKind.VVLH, FrameKind.BODY, FrameKind.SENSOR],
)
@pytest.mark.parametrize("missing_field", ["owner_id", "convention", "reference_epoch"])
def test_local_frames_require_owner_convention_and_reference_epoch(
    kind: FrameKind,
    missing_field: str,
) -> None:
    metadata: dict[str, object] = {
        "owner_id": "spacecraft-1",
        "convention": "local-rh",
        "reference_epoch": _REFERENCE_EPOCH,
    }
    del metadata[missing_field]

    with pytest.raises(ValidationError):
        FrameRef(kind=kind, **metadata)


@pytest.mark.parametrize(
    "field_name",
    ["owner_id", "convention"],
)
def test_local_frame_required_strings_reject_whitespace_only(field_name: str) -> None:
    metadata: dict[str, object] = {
        "owner_id": "spacecraft-1",
        "convention": "local-rh",
        "reference_epoch": _REFERENCE_EPOCH,
    }
    metadata[field_name] = " \t "

    with pytest.raises(ValidationError):
        FrameRef(kind=FrameKind.LVLH, **metadata)


def test_local_frame_required_strings_trim_surrounding_whitespace() -> None:
    frame = FrameRef(
        kind=FrameKind.LVLH,
        owner_id=" spacecraft-1 ",
        convention=" local-rh ",
        reference_epoch=_REFERENCE_EPOCH,
    )

    assert frame.owner_id == "spacecraft-1"
    assert frame.convention == "local-rh"


@pytest.mark.parametrize(
    "kind",
    [FrameKind.LVLH, FrameKind.VVLH, FrameKind.BODY, FrameKind.SENSOR],
)
@pytest.mark.parametrize(
    "metadata",
    [
        {"earth_fixed": _EARTH_FIXED_SPEC},
        {"ellipsoid": ReferenceEllipsoid.WGS84},
    ],
)
def test_local_frames_reject_each_irrelevant_earth_fixed_metadata_field(
    kind: FrameKind,
    metadata: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        FrameRef(
            kind=kind,
            owner_id="spacecraft-1",
            convention="local-rh",
            reference_epoch=_REFERENCE_EPOCH,
            **metadata,
        )


def test_frame_models_reject_extra_fields_and_post_construction_mutation() -> None:
    frame = FrameRef(kind=FrameKind.J2000)

    with pytest.raises(ValidationError):
        FrameRef(kind=FrameKind.J2000, backend_name="EME2000")
    with pytest.raises(ValidationError):
        frame.kind = FrameKind.EARTH_FIXED
    with pytest.raises(ValidationError):
        _EARTH_FIXED_SPEC.itrf_realization = "ITRF2014"
