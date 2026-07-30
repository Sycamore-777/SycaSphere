# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_package.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-30
版本号    : v1.7.0

■ 用途说明:
  验证 Core 分发包版本、许可证以及公开文档中的领域契约一致性。

■ 主要函数功能:
  - test_core_package_exposes_version: 验证导入后可读取包版本。
  - test_core_package_declares_and_copies_license: 验证许可证声明和包级文件。
  - test_readme_documents_approved_execution_contracts: 验证两个 README 记录批准名称。
  - test_core_readme_does_not_exclude_run_requests: 验证 Core README 删除旧排除说明。
  - test_authoritative_documents_mark_delivery_contract_status: 验证实现与计划边界。
  - test_authoritative_documents_define_delivery_pipeline_semantics: 验证交付科学语义。
  - test_authoritative_documents_keep_deferred_features_out_of_v1: 验证首版延后边界。
  - test_core_data_model_routes_observations_through_delivery_gate: 验证观测交付门控流程。
  - test_core_data_model_orders_event_before_visible_measurement: 验证 Event 先于测量形成。
  - test_runtime_design_branches_selected_channel_before_link: 验证双通道分支和拒绝终止。
  - test_algorithm_integration_keeps_v1_fifo_out_of_session_configuration: 验证首版 FIFO 归属。
  - test_delivery_design_preserves_schema_version_scope: 验证 SchemaVersion 范围说明。

■ 功能特性:
  ✓ 验证 Core 包的基础导入契约。
  ✓ 验证包级许可证与仓库根许可证字节一致。
  ✓ 锁定根目录和 Core README 的执行输入公开名称。
  ✓ 锁定两个 README 的 Truth、Observation 与 Delivery 公开名称。
  ✓ 锁定三份权威架构文档的实现状态和首版交付边界。
  ✓ 锁定 Core 数据流、在线 FIFO 请求边界和 SchemaVersion 修改范围。
  ✓ 锁定几何、Event、测量、误差与链路的权威图示顺序。

■ 更新日志:
  v1.7.0 (2026-07-30): 同步 Engine v0.1 已实现与后续计划状态。
  v1.6.0 (2026-07-28): 增加 Core 与 Runtime 图示阶段顺序回归测试。
  v1.5.0 (2026-07-28): 增加文档专属交付门控、FIFO 和 SchemaVersion 回归测试。
  v1.4.0 (2026-07-28): 新增权威架构文档状态与交付语义一致性测试。
  v1.3.0 (2026-07-28): 新增结果与观测交付 README 契约测试。
  v1.2.0 (2026-07-26): 新增 PEP 639 许可证打包一致性测试。
  v1.1.0 (2026-07-26): 新增 README 执行契约一致性测试。
  v1.0.0 (2026-07-20): 创建 Core 包烟雾测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

# Exact Chinese architecture phrases intentionally retain their approved punctuation.
# ruff: noqa: RUF001
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

