# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : preparation.py
创建者    : Sycamore
创建日期  : 2026-07-31
最后修改  : 2026-07-31
版本号    : v1.1.0

■ 用途说明:
  将完整仿真请求准备为不含运行状态和后端对象的不可变执行清单。

■ 主要函数功能:
  - ManifestPreparer.prepare: 快照请求、校验范围并创建 Core 执行清单
  - _validate_consumed_epochs: 通过已解析后端适配器校验全部消费时刻
  - _prepare_maneuvers: 使用已解析后端时间适配器稳定合并机动来源

■ 功能特性:
  ✓ 在公共边界重新验证完整请求
  ✓ 精确解析后端并锁定配置与外部数据 provenance
  ✓ 通过同一后端时间适配器校验和排序全部运行消费时刻
  ✓ 保持同刻 PLANNED、COMMAND 和源元组位置的稳定顺序
  ✓ 准备期不创建科学后端 runtime

■ 待办事项:
  - 无

■ 更新日志:
  v1.1.0 (2026-07-31): 校验全部运行消费 Epoch 后再构造时间线
  v1.0.0 (2026-07-31): 创建 Manifest 准备服务

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cmp_to_key
from typing import NoReturn

from sycasphere.core import (
    Epoch,
    ErrorCategory,
    FiniteBurnManeuverSpec,
    FrameKind,
    ManeuverSpec,
    OtherSpaceObjectDefinition,
    OutputProduct,
    OutputRequirement,
    PreparedManeuverEntry,
    PreparedManeuverSource,
    PreparedTimeline,
    ResolvedPluginRecord,
    SimulationExecutionManifest,
    SimulationRunRequest,
    SpacecraftDefinition,
)
from sycasphere.engine.backend import PreparationTimeAdapter
from sycasphere.engine.errors import SimulationPreparationError, make_error_detail
from sycasphere.engine.registry import PluginRegistry

# =============================👐Seperate👐=============================
# Immutable manifest preparation
# =============================👐Seperate👐=============================

_COMPONENT_REF = "sycasphere.engine.preparation"
_ALLOWED_OUTPUT_REQUIREMENTS = frozenset(
    {
        OutputRequirement.TRUTH,
        OutputRequirement.ATTITUDE,
    }
)
_ALLOWED_SAMPLING_PRODUCTS = frozenset(
    {
        OutputProduct.TRUTH_STATE,
        OutputProduct.ATTITUDE_STATE,
    }
)


@dataclass(frozen=True, slots=True)
class _ManeuverCandidate:
    """One source maneuver with its stable source-local tuple position."""

    source: PreparedManeuverSource
    source_position: int
    event_id: str
    spacecraft_id: str
    epoch: Epoch
    maneuver: ManeuverSpec


def _raise_scope_error(
    *,
    category: ErrorCategory,
    code: str,
    message: str,
    context: Mapping[str, object] | None = None,
) -> NoReturn:
    """Raise one stable Engine-owned v0.1 scope incompatibility."""
    raise SimulationPreparationError(
        make_error_detail(
            category=category,
            code=code,
            message=message,
            component_ref=_COMPONENT_REF,
            context={} if context is None else context,
        )
    )


