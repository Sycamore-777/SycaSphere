# SycaSphere Core Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可由 `uv` 管理的单仓库多安装包工作区，并交付一个可独立安装、无需 JDK/Orekit 的 `sycasphere-core` 基础发行包，固定时间、坐标系、笛卡尔状态、插件身份和结构化错误等后续模块共同依赖的稳定契约。

**Architecture:** `sycasphere-core` 发行包通过 PEP 420 命名空间导出 `sycasphere.core`；它只依赖 Pydantic v2 与 NumPy，不导入 Orekit、JPype、数据库、API 或 UI 技术。Pydantic 模型负责序列化边界与不变量，数值计算通过显式方法转换成 `numpy.ndarray`。本计划只完成依赖链最前端的 Core 基础；观测契约、`SimulationRunRequest`、Engine、Orekit、运行存储和平台集成分别编写后续计划。

**Tech Stack:** Python 3.12、uv workspace、Pydantic v2、NumPy、pytest、Ruff、mypy、Hatchling

## Global Constraints

- 严格遵循仓库根目录 `AGENTS.md`，尤其是依赖方向、SI 单位、数组有限值校验和 Python 文件头格式。
- 所有新增 Python 文件必须带与实际内容一致的 Sycamore 文件头和 `from __future__ import annotations`；不得照抄不真实的“已完成”或 TODO。
- 使用测试驱动：每个行为先写失败测试，确认失败原因正确，再写最小实现。
- Core 的运行时依赖只允许 `numpy` 和 `pydantic`；构建依赖 `hatchling`，开发工具放在根工作区依赖组。
- 不在本阶段引入 Orekit、JPype、PyArrow、SQLite、FastAPI 或任何前端依赖。
- 不创建通用 `Vector3`/`StateVector6` 类；JSON 边界使用定长数组，模型内部用定长元组保证深层不可变，数值入口显式返回 `numpy.ndarray`。
- 绝对时刻在公共边界用字符串表达；UTC 持久化规范化为 `Z`，TAI/TT 不带 `Z` 或时区偏移。Core 不执行时间尺度转换。
- 公共 `J2000` 只声明稳定语义；与 Orekit `EME2000` 的映射由后续 Orekit 适配计划实现。
- 每个任务只提交列出的文件，执行提交前用 `git status --short` 确认没有把现有未跟踪的 `AGENTS.md`、`docs/architecture/` 或 `docs/assets/` 意外纳入。

---

## Task 1: Bootstrap the uv workspace and installable Core distribution

**Files:**

- Create: `.python-version`
- Create: `pyproject.toml`
- Create: `packages/sycasphere-core/pyproject.toml`
- Create: `packages/sycasphere-core/src/sycasphere/core/__init__.py`
- Create: `packages/sycasphere-core/src/sycasphere/core/py.typed`
- Create: `packages/sycasphere-core/tests/test_package.py`
- Modify: `.gitignore`（若不存在则创建；只加入 Python/uv 构建与缓存项）
- Generate: `uv.lock`

- [ ] **Step 1: Write the package smoke test first**

```python
def test_core_package_exposes_version() -> None:
    import sycasphere.core

    assert sycasphere.core.__version__ == "0.1.0"
```

- [ ] **Step 2: Run the smoke test and confirm the workspace is absent**

Run: `uv run pytest packages/sycasphere-core/tests/test_package.py -q`

Expected: FAIL because no root `pyproject.toml` or importable `sycasphere.core` package exists.

- [ ] **Step 3: Create the root uv/tool configuration**

Create a non-package root project with:

```toml
[project]
name = "sycasphere-workspace"
version = "0.0.0"
requires-python = ">=3.12,<3.13"

[dependency-groups]
dev = [
  "mypy>=1.17,<2",
  "pytest>=8.4,<9",
  "ruff>=0.12,<1",
  "sycasphere-core",
]

[tool.uv]
package = false

[tool.uv.workspace]
members = ["packages/*"]

[tool.uv.sources]
sycasphere-core = { workspace = true }

[tool.pytest.ini_options]
addopts = "--strict-config --strict-markers"
testpaths = ["packages/*/tests", "tests"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["sycasphere.core"]
mypy_path = ["packages/sycasphere-core/src"]
```

