# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_package.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  验证 Engine 分发元数据、README 可执行示例与权威实现状态边界。

■ 主要函数功能:
  - test_engine_package_declares_version_dependencies_and_license: 验证包元数据。
  - test_engine_readme_documents_batch_runtime_boundaries: 验证公开使用与限制说明。
  - test_readme_example_matches_fixture_and_executes: 验证示例单一来源与执行结果。
  - test_authoritative_documents_publish_truthful_engine_status: 验证架构状态同步。

■ 功能特性:
  ✓ 锁定无 Orekit/JDK 的后端中立分发边界
  ✓ 执行 README 的有界 FakeBackend 示例
  ✓ 区分 Engine Result 与未来 Platform RunOutcome

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

# Exact Chinese architecture phrases intentionally retain their approved punctuation.
# ruff: noqa: RUF001
from __future__ import annotations

import runpy
import tomllib
from pathlib import Path

import pytest

# =============================👐Seperate👐=============================
# Package and documentation boundaries
# =============================👐Seperate👐=============================
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ENGINE_PACKAGE_ROOT = REPOSITORY_ROOT / "packages/sycasphere-engine"
ENGINE_README = ENGINE_PACKAGE_ROOT / "README.md"
README_FIXTURE = ENGINE_PACKAGE_ROOT / "tests/fixtures/readme_fake_run.py"
AUTHORITATIVE_ARCHITECTURE_PATHS = (
    REPOSITORY_ROOT / "docs/architecture/core-data-model-v0.2.md",
    REPOSITORY_ROOT / "docs/architecture/algorithm-integration-v0.2.md",
    REPOSITORY_ROOT
    / "docs/superpowers/specs/2026-07-20-sycasphere-runtime-and-simulation-engine-design.md",
)
IMPLEMENTED_ENGINE_STATUS = (
    "Engine v0.1 已实现同步 `prepare()`/`run()`、显式 `PluginRegistry`、"
    "非科学 `FakeBackend` 和输出 sinks。"
)
PLANNED_AFTER_ENGINE_STATUS = (
    "Observation 流水线、交互式 Session、Orekit、Sim 保留、Platform 生命周期和前端仍为计划。"
)
RESULT_BOUNDARY_STATUS = "`SimulationExecutionResult` 不是 `RunOutcome`。"
FAKE_MASS_STATUS = "`FakeBackend` 质量保持不变，因为当前脉冲输入没有消耗量。"


def _normalized_document(path: Path) -> str:
    """Collapse formatting whitespace while retaining exact architecture wording."""
    return " ".join(path.read_text(encoding="utf-8").split())


def _fixture_example_body() -> str:
    """Read the canonical README body from the executable fixture markers."""
    fixture = README_FIXTURE.read_text(encoding="utf-8")
    return (
        fixture.split("# README_EXAMPLE_START\n", maxsplit=1)[1]
        .split("# README_EXAMPLE_END", maxsplit=1)[0]
        .rstrip()
    )


def _readme_example_body() -> str:
    """Extract the sole marked Python example from the Engine package README."""
    readme = ENGINE_README.read_text(encoding="utf-8")
    return readme.split("<!-- README_EXAMPLE_START -->\n```python\n", maxsplit=1)[1].split(
        "\n```\n<!-- README_EXAMPLE_END -->", maxsplit=1
    )[0]


def test_engine_package_declares_version_dependencies_and_license() -> None:
    """Engine metadata remains independently installable and backend-neutral."""
    root_license = REPOSITORY_ROOT / "LICENSE"
    package_license = ENGINE_PACKAGE_ROOT / "LICENSE"
    package_metadata = tomllib.loads(
        (ENGINE_PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    project = package_metadata["project"]

    assert package_license.is_file()
    assert package_license.read_bytes() == root_license.read_bytes()
    assert project["version"] == "0.1.0"
    assert project["license"] == "Apache-2.0"
    assert project["license-files"] == ["LICENSE"]
    assert project["requires-python"] == ">=3.12,<3.13"
    assert project["dependencies"] == ["numpy>=2.0,<3", "sycasphere-core"]

    serialized_metadata = str(project).lower()
    for forbidden_dependency in ("orekit", "jpype", "java", "fastapi", "pyarrow", "sqlite"):
        assert forbidden_dependency not in serialized_metadata


@pytest.mark.parametrize(
    "required_text",
    (
        "engine.prepare(request)",
        "engine.run(manifest, sink, CancellationToken())",
        "synchronous batch API",
        "InMemoryOutputSink(max_records=32)",
        "non-scientific compatibility backend",
        "J2000 only",
        "same time scale",
        "impulsive maneuvers only",
        "Manifest excludes lifecycle state",
        "Observation remains planned",
        "interactive Session remains planned",
        "Orekit remains planned",
    ),
)
def test_engine_readme_documents_batch_runtime_boundaries(required_text: str) -> None:
    """The package guide states the usable API and every material v0.1 limitation."""
    assert required_text in ENGINE_README.read_text(encoding="utf-8")


def test_readme_example_matches_fixture_and_executes(capsys: pytest.CaptureFixture[str]) -> None:
    """The documented example is copied exactly from one executable fixture source."""
    assert _readme_example_body() == _fixture_example_body()

    runpy.run_path(str(README_FIXTURE), run_name="__main__")

    assert capsys.readouterr().out.splitlines() == [
        "Truth states: 3",
        "Attitude states: 3",
        "Truth maneuvers: 1",
    ]


@pytest.mark.parametrize("document_path", AUTHORITATIVE_ARCHITECTURE_PATHS)
@pytest.mark.parametrize(
    "expected_status",
    (
        IMPLEMENTED_ENGINE_STATUS,
        PLANNED_AFTER_ENGINE_STATUS,
        RESULT_BOUNDARY_STATUS,
        FAKE_MASS_STATUS,
    ),
)
def test_authoritative_documents_publish_truthful_engine_status(
    document_path: Path,
    expected_status: str,
) -> None:
    """All authoritative architecture documents distinguish delivered and planned work."""
    assert expected_status in _normalized_document(document_path)