def _validate_v01_scope(request: SimulationRunRequest) -> None:
    """Reject all scientific inputs that Engine v0.1 cannot execute."""
    ## -------------- step: reject the not-yet-implemented measurement pipeline ---------
    if request.observation_schedules:
        _raise_scope_error(
            category=ErrorCategory.UNSUPPORTED_MEASUREMENT,
            code="engine.observations_unsupported",
            message="Engine v0.1 does not support observation schedules.",
            context={"feature": "observation_schedules"},
        )
    if request.link_models:
        _raise_scope_error(
            category=ErrorCategory.UNSUPPORTED_MEASUREMENT,
            code="engine.link_models_unsupported",
            message="Engine v0.1 does not support link models.",
            context={"feature": "link_models"},
        )

    ## -------------- step: require the exact v0.1 output surface ---------
    sampled_products = frozenset(rule.product for rule in request.output_sampling.rules)
    if (
        OutputRequirement.TRUTH not in request.output_requirements
        or not request.output_requirements.issubset(_ALLOWED_OUTPUT_REQUIREMENTS)
        or OutputProduct.TRUTH_STATE not in sampled_products
        or not sampled_products.issubset(_ALLOWED_SAMPLING_PRODUCTS)
    ):
        _raise_scope_error(
            category=ErrorCategory.PLUGIN_INCOMPATIBLE,
            code="engine.output_unsupported",
            message="Engine v0.1 supports Truth and optional paired attitude output only.",
            context={
                "output_requirements": sorted(item.value for item in request.output_requirements),
                "sampling_products": sorted(item.value for item in sampled_products),
            },
        )

    ## -------------- step: reject every non-J2000 propagated state ---------
    for entity in request.simulation_definition.entities:
        if not isinstance(
            entity,
            (SpacecraftDefinition, OtherSpaceObjectDefinition),
        ):
            continue
        if entity.initial_state.frame.kind is not FrameKind.J2000:
            _raise_scope_error(
                category=ErrorCategory.UNSUPPORTED_FRAME,
                code="engine.frame_unsupported",
                message="Engine v0.1 requires J2000 propagated initial states.",
                context={
                    "source_kind": "initial_state",
                    "source_id": entity.id,
                    "frame": entity.initial_state.frame.kind.value,
                },
            )

    ## -------------- step: reject non-J2000 and finite source maneuvers ---------
    maneuver_sources = (
        (
            "planned_maneuver",
            maneuver.maneuver_id,
            maneuver.maneuver,
        )
        for maneuver in request.simulation_definition.planned_maneuvers
    )
    command_sources = (
        (
            "command",
            command.command_id,
            command.maneuver,
        )
        for command in request.command_timeline
    )
    for source_kind, source_id, maneuver in (*maneuver_sources, *command_sources):
        if maneuver.frame.kind is not FrameKind.J2000:
            _raise_scope_error(
                category=ErrorCategory.UNSUPPORTED_FRAME,
                code="engine.frame_unsupported",
                message="Engine v0.1 requires J2000 maneuver vectors.",
                context={
                    "source_kind": source_kind,
                    "source_id": source_id,
                    "frame": maneuver.frame.kind.value,
                },
            )
        if isinstance(maneuver, FiniteBurnManeuverSpec):
            _raise_scope_error(
                category=ErrorCategory.PLUGIN_INCOMPATIBLE,
                code="engine.finite_burn_unsupported",
                message="Engine v0.1 supports impulsive maneuvers only.",
                context={
                    "source_kind": source_kind,
                    "source_id": source_id,
                },
            )


def _candidate_order(
    left: _ManeuverCandidate,
    right: _ManeuverCandidate,
    time_adapter: PreparationTimeAdapter,
) -> int:
    """Compare by absolute epoch, equal-epoch source priority, then source position."""
    chronological_order = time_adapter.compare(left.epoch, right.epoch)
    if chronological_order != 0:
        return chronological_order

    source_priority = {
        PreparedManeuverSource.PLANNED: 0,
        PreparedManeuverSource.COMMAND: 1,
    }
    left_priority = source_priority[left.source]
    right_priority = source_priority[right.source]
    if left_priority != right_priority:
        return (left_priority > right_priority) - (left_priority < right_priority)
    return (left.source_position > right.source_position) - (
        left.source_position < right.source_position
    )


def _consumed_epochs(request: SimulationRunRequest) -> tuple[Epoch, ...]:
    """Enumerate every run-consumed Epoch in deterministic request-field order."""
    epochs = [
        request.simulation_definition.synchronization_epoch,
        request.time_range.start,
        request.time_range.end,
    ]
    epochs.extend(
        entity.initial_state.epoch
        for entity in request.simulation_definition.entities
        if isinstance(
            entity,
            (SpacecraftDefinition, OtherSpaceObjectDefinition),
        )
    )
    epochs.extend(maneuver.epoch for maneuver in request.simulation_definition.planned_maneuvers)
    epochs.extend(command.epoch for command in request.command_timeline)
    return tuple(epochs)


def _validate_consumed_epochs(
    request: SimulationRunRequest,
    time_adapter: PreparationTimeAdapter,
) -> None:
    """Parse and validate every consumed Epoch against one fixed synchronization anchor."""
    anchor = request.simulation_definition.synchronization_epoch
    for epoch in _consumed_epochs(request):
        time_adapter.compare(anchor, epoch)


