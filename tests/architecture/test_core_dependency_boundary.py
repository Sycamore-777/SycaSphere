# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_core_dependency_boundary.py
创建者    : Sycamore
创建日期  : 2026-07-20
最后修改  : 2026-07-20
版本号    : v1.1.0

■ 用途说明:
  验证 Core 源码不依赖基础设施或科学后端模块。

■ 主要函数功能:
  - test_scanner_rejects_forbidden_import_in_temporary_file: 验证扫描器拒绝禁用导入。
  - test_core_source_tree_has_no_forbidden_imports: 验证实际 Core 源码树保持依赖边界。

■ 功能特性:
  ✓ 通过 AST 检查普通导入和 from 导入。
  ✓ 使用临时文件和目录验证拒绝行为与明确的源树错误，不污染生产源码。

■ 更新日志:
  v1.1.0 (2026-07-20): 验证扫描器使用调用方目录并拒绝不存在或空源树。
  v1.0.0 (2026-07-20): 新增 Core 依赖边界测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

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
    if not source_path.exists():
        raise FileNotFoundError(f"source path does not exist: {source_path}")

    source_files = (source_path,) if source_path.is_file() else tuple(source_path.rglob("*.py"))
    if not source_files:
        raise ValueError(f"source tree does not contain any Python source files: {source_path}")
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


def test_scanner_traverses_the_supplied_directory(tmp_path: Path) -> None:
    """A caller-supplied source tree, including nested modules, must be scanned."""
    source_file = tmp_path / "nested" / "adapter.py"
    source_file.parent.mkdir()
    source_file.write_text("import orekit\n", encoding="utf-8")

    assert _find_forbidden_imports(tmp_path) == {source_file: {"orekit"}}


def test_scanner_rejects_an_absent_source_tree(tmp_path: Path) -> None:
    """A missing expected source tree must fail instead of appearing dependency-clean."""
    missing_source_tree = tmp_path / "missing"

    with pytest.raises(FileNotFoundError, match="source path does not exist"):
        _find_forbidden_imports(missing_source_tree)


def test_scanner_rejects_an_empty_source_tree(tmp_path: Path) -> None:
    """An expected source tree without Python modules must fail clearly."""
    empty_source_tree = tmp_path / "empty"
    empty_source_tree.mkdir()

    with pytest.raises(ValueError, match="does not contain any Python source files"):
        _find_forbidden_imports(empty_source_tree)


def test_core_source_tree_has_no_forbidden_imports() -> None:
    """The real Core source tree must remain independent from forbidden infrastructure."""
    core_source = Path("packages/sycasphere-core/src/sycasphere/core")

    assert _find_forbidden_imports(core_source) == {}