Resolve the `sycasphere-core` development dependency through `[tool.uv.sources]`, so both root-wide checks and `--package sycasphere-core` checks import the workspace member. Do not make the root itself an installable package.

- [ ] **Step 4: Create the Core distribution metadata**

Use this package contract:

```toml
[project]
name = "sycasphere-core"
version = "0.1.0"
description = "Pure domain contracts for SycaSphere"
requires-python = ">=3.12,<3.13"
dependencies = [
  "numpy>=2.0,<3",
  "pydantic>=2.11,<3",
]

[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/sycasphere"]
```

Use `packages/sycasphere-core/src/sycasphere/` as a PEP 420 namespace directory: do not create `sycasphere/__init__.py`. Put `__version__: Final = "0.1.0"` in `sycasphere/core/__init__.py`.

- [ ] **Step 5: Lock dependencies and run the smoke test**

Run: `uv lock`

Expected: `uv.lock` is generated and resolves only the declared workspace/build/dev graph.

Run: `uv run --package sycasphere-core pytest packages/sycasphere-core/tests/test_package.py -q`

Expected: PASS, 1 test.

- [ ] **Step 6: Run formatting, lint, and type checks for the bootstrap**

Run: `uv run ruff format --check .`

Expected: PASS.

Run: `uv run ruff check .`

Expected: PASS.

Run: `uv run mypy packages/sycasphere-core/src`

Expected: PASS with no issues.

- [ ] **Step 7: Commit only the bootstrap files**

```bash
git add .python-version .gitignore pyproject.toml uv.lock packages/sycasphere-core
git commit -m "build: bootstrap core workspace"
```

## Task 2: Define stable schema-version and structured-error contracts

**Files:**

- Create: `packages/sycasphere-core/src/sycasphere/core/schema.py`
- Create: `packages/sycasphere-core/src/sycasphere/core/errors.py`
- Create: `packages/sycasphere-core/tests/test_schema.py`
- Create: `packages/sycasphere-core/tests/test_errors.py`
- Modify: `packages/sycasphere-core/src/sycasphere/core/__init__.py`

- [ ] **Step 1: Write failing schema compatibility tests**

Cover these exact cases:

```python
def test_schema_version_accepts_same_major_and_newer_minor() -> None:
    required = SchemaVersion(major=1, minor=1)
    provided = SchemaVersion(major=1, minor=3)
    assert provided.satisfies(required)


def test_schema_version_rejects_different_major() -> None:
    required = SchemaVersion(major=1, minor=0)
    provided = SchemaVersion(major=2, minor=0)
    assert not provided.satisfies(required)
```

Also assert that major/minor values cannot be negative and that model instances are frozen.

- [ ] **Step 2: Run the schema tests and confirm missing-symbol failures**

Run: `uv run --package sycasphere-core pytest packages/sycasphere-core/tests/test_schema.py -q`

Expected: FAIL because `SchemaVersion` does not exist.

- [ ] **Step 3: Implement the immutable schema version**

Implement the public shape exactly:

```python
class SchemaVersion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    major: NonNegativeInt
    minor: NonNegativeInt

    def satisfies(self, required: SchemaVersion) -> bool:
        return self.major == required.major and self.minor >= required.minor
```

- [ ] **Step 4: Write failing structured-error tests**

Test serialization and frozen behavior for:

```python
error = ErrorDetail(
    category=ErrorCategory.VALIDATION,
    code="CORE.INVALID_FRAME",
    message="EARTH_FIXED requires earth-fixed metadata",
    retryable=False,
    component_ref="sycasphere.core.frames",
    context={"frame": "EARTH_FIXED"},
)
```

