# Core Entity and Sensor Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `sycasphere-core` 交付不可变、可序列化、后端中立的模型引用、安装几何、WGS84 地理位置、传感器和实体联合契约，同时保持无 JDK/Orekit 的独立安装边界。

**Architecture:** 物理结构使用强类型 Pydantic v2 模型；动力学、姿态、指向、视场、可见性等可替换科学子模型统一通过深度不可变的 `ModelRef` 描述。传感器只嵌套在航天器或地面站内，公共 `EntityDefinition` 使用 `entity_type` 判别三个具体实体类型；Core 只校验数据，不解析或执行模型。

**Tech Stack:** Python 3.12、Pydantic v2、NumPy、uv、pytest、Ruff、mypy、Hatchling

## Global Constraints

- 严格遵循根目录 `AGENTS.md` 和 `docs/superpowers/specs/2026-07-21-core-entity-and-sensor-contracts-design.md`。
- Core 运行时依赖仍只能是 Pydantic 与 NumPy；不得引入 Orekit、JPype、Java、SQLite、PyArrow、FastAPI 或前端依赖。
- 所有新增 Python 文件必须使用准确的 Sycamore 文件头、`from __future__ import annotations` 和项目分隔符，不得写不真实的完成状态。
- 所有公开模型必须 `frozen=True`、`extra="forbid"`，所有公开函数、方法和模型都必须有类型标注。
- 数值字段使用 SI 单位；三维向量和四元数必须是严格有限浮点数，不接受字符串等隐式转换。
- 四元数顺序唯一为 `w, x, y, z`，字段名为 `rotation_parent_to_child_wxyz`；不得增加 `xyzw` 别名或自动猜测。
- 单位向量、正交、右手关系和单位四元数使用绝对容差 `1e-9`，不得静默归一化。
- metadata 和 configuration 必须复用 `_json.py`，做到有限、深度不可变、输入别名隔离和普通 JSON 序列化。
- 定义对象共享字段和 metadata 验证必须集中在私有 `_definitions.py`；该模块不得加入 `sycasphere.core.__all__`。
- 传感器不得包含独立轨道或状态；实体不得包含固定任务角色。
- 本计划不实现 SimulationDefinition、机动、观测、传播、姿态计算、可见性计算、存储、API、CLI 或前端。
- 每个行为先写失败测试并确认失败原因，再写最小实现；每个任务完成后单独提交。
- 执行本计划前使用 `using-git-worktrees` 创建隔离工作树；不要把现有未跟踪的 `docs/assets/` 纳入提交。

## File Structure

```text
packages/sycasphere-core/src/sycasphere/core/
├── _definitions.py # 私有共享定义字段、标签与 metadata 冻结
├── model_refs.py  # ModelRef 与深度不可变配置
├── geometry.py    # RigidTransform、SensorAxes、GeodeticLocation
├── sensors.py     # SensorType 与 SensorDefinition
├── entities.py    # EntityType、物理属性、三个实体与判别联合
└── __init__.py    # 审查后的公共导出

packages/sycasphere-core/tests/
├── test_model_refs.py
├── test_geometry.py
├── test_sensors.py
├── test_entities.py
├── test_public_api.py
└── snapshots/core-schemas.json
```

---

### Task 1: Add immutable data-only ModelRef

**Files:**

- Create: `packages/sycasphere-core/src/sycasphere/core/model_refs.py`
- Create: `packages/sycasphere-core/tests/test_model_refs.py`

**Interfaces:**

- Consumes: `SchemaVersion`, `_json.normalize_json_object`, `_json.freeze_json_object`, `_json.thaw_json_value`.
- Produces: `ModelRef(model_id: str, interface_version: SchemaVersion, configuration: Mapping[str, JsonValue])` for Sensors and Entities.

- [ ] **Step 1: Write failing ModelRef boundary tests**

Create `packages/sycasphere-core/tests/test_model_refs.py` with this complete content:

```python
# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_model_refs.py
创建者    : Sycamore
创建日期  : 2026-07-21
最后修改  : 2026-07-21
版本号    : v1.0.0

■ 用途说明:
  验证可插拔科学子模型引用的身份、版本、有限 JSON 和深层不可变契约。

■ 主要函数功能:
  - 模型身份验证: 验证稳定非空 ID 和接口模式版本。
  - 配置快照验证: 验证深层冻结、输入别名隔离和 JSON 往返。

■ 功能特性:
  ✓ 覆盖有限 JSON、未知字段和冻结行为。
  ✓ 验证模型引用不携带加载器或实现对象。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-21): 创建 ModelRef 契约测试。

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
```

- [ ] **Step 2: Run the focused test and confirm the missing-module failure**

Run:

```bash
uv run pytest packages/sycasphere-core/tests/test_model_refs.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'sycasphere.core.model_refs'`.

- [ ] **Step 3: Implement ModelRef with the shared immutable JSON utility**

Create `packages/sycasphere-core/src/sycasphere/core/model_refs.py`:

```python
# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : model_refs.py
创建者    : Sycamore
创建日期  : 2026-07-21
最后修改  : 2026-07-21
版本号    : v1.0.0

■ 用途说明:
  定义后端中立、仅数据化且深度不可变的科学子模型配置引用。

■ 主要函数功能:
  - ModelRef: 保存稳定模型 ID、接口模式版本和有限 JSON 配置。

■ 功能特性:
  ✓ 配置在输入边界复制并深度冻结。
  ✓ 序列化恢复普通 JSON 对象且不加载模型实现。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-21): 创建通用 ModelRef 契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_serializer,
    field_validator,
)
from sycasphere.core._json import (
    FrozenJsonValue,
    freeze_json_object,
    normalize_json_object,
    thaw_json_value,
)
from sycasphere.core.schema import SchemaVersion

type StableModelId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


# =============================👐Seperate👐==============================
# Immutable scientific-model references
# =============================👐Seperate👐==============================
class ModelRef(BaseModel):
    """A data-only reference to a configured scientific submodel."""

    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)

    model_id: StableModelId
    interface_version: SchemaVersion
    configuration: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("configuration", mode="before")
    @classmethod
    def normalize_configuration(cls, value: Any) -> dict[str, JsonValue]:
        """Normalize a supported mapping and reject non-finite or private values."""
        return normalize_json_object(value)

    @field_validator("configuration")
    @classmethod
    def freeze_configuration(
        cls, value: Mapping[str, JsonValue]
    ) -> Mapping[str, FrozenJsonValue]:
        """Store an alias-independent immutable configuration snapshot."""
        return freeze_json_object(value)

    @field_serializer("configuration", when_used="always")
    def serialize_configuration(
        self, value: Mapping[str, FrozenJsonValue]
    ) -> dict[str, JsonValue]:
        """Serialize the immutable snapshot as ordinary JSON values."""
        return {key: thaw_json_value(nested) for key, nested in value.items()}
```

- [ ] **Step 4: Run focused tests and static checks**

Run:

```bash
uv run pytest packages/sycasphere-core/tests/test_model_refs.py -q
uv run mypy packages/sycasphere-core/src/sycasphere/core/model_refs.py
uv run ruff check packages/sycasphere-core/src/sycasphere/core/model_refs.py packages/sycasphere-core/tests/test_model_refs.py
```

Expected: all commands PASS with no issues.

- [ ] **Step 5: Commit the ModelRef contract**

```bash
git add packages/sycasphere-core/src/sycasphere/core/model_refs.py packages/sycasphere-core/tests/test_model_refs.py
git commit -m "feat(core): add immutable model references"
```

---

### Task 2: Add mount transforms and explicit sensor axes

**Files:**

- Create: `packages/sycasphere-core/src/sycasphere/core/geometry.py`
- Create: `packages/sycasphere-core/tests/test_geometry.py`

**Interfaces:**

- Consumes: NumPy only for vector validation; no backend types.
- Produces: `RigidTransform` and `SensorAxes` for `SensorDefinition`.

- [ ] **Step 1: Write failing transform and axes tests**

Create `packages/sycasphere-core/tests/test_geometry.py` with this initial content:

