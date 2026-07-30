# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_engine_dependency_boundary.py
创建者    : Sycamore
创建日期  : 2026-07-30
最后修改  : 2026-07-30
版本号    : v1.0.0

■ 用途说明:
  验证 Engine 源码保持后端中立，不依赖受限基础设施或外层 SycaSphere 包。

■ 主要函数功能:
  - _find_forbidden_imports: 扫描 Python 源码中的受限绝对导入。
  - test_engine_source_tree_has_no_forbidden_imports: 验证实际 Engine 源码树的依赖边界。

■ 功能特性:
  ✓ 通过 AST 检查普通导入和绝对 from 导入。
  ✓ 拒绝 Orekit 和 Platform 的绝对 SycaSphere 导入。

■ 待办事项:
  - [ ] 后续任务增加 Engine 模块时继续由本测试守护边界。

■ 更新日志:
  v1.0.0 (2026-07-30): 初始版本。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# =============================👐Seperate👐=============================
# Engine dependency-boundary tests
# =============================👐Seperate👐=============================
FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "fastapi",
        "java",
        "jpype",
        "kafka",
        "orekit",
        "pyarrow",
        "redis",
        "sqlalchemy",
        "sqlite3",
    }
)
FORBIDDEN_SYCASPHERE_MODULES = frozenset({"sycasphere.orekit", "sycasphere.platform"})


def _find_forbidden_imports(source_path: Path) -> dict[Path, set[str]]:
    """Return prohibited absolute imports found in one Python file or source tree."""
    if not source_path.exists():
        raise FileNotFoundError(f"source path does not exist: {source_path}")

    source_files = (source_path,) if source_path.is_file() else tuple(source_path.rglob("*.py"))
    if not source_files:
        raise ValueError(f"source tree does not contain any Python source files: {source_path}")
    violations: dict[Path, set[str]] = {}

    for python_file in source_files:
        parsed = ast.parse(python_file.read_text(encoding="utf-8"), filename=str(python_file))
        imported_modules: set[str] = set()
        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
                imported_modules.add(node.module)

        forbidden_modules = {
            module
            for module in imported_modules
            if module.split(".", maxsplit=1)[0] in FORBIDDEN_IMPORT_ROOTS
            or any(
                module == forbidden_module or module.startswith(f"{forbidden_module}.")
                for forbidden_module in FORBIDDEN_SYCASPHERE_MODULES
            )
        }
        if forbidden_modules:
            violations[python_file] = forbidden_modules

    return violations


def test_scanner_rejects_forbidden_import_in_temporary_file(tmp_path: Path) -> None:
    """The scanner reports an import root that Engine is prohibited from using."""
    source_file = tmp_path / "fixture.py"
    source_file.write_text("import jpype\n", encoding="utf-8")

    assert _find_forbidden_imports(source_file) == {source_file: {"jpype"}}


@pytest.mark.parametrize("forbidden_root", ("java", "kafka"))
def test_scanner_rejects_engine_binding_import_roots(tmp_path: Path, forbidden_root: str) -> None:
    """The scanner rejects each additional Engine binding import root."""
    source_file = tmp_path / f"{forbidden_root}_binding.py"
    source_file.write_text(f"import {forbidden_root}\n", encoding="utf-8")

    assert _find_forbidden_imports(source_file) == {source_file: {forbidden_root}}


def test_scanner_rejects_absolute_sycasphere_outer_layer(tmp_path: Path) -> None:
    """The scanner rejects Engine imports from Orekit and Platform layers."""
    source_file = tmp_path / "outer_layer.py"
    source_file.write_text("from sycasphere.orekit import Adapter\n", encoding="utf-8")

    assert _find_forbidden_imports(source_file) == {source_file: {"sycasphere.orekit"}}


def test_scanner_ignores_relative_import_from_in_temporary_file(tmp_path: Path) -> None:
    """The scanner does not mistake a relative Engine module for an outer dependency."""
    source_file = tmp_path / "relative_import_from.py"
    source_file.write_text("from .orekit import Adapter\n", encoding="utf-8")

    assert _find_forbidden_imports(source_file) == {}


def test_scanner_rejects_an_absent_source_tree(tmp_path: Path) -> None:
    """A missing expected Engine tree fails instead of appearing dependency-clean."""
    missing_source_tree = tmp_path / "missing"

    with pytest.raises(FileNotFoundError, match="source path does not exist"):
        _find_forbidden_imports(missing_source_tree)


def test_scanner_rejects_an_empty_source_tree(tmp_path: Path) -> None:
    """An expected source tree without Python modules fails clearly."""
    empty_source_tree = tmp_path / "empty"
    empty_source_tree.mkdir()

    with pytest.raises(ValueError, match="does not contain any Python source files"):
        _find_forbidden_imports(empty_source_tree)


def test_engine_source_tree_has_no_forbidden_imports() -> None:
    """The real Engine source tree remains backend-neutral and infrastructure-free."""
    engine_source = Path("packages/sycasphere-engine/src/sycasphere/engine")

    assert _find_forbidden_imports(engine_source) == {}