Assert stable enum serialization and forbid arbitrary exception/traceback objects in `context`.

- [ ] **Step 5: Run the error tests and confirm missing-symbol failures**

Run: `uv run --package sycasphere-core pytest packages/sycasphere-core/tests/test_errors.py -q`

Expected: FAIL because the error contracts do not exist.

- [ ] **Step 6: Implement public error categories and payload**

Define at least these categories from the approved design:

```python
class ErrorCategory(StrEnum):
    VALIDATION = "VALIDATION"
    PLUGIN_MISSING = "PLUGIN_MISSING"
    PLUGIN_INCOMPATIBLE = "PLUGIN_INCOMPATIBLE"
    BACKEND_INITIALIZATION = "BACKEND_INITIALIZATION"
    EXTERNAL_DATA = "EXTERNAL_DATA"
    UNSUPPORTED_FRAME = "UNSUPPORTED_FRAME"
    UNSUPPORTED_MEASUREMENT = "UNSUPPORTED_MEASUREMENT"
    NUMERICAL_FAILURE = "NUMERICAL_FAILURE"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    INTERNAL = "INTERNAL"
```

`ErrorDetail` must be frozen, reject extra fields, use a stable machine-readable `code`, and constrain `context` to JSON-compatible scalar/list/dict values. Do not expose Python/Java exception instances or stack traces through this model.

- [ ] **Step 7: Export the contracts and run focused tests**

Run: `uv run --package sycasphere-core pytest packages/sycasphere-core/tests/test_schema.py packages/sycasphere-core/tests/test_errors.py -q`

Expected: PASS.

- [ ] **Step 8: Commit the schema/error contracts**

```bash
git add packages/sycasphere-core/src/sycasphere/core packages/sycasphere-core/tests
git commit -m "feat(core): add schema and error contracts"
```

## Task 3: Implement scale-aware immutable Epoch values

**Files:**

- Create: `packages/sycasphere-core/src/sycasphere/core/epoch.py`
- Create: `packages/sycasphere-core/tests/test_epoch.py`
- Modify: `packages/sycasphere-core/src/sycasphere/core/__init__.py`

- [ ] **Step 1: Write failing UTC normalization tests**

Cover all of the following:

```python
@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("2026-07-20T10:00:00Z", "2026-07-20T10:00:00Z"),
        ("2026-07-20T18:00:00+08:00", "2026-07-20T10:00:00Z"),
        ("2026-07-20T10:00:00.125+00:00", "2026-07-20T10:00:00.125Z"),
    ],
)
def test_utc_is_normalized_to_z(raw: str, canonical: str) -> None:
    assert Epoch(value=raw, scale=TimeScale.UTC).value == canonical
```

Also test:

- UTC without `Z` or offset is rejected;
- TAI and TT accept timezone-free calendar strings;
- TAI/TT with `Z` or offsets are rejected;
- `Epoch` is frozen and rejects extra fields;
- `2026-12-31T23:59:60Z` is accepted and preserved, while an offset-form leap second is rejected because the standard library cannot normalize it safely;
- invalid calendar dates and values beyond the leap-second exception are rejected.

- [ ] **Step 2: Run tests and confirm missing-symbol failures**

Run: `uv run --package sycasphere-core pytest packages/sycasphere-core/tests/test_epoch.py -q`

Expected: FAIL because `Epoch` and `TimeScale` do not exist.

- [ ] **Step 3: Implement the public Epoch contract**

Use this public shape:

```python
class TimeScale(StrEnum):
    UTC = "UTC"
    TAI = "TAI"
    TT = "TT"


class Epoch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str
    scale: TimeScale
```

Implement validation in small private pure functions:

- `_normalize_utc(value: str) -> str` parses aware ISO-8601 values and emits `Z`;
- `_validate_unzoned_calendar(value: str, scale: TimeScale) -> str` validates TAI/TT syntax without attaching a timezone;
- a narrowly defined regex branch accepts only `second == 60` with a `Z` suffix and otherwise delegates to calendar validation;
- never silently interpret a timezone-free UTC string using the machine timezone;
- never convert between UTC, TAI, and TT in Core.