# =============================👐Seperate👐=============================
# Core package and documentation smoke tests
# =============================👐Seperate👐=============================
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CORE_PACKAGE_ROOT = REPOSITORY_ROOT / "packages/sycasphere-core"
DOCUMENTED_CONTRACTS = (
    "SimulationDefinition",
    "SimulationRunRequest",
    "SimulationExecutionManifest",
    "ManeuverCommand",
    "PeriodicObservationSchedule",
    "ExplicitObservationSchedule",
    "TruthState",
    "TruthManeuver",
    "IdealObservation",
    "ReportedObservation",
    "ObservationDeliveryRecord",
    "DeliverySummary",
)
README_PATHS = (
    Path("README.md"),
    Path("packages/sycasphere-core/README.md"),
)
CORE_DATA_MODEL_PATH = Path("docs/architecture/core-data-model-v0.2.md")
ALGORITHM_INTEGRATION_PATH = Path("docs/architecture/algorithm-integration-v0.2.md")
RUNTIME_ENGINE_DESIGN_PATH = Path(
    "docs/superpowers/specs/2026-07-20-sycasphere-runtime-and-simulation-engine-design.md"
)
DELIVERY_DESIGN_PATH = Path(
    "docs/superpowers/specs/2026-07-28-core-truth-observation-delivery-design.md"
)
AUTHORITATIVE_ARCHITECTURE_PATHS = (
    CORE_DATA_MODEL_PATH,
    ALGORITHM_INTEGRATION_PATH,
    RUNTIME_ENGINE_DESIGN_PATH,
)
IMPLEMENTED_CORE_CONTRACT_STATUS = (
    "Core 已实现 `AttitudeState`、`TruthState`、`TruthManeuver`、"
    "`ObservationEvent`、`ObservationMeasurement`、`IdealObservation`、"
    "`ReportedObservation`、`MeasurementUncertainty`、"
    "`ObservationDeliveryRecord`、`DeliverySummary` 和"
    " `StreamingObservationEnvelope`。"
)
IMPLEMENTED_ENGINE_STATUS = (
    "Engine v0.1 已实现同步 `prepare()`/`run()`、显式 `PluginRegistry`、"
    "非科学 `FakeBackend` 和输出 sinks。"
)
PLANNED_AFTER_ENGINE_STATUS = (
    "Observation 流水线、交互式 Session、Orekit、Sim 保留、Platform 生命周期和前端仍为计划。"
)
ENGINE_RESULT_BOUNDARY_STATUS = "`SimulationExecutionResult` 不是 `RunOutcome`。"
FAKE_MASS_STATUS = "`FakeBackend` 质量保持不变，因为当前脉冲输入没有消耗量。"
DELIVERY_PIPELINE_PHRASES = (
    "先分配 `event_id`，完成几何检查后一次性创建不可变 Event，不创建可回填的半成品。",
    "Event 只跟随 ObservationSchedule 触发。积分步、Truth 输出采样和"
    "前端渲染帧均不得隐式产生 Event。",
    "每个 ObservationSchedule 的交付通道由 `error_profile_id` 唯一决定："
    " `error_profile_id is None` 选择 IDEAL；`error_profile_id` 存在选择 REPORTED。",
    "OutputRequirement 只控制 artifact 持久化；Engine 仍必须生成所选交付通道"
    "需要的 Ideal 或 Reported payload，不能因为未请求对应 artifact 而跳过科学流水线。",
    "算法只接收成功交付的 Ideal 或 Reported。",
    "链路延迟和丢包属于 LinkModel，不属于 ErrorPipeline。",
    "首版 `StreamingObservationEnvelope` 使用 `delivery_epoch`，"
    "不包含 `arrival_time` 或 `sequence_number`。",
    "逐事件交付记录通过显式 `DELIVERY_RECORDS` 输出要求控制，不要求全部常驻内存。",
    "Sim 后续默认使用 TRANSIENT，只保留最近一次临时运行。",
    "所有机器字段和枚举使用稳定英文值；后续前端必须提供中文标签、说明和磁盘占用提示。",
    "中文文案不写入 Manifest、科学哈希或稳定数据库枚举。",
)
DEFERRED_FIRST_VERSION_PHRASES = (
    "`IdealObservation` 与 `ReportedObservation` 是两个独立模型；"
    "算法直接读取被授权的模型，不增加 `AlgorithmObservationView`。",
    "首版算法只接收成功交付的 Ideal/Reported，不提供 `NonDetectionReport`。",
    "首版链路只模拟延迟和丢包，不模拟乱序、重复、重传或多次交付尝试。",
    "Engine 后续保证每个算法输入流 FIFO；链路延迟不改变测量顺序。",
)
OBSOLETE_DIRECT_ALGORITHM_FLOW = "I --> A1[算法端自行加噪] R --> A2[算法直接处理]"
APPROVED_DELIVERY_GATED_FLOW = (
    "一次 Event 的 schedule `error_profile_id` 只选择一个交付通道：`None` 选择 Ideal，"
    " 存在时选择 Reported。所选 payload 必须经过 LinkModel 的延迟、丢包和 FIFO 处理； "
    "只有 `DELIVERED` 创建 `StreamingObservationEnvelope` 并到达算法，其他终态只形成"
    " `ObservationDeliveryRecord` 事实。"
)
OBSOLETE_ONLINE_TIMING_BULLET = "- 到达时序；"
OBSOLETE_SESSION_ORDERING_BULLET = "- 排序策略；"
APPROVED_NONCONFIGURABLE_FIFO = (
    "在线模式中的时序仅指成功交付时序。首版 `StreamingSessionRequest` 不包含排序策略； "
    "每个算法输入流的 FIFO 顺序由 Engine 固定保证，调用方不能在会话请求中配置重排。"
)
APPROVED_SCHEMA_VERSION_SCOPE = (
    "`schema.py` 不属于本批次修改范围：实现复用现有 `SchemaVersion` 且未引入任何 "
    "schema-version 行为。Schema 快照的新增内容来自公开模型注册，不需要修改版本类型。"
)
OBSOLETE_CORE_MEASUREMENT_GEOMETRY_FLOW = (
    r"T[TruthState] --> G[Deterministic Measurement Model] "
    r"G -->|VISIBLE| I[IdealObservation\n无误差接口] "
    r"G -->|GEOMETRY_REJECTED| D[ObservationDeliveryRecord\n终态事实]"
)
APPROVED_CORE_EVENT_MEASUREMENT_STAGES = (
    "S[ObservationSchedule trigger] --> P[preallocate deterministic event_id]",
    "P --> G[geometry / visibility / pointing]",
    "G --> E[create immutable ObservationEvent once]",
    r"E -->|GEOMETRY_REJECTED| D[ObservationDeliveryRecord\n终态事实]",
    "E -->|VISIBLE| M[Deterministic Measurement Model]",
    r"M --> I[IdealObservation\n无误差接口]",
)
OBSOLETE_RUNTIME_LINEAR_ERROR_FLOW = (
    "IdealObservation ↓ ErrorPipeline ReportedObservation 或未形成报告 "
    "↓ select IDEAL/REPORTED from schedule error_profile_id LinkModel"
)
APPROVED_RUNTIME_DELIVERY_STAGES = (
    "schedule trigger ↓ preallocate deterministic event_id",
    "geometry / visibility / pointing ↓ create immutable ObservationEvent once",
    "branch on ObservationEvent.geometry_status",
    "├─ GEOMETRY_REJECTED → ObservationDeliveryRecord → terminal",
    "└─ VISIBLE → Deterministic Measurement Model → IdealObservation",
    "↓ branch on schedule error_profile_id",
    "├─ None → select IDEAL → LinkModel",
    "└─ present → ErrorPipeline",
    "├─ SENSOR_MISSED / QUALITY_REJECTED → ObservationDeliveryRecord → terminal",
    "└─ ReportedObservation → select REPORTED → LinkModel",
)


