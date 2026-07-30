# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : registry.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  提供显式注入、构造后不可修改的科学后端注册表。

■ 主要函数功能:
  - PluginRegistry: 按完整 PluginRef 精确解析已注册的科学后端。
  - resolve: 将缺失后端转换为稳定的准备期结构化错误。

■ 功能特性:
  ✓ 不扫描 Python entry point 或维护全局注册状态
  ✓ 不校验配置、不比较时间且不创建后端运行时
  ✓ 使用只读映射保存固定注册项

■ 待办事项:
  - [ ] 后续准备服务执行能力和配置兼容性验证

■ 更新日志:
  v1.0.0 (2026-07-30): 创建不可变显式后端注册表

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from sycasphere.core import ErrorCategory, PluginKind, PluginRef
from sycasphere.engine.backend import ScienceBackendRegistration
from sycasphere.engine.errors import SimulationPreparationError, make_error_detail

# =============================👐Seperate👐=============================
# Explicit immutable backend registry
# =============================👐Seperate👐=============================


class PluginRegistry:
    """Resolve caller-supplied science-backend registrations by an exact plugin reference."""

    __slots__ = ("_registrations",)

    def __init__(self, registrations: tuple[ScienceBackendRegistration, ...]) -> None:
        """Freeze explicit science-backend registrations without invoking their dependencies."""
        resolved: dict[PluginRef, ScienceBackendRegistration] = {}
        for registration in registrations:
            manifest = registration.manifest
            if manifest.kind is not PluginKind.SCIENCE_BACKEND:
                raise ValueError("backend registration manifest kind must be SCIENCE_BACKEND")
            if manifest.ref in resolved:
                raise ValueError(f"duplicate backend registration for {manifest.ref.plugin_id}")
            resolved[manifest.ref] = registration
        self._registrations: MappingProxyType[PluginRef, ScienceBackendRegistration] = (
            MappingProxyType(resolved)
        )

    @property
    def registrations(self) -> Mapping[PluginRef, ScienceBackendRegistration]:
        """Return the immutable exact-reference registration mapping."""
        return self._registrations

    def resolve(self, ref: PluginRef) -> ScienceBackendRegistration:
        """Return an exact registration or raise a stable missing-backend preparation error."""
        try:
            return self._registrations[ref]
        except KeyError as error:
            raise SimulationPreparationError(
                make_error_detail(
                    category=ErrorCategory.PLUGIN_MISSING,
                    code="plugin.backend_missing",
                    message=f"Science backend {ref.plugin_id!r} is not registered.",
                    component_ref="sycasphere.engine.registry",
                    context={"plugin_ref": ref.model_dump(mode="json")},
                )
            ) from error


__all__ = ["PluginRegistry"]