- [ ] **Step 4: Run focused tests and inspect JSON round trips**

Run: `uv run --package sycasphere-core pytest packages/sycasphere-core/tests/test_epoch.py -q`

Expected: PASS.

Add a round-trip assertion using `Epoch.model_validate_json(epoch.model_dump_json())` and confirm equality.

- [ ] **Step 5: Commit the Epoch contract**

```bash
git add packages/sycasphere-core/src/sycasphere/core packages/sycasphere-core/tests/test_epoch.py
git commit -m "feat(core): add scale-aware epoch values"
```

## Task 4: Define public frame references without backend leakage

**Files:**

- Create: `packages/sycasphere-core/src/sycasphere/core/frames.py`
- Create: `packages/sycasphere-core/tests/test_frames.py`
- Modify: `packages/sycasphere-core/src/sycasphere/core/__init__.py`

- [ ] **Step 1: Write failing frame invariant tests**

Test these valid forms:

```python
j2000 = FrameRef(kind=FrameKind.J2000)

earth_fixed = FrameRef(
    kind=FrameKind.EARTH_FIXED,
    representation=CoordinateRepresentation.CARTESIAN,
    earth_fixed=EarthFixedFrameSpec(
        itrf_realization="ITRF2020",
        iers_conventions="IERS_2010",
        eop_data_id="iers-bulletin-a:2026-07-20",
    ),
)

sensor = FrameRef(
    kind=FrameKind.SENSOR,
    owner_id="sensor-1",
    convention="sensor-boresight-rh",
    reference_epoch=Epoch(value="2026-07-20T10:00:00Z", scale=TimeScale.UTC),
)
```

Test these invalid forms:

- public kind `WGS84` is rejected because WGS84 is an ellipsoid, not a frame;
- `EARTH_FIXED` without ITRF/IERS/EOP metadata is rejected;
- `J2000` with Earth-fixed or owner metadata is rejected;
- `GEODETIC` outside `EARTH_FIXED` is rejected;
- `GEODETIC` requires `ellipsoid=WGS84`;
- LVLH/VVLH/BODY/SENSOR without owner, convention, or reference epoch is rejected;
- extra fields and post-construction mutation are rejected.

- [ ] **Step 2: Run tests and confirm missing-symbol failures**

Run: `uv run --package sycasphere-core pytest packages/sycasphere-core/tests/test_frames.py -q`

Expected: FAIL because frame contracts do not exist.

- [ ] **Step 3: Implement explicit frame and representation enums**

Use these stable public values:

```python
class FrameKind(StrEnum):
    J2000 = "J2000"
    EARTH_FIXED = "EARTH_FIXED"
    LVLH = "LVLH"
    VVLH = "VVLH"
    BODY = "BODY"
    SENSOR = "SENSOR"


class CoordinateRepresentation(StrEnum):
    CARTESIAN = "CARTESIAN"
    GEODETIC = "GEODETIC"


class ReferenceEllipsoid(StrEnum):
    WGS84 = "WGS84"
```

`EarthFixedFrameSpec` and `FrameRef` are frozen Pydantic models with `extra="forbid"`. Use one model-level validator to enforce the combinations listed above. The model must not mention Orekit class names; a docstring may state that the public `J2000` semantic is mapped by a backend adapter.

- [ ] **Step 4: Run focused tests and schema assertions**

Run: `uv run --package sycasphere-core pytest packages/sycasphere-core/tests/test_frames.py -q`

Expected: PASS.

Assert in tests that `FrameKind` has exactly the six approved values so GCRF or WGS84 cannot enter accidentally.

- [ ] **Step 5: Commit the frame contracts**

```bash
git add packages/sycasphere-core/src/sycasphere/core packages/sycasphere-core/tests/test_frames.py
git commit -m "feat(core): define public frame references"
```

