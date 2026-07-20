# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_core_dependency_boundary.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.0.0

■ 用途说明:
  验证 Core 源码不依赖基础设施或科学后端模块。

■ 主要函数功能:
  - test_scanner_rejects_forbidden_import_in_temporary_file: 验证扫描器拒绝禁用导入。
  - test_core_source_tree_has_no_forbidden_imports: 验证实际 Core 源码树保持依赖边界。

■ 功能特性:
  ✓ 通过 AST 检查普通导入和 from 导入。
  ✓ 使用临时文件验证拒绝行为，不污染生产源码。

■ 更新日志:
  v1.0.0 (2026-07-20): 新增 Core 依赖边界测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import ast
from pathlib import Path

# =============================👐Seperate👐=============================
# Core dependency-boundary tests
# =============================👐Seperate👐=============================
FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "fastapi",
        "jpype",
        "orekit",
        "pyarrow",
        "sqlalchemy",
        "sqlite3",
    }
)


def _find_forbidden_imports(source_path: Path) -> dict[Path, set[str]]:
    """Return forbidden import roots found in one Python file or a source tree."""
    source_files = (
        (source_path,)
        if source_path.is_file()
        else Path("packages/sycasphere-core/src/sycasphere/core").rglob("*.py")
    )
    violations: dict[Path, set[str]] = {}

    for python_file in source_files:
        parsed = ast.parse(python_file.read_text(encoding="utf-8"), filename=str(python_file))
        roots: set[str] = set()
        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
                roots.add(node.module.split(".", maxsplit=1)[0])

        forbidden_roots = roots & FORBIDDEN_IMPORT_ROOTS
        if forbidden_roots:
            violations[python_file] = forbidden_roots

    return violations


def test_scanner_rejects_forbidden_import_in_temporary_file(tmp_path: Path) -> None:
    """The scanner must report an import root that Core is prohibited from using."""
    source_file = tmp_path / "fixture.py"
    source_file.write_text("import jpype\n", encoding="utf-8")

    assert _find_forbidden_imports(source_file) == {source_file: {"jpype"}}


def test_scanner_rejects_absolute_import_from_in_temporary_file(tmp_path: Path) -> None:
    """The scanner must reject an absolute import from a forbidden external root."""
    source_file = tmp_path / "absolute_import_from.py"
    source_file.write_text("from jpype import JClass\n", encoding="utf-8")

    assert _find_forbidden_imports(source_file) == {source_file: {"jpype"}}


def test_scanner_ignores_relative_import_from_in_temporary_file(tmp_path: Path) -> None:
    """The scanner must not mistake a relative Core module for an external dependency."""
    source_file = tmp_path / "relative_import_from.py"
    source_file.write_text("from .jpype import Adapter\n", encoding="utf-8")

    assert _find_forbidden_imports(source_file) == {}


def test_core_source_tree_has_no_forbidden_imports() -> None:
    """The real Core source tree must remain independent from forbidden infrastructure."""
    core_source = Path("packages/sycasphere-core/src/sycasphere/core")

    assert _find_forbidden_imports(core_source) == {}