```python
# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_geometry.py
创建者    : Sycamore
创建日期  : 2026-07-21
最后修改  : 2026-07-21
版本号    : v1.0.0

■ 用途说明:
  验证安装刚体变换、显式传感器轴和地面站大地位置契约。

■ 主要函数功能:
  - 安装变换验证: 验证 SI 平移与 wxyz 单位四元数。
  - 传感器轴验证: 验证单位、正交和右手轴约定。

■ 功能特性:
  ✓ 拒绝非有限、错误长度和隐式数值转换。
  ✓ 固定父到子旋转与非默认视轴语义。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-21): 创建安装变换和传感器轴测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from sycasphere.core.geometry import RigidTransform, SensorAxes

# =============================👐Seperate👐==============================
# Rigid-transform and sensor-axes tests
# =============================👐Seperate👐==============================
def _identity_transform() -> RigidTransform:
    return RigidTransform(
        translation_m=[1.0, 2.0, 3.0],
        rotation_parent_to_child_wxyz=[1.0, 0.0, 0.0, 0.0],
    )


def _right_handed_axes() -> SensorAxes:
    return SensorAxes(
        boresight=[0.0, 0.0, 1.0],
        horizontal=[1.0, 0.0, 0.0],
        vertical=[0.0, 1.0, 0.0],
    )


def test_rigid_transform_uses_explicit_parent_to_child_wxyz_contract() -> None:
    transform = _identity_transform()

    assert transform.translation_m == (1.0, 2.0, 3.0)
    assert transform.rotation_parent_to_child_wxyz == (1.0, 0.0, 0.0, 0.0)
    assert transform.model_dump(mode="json") == {
        "translation_m": [1.0, 2.0, 3.0],
        "rotation_parent_to_child_wxyz": [1.0, 0.0, 0.0, 0.0],
    }


def test_rigid_transform_rejects_xyzw_compatibility_field() -> None:
    with pytest.raises(ValidationError):
        RigidTransform.model_validate(
            {
                "translation_m": [0.0, 0.0, 0.0],
                "rotation_parent_to_child_xyzw": [0.0, 0.0, 0.0, 1.0],
            }
        )


@pytest.mark.parametrize(
    "quaternion",
    [
        [0.0, 0.0, 0.0, 0.0],
        [2.0, 0.0, 0.0, 0.0],
        [math.nan, 0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [1.0, 0.0, 0.0, 0.0, 0.0],
        ["1.0", 0.0, 0.0, 0.0],
    ],
)
def test_rigid_transform_rejects_invalid_quaternions(quaternion: list[object]) -> None:
    with pytest.raises(ValidationError):
        RigidTransform(
            translation_m=[0.0, 0.0, 0.0],
            rotation_parent_to_child_wxyz=quaternion,
        )


@pytest.mark.parametrize(
    "translation",
    [
        [0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0],
        [math.inf, 0.0, 0.0],
        ["0.0", 0.0, 0.0],
    ],
)
def test_rigid_transform_rejects_invalid_translation(translation: list[object]) -> None:
    with pytest.raises(ValidationError):
        RigidTransform(
            translation_m=translation,
            rotation_parent_to_child_wxyz=[1.0, 0.0, 0.0, 0.0],
        )


def test_sensor_axes_accept_explicit_right_handed_non_default_boresight() -> None:
    axes = _right_handed_axes()

    assert axes.boresight == (0.0, 0.0, 1.0)
    assert axes.horizontal == (1.0, 0.0, 0.0)
    assert axes.vertical == (0.0, 1.0, 0.0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"boresight": [0.0, 0.0, 2.0]},
        {"horizontal": [1.0, 1.0, 0.0]},
        {"vertical": [1.0, 0.0, 0.0]},
        {"vertical": [0.0, -1.0, 0.0]},
        {"boresight": [math.nan, 0.0, 1.0]},
        {"horizontal": [1.0, 0.0]},
        {"vertical": ["0.0", 1.0, 0.0]},
    ],
)
def test_sensor_axes_reject_non_unit_non_orthogonal_or_left_handed_axes(
    overrides: dict[str, list[object]],
) -> None:
    data = _right_handed_axes().model_dump()
    data.update(overrides)

    with pytest.raises(ValidationError):
        SensorAxes.model_validate(data)


def test_geometry_models_are_frozen() -> None:
    transform = _identity_transform()
    axes = _right_handed_axes()

    with pytest.raises(ValidationError):
        transform.translation_m = (0.0, 0.0, 0.0)
    with pytest.raises(ValidationError):
        axes.boresight = (1.0, 0.0, 0.0)
```

- [ ] **Step 2: Run the focused test and confirm the missing-module failure**

Run:

```bash
uv run pytest packages/sycasphere-core/tests/test_geometry.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'sycasphere.core.geometry'`.

- [ ] **Step 3: Implement strict finite geometry and tolerance checks**

Create `packages/sycasphere-core/src/sycasphere/core/geometry.py`:

```python
# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : geometry.py
创建者    : Sycamore
创建日期  : 2026-07-21
最后修改  : 2026-07-21
版本号    : v1.0.0

■ 用途说明:
  定义传感器安装刚体变换和显式右手传感器轴边界契约。

■ 主要函数功能:
  - RigidTransform: 验证父坐标系到子坐标系的 SI 平移和 wxyz 旋转。
  - SensorAxes: 验证单位、正交且右手的 SENSOR 坐标轴。

■ 功能特性:
  ✓ 固定四元数顺序和旋转方向。
  ✓ 使用严格有限浮点值并拒绝静默归一化。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-21): 创建安装变换和传感器轴契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math
from typing import Annotated

import numpy as np
from pydantic import AllowInfNan, BaseModel, ConfigDict, Strict, model_validator

type FiniteComponent = Annotated[float, Strict(), AllowInfNan(False)]
type Vector3 = tuple[FiniteComponent, FiniteComponent, FiniteComponent]
type QuaternionWxyz = tuple[
    FiniteComponent,
    FiniteComponent,
    FiniteComponent,
    FiniteComponent,
]

_GEOMETRY_TOLERANCE = 1e-9


def _as_vector(value: Vector3) -> np.ndarray:
    """Return one validated three-component tuple as a float64 array."""
    return np.asarray(value, dtype=np.float64)


# =============================👐Seperate👐==============================
# Immutable installation and sensor-axis geometry
# =============================👐Seperate👐==============================
class RigidTransform(BaseModel):
    """A fixed parent-to-child transform with scalar-first quaternion order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    translation_m: Vector3
    rotation_parent_to_child_wxyz: QuaternionWxyz

    @model_validator(mode="after")
    def validate_unit_quaternion(self) -> RigidTransform:
        """Require a unit wxyz quaternion without silently normalizing it."""
        norm = math.sqrt(sum(component * component for component in self.rotation_parent_to_child_wxyz))
        if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=_GEOMETRY_TOLERANCE):
            raise ValueError("rotation_parent_to_child_wxyz must be a unit quaternion")
        return self


class SensorAxes(BaseModel):
    """Explicit right-handed boresight and image-plane axes in SENSOR coordinates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    boresight: Vector3
    horizontal: Vector3
    vertical: Vector3

    @model_validator(mode="after")
    def validate_right_handed_orthonormal_axes(self) -> SensorAxes:
        """Require unit, pairwise-orthogonal axes with horizontal × vertical = boresight."""
        boresight = _as_vector(self.boresight)
        horizontal = _as_vector(self.horizontal)
        vertical = _as_vector(self.vertical)

        for name, vector in (
            ("boresight", boresight),
            ("horizontal", horizontal),
            ("vertical", vertical),
        ):
            if not math.isclose(
                float(np.linalg.norm(vector)),
                1.0,
                rel_tol=0.0,
                abs_tol=_GEOMETRY_TOLERANCE,
            ):
                raise ValueError(f"{name} must be a unit vector")

        for first, second in (
            (boresight, horizontal),
            (boresight, vertical),
            (horizontal, vertical),
        ):
            if not math.isclose(
                float(np.dot(first, second)),
                0.0,
                rel_tol=0.0,
                abs_tol=_GEOMETRY_TOLERANCE,
            ):
                raise ValueError("sensor axes must be pairwise orthogonal")

        if not np.allclose(
            np.cross(horizontal, vertical),
            boresight,
            rtol=0.0,
            atol=_GEOMETRY_TOLERANCE,
        ):
            raise ValueError("sensor axes must satisfy horizontal × vertical = boresight")
        return self
```

- [ ] **Step 4: Run focused tests, formatting and type checks**

Run:

```bash
uv run pytest packages/sycasphere-core/tests/test_geometry.py -q
uv run ruff format packages/sycasphere-core/src/sycasphere/core/geometry.py packages/sycasphere-core/tests/test_geometry.py
uv run ruff check packages/sycasphere-core/src/sycasphere/core/geometry.py packages/sycasphere-core/tests/test_geometry.py
uv run mypy packages/sycasphere-core/src/sycasphere/core/geometry.py
```

Expected: all commands PASS; formatting may rewrite line wrapping only.

- [ ] **Step 5: Commit geometry contracts**

```bash
git add packages/sycasphere-core/src/sycasphere/core/geometry.py packages/sycasphere-core/tests/test_geometry.py
git commit -m "feat(core): add sensor installation geometry"
```