## Task 5: Add validated Cartesian state boundary models

**Files:**

- Create: `packages/sycasphere-core/src/sycasphere/core/states.py`
- Create: `packages/sycasphere-core/tests/test_states.py`
- Modify: `packages/sycasphere-core/src/sycasphere/core/__init__.py`

- [ ] **Step 1: Write failing shape, unit, and finite-value tests**

Build the canonical valid state:

```python
state = CartesianState(
    epoch=Epoch(value="2026-07-20T10:00:00Z", scale=TimeScale.UTC),
    frame=FrameRef(kind=FrameKind.J2000),
    position_m=[7_000_000.0, 0.0, 0.0],
    velocity_mps=[0.0, 7_500.0, 0.0],
)
```

Assert:

- both vectors must contain exactly three values;
- NaN and positive/negative infinity are rejected;
- string coercion such as `"7000000"` is rejected by strict validation;
- serialized field names preserve SI units;
- mutation is rejected;
- `position_array()` and `velocity_array()` return independent `float64` NumPy arrays with shape `(3,)`;
- mutating a returned array does not mutate the Pydantic model.

- [ ] **Step 2: Run tests and confirm missing-symbol failures**

Run: `uv run --package sycasphere-core pytest packages/sycasphere-core/tests/test_states.py -q`

Expected: FAIL because `CartesianState` does not exist.

- [ ] **Step 3: Implement the boundary model without Vector3 wrappers**

Use explicit constrained-list aliases and finite validators. The public API is:

```python
class CartesianState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    epoch: Epoch
    frame: FrameRef
    position_m: tuple[FiniteComponent, FiniteComponent, FiniteComponent]
    velocity_mps: tuple[FiniteComponent, FiniteComponent, FiniteComponent]

    def position_array(self) -> NDArray[np.float64]:
        return np.asarray(self.position_m, dtype=np.float64).copy()

    def velocity_array(self) -> NDArray[np.float64]:
        return np.asarray(self.velocity_mps, dtype=np.float64).copy()
```

Define `FiniteComponent = Annotated[float, Strict(), AllowInfNan(False)]`. Pydantic accepts a three-element JSON/list input at validation time, stores it as an immutable fixed-length tuple, and emits a JSON array through `model_dump(mode="json")`. Do not add `Vector3`, `StateVector6`, or implicit unit conversion.

- [ ] **Step 4: Run focused tests and static checks**

Run: `uv run --package sycasphere-core pytest packages/sycasphere-core/tests/test_states.py -q`

Expected: PASS.

Run: `uv run mypy packages/sycasphere-core/src/sycasphere/core/states.py`

Expected: PASS with strict typing.

- [ ] **Step 5: Commit the state model**

```bash
git add packages/sycasphere-core/src/sycasphere/core packages/sycasphere-core/tests/test_states.py
git commit -m "feat(core): add Cartesian state contract"
```

## Task 6: Define backend-neutral plugin identity and capability manifests

**Files:**

- Create: `packages/sycasphere-core/src/sycasphere/core/plugins.py`
- Create: `packages/sycasphere-core/tests/test_plugins.py`
- Modify: `packages/sycasphere-core/src/sycasphere/core/__init__.py`

- [ ] **Step 1: Write failing plugin-reference and compatibility tests**

Use the approved first-version plugin kinds:

```python
class PluginKind(StrEnum):
    SCIENCE_BACKEND = "SCIENCE_BACKEND"
    MEASUREMENT_MODEL = "MEASUREMENT_MODEL"
    ERROR_MODEL = "ERROR_MODEL"
    LINK_MODEL = "LINK_MODEL"
```

Test a complete manifest containing:

- stable plugin ID;
- implementation version;
- interface `SchemaVersion`;
- plugin kind;
- a non-empty set of stable capability strings;
- JSON-compatible configuration schema;
- deterministic flag;
- resource requirements that do not require importing backend libraries.