def _prepare_maneuvers(
    request: SimulationRunRequest,
    time_adapter: PreparationTimeAdapter,
) -> tuple[PreparedManeuverEntry, ...]:
    """Merge planned and command sources using the resolved backend's absolute time."""
    candidates = [
        _ManeuverCandidate(
            source=PreparedManeuverSource.PLANNED,
            source_position=position,
            event_id=item.maneuver_id,
            spacecraft_id=item.spacecraft_id,
            epoch=item.epoch,
            maneuver=item.maneuver,
        )
        for position, item in enumerate(request.simulation_definition.planned_maneuvers)
    ]
    candidates.extend(
        _ManeuverCandidate(
            source=PreparedManeuverSource.COMMAND,
            source_position=position,
            event_id=item.command_id,
            spacecraft_id=item.spacecraft_id,
            epoch=item.epoch,
            maneuver=item.maneuver,
        )
        for position, item in enumerate(request.command_timeline)
    )

    def compare_candidates(
        left: _ManeuverCandidate,
        right: _ManeuverCandidate,
    ) -> int:
        """Bind the resolved time adapter to the typed stable comparator."""
        return _candidate_order(left, right, time_adapter)

    ordered = sorted(candidates, key=cmp_to_key(compare_candidates))
    return tuple(
        PreparedManeuverEntry(
            order_index=index,
            source=candidate.source,
            event_id=candidate.event_id,
            spacecraft_id=candidate.spacecraft_id,
            epoch=candidate.epoch,
            maneuver=candidate.maneuver,
        )
        for index, candidate in enumerate(ordered)
    )


class ManifestPreparer:
    """Prepare immutable execution provenance using one explicit plugin registry."""

    __slots__ = ("_registry",)

    def __init__(self, registry: PluginRegistry) -> None:
        """Retain the caller-supplied immutable registry."""
        self._registry = registry

    def prepare(self, request: SimulationRunRequest) -> SimulationExecutionManifest:
        """Snapshot one request and create its immutable Core execution manifest."""
        try:
            validated_request = SimulationRunRequest.model_validate(
                request.model_dump(mode="python")
            )
        except ValueError as error:
            raise SimulationPreparationError(
                make_error_detail(
                    category=ErrorCategory.VALIDATION_ERROR,
                    code="engine.request_invalid",
                    message="Simulation run request failed preparation validation.",
                    component_ref=_COMPONENT_REF,
                    context={"validation_stage": "simulation_run_request"},
                )
            ) from error
        try:
            ## -------------- step: resolve before Engine and plugin compatibility ---------
            registration = self._registry.resolve(validated_request.backend.ref)
            _validate_v01_scope(validated_request)
            registration.configuration_validator.validate(validated_request)

            ## -------------- step: lock ordered timeline and resolved provenance ---------
            _validate_consumed_epochs(
                validated_request,
                registration.time_adapter,
            )
            prepared_maneuvers = _prepare_maneuvers(
                validated_request,
                registration.time_adapter,
            )
            return SimulationExecutionManifest.create(
                schema_version=validated_request.schema_version,
                source_request=validated_request,
                resolved_plugins=(
                    ResolvedPluginRecord.create(
                        component_id="science-backend",
                        kind=registration.manifest.kind,
                        ref=registration.manifest.ref,
                        configuration=validated_request.backend.configuration,
                    ),
                ),
                resolved_external_data=(
                    validated_request.simulation_definition.environment.external_data_refs
                ),
                derived_random_streams=(),
                prepared_timeline=PreparedTimeline(
                    maneuvers=prepared_maneuvers,
                    observation_schedules=validated_request.observation_schedules,
                    output_sampling=validated_request.output_sampling,
                ),
            )
        except ValueError as error:
            raise SimulationPreparationError(
                make_error_detail(
                    category=ErrorCategory.VALIDATION_ERROR,
                    code="engine.preparation_invalid",
                    message="Validated inputs could not form an execution manifest.",
                    component_ref=_COMPONENT_REF,
                    context={"validation_stage": "manifest_preparation"},
                )
            ) from error


__all__ = ["ManifestPreparer"]
