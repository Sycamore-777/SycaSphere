# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_package.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-26
版本号    : v1.2.0

■ 用途说明:
  验证 Core 分发包版本、许可证和用户 README 中公开执行契约的一致性。

■ 主要函数功能:
  - test_core_package_exposes_version: 验证导入后可读取包版本。
  - test_core_package_declares_and_copies_license: 验证许可证声明和包级文件。
  - test_readme_documents_approved_execution_contracts: 验证两个 README 记录批准名称。
  - test_core_readme_does_not_exclude_run_requests: 验证 Core README 删除旧排除说明。

■ 功能特性:
  ✓ 验证 Core 包的基础导入契约。
  ✓ 验证包级许可证与仓库根许可证字节一致。
  ✓ 锁定根目录和 Core README 的执行输入公开名称。

■ 更新日志:
  v1.2.0 (2026-07-26): 新增 PEP 639 许可证打包一致性测试。
  v1.1.0 (2026-07-26): 新增 README 执行契约一致性测试。
  v1.0.0 (2026-07-20): 创建 Core 包烟雾测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

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
)
README_PATHS = (
    Path("README.md"),
    Path("packages/sycasphere-core/README.md"),
)


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


@pytest.mark.parametrize("readme_path", README_PATHS)
def test_readme_documents_approved_execution_contracts(readme_path: Path) -> None:
    readme = (REPOSITORY_ROOT / readme_path).read_text(encoding="utf-8")

    assert all(contract in readme for contract in DOCUMENTED_CONTRACTS)


def test_core_readme_does_not_exclude_run_requests() -> None:
    readme = (REPOSITORY_ROOT / README_PATHS[1]).read_text(encoding="utf-8")
    normalized_readme = " ".join(readme.lower().split())

    assert "core phase 1 explicitly excludes observations, run requests" not in normalized_readme