Test that duplicate/blank capabilities, malformed semantic versions, unknown extra fields, and incompatible interface major versions are rejected.

- [ ] **Step 2: Run tests and confirm missing-symbol failures**

Run: `uv run --package sycasphere-core pytest packages/sycasphere-core/tests/test_plugins.py -q`

Expected: FAIL because plugin contracts do not exist.

- [ ] **Step 3: Implement immutable plugin contracts**

Provide these public models:

```python
class PluginRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plugin_id: str
    implementation_version: str
    interface_version: SchemaVersion


class ResourceRequirements(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    requires_jdk: bool = False
    requires_network: bool = False
    minimum_memory_mb: NonNegativeInt | None = None


class PluginManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ref: PluginRef
    kind: PluginKind
    capabilities: frozenset[str]
    configuration_schema: dict[str, JsonValue]
    deterministic: bool
    resources: ResourceRequirements

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def is_interface_compatible_with(self, required: SchemaVersion) -> bool:
        return self.ref.interface_version.satisfies(required)
```

Validate identifiers and implementation versions with narrowly scoped patterns. Capability selection must use `supports()`; do not infer behavior from a display name or Python import path. Model construction and JSON schema generation must not import or initialize any plugin implementation.

- [ ] **Step 4: Run focused tests and prove Core imports without Java**

Run: `uv run --package sycasphere-core pytest packages/sycasphere-core/tests/test_plugins.py -q`

Expected: PASS.

Run:

```bash
uv run --package sycasphere-core python -c "import sys; import sycasphere.core; assert 'jpype' not in sys.modules"
```

Expected: exit 0 with no output.

- [ ] **Step 5: Commit plugin contracts**

```bash
git add packages/sycasphere-core/src/sycasphere/core packages/sycasphere-core/tests/test_plugins.py
git commit -m "feat(core): define plugin capability manifests"
```

## Task 7: Enforce the Core dependency boundary and public schema surface

**Files:**

- Create: `tests/architecture/test_core_dependency_boundary.py`
- Create: `packages/sycasphere-core/tests/test_public_api.py`
- Create: `packages/sycasphere-core/tests/snapshots/core-schemas.json`
- Modify: `packages/sycasphere-core/src/sycasphere/core/__init__.py`

- [ ] **Step 1: Write an architecture test that initially detects a deliberate fixture violation**

Write a pure AST scanner helper that calls `Path("packages/sycasphere-core/src/sycasphere/core").rglob("*.py")`, inspects both `ast.Import` and `ast.ImportFrom` nodes, extracts every root module, and rejects these roots:

```python
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
```

Unit-test the scanner itself with an in-memory or temporary Python file containing `import jpype`, then test the actual Core tree. The scanner test must fail before the rejection logic is implemented and pass afterward; do not insert a real forbidden import into production source.

- [ ] **Step 2: Implement the scanner and run the architecture test**

Run: `uv run pytest tests/architecture/test_core_dependency_boundary.py -q`

Expected: PASS and no forbidden Core imports.

- [ ] **Step 3: Define and test the intentional public API**

Populate `sycasphere.core.__all__` with only the approved public names from Tasks 2–6. Add a test asserting the exact set. This turns accidental exports into a reviewed schema change.

- [ ] **Step 4: Generate a deterministic schema snapshot**

Build one sorted JSON object mapping public Pydantic model names to `model_json_schema()` results, serialize with `indent=2`, `sort_keys=True`, UTF-8, and a final newline. The initial snapshot includes:

- `SchemaVersion`;
- `ErrorDetail`;
- `Epoch`;
- `EarthFixedFrameSpec`;
- `FrameRef`;
- `CartesianState`;
- `PluginRef`;
- `ResourceRequirements`;
- `PluginManifest`.

Implement a pytest assertion that regenerates the object in memory and compares it to `core-schemas.json`. Do not introduce a snapshot plugin dependency.

- [ ] **Step 5: Run public API and schema tests**

