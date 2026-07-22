# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_model_refs.py
创建者    : Sycamore
创建日期  : 2026-07-22
最后修改  : 2026-07-22
版本号    : v1.0.0

■ 用途说明:
  验证科学子模型引用的身份、版本、有限 JSON 配置与深层不可变契约。

■ 主要函数功能:
  - ModelRef 边界验证: 验证稳定模型标识、接口模式版本及其配置快照。

■ 功能特性:
  ✓ 覆盖有限 JSON、未知字段、深层冻结和 JSON 往返序列化。
  ✓ 验证模型引用不携带加载器或实现对象。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-22): 创建 ModelRef 契约测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.schema import SchemaVersion


# =============================👐Seperate👐==============================
# ModelRef contract tests
# =============================👐Seperate👐==============================
def _model_ref() -> ModelRef:
    return ModelRef(
        model_id="sycasphere.pointing.fixed",
        interface_version=SchemaVersion(major=1, minor=0),
        configuration={"axis": [0.0, 0.0, 1.0], "enabled": True},
    )


def test_model_ref_is_data_only_and_trims_its_stable_id() -> None:
    ref = ModelRef(
        model_id=" sycasphere.pointing.fixed ",
        interface_version=SchemaVersion(major=1, minor=0),
        configuration={},
    )

    assert ref.model_id == "sycasphere.pointing.fixed"
    assert ref.interface_version == SchemaVersion(major=1, minor=0)


@pytest.mark.parametrize("model_id", ["", " ", "\t"])
def test_model_ref_rejects_blank_ids(model_id: str) -> None:
    with pytest.raises(ValidationError):
        ModelRef(
            model_id=model_id,
            interface_version=SchemaVersion(major=1, minor=0),
            configuration={},
        )


def test_model_ref_rejects_bytes_ids() -> None:
    with pytest.raises(ValidationError):
        ModelRef(
            model_id=b"sycasphere.pointing.fixed",
            interface_version=SchemaVersion(major=1, minor=0),
            configuration={},
        )


def test_model_ref_deeply_freezes_and_isolates_configuration() -> None:
    configuration = {"nested": {"thresholds": [1.0, 2.0]}}
    ref = ModelRef(
        model_id="sycasphere.visibility.basic",
        interface_version=SchemaVersion(major=1, minor=0),
        configuration=configuration,
    )

    configuration["nested"]["thresholds"].append(3.0)

    assert ref.configuration["nested"]["thresholds"] == (1.0, 2.0)
    with pytest.raises(TypeError):
        ref.configuration["nested"]["thresholds"][0] = 0.0


def test_model_ref_configuration_round_trips_as_ordinary_json() -> None:
    ref = _model_ref()
    serialized = ref.model_dump(mode="json")
    restored = ModelRef.model_validate(serialized)

    assert serialized["configuration"] == {
        "axis": [0.0, 0.0, 1.0],
        "enabled": True,
    }
    assert restored == ref


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_model_ref_rejects_non_finite_nested_json(invalid: float) -> None:
    with pytest.raises(ValidationError):
        ModelRef(
            model_id="sycasphere.error.gaussian",
            interface_version=SchemaVersion(major=1, minor=0),
            configuration={"sigma": [invalid]},
        )


def test_model_ref_rejects_exceptions_and_unknown_loader_fields() -> None:
    with pytest.raises(ValidationError):
        ModelRef(
            model_id="sycasphere.pointing.fixed",
            interface_version=SchemaVersion(major=1, minor=0),
            configuration={"error": RuntimeError("private")},
        )

    with pytest.raises(ValidationError):
        ModelRef.model_validate(
            {
                "model_id": "sycasphere.pointing.fixed",
                "interface_version": {"major": 1, "minor": 0},
                "configuration": {},
                "python_loader": "private.module:create",
            }
        )


def test_model_ref_defaults_to_an_independent_empty_configuration() -> None:
    first = ModelRef(
        model_id="sycasphere.pointing.fixed",
        interface_version=SchemaVersion(major=1, minor=0),
    )
    second = ModelRef(
        model_id="sycasphere.pointing.target",
        interface_version=SchemaVersion(major=1, minor=0),
    )

    assert first.configuration == {}
    assert second.configuration == {}
    assert first.configuration is not second.configuration
    with pytest.raises(TypeError):
        first.configuration["changed"] = True


def test_model_ref_is_frozen() -> None:
    ref = _model_ref()

    with pytest.raises(ValidationError):
        ref.model_id = "other"