---

### Task 3: Add WGS84 geodetic ground location

**Files:**

- Modify: `packages/sycasphere-core/src/sycasphere/core/geometry.py`
- Modify: `packages/sycasphere-core/tests/test_geometry.py`

**Interfaces:**

- Consumes: `FrameRef`, `FrameKind.EARTH_FIXED`, `CoordinateRepresentation.GEODETIC`, `ReferenceEllipsoid.WGS84`.
- Produces: `GeodeticLocation(frame, longitude_rad, latitude_rad, ellipsoid_height_m)` for `GroundStationDefinition`.

- [ ] **Step 1: Append failing geodetic-location tests**

Add these imports to `test_geometry.py`:

```python
from sycasphere.core.frames import (
    CoordinateRepresentation,
    EarthFixedFrameSpec,
    FrameKind,
    FrameRef,
    ReferenceEllipsoid,
)
from sycasphere.core.geometry import GeodeticLocation, RigidTransform, SensorAxes
```

Replace the existing single geometry import, then append:

```python

# =============================👐Seperate👐==============================
# WGS84 geodetic-location tests
# =============================👐Seperate👐==============================
def _geodetic_frame() -> FrameRef:
    return FrameRef(
        kind=FrameKind.EARTH_FIXED,
        representation=CoordinateRepresentation.GEODETIC,
        earth_fixed=EarthFixedFrameSpec(
            itrf_realization="ITRF2020",
            iers_conventions="IERS_2010",
            eop_data_id="iers-bulletin-a:2026-07-21",
        ),
        ellipsoid=ReferenceEllipsoid.WGS84,
    )


def test_geodetic_location_accepts_wgs84_and_negative_ellipsoid_height() -> None:
    location = GeodeticLocation(
        frame=_geodetic_frame(),
        longitude_rad=2.03444394,
        latitude_rad=0.69625189,
        ellipsoid_height_m=-20.0,
    )

    assert location.frame.ellipsoid is ReferenceEllipsoid.WGS84
    assert location.ellipsoid_height_m == -20.0


@pytest.mark.parametrize(
    ("longitude_rad", "latitude_rad"),
    [
        (math.pi + 1e-6, 0.0),
        (-math.pi - 1e-6, 0.0),
        (0.0, math.pi / 2 + 1e-6),
        (0.0, -math.pi / 2 - 1e-6),
    ],
)
def test_geodetic_location_rejects_out_of_range_angles(
    longitude_rad: float,
    latitude_rad: float,
) -> None:
    with pytest.raises(ValidationError):
        GeodeticLocation(
            frame=_geodetic_frame(),
            longitude_rad=longitude_rad,
            latitude_rad=latitude_rad,
            ellipsoid_height_m=0.0,
        )


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_geodetic_location_rejects_non_finite_height(invalid: float) -> None:
    with pytest.raises(ValidationError):
        GeodeticLocation(
            frame=_geodetic_frame(),
            longitude_rad=0.0,
            latitude_rad=0.0,
            ellipsoid_height_m=invalid,
        )


def test_geodetic_location_rejects_non_geodetic_or_non_wgs84_frame() -> None:
    with pytest.raises(ValidationError):
        GeodeticLocation(
            frame=FrameRef(kind=FrameKind.J2000),
            longitude_rad=0.0,
            latitude_rad=0.0,
            ellipsoid_height_m=0.0,
        )


def test_geodetic_location_rejects_string_number_coercion() -> None:
    with pytest.raises(ValidationError):
        GeodeticLocation(
            frame=_geodetic_frame(),
            longitude_rad="2.0",
            latitude_rad=0.0,
            ellipsoid_height_m=0.0,
        )


def test_geodetic_location_round_trips_and_is_frozen() -> None:
    location = GeodeticLocation(
        frame=_geodetic_frame(),
        longitude_rad=1.0,
        latitude_rad=0.5,
        ellipsoid_height_m=100.0,
    )
    restored = GeodeticLocation.model_validate(location.model_dump(mode="json"))

    assert restored == location
    with pytest.raises(ValidationError):
        location.longitude_rad = 0.0
```

- [ ] **Step 2: Run focused tests and confirm the missing-symbol failure**

Run:

```bash
uv run pytest packages/sycasphere-core/tests/test_geometry.py -q
```

Expected: FAIL during collection because `GeodeticLocation` is not defined in `sycasphere.core.geometry`.

- [ ] **Step 3: Implement GeodeticLocation in geometry.py**

Add these imports:

```python
from pydantic import AllowInfNan, BaseModel, ConfigDict, Field, Strict, model_validator
from sycasphere.core.frames import (
    CoordinateRepresentation,
    FrameKind,
    FrameRef,
    ReferenceEllipsoid,
)
```

Append the following class after `SensorAxes`, and update the file header to version `v1.1.0` with a matching update-log entry:

```python

class GeodeticLocation(BaseModel):
    """A validated WGS84 location in an explicitly versioned Earth-fixed frame."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    frame: FrameRef
    longitude_rad: FiniteComponent = Field(ge=-math.pi, le=math.pi)
    latitude_rad: FiniteComponent = Field(ge=-math.pi / 2, le=math.pi / 2)
    ellipsoid_height_m: FiniteComponent

    @model_validator(mode="after")
    def validate_wgs84_geodetic_frame(self) -> GeodeticLocation:
        """Require EARTH_FIXED/GEODETIC with the WGS84 reference ellipsoid."""
        if (
            self.frame.kind is not FrameKind.EARTH_FIXED
            or self.frame.representation is not CoordinateRepresentation.GEODETIC
            or self.frame.ellipsoid is not ReferenceEllipsoid.WGS84
        ):
            raise ValueError(
                "GeodeticLocation requires an EARTH_FIXED GEODETIC WGS84 frame"
            )
        return self
```

- [ ] **Step 4: Run focused tests and Core regression tests**

Run:

```bash
uv run pytest packages/sycasphere-core/tests/test_geometry.py packages/sycasphere-core/tests/test_frames.py -q
uv run ruff format packages/sycasphere-core/src/sycasphere/core/geometry.py packages/sycasphere-core/tests/test_geometry.py
uv run ruff check packages/sycasphere-core/src/sycasphere/core/geometry.py packages/sycasphere-core/tests/test_geometry.py
uv run mypy packages/sycasphere-core/src/sycasphere/core/geometry.py
```

Expected: all commands PASS.

- [ ] **Step 5: Commit the geodetic location contract**

```bash
git add packages/sycasphere-core/src/sycasphere/core/geometry.py packages/sycasphere-core/tests/test_geometry.py
git commit -m "feat(core): add WGS84 geodetic locations"
```

---

### Task 4: Add SensorDefinition composition contract

**Files:**

- Create: `packages/sycasphere-core/src/sycasphere/core/_definitions.py`
- Create: `packages/sycasphere-core/src/sycasphere/core/sensors.py`
- Create: `packages/sycasphere-core/tests/test_sensors.py`

**Interfaces:**

- Consumes: `ModelRef`, `RigidTransform`, `SensorAxes`, `SchemaVersion`, shared immutable JSON helpers.
- Produces: private `_DefinitionBase` for shared definition metadata, plus public `SensorType` and `SensorDefinition` for nested entity composition.

- [ ] **Step 1: Write failing SensorDefinition tests**

Create `packages/sycasphere-core/tests/test_sensors.py`:

```python
# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_sensors.py
创建者    : Sycamore
创建日期  : 2026-07-21
最后修改  : 2026-07-21
版本号    : v1.0.0

■ 用途说明:
  验证传感器定义的嵌套组件、模型引用、不可变性和无独立轨道边界。

■ 主要函数功能:
  - 传感器组成验证: 验证安装、轴、模型和元数据。
  - 模型集合验证: 验证必填测量模型和唯一模型 ID。

■ 功能特性:
  ✓ 覆盖四种首版传感器类型。
  ✓ 拒绝独立状态、重复模型和可变输入别名。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-21): 创建 SensorDefinition 契约测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from sycasphere.core.geometry import RigidTransform, SensorAxes
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.schema import SchemaVersion
from sycasphere.core.sensors import SensorDefinition, SensorType

# =============================👐Seperate👐==============================
# SensorDefinition contract tests
# =============================👐Seperate👐==============================
def _model(model_id: str) -> ModelRef:
    return ModelRef(
        model_id=model_id,
        interface_version=SchemaVersion(major=1, minor=0),
        configuration={},
    )


def _sensor() -> SensorDefinition:
    return SensorDefinition(
        id="optical-sensor-1",
        name="Optical Sensor 1",
        revision=1,
        schema_version=SchemaVersion(major=1, minor=0),
        tags=["optical", "ssa"],
        metadata={"manufacturer": "Sycamore", "bands": ["visible"]},
        sensor_type=SensorType.OPTICAL,
        mount_transform=RigidTransform(
            translation_m=[1.0, 0.0, 0.0],
            rotation_parent_to_child_wxyz=[1.0, 0.0, 0.0, 0.0],
        ),
        axes=SensorAxes(
            boresight=[1.0, 0.0, 0.0],
            horizontal=[0.0, 1.0, 0.0],
            vertical=[0.0, 0.0, 1.0],
        ),
        pointing_model=_model("sycasphere.pointing.fixed"),
        field_of_view_model=_model("sycasphere.fov.conical"),
        visibility_model=_model("sycasphere.visibility.basic"),
        measurement_models=[_model("sycasphere.measurement.angles_ra_dec")],
        error_profiles=[_model("sycasphere.error.optical_default")],
        availability_model=None,
    )


def test_sensor_exposes_strong_structure_and_data_only_models() -> None:
    sensor = _sensor()

    assert sensor.sensor_type is SensorType.OPTICAL
    assert sensor.axes.boresight == (1.0, 0.0, 0.0)
    assert sensor.measurement_models[0].model_id == "sycasphere.measurement.angles_ra_dec"
    assert sensor.availability_model is None


def test_sensor_type_contains_only_approved_values() -> None:
    assert {item.value for item in SensorType} == {"OPTICAL", "RADAR", "RADIO", "CUSTOM"}


def test_sensor_requires_at_least_one_measurement_model() -> None:
    data = _sensor().model_dump(mode="python")
    data["measurement_models"] = []

    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(data)


@pytest.mark.parametrize(
    "required_field",
    ["pointing_model", "field_of_view_model", "visibility_model", "measurement_models"],
)
def test_sensor_requires_each_scientific_model_component(required_field: str) -> None:
    data = _sensor().model_dump(mode="json")
    del data[required_field]

    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(data)


@pytest.mark.parametrize("field_name", ["measurement_models", "error_profiles"])
def test_sensor_rejects_duplicate_model_ids(field_name: str) -> None:
    data = _sensor().model_dump(mode="python")
    model = _model("duplicate.model")
    data[field_name] = [model, model]

    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(data)


def test_sensor_rejects_independent_orbit_and_state_fields() -> None:
    data = _sensor().model_dump(mode="json")
    data["initial_state"] = {
        "position_m": [0.0, 0.0, 0.0],
        "velocity_mps": [0.0, 0.0, 0.0],
    }

    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(data)


def test_sensor_deeply_freezes_metadata_and_isolates_input_aliases() -> None:
    metadata = {"calibration": {"coefficients": [1.0, 2.0]}}
    data = _sensor().model_dump(mode="python")
    data["metadata"] = metadata
    sensor = SensorDefinition.model_validate(data)

    metadata["calibration"]["coefficients"].append(3.0)

    assert sensor.metadata["calibration"]["coefficients"] == (1.0, 2.0)
    with pytest.raises(TypeError):
        sensor.metadata["calibration"]["coefficients"][0] = 0.0


@pytest.mark.parametrize("tags", [["ssa", " ssa "], [" "]])
def test_sensor_rejects_blank_or_duplicate_tags(tags: list[str]) -> None:
    data = _sensor().model_dump(mode="python")
    data["tags"] = tags

    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(data)


@pytest.mark.parametrize("revision", [0, -1, "1", True])
def test_sensor_revision_is_a_strict_positive_integer(revision: object) -> None:
    data = _sensor().model_dump(mode="python")
    data["revision"] = revision

    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(data)


@pytest.mark.parametrize(("field_name", "value"), [("id", " "), ("name", "")])
def test_sensor_requires_non_blank_identity_fields(field_name: str, value: str) -> None:
    data = _sensor().model_dump(mode="python")
    data[field_name] = value

    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(data)


def test_sensor_rejects_non_finite_metadata_and_freezes_default_metadata() -> None:
    data = _sensor().model_dump(mode="python")
    data["metadata"] = {"calibration": math.nan}
    with pytest.raises(ValidationError):
        SensorDefinition.model_validate(data)

    default_data = _sensor().model_dump(mode="python")
    del default_data["metadata"]
    default_sensor = SensorDefinition.model_validate(default_data)
    with pytest.raises(TypeError):
        default_sensor.metadata["changed"] = True


def test_sensor_serializes_sets_and_nested_json_deterministically() -> None:
    sensor = _sensor()
    serialized = sensor.model_dump(mode="json")
    restored = SensorDefinition.model_validate(serialized)

    assert serialized["tags"] == ["optical", "ssa"]
    assert serialized["metadata"] == {
        "bands": ["visible"],
        "manufacturer": "Sycamore",
    }
    assert restored == sensor


def test_sensor_is_frozen_and_rejects_unknown_fields() -> None:
    sensor = _sensor()

    with pytest.raises(ValidationError):
        sensor.name = "Changed"
    with pytest.raises(ValidationError):
        SensorDefinition.model_validate({**sensor.model_dump(mode="json"), "mission_role": "PRIMARY"})
```

- [ ] **Step 2: Run the focused test and confirm the missing-module failure**

Run:

```bash
uv run pytest packages/sycasphere-core/tests/test_sensors.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'sycasphere.core.sensors'`.

- [ ] **Step 3: Implement SensorDefinition**

Create `packages/sycasphere-core/src/sycasphere/core/_definitions.py`:

```python
# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : _definitions.py
创建者    : Sycamore
创建日期  : 2026-07-22
最后修改  : 2026-07-22
版本号    : v1.0.0

■ 用途说明:
  为 Core 内部定义对象集中提供身份、修订、标签和不可变 metadata 验证。

■ 主要函数功能:
  - _normalize_unique_strings: 规范化非空、唯一字符串集合。
  - _DefinitionBase: 保存定义对象共享字段并深度冻结 metadata。

■ 功能特性:
  ✓ 修订号使用严格正整数。
  ✓ 默认和显式 metadata 均深度冻结且稳定序列化。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-22): 创建 Core 私有共享定义验证。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    Strict,
    StringConstraints,
    field_serializer,
    field_validator,
)
from sycasphere.core._json import (
    FrozenJsonValue,
    freeze_json_object,
    normalize_json_object,
    thaw_json_value,
)
from sycasphere.core.schema import SchemaVersion

type DefinitionString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
type Revision = Annotated[int, Strict(), Field(gt=0)]


def _normalize_unique_strings(value: Any, field_name: str) -> tuple[str, ...]:
    """Return stripped unique non-blank strings from a collection input."""
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError(f"{field_name} must be a collection of strings")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must contain only strings")
    normalized = tuple(item.strip() for item in value)
    if any(not item for item in normalized):
        raise ValueError(f"{field_name} must not contain blank values")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


# =============================👐Seperate👐==============================
# Private immutable definition base
# =============================👐Seperate👐==============================
class _DefinitionBase(BaseModel):
    """Shared immutable fields for versioned Core definition objects."""

    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)

    id: DefinitionString
    name: DefinitionString
    revision: Revision
    schema_version: SchemaVersion
    tags: frozenset[str] = Field(default_factory=frozenset)
    metadata: Mapping[str, JsonValue] = Field(default_factory=dict)

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: Any) -> tuple[str, ...]:
        return _normalize_unique_strings(value, "tags")

    @field_serializer("tags", when_used="always")
    def serialize_tags(self, value: frozenset[str]) -> list[str]:
        return sorted(value)

    @field_validator("metadata", mode="before")
    @classmethod
    def normalize_metadata(cls, value: Any) -> dict[str, JsonValue]:
        return normalize_json_object(value)

    @field_validator("metadata")
    @classmethod
    def freeze_metadata(cls, value: Mapping[str, JsonValue]) -> Mapping[str, FrozenJsonValue]:
        return freeze_json_object(value)

    @field_serializer("metadata", when_used="always")
    def serialize_metadata(self, value: Mapping[str, FrozenJsonValue]) -> dict[str, JsonValue]:
        return {key: thaw_json_value(nested) for key, nested in value.items()}
```

Create `packages/sycasphere-core/src/sycasphere/core/sensors.py`:

```python
# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : sensors.py
创建者    : Sycamore
创建日期  : 2026-07-21
最后修改  : 2026-07-21
版本号    : v1.0.0

■ 用途说明:
  定义依附于父平台、无独立轨道且科学子模型可插拔的传感器契约。

■ 主要函数功能:
  - SensorType: 声明首版传感器类别。
  - SensorDefinition: 验证安装、轴、模型引用和不可变定义元数据。

■ 功能特性:
  ✓ 强制至少一个测量模型并拒绝重复模型 ID。
  ✓ 深度冻结非控制性 metadata 且稳定序列化标签。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-21): 创建传感器定义契约。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import field_validator
from sycasphere.core._definitions import _DefinitionBase
from sycasphere.core.geometry import RigidTransform, SensorAxes
from sycasphere.core.model_refs import ModelRef


def _require_unique_model_ids(values: tuple[ModelRef, ...], field_name: str) -> tuple[ModelRef, ...]:
    """Reject ambiguous duplicate model identities in one configured collection."""
    model_ids = tuple(value.model_id for value in values)
    if len(model_ids) != len(set(model_ids)):
        raise ValueError(f"{field_name} must contain unique model_id values")
    return values


# =============================👐Seperate👐==============================
# Immutable sensor definitions
# =============================👐Seperate👐==============================
class SensorType(StrEnum):
    """Supported first-version physical sensor categories."""

    OPTICAL = "OPTICAL"
    RADAR = "RADAR"
    RADIO = "RADIO"
    CUSTOM = "CUSTOM"


class SensorDefinition(_DefinitionBase):
    """A sensor child component whose state is derived from its parent platform."""

    sensor_type: SensorType
    mount_transform: RigidTransform
    axes: SensorAxes
    pointing_model: ModelRef
    field_of_view_model: ModelRef
    visibility_model: ModelRef
    measurement_models: tuple[ModelRef, ...]
    error_profiles: tuple[ModelRef, ...] = ()
    availability_model: ModelRef | None = None

    @field_validator("measurement_models")
    @classmethod
    def validate_measurement_models(cls, value: tuple[ModelRef, ...]) -> tuple[ModelRef, ...]:
        if not value:
            raise ValueError("measurement_models must not be empty")
        return _require_unique_model_ids(value, "measurement_models")

    @field_validator("error_profiles")
    @classmethod
    def validate_error_profiles(cls, value: tuple[ModelRef, ...]) -> tuple[ModelRef, ...]:
        return _require_unique_model_ids(value, "error_profiles")
```

- [ ] **Step 4: Run focused tests and static checks**

Run:

```bash
uv run pytest packages/sycasphere-core/tests/test_sensors.py packages/sycasphere-core/tests/test_model_refs.py packages/sycasphere-core/tests/test_geometry.py -q
uv run ruff format packages/sycasphere-core/src/sycasphere/core/_definitions.py packages/sycasphere-core/src/sycasphere/core/sensors.py packages/sycasphere-core/tests/test_sensors.py
uv run ruff check packages/sycasphere-core/src/sycasphere/core/_definitions.py packages/sycasphere-core/src/sycasphere/core/sensors.py packages/sycasphere-core/tests/test_sensors.py
uv run mypy packages/sycasphere-core/src/sycasphere/core/_definitions.py packages/sycasphere-core/src/sycasphere/core/sensors.py
```

Expected: all commands PASS.

- [ ] **Step 5: Commit the sensor contract**

```bash
git add packages/sycasphere-core/src/sycasphere/core/_definitions.py packages/sycasphere-core/src/sycasphere/core/sensors.py packages/sycasphere-core/tests/test_sensors.py
git commit -m "feat(core): define sensor components"
```

---

### Task 5: Add the discriminated physical entity hierarchy

**Files:**

- Create: `packages/sycasphere-core/src/sycasphere/core/entities.py`
- Create: `packages/sycasphere-core/tests/test_entities.py`

**Interfaces:**

- Consumes: private `_DefinitionBase`, `CartesianState`, `GeodeticLocation`, `ModelRef`, `SensorDefinition`, `SchemaVersion`.
- Produces: `EntityType`, `SpaceObjectPhysicalProperties`, `SpacecraftDefinition`, `OtherSpaceObjectDefinition`, `GroundStationDefinition`, and discriminated `EntityDefinition`.

- [ ] **Step 1: Write failing entity hierarchy tests**

Create `packages/sycasphere-core/tests/test_entities.py`:

```python
# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : test_entities.py
创建者    : Sycamore
创建日期  : 2026-07-21
最后修改  : 2026-07-21
版本号    : v1.0.0

■ 用途说明:
  验证航天器、其他空间对象和地面站的判别联合与传感器组合边界。

■ 主要函数功能:
  - 实体类型验证: 验证三种具体实体和物理参数。
  - 组合验证: 验证传感器父子关系、唯一 ID 和任务角色隔离。

■ 功能特性:
  ✓ 覆盖空间对象初始状态和地面站 WGS84 位置。
  ✓ 覆盖不可变 metadata、capabilities 和 JSON 联合往返。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-21): 创建实体层级契约测试。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

import math

import pytest
from pydantic import TypeAdapter, ValidationError
from sycasphere.core.entities import (
    EntityDefinition,
    EntityType,
    GroundStationDefinition,
    OtherSpaceObjectDefinition,
    SpaceObjectPhysicalProperties,
    SpacecraftDefinition,
)
from sycasphere.core.epoch import Epoch, TimeScale
from sycasphere.core.frames import (
    CoordinateRepresentation,
    EarthFixedFrameSpec,
    FrameKind,
    FrameRef,
    ReferenceEllipsoid,
)
from sycasphere.core.geometry import GeodeticLocation, RigidTransform, SensorAxes
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.schema import SchemaVersion
from sycasphere.core.sensors import SensorDefinition, SensorType
from sycasphere.core.states import CartesianState

_ENTITY_ADAPTER = TypeAdapter(EntityDefinition)


# =============================👐Seperate👐==============================
# Entity fixtures
# =============================👐Seperate👐==============================
def _model(model_id: str) -> ModelRef:
    return ModelRef(
        model_id=model_id,
        interface_version=SchemaVersion(major=1, minor=0),
        configuration={},
    )


def _sensor(sensor_id: str = "sensor-1") -> SensorDefinition:
    return SensorDefinition(
        id=sensor_id,
        name=sensor_id,
        revision=1,
        schema_version=SchemaVersion(major=1, minor=0),
        sensor_type=SensorType.OPTICAL,
        mount_transform=RigidTransform(
            translation_m=[0.0, 0.0, 0.0],
            rotation_parent_to_child_wxyz=[1.0, 0.0, 0.0, 0.0],
        ),
        axes=SensorAxes(
            boresight=[0.0, 0.0, 1.0],
            horizontal=[1.0, 0.0, 0.0],
            vertical=[0.0, 1.0, 0.0],
        ),
        pointing_model=_model("sycasphere.pointing.fixed"),
        field_of_view_model=_model("sycasphere.fov.conical"),
        visibility_model=_model("sycasphere.visibility.basic"),
        measurement_models=[_model("sycasphere.measurement.angles_ra_dec")],
    )


def _state() -> CartesianState:
    return CartesianState(
        epoch=Epoch(value="2026-07-21T00:00:00Z", time_scale=TimeScale.UTC),
        frame=FrameRef(kind=FrameKind.J2000),
        position_m=[7_000_000.0, 0.0, 0.0],
        velocity_mps=[0.0, 7_500.0, 0.0],
    )


def _properties() -> SpaceObjectPhysicalProperties:
    return SpaceObjectPhysicalProperties(
        mass_kg=1_000.0,
        cross_section_area_m2=12.0,
        drag_coefficient=2.2,
        solar_radiation_pressure_coefficient=1.3,
    )


def _location() -> GeodeticLocation:
    return GeodeticLocation(
        frame=FrameRef(
            kind=FrameKind.EARTH_FIXED,
            representation=CoordinateRepresentation.GEODETIC,
            earth_fixed=EarthFixedFrameSpec(
                itrf_realization="ITRF2020",
                iers_conventions="IERS_2010",
                eop_data_id="iers-bulletin-a:2026-07-21",
            ),
            ellipsoid=ReferenceEllipsoid.WGS84,
        ),
        longitude_rad=2.0,
        latitude_rad=0.5,
        ellipsoid_height_m=50.0,
    )


def _spacecraft() -> SpacecraftDefinition:
    return SpacecraftDefinition(
        id="spacecraft-1",
        name="Observer",
        revision=1,
        schema_version=SchemaVersion(major=1, minor=0),
        tags=["observer"],
        metadata={"programme": {"name": "demo"}},
        capabilities=["sensor_host", "maneuverable"],
        initial_state=_state(),
        physical_properties=_properties(),
        dynamics_model=_model("sycasphere.dynamics.numerical"),
        attitude_model=_model("sycasphere.attitude.nadir"),
        sensors=[_sensor()],
    )


# =============================👐Seperate👐==============================
# Entity hierarchy tests
# =============================👐Seperate👐==============================
def test_entity_type_contains_only_three_physical_entity_kinds() -> None:
    assert {item.value for item in EntityType} == {
        "SPACECRAFT",
        "OTHER_SPACE_OBJECT",
        "GROUND_STATION",
    }


def test_spacecraft_composes_state_physics_models_and_sensors() -> None:
    spacecraft = _spacecraft()

    assert spacecraft.entity_type is EntityType.SPACECRAFT
    assert spacecraft.sensors[0].id == "sensor-1"
    assert spacecraft.initial_state.frame.kind is FrameKind.J2000


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("id", " "),
        ("name", ""),
        ("revision", 0),
        ("revision", -1),
        ("revision", "1"),
        ("revision", True),
        ("tags", ["observer", " observer "]),
        ("capabilities", ["sensor_host", " sensor_host "]),
    ],
)
def test_entity_common_fields_reject_blank_duplicate_or_non_strict_values(
    field_name: str,
    value: object,
) -> None:
    data = _spacecraft().model_dump(mode="python")
    data[field_name] = value

    with pytest.raises(ValidationError):
        SpacecraftDefinition.model_validate(data)


def test_other_space_object_has_no_sensor_field() -> None:
    other = OtherSpaceObjectDefinition(
        id="debris-1",
        name="Debris",
        revision=1,
        schema_version=SchemaVersion(major=1, minor=0),
        initial_state=_state(),
        physical_properties=_properties(),
        dynamics_model=_model("sycasphere.dynamics.numerical"),
        attitude_model=_model("sycasphere.attitude.tumbling"),
    )

    assert other.entity_type is EntityType.OTHER_SPACE_OBJECT
    with pytest.raises(ValidationError):
        OtherSpaceObjectDefinition.model_validate(
            {**other.model_dump(mode="json"), "sensors": [_sensor().model_dump(mode="json")]}
        )


def test_ground_station_uses_wgs84_location_and_nested_sensors() -> None:
    station = GroundStationDefinition(
        id="ground-station-1",
        name="Ground Station",
        revision=1,
        schema_version=SchemaVersion(major=1, minor=0),
        capabilities=["sensor_host"],
        location=_location(),
        body_axes_convention="NED_RH",
        environment_models=[_model("sycasphere.environment.standard")],
        sensors=[_sensor("ground-optical-1")],
    )

    assert station.entity_type is EntityType.GROUND_STATION
    assert station.location.frame.ellipsoid is ReferenceEllipsoid.WGS84
    assert station.sensors[0].id == "ground-optical-1"


def test_parent_entity_rejects_duplicate_sensor_ids() -> None:
    data = _spacecraft().model_dump(mode="python")
    data["sensors"] = [_sensor("duplicate"), _sensor("duplicate")]

    with pytest.raises(ValidationError):
        SpacecraftDefinition.model_validate(data)


def test_ground_station_rejects_duplicate_environment_model_ids() -> None:
    model = _model("duplicate.environment")

    with pytest.raises(ValidationError):
        GroundStationDefinition(
            id="ground-station-1",
            name="Ground Station",
            revision=1,
            schema_version=SchemaVersion(major=1, minor=0),
            location=_location(),
            body_axes_convention="NED_RH",
            environment_models=[model, model],
        )


def test_ground_station_rejects_duplicate_sensor_ids_and_independent_state() -> None:
    station = GroundStationDefinition(
        id="ground-station-1",
        name="Ground Station",
        revision=1,
        schema_version=SchemaVersion(major=1, minor=0),
        location=_location(),
        body_axes_convention="NED_RH",
        sensors=[_sensor("duplicate")],
    )
    duplicate_data = station.model_dump(mode="python")
    duplicate_data["sensors"] = [_sensor("duplicate"), _sensor("duplicate")]
    with pytest.raises(ValidationError):
        GroundStationDefinition.model_validate(duplicate_data)

    state_data = station.model_dump(mode="json")
    state_data["initial_state"] = _state().model_dump(mode="json")
    with pytest.raises(ValidationError):
        GroundStationDefinition.model_validate(state_data)


@pytest.mark.parametrize(
    ("field_name", "invalid"),
    [
        ("mass_kg", 0.0),
        ("mass_kg", -1.0),
        ("mass_kg", math.nan),
        ("mass_kg", math.inf),
        ("mass_kg", "1000.0"),
        ("cross_section_area_m2", 0.0),
        ("cross_section_area_m2", -1.0),
        ("drag_coefficient", -0.1),
        ("solar_radiation_pressure_coefficient", -0.1),
    ],
)
def test_space_object_physical_properties_reject_invalid_values(
    field_name: str,
    invalid: object,
) -> None:
    data = _properties().model_dump()
    data[field_name] = invalid

    with pytest.raises(ValidationError):
        SpaceObjectPhysicalProperties.model_validate(data)


def test_physical_coefficients_can_be_zero_or_missing() -> None:
    properties = SpaceObjectPhysicalProperties(
        mass_kg=1.0,
        cross_section_area_m2=1.0,
        drag_coefficient=0.0,
        solar_radiation_pressure_coefficient=None,
    )

    assert properties.drag_coefficient == 0.0
    assert properties.solar_radiation_pressure_coefficient is None


@pytest.mark.parametrize("role_field", ["target_role", "mission_role", "primary_sensor"])
def test_entities_reject_fixed_task_role_fields(role_field: str) -> None:
    data = _spacecraft().model_dump(mode="json")
    data[role_field] = "TRACKING_TARGET"

    with pytest.raises(ValidationError):
        SpacecraftDefinition.model_validate(data)


def test_entity_metadata_capabilities_and_tags_are_deeply_immutable() -> None:
    metadata = {"programme": {"members": ["a"]}}
    capabilities = ["sensor_host"]
    data = _spacecraft().model_dump(mode="python")
    data["metadata"] = metadata
    data["capabilities"] = capabilities
    entity = SpacecraftDefinition.model_validate(data)

    metadata["programme"]["members"].append("b")
    capabilities.append("changed")

    assert entity.metadata["programme"]["members"] == ("a",)
    assert entity.capabilities == frozenset({"sensor_host"})

    default_data = _spacecraft().model_dump(mode="python")
    del default_data["metadata"]
    default_entity = SpacecraftDefinition.model_validate(default_data)
    with pytest.raises(TypeError):
        default_entity.metadata["changed"] = True


def test_entity_definition_discriminates_and_round_trips_all_concrete_types() -> None:
    entities = (
        _spacecraft(),
        OtherSpaceObjectDefinition(
            id="debris-1",
            name="Debris",
            revision=1,
            schema_version=SchemaVersion(major=1, minor=0),
            initial_state=_state(),
            physical_properties=_properties(),
            dynamics_model=_model("sycasphere.dynamics.numerical"),
            attitude_model=_model("sycasphere.attitude.tumbling"),
        ),
        GroundStationDefinition(
            id="ground-station-1",
            name="Ground Station",
            revision=1,
            schema_version=SchemaVersion(major=1, minor=0),
            location=_location(),
            body_axes_convention="NED_RH",
            sensors=[_sensor("ground-optical-1")],
        ),
    )

    for entity in entities:
        serialized = _ENTITY_ADAPTER.dump_python(entity, mode="json")
        restored = _ENTITY_ADAPTER.validate_python(serialized)
        assert type(restored) is type(entity)
        assert restored == entity


def test_entities_are_frozen() -> None:
    entity = _spacecraft()

    with pytest.raises(ValidationError):
        entity.name = "Changed"
```

- [ ] **Step 2: Run the focused test and confirm the missing-module failure**

Run:

```bash
uv run pytest packages/sycasphere-core/tests/test_entities.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'sycasphere.core.entities'`.

- [ ] **Step 3: Implement concrete entities and the discriminated union**

Create `packages/sycasphere-core/src/sycasphere/core/entities.py`:

```python
# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : entities.py
创建者    : Sycamore
创建日期  : 2026-07-21
最后修改  : 2026-07-21
版本号    : v1.0.0

■ 用途说明:
  定义航天器、其他空间对象和地面站的物理实体层级与传感器组合关系。

■ 主要函数功能:
  - SpaceObjectPhysicalProperties: 验证空间对象 SI 物理参数。
  - EntityDefinition: 以 entity_type 判别三个具体实体模型。

■ 功能特性:
  ✓ 传感器只嵌套在航天器或地面站内。
  ✓ 实体保存物理能力但拒绝固定任务角色。

■ 待办事项:
  - 无

■ 更新日志:
  v1.0.0 (2026-07-21): 创建物理实体定义层级。

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    AllowInfNan,
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    field_serializer,
    field_validator,
)
from sycasphere.core._definitions import (
    DefinitionString,
    _DefinitionBase,
    _normalize_unique_strings,
)
from sycasphere.core.geometry import GeodeticLocation
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.sensors import SensorDefinition
from sycasphere.core.states import CartesianState

type PositiveFiniteFloat = Annotated[
    float,
    Strict(),
    AllowInfNan(False),
    Field(gt=0.0),
]
type NonNegativeFiniteFloat = Annotated[
    float,
    Strict(),
    AllowInfNan(False),
    Field(ge=0.0),
]


def _require_unique_sensor_ids(
    values: tuple[SensorDefinition, ...],
) -> tuple[SensorDefinition, ...]:
    """Reject duplicate sensor IDs within one parent entity."""
    identifiers = tuple(value.id for value in values)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("sensors must contain unique id values")
    return values


def _require_unique_model_ids(values: tuple[ModelRef, ...]) -> tuple[ModelRef, ...]:
    """Reject duplicate model IDs within one entity model collection."""
    identifiers = tuple(value.model_id for value in values)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("environment_models must contain unique model_id values")
    return values


# =============================👐Seperate👐==============================
# Shared entity metadata and physical properties
# =============================👐Seperate👐==============================
class EntityType(StrEnum):
    """Supported physical entity kinds."""

    SPACECRAFT = "SPACECRAFT"
    OTHER_SPACE_OBJECT = "OTHER_SPACE_OBJECT"
    GROUND_STATION = "GROUND_STATION"


class SpaceObjectPhysicalProperties(BaseModel):
    """Validated SI physical parameters for a propagated space object."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mass_kg: PositiveFiniteFloat
    cross_section_area_m2: PositiveFiniteFloat
    drag_coefficient: NonNegativeFiniteFloat | None = None
    solar_radiation_pressure_coefficient: NonNegativeFiniteFloat | None = None


class _EntityDefinitionBase(_DefinitionBase):
    """Shared immutable identity and non-controlling metadata for physical entities."""

    capabilities: frozenset[str] = Field(default_factory=frozenset)

    @field_validator("capabilities", mode="before")
    @classmethod
    def normalize_capabilities(cls, value: Any) -> tuple[str, ...]:
        return _normalize_unique_strings(value, "capabilities")

    @field_serializer("capabilities", when_used="always")
    def serialize_capabilities(self, value: frozenset[str]) -> list[str]:
        return sorted(value)


# =============================👐Seperate👐==============================
# Concrete entity definitions and discriminated public union
# =============================👐Seperate👐==============================
class SpacecraftDefinition(_EntityDefinitionBase):
    """A propagated spacecraft that may host sensor child components."""

    entity_type: Literal[EntityType.SPACECRAFT] = EntityType.SPACECRAFT
    initial_state: CartesianState
    physical_properties: SpaceObjectPhysicalProperties
    dynamics_model: ModelRef
    attitude_model: ModelRef
    sensors: tuple[SensorDefinition, ...] = ()

    @field_validator("sensors")
    @classmethod
    def validate_unique_sensor_ids(
        cls, value: tuple[SensorDefinition, ...]
    ) -> tuple[SensorDefinition, ...]:
        return _require_unique_sensor_ids(value)


class OtherSpaceObjectDefinition(_EntityDefinitionBase):
    """A propagated non-spacecraft object that cannot host sensors."""

    entity_type: Literal[EntityType.OTHER_SPACE_OBJECT] = EntityType.OTHER_SPACE_OBJECT
    initial_state: CartesianState
    physical_properties: SpaceObjectPhysicalProperties
    dynamics_model: ModelRef
    attitude_model: ModelRef


class GroundStationDefinition(_EntityDefinitionBase):
    """A WGS84 ground site that may host sensor child components."""

    entity_type: Literal[EntityType.GROUND_STATION] = EntityType.GROUND_STATION
    location: GeodeticLocation
    body_axes_convention: DefinitionString
    environment_models: tuple[ModelRef, ...] = ()
    availability_model: ModelRef | None = None
    sensors: tuple[SensorDefinition, ...] = ()

    @field_validator("environment_models")
    @classmethod
    def validate_unique_environment_model_ids(
        cls, value: tuple[ModelRef, ...]
    ) -> tuple[ModelRef, ...]:
        return _require_unique_model_ids(value)

    @field_validator("sensors")
    @classmethod
    def validate_unique_sensor_ids(
        cls, value: tuple[SensorDefinition, ...]
    ) -> tuple[SensorDefinition, ...]:
        return _require_unique_sensor_ids(value)


type EntityDefinition = Annotated[
    SpacecraftDefinition | OtherSpaceObjectDefinition | GroundStationDefinition,
    Field(discriminator="entity_type"),
]
```

- [ ] **Step 4: Run focused and upstream tests**

Run:

```bash
uv run pytest packages/sycasphere-core/tests/test_entities.py packages/sycasphere-core/tests/test_sensors.py packages/sycasphere-core/tests/test_states.py -q
uv run ruff format packages/sycasphere-core/src/sycasphere/core/entities.py packages/sycasphere-core/tests/test_entities.py
uv run ruff check packages/sycasphere-core/src/sycasphere/core/entities.py packages/sycasphere-core/tests/test_entities.py
uv run mypy packages/sycasphere-core/src/sycasphere/core/entities.py
```

Expected: all commands PASS with strict mypy settings unchanged.

- [ ] **Step 5: Commit the entity hierarchy**

```bash
git add packages/sycasphere-core/src/sycasphere/core/entities.py packages/sycasphere-core/tests/test_entities.py
git commit -m "feat(core): define physical entity hierarchy"
```

---

### Task 6: Publish schemas, document examples, and verify package isolation

**Files:**

- Modify: `packages/sycasphere-core/src/sycasphere/core/__init__.py`
- Modify: `packages/sycasphere-core/tests/test_public_api.py`
- Modify: `packages/sycasphere-core/tests/snapshots/core-schemas.json`
- Modify: `packages/sycasphere-core/README.md`

**Interfaces:**

- Consumes: all models from Tasks 1–5.
- Produces: exact reviewed `sycasphere.core` public import surface, deterministic JSON Schema snapshot, and executable construction examples.

- [ ] **Step 1: Expand the public API test before exporting symbols**

Update `EXPECTED_PUBLIC_CONTRACTS` in `test_public_api.py` to this exact set:

```python
EXPECTED_PUBLIC_CONTRACTS = {
    "CartesianState",
    "CoordinateRepresentation",
    "EarthFixedFrameSpec",
    "EntityDefinition",
    "EntityType",
    "Epoch",
    "ErrorCategory",
    "ErrorDetail",
    "FrameKind",
    "FrameRef",
    "GeodeticLocation",
    "GroundStationDefinition",
    "ModelRef",
    "OtherSpaceObjectDefinition",
    "PluginKind",
    "PluginManifest",
    "PluginRef",
    "ReferenceEllipsoid",
    "ResourceRequirements",
    "RigidTransform",
    "SchemaVersion",
    "SensorAxes",
    "SensorDefinition",
    "SensorType",
    "SpaceObjectPhysicalProperties",
    "SpacecraftDefinition",
    "TimeScale",
}
```

Import `TypeAdapter` beside `BaseModel`, extend the concrete model tuple, and add the union schema exactly as follows:

```python
from pydantic import BaseModel, TypeAdapter


def _public_model_schemas() -> dict[str, dict[str, Any]]:
    """Return JSON Schemas for the reviewed public Pydantic model surface."""
    models: tuple[type[BaseModel], ...] = (
        core.SchemaVersion,
        core.ErrorDetail,
        core.Epoch,
        core.EarthFixedFrameSpec,
        core.FrameRef,
        core.CartesianState,
        core.PluginRef,
        core.ResourceRequirements,
        core.PluginManifest,
        core.ModelRef,
        core.RigidTransform,
        core.SensorAxes,
        core.GeodeticLocation,
        core.SensorDefinition,
        core.SpaceObjectPhysicalProperties,
        core.SpacecraftDefinition,
        core.OtherSpaceObjectDefinition,
        core.GroundStationDefinition,
    )
    schemas = {model.__name__: model.model_json_schema() for model in models}
    schemas["EntityDefinition"] = TypeAdapter(core.EntityDefinition).json_schema()
    return schemas
```

- [ ] **Step 2: Run the public API tests and confirm missing exports**

Run:

```bash
uv run pytest packages/sycasphere-core/tests/test_public_api.py -q
```

Expected: FAIL because the new names are not yet exported from `sycasphere.core`.

- [ ] **Step 3: Export the reviewed contracts from __init__.py**