Run: `uv run --package sycasphere-core pytest packages/sycasphere-core/tests/test_public_api.py -q`

Expected: PASS.

- [ ] **Step 6: Commit boundary enforcement and snapshots**

```bash
git add tests/architecture packages/sycasphere-core
git commit -m "test(core): lock public schemas and dependency boundary"
```

## Task 8: Document, verify, and review the Phase 1 deliverable

**Files:**

- Create: `packages/sycasphere-core/README.md`
- Modify: `README.md`
- Modify only if an actual contradiction remains: `docs/superpowers/specs/2026-07-20-sycasphere-runtime-and-simulation-engine-design.md`

- [ ] **Step 1: Write Core installation and usage documentation**

Document:

- distribution name `sycasphere-core` versus import path `sycasphere.core`;
- installation from the workspace and from a built wheel;
- a minimal `Epoch` + `FrameRef` + `CartesianState` example;
- the rule that Core performs no UTC/TAI/TT conversion and has no Orekit/JDK dependency;
- schema compatibility and plugin capability selection semantics;
- explicit Phase 1 exclusions: observations, run requests, engine sessions, propagation, persistence, API, and UI.

- [ ] **Step 2: Verify build artifacts in a temporary output directory**

Run: `uv build --package sycasphere-core --out-dir .build/core`

Expected: one sdist and one wheel are produced successfully.

Run:

```bash
uv run python -c "import zipfile, pathlib; wheel=next(pathlib.Path('.build/core').glob('*.whl')); names=zipfile.ZipFile(wheel).namelist(); assert any(n.endswith('sycasphere/core/py.typed') for n in names); assert not any('orekit' in n.lower() or 'jpype' in n.lower() for n in names)"
```

Expected: exit 0. Remove `.build/` only after confirming it is covered by `.gitignore`; this is generated, recoverable build output.

- [ ] **Step 3: Run the mandatory repository checks**

Run: `uv run ruff format --check .`

Expected: PASS.

Run: `uv run ruff check .`

Expected: PASS.

Run: `uv run mypy packages/sycasphere-core/src`

Expected: PASS with no issues.

Run: `uv run pytest`

Expected: all Phase 1 package and architecture tests PASS.

- [ ] **Step 4: Perform the required final diff audit**

Run: `git diff --check`

Expected: no whitespace errors.

Run: `git status --short`

Expected: only the intended README/documentation changes are pending; pre-existing untracked project files remain unstaged.

Review the complete Phase 1 diff specifically for:

- UTC `Z` normalization and TAI/TT no-zone rules;
- `J2000`/`EARTH_FIXED`/WGS84 semantic separation;
- SI units in serialized state fields;
- strict finite vector validation;
- frozen model behavior;
- absence of truth/observation concepts that belong in the next plan;
- absence of Orekit/JPype/JVM imports and initialization;
- no unrequested production dependencies.

- [ ] **Step 5: Commit documentation after all checks pass**

```bash
git add README.md packages/sycasphere-core/README.md
git commit -m "docs: document core foundation package"
```

## Phase Boundary and Next Plans

This plan ends with a working, independently installable Core foundation. Do not extend it opportunistically. Prepare and approve the following plans in dependency order after this phase passes:

1. Core simulation, maneuver, observation, and run-lifecycle schemas.
2. Backend-neutral Engine kernel, batch API, interactive session, control trace, and command journal using a fake backend.
3. Measurement/error/link pipeline, delivery accounting, streaming envelopes, and deterministic random-stream derivation.
4. Orekit backend plugin, JVM lifecycle, time/frame adapters, propagation, geometry, and impulsive maneuvers.
5. Standalone Sim product, Parquet/artifact ports, staging publication, retention policy, and CLI.
6. Platform run orchestration, algorithm gateway, evaluation, API, and frontend integration.

Each later plan must start from the schemas and test evidence produced by the preceding phase and must remain independently runnable without relying on uncommitted work.