def _normalized_document(path: Path) -> str:
    return " ".join((REPOSITORY_ROOT / path).read_text(encoding="utf-8").split())


def _assert_stages_in_order(document: str, stages: tuple[str, ...]) -> None:
    positions: list[int] = []
    for stage in stages:
        assert stage in document, f"missing exact architecture stage: {stage}"
        positions.append(document.index(stage))

    assert positions == sorted(positions), "architecture stages are out of order"


def test_core_package_exposes_version() -> None:
    import sycasphere.core

    assert sycasphere.core.__version__ == "0.1.0"


def test_core_package_declares_and_copies_license() -> None:
    root_license = REPOSITORY_ROOT / "LICENSE"
    package_license = CORE_PACKAGE_ROOT / "LICENSE"
    package_metadata = tomllib.loads(
        (CORE_PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert package_license.is_file()
    assert package_license.read_bytes() == root_license.read_bytes()
    assert package_metadata["project"]["license"] == "Apache-2.0"
    assert package_metadata["project"]["license-files"] == ["LICENSE"]


@pytest.mark.parametrize("contract", DOCUMENTED_CONTRACTS)
@pytest.mark.parametrize("readme_path", README_PATHS, ids=lambda path: path.as_posix())
def test_readme_documents_approved_execution_contracts(
    readme_path: Path,
    contract: str,
) -> None:
    readme = (REPOSITORY_ROOT / readme_path).read_text(encoding="utf-8")

    assert contract in readme


def test_core_readme_does_not_exclude_run_requests() -> None:
    readme = (REPOSITORY_ROOT / README_PATHS[1]).read_text(encoding="utf-8")
    normalized_readme = " ".join(readme.lower().split())

    assert "core phase 1 explicitly excludes observations, run requests" not in normalized_readme


@pytest.mark.parametrize(
    "expected_phrase",
    (
        IMPLEMENTED_CORE_CONTRACT_STATUS,
        IMPLEMENTED_ENGINE_STATUS,
        PLANNED_AFTER_ENGINE_STATUS,
        ENGINE_RESULT_BOUNDARY_STATUS,
        FAKE_MASS_STATUS,
    ),
    ids=(
        "implemented-core-contracts",
        "implemented-engine-runtime",
        "planned-after-engine",
        "engine-result-not-run-outcome",
        "fake-mass-unchanged",
    ),
)
@pytest.mark.parametrize(
    "document_path",
    AUTHORITATIVE_ARCHITECTURE_PATHS,
    ids=lambda path: path.name,
)
def test_authoritative_documents_mark_delivery_contract_status(
    document_path: Path,
    expected_phrase: str,
) -> None:
    document = _normalized_document(document_path)

    assert expected_phrase in document


@pytest.mark.parametrize(
    "expected_phrase",
    DELIVERY_PIPELINE_PHRASES,
    ids=(
        "event-created-once",
        "schedule-trigger-only",
        "error-profile-selects-channel",
        "output-requirement-persists-only",
        "algorithms-receive-delivered-only",
        "link-model-owns-delay-drop",
        "minimal-streaming-envelope",
        "delivery-record-output",
        "transient-retention",
        "chinese-frontend-labels",
        "chinese-text-excluded-from-science",
    ),
)
@pytest.mark.parametrize(
    "document_path",
    AUTHORITATIVE_ARCHITECTURE_PATHS,
    ids=lambda path: path.name,
)
def test_authoritative_documents_define_delivery_pipeline_semantics(
    document_path: Path,
    expected_phrase: str,
) -> None:
    document = _normalized_document(document_path)

    assert expected_phrase in document


@pytest.mark.parametrize(
    "expected_phrase",
    DEFERRED_FIRST_VERSION_PHRASES,
    ids=(
        "separate-observation-models",
        "no-nondetection-report",
        "no-reorder-duplicate-retransmission",
        "engine-fifo",
    ),
)
@pytest.mark.parametrize(
    "document_path",
    AUTHORITATIVE_ARCHITECTURE_PATHS,
    ids=lambda path: path.name,
)
def test_authoritative_documents_keep_deferred_features_out_of_v1(
    document_path: Path,
    expected_phrase: str,
) -> None:
    document = _normalized_document(document_path)

    assert expected_phrase in document


def test_core_data_model_routes_observations_through_delivery_gate() -> None:
    document = _normalized_document(CORE_DATA_MODEL_PATH)

    assert OBSOLETE_DIRECT_ALGORITHM_FLOW not in document
    assert APPROVED_DELIVERY_GATED_FLOW in document
    assert "T -.仅评价器可见.-> V[Evaluator]" in document


def test_core_data_model_rejects_measurement_model_geometry_branch() -> None:
    document = _normalized_document(CORE_DATA_MODEL_PATH)

    assert OBSOLETE_CORE_MEASUREMENT_GEOMETRY_FLOW not in document


def test_core_data_model_orders_event_before_visible_measurement() -> None:
    document = _normalized_document(CORE_DATA_MODEL_PATH)

    _assert_stages_in_order(document, APPROVED_CORE_EVENT_MEASUREMENT_STAGES)


def test_runtime_design_rejects_linear_error_before_channel_selection() -> None:
    document = _normalized_document(RUNTIME_ENGINE_DESIGN_PATH)

    assert OBSOLETE_RUNTIME_LINEAR_ERROR_FLOW not in document


def test_runtime_design_branches_selected_channel_before_link() -> None:
    document = _normalized_document(RUNTIME_ENGINE_DESIGN_PATH)

    _assert_stages_in_order(document, APPROVED_RUNTIME_DELIVERY_STAGES)


def test_algorithm_integration_keeps_v1_fifo_out_of_session_configuration() -> None:
    document = _normalized_document(ALGORITHM_INTEGRATION_PATH)

    assert OBSOLETE_ONLINE_TIMING_BULLET not in document
    assert OBSOLETE_SESSION_ORDERING_BULLET not in document
    assert APPROVED_NONCONFIGURABLE_FIFO in document


def test_delivery_design_preserves_schema_version_scope() -> None:
    document = _normalized_document(DELIVERY_DESIGN_PATH)

    assert APPROVED_SCHEMA_VERSION_SCOPE in document