Add these imports to `packages/sycasphere-core/src/sycasphere/core/__init__.py`:

```python
from sycasphere.core.entities import (
    EntityDefinition,
    EntityType,
    GroundStationDefinition,
    OtherSpaceObjectDefinition,
    SpaceObjectPhysicalProperties,
    SpacecraftDefinition,
)
from sycasphere.core.geometry import GeodeticLocation, RigidTransform, SensorAxes
from sycasphere.core.model_refs import ModelRef
from sycasphere.core.sensors import SensorDefinition, SensorType
```

Replace `__all__` with this sorted list and update the file header purpose/features/log to mention entity and sensor contracts without changing `__version__ = "0.1.0"`:

```python
__all__ = [
    "CartesianState",
    "CoordinateRepresentation",
    "EarthFixedFrameSpec",
    "EntityDefinition",
    "EntityType",
    "Epoch",
    "ErrorCategory",
    "ErrorDetail",
    "FrameKind",
    "FrameRef",
    "GeodeticLocation",
    "GroundStationDefinition",
    "ModelRef",
    "OtherSpaceObjectDefinition",
    "PluginKind",
    "PluginManifest",
    "PluginRef",
    "ReferenceEllipsoid",
    "ResourceRequirements",
    "RigidTransform",
    "SchemaVersion",
    "SensorAxes",
    "SensorDefinition",
    "SensorType",
    "SpaceObjectPhysicalProperties",
    "SpacecraftDefinition",
    "TimeScale",
]
```

- [ ] **Step 4: Regenerate the deterministic schema snapshot and confirm the public test passes**

Run this exact command from the repository root after Task 1–5 code exists:

```powershell
uv run python -c "import json; from pathlib import Path; import sycasphere.core as c; from pydantic import TypeAdapter; models=(c.SchemaVersion,c.ErrorDetail,c.Epoch,c.EarthFixedFrameSpec,c.FrameRef,c.CartesianState,c.PluginRef,c.ResourceRequirements,c.PluginManifest,c.ModelRef,c.RigidTransform,c.SensorAxes,c.GeodeticLocation,c.SensorDefinition,c.SpaceObjectPhysicalProperties,c.SpacecraftDefinition,c.OtherSpaceObjectDefinition,c.GroundStationDefinition); schemas={m.__name__:m.model_json_schema() for m in models}; schemas['EntityDefinition']=TypeAdapter(c.EntityDefinition).json_schema(); Path('packages/sycasphere-core/tests/snapshots/core-schemas.json').write_text(json.dumps(schemas,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')"
uv run pytest packages/sycasphere-core/tests/test_public_api.py -q
```

Expected: the snapshot changes once, then both public API tests PASS.

- [ ] **Step 5: Add complete spacecraft and ground-station examples to the Core README**

Add a new `## Entity and sensor definitions` section before `## Time and backend boundary`. The section must state that the following examples validate definitions only and do not propagate or generate observations. Use this complete example for the reusable model and sensor construction:

```python
from sycasphere.core import (
    CartesianState,
    CoordinateRepresentation,
    EarthFixedFrameSpec,
    Epoch,
    FrameKind,
    FrameRef,
    GeodeticLocation,
    GroundStationDefinition,
    ModelRef,
    ReferenceEllipsoid,
    RigidTransform,
    SchemaVersion,
    SensorAxes,
    SensorDefinition,
    SensorType,
    SpaceObjectPhysicalProperties,
    SpacecraftDefinition,
    TimeScale,
)

interface_v1 = SchemaVersion(major=1, minor=0)


def model(model_id: str) -> ModelRef:
    return ModelRef(model_id=model_id, interface_version=interface_v1)


def optical_sensor(sensor_id: str) -> SensorDefinition:
    return SensorDefinition(
        id=sensor_id,
        name="Optical Sensor",
        revision=1,
        schema_version=interface_v1,
        sensor_type=SensorType.OPTICAL,
        mount_transform=RigidTransform(
            translation_m=(0.5, 0.0, 0.0),
            rotation_parent_to_child_wxyz=(1.0, 0.0, 0.0, 0.0),
        ),
        axes=SensorAxes(
            boresight=(1.0, 0.0, 0.0),
            horizontal=(0.0, 1.0, 0.0),
            vertical=(0.0, 0.0, 1.0),
        ),
        pointing_model=model("sycasphere.pointing.fixed"),
        field_of_view_model=model("sycasphere.fov.conical"),
        visibility_model=model("sycasphere.visibility.basic"),
        measurement_models=(model("sycasphere.measurement.angles_ra_dec"),),
    )


spacecraft = SpacecraftDefinition(
    id="observer-spacecraft-1",
    name="Observer",
    revision=1,
    schema_version=interface_v1,
    capabilities=("sensor_host",),
    initial_state=CartesianState(
        epoch=Epoch(value="2026-07-21T00:00:00Z", time_scale=TimeScale.UTC),
        frame=FrameRef(kind=FrameKind.J2000),
        position_m=(7_000_000.0, 0.0, 0.0),
        velocity_mps=(0.0, 7_500.0, 0.0),
    ),
    physical_properties=SpaceObjectPhysicalProperties(
        mass_kg=1_000.0,
        cross_section_area_m2=12.0,
        drag_coefficient=2.2,
        solar_radiation_pressure_coefficient=1.3,
    ),
    dynamics_model=model("sycasphere.dynamics.numerical"),
    attitude_model=model("sycasphere.attitude.nadir"),
    sensors=(optical_sensor("space-optical-1"),),
)

earth_fixed = FrameRef(
    kind=FrameKind.EARTH_FIXED,
    representation=CoordinateRepresentation.GEODETIC,
    earth_fixed=EarthFixedFrameSpec(
        itrf_realization="ITRF2020",
        iers_conventions="IERS_2010",
        eop_data_id="iers-bulletin-a:2026-07-21",
    ),
    ellipsoid=ReferenceEllipsoid.WGS84,
)
ground_station = GroundStationDefinition(
    id="ground-station-1",
    name="Ground Station",
    revision=1,
    schema_version=interface_v1,
    capabilities=("sensor_host",),
    location=GeodeticLocation(
        frame=earth_fixed,
        longitude_rad=2.0,
        latitude_rad=0.5,
        ellipsoid_height_m=50.0,
    ),
    body_axes_convention="NED_RH",
    sensors=(optical_sensor("ground-optical-1"),),
)
```

Update `## Phase 1 exclusions` so it no longer says entities or sensors are absent. It must still explicitly exclude observations, run requests, engine sessions, propagation, persistence, API and UI.

- [ ] **Step 6: Run the complete quality gate**

Run:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy packages/sycasphere-core/src
uv run pytest
uv build --offline --no-build-isolation --package sycasphere-core --out-dir .build/core
```

Expected:

- Ruff format and lint PASS;
- mypy reports `Success: no issues found`;
- every pytest test passes;
- the build creates `sycasphere_core-0.1.0-py3-none-any.whl` and its source archive without network access.

- [ ] **Step 7: Smoke-test the built wheel in an isolated Python 3.12 environment**

Run in PowerShell:

```powershell
uv venv --python 3.12 .build/core-smoke
uv pip install --offline --python .build/core-smoke/Scripts/python.exe .build/core/sycasphere_core-0.1.0-py3-none-any.whl
.build/core-smoke/Scripts/python.exe -c "from sycasphere.core import EntityDefinition, SensorDefinition; print('core entity contracts import without JDK')"
```

Expected output:

```text
core entity contracts import without JDK
```

No Java/JDK/Orekit process or import is required.

- [ ] **Step 8: Review the final diff for domain-boundary mistakes**

Run:

```bash
git diff --check
git diff --stat
git status --short
```

Manually confirm all of the following before committing:

- `rotation_parent_to_child_wxyz` is the only public quaternion field;
- every physical number is finite and uses the documented SI unit;
- `GeodeticLocation` requires EARTH_FIXED/GEODETIC/WGS84;
- sensors have no state or orbit fields;
- entities have no task-role fields;
- metadata/configuration are deeply immutable;
- no Orekit, JPype, Java, storage, API or UI import entered Core;
- only plan-listed files are modified and `docs/assets/` remains untracked.

- [ ] **Step 9: Commit the reviewed public contract release surface**

```bash
git add packages/sycasphere-core/src/sycasphere/core/__init__.py packages/sycasphere-core/tests/test_public_api.py packages/sycasphere-core/tests/snapshots/core-schemas.json packages/sycasphere-core/README.md
git commit -m "docs(core): publish entity and sensor contracts"
```

After the commit, rerun `git status --short` and verify that the only remaining entry, if still present, is the pre-existing untracked `docs/assets/` directory.
