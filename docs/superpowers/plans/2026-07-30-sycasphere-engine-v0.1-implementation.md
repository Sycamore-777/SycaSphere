# SycaSphere Engine v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付可独立安装的后端中立 Engine，通过显式插件注册表、不可变 Manifest、
确定性 FakeBackend 和流式 sink 完成可取消的批量 Truth、姿态与脉冲机动运行。

**Architecture:** `SimulationEngine` 统一准备请求、调度事件、控制输出与错误生命周期；
科学后端只实现准备期校验/时间适配和一次运行的物理状态推进端口。稳定、可序列化的执行
结果放入 Core，包含行为的 registry、backend、scheduler、sink 和 runner 放入 Engine。

**Tech Stack:** Python 3.12、Pydantic v2、NumPy、pytest、Ruff、mypy、uv、Hatchling。

## Global Constraints

- 权威规格是
  `docs/superpowers/specs/2026-07-30-sycasphere-engine-v0.1-design.md`，并继续服从
  `AGENTS.md` 列出的三份架构文档。
- Engine 只依赖 Core 和 NumPy；不得导入 Orekit、JPype、Java、FastAPI、SQLite、
  PyArrow、Redis、Kafka 或 Platform。
- 不新增生产依赖；若实现发现标准库、Core 和 NumPy 不足，必须停止并重新审查设计。
- 所有新 Python 文件使用准确的 Sycamore 头，创建/最后修改日期为 `2026-07-30`，
  初始文件版本为 `v1.0.0`，并包含 `from __future__ import annotations`。
- 公共函数、方法、Protocol、模型和异常完整标注类型；公共数值边界只使用 Core 模型、
  固定长度元组和 SI 单位，NumPy 数组不得逃逸。
- 四元数固定为 reference-to-BODY 的 `(w, x, y, z)`。
- v0.1 要求 J2000、同一 `TimeScale`、非 UTC 闰秒、Truth 必选、姿态可选、无观测、
  无链路、无几何、无有限推力。
- 同刻机动按“PLANNED 在 COMMAND 前；同一来源保持请求声明顺序”生成稳定
  `order_index`；同刻普通采样只看到全部机动后的状态。
- 每个行为变更先写失败测试，再写最小实现；每个 Task 只提交该 Task 的文件。
- 不触碰既有未跟踪 `docs/assets/`。

---

## File Structure

### Core production and tests

- Create: `packages/sycasphere-core/src/sycasphere/core/execution_results.py`
  - `SimulationExecutionStatus`、`SimulationOutputSummary`、
    `SimulationExecutionResult`。
- Modify: `packages/sycasphere-core/src/sycasphere/core/execution.py`
  - 为 `ResolvedPluginRecord` 增加规范配置哈希工厂。
- Modify: `packages/sycasphere-core/src/sycasphere/core/__init__.py`
  - 发布新增稳定结果契约。
- Create: `packages/sycasphere-core/tests/test_execution_results.py`
- Modify: `packages/sycasphere-core/tests/test_execution.py`
- Modify: `packages/sycasphere-core/tests/test_public_api.py`
- Modify: `packages/sycasphere-core/tests/snapshots/core-schemas.json`

### Engine production

- Create: `packages/sycasphere-engine/pyproject.toml`
- Create: `packages/sycasphere-engine/LICENSE`
- Create: `packages/sycasphere-engine/README.md`
- Create: `packages/sycasphere-engine/src/sycasphere/engine/__init__.py`
- Create: `packages/sycasphere-engine/src/sycasphere/engine/api.py`
  - `SimulationEngine` 公共门面。
- Create: `packages/sycasphere-engine/src/sycasphere/engine/backend.py`
  - 配置校验、时间适配、factory/runtime Protocol 和机动执行值对象。
- Create: `packages/sycasphere-engine/src/sycasphere/engine/cancellation.py`
  - `CancellationProbe` 与线程安全 `CancellationToken`。
- Create: `packages/sycasphere-engine/src/sycasphere/engine/errors.py`
  - 公共异常和稳定 `ErrorDetail` 构造辅助函数。
- Create: `packages/sycasphere-engine/src/sycasphere/engine/execution.py`
  - 同步批量 Runner、缓冲和生命周期状态机。
- Create: `packages/sycasphere-engine/src/sycasphere/engine/preparation.py`
  - v0.1 范围校验、插件解析、时间线和 Manifest 生成。
- Create: `packages/sycasphere-engine/src/sycasphere/engine/registry.py`
  - 构造后不可修改的 `PluginRegistry`。
- Create: `packages/sycasphere-engine/src/sycasphere/engine/scheduling.py`
  - 同尺度时间实现、惰性采样和事件组合。
- Create: `packages/sycasphere-engine/src/sycasphere/engine/sinks.py`
  - sink Protocol 与 Null/InMemory/Composite 实现。
- Create: `packages/sycasphere-engine/src/sycasphere/engine/testing/__init__.py`
- Create: `packages/sycasphere-engine/src/sycasphere/engine/testing/fake_backend.py`
- Create: `packages/sycasphere-engine/src/sycasphere/engine/py.typed`

### Engine tests and workspace

- Create: `packages/sycasphere-engine/tests/conftest.py`
- Create: `packages/sycasphere-engine/tests/test_cancellation_errors.py`
- Create: `packages/sycasphere-engine/tests/test_registry_backend.py`
- Create: `packages/sycasphere-engine/tests/test_scheduling.py`
- Create: `packages/sycasphere-engine/tests/test_sinks.py`
- Create: `packages/sycasphere-engine/tests/test_fake_backend.py`
- Create: `packages/sycasphere-engine/tests/test_preparation.py`
- Create: `packages/sycasphere-engine/tests/test_execution.py`
- Create: `packages/sycasphere-engine/tests/test_public_api.py`
- Create: `packages/sycasphere-engine/tests/test_package.py`
- Create: `packages/sycasphere-engine/tests/fixtures/readme_fake_run.py`
- Create: `tests/architecture/test_engine_dependency_boundary.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`

### Documentation

- Modify: `README.md`
- Modify: `packages/sycasphere-core/README.md`
- Modify: `docs/architecture/core-data-model-v0.2.md`
- Modify: `docs/architecture/algorithm-integration-v0.2.md`
- Modify:
  `docs/superpowers/specs/2026-07-20-sycasphere-runtime-and-simulation-engine-design.md`

---

## Cross-Task Interface Map

Task 1 produces:

```python
class SimulationExecutionStatus(StrEnum):
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class SimulationOutputSummary(BaseModel):
    truth_state_count: StrictNonNegativeInt = 0
    attitude_state_count: StrictNonNegativeInt = 0
    truth_maneuver_count: StrictNonNegativeInt = 0


class SimulationExecutionResult(BaseModel):
    manifest_content_hash: Sha256Hex
    status: SimulationExecutionStatus
    final_epoch: Epoch
    output_summary: SimulationOutputSummary
    termination_detail: ErrorDetail | None = None


ResolvedPluginRecord.create(
    *,
    component_id: str,
    kind: PluginKind,
    ref: PluginRef,
    configuration: Mapping[str, JsonValue],
) -> ResolvedPluginRecord
```

Tasks 2–8 use these Engine interfaces exactly:

```python
class CancellationProbe(Protocol):
    @property
    def is_cancelled(self) -> bool: ...


class BackendConfigurationValidator(Protocol):
    def validate(self, request: SimulationRunRequest) -> None: ...


class PreparationTimeAdapter(Protocol):
    def compare(self, left: Epoch, right: Epoch) -> int: ...
    def seconds_between(self, start: Epoch, end: Epoch) -> float: ...
    def add_seconds(self, epoch: Epoch, seconds: float) -> Epoch: ...
    def same_instant(self, left: Epoch, right: Epoch) -> bool: ...


class PropagationOutcome(StrEnum):
    REACHED_TARGET = "REACHED_TARGET"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class ManeuverExecution:
    executed_epoch: Epoch
    actual_delta_v_j2000_mps: tuple[float, float, float]
    state_before: TruthState
    state_after: TruthState


class ScienceBackendRuntime(Protocol):
    @property
    def current_epoch(self) -> Epoch: ...
    def initialize(self) -> None: ...
    def propagate_to(
        self, target_epoch: Epoch, cancellation: CancellationProbe
    ) -> PropagationOutcome: ...
    def snapshot_truth(self) -> tuple[TruthState, ...]: ...
    def snapshot_attitudes(self) -> tuple[AttitudeState, ...]: ...
    def execute_impulsive_maneuver(
        self, entry: PreparedManeuverEntry
    ) -> ManeuverExecution: ...
    def close(self) -> None: ...


class ScienceBackendFactory(Protocol):
    def create(
        self, manifest: SimulationExecutionManifest
    ) -> ScienceBackendRuntime: ...


@dataclass(frozen=True, slots=True)
class ScienceBackendRegistration:
    manifest: PluginManifest
    configuration_validator: BackendConfigurationValidator
    time_adapter: PreparationTimeAdapter
    factory: ScienceBackendFactory


class SimulationOutputSink(Protocol):
    def begin(self, manifest: SimulationExecutionManifest) -> None: ...
    def write_truth_states(self, batch: tuple[TruthState, ...]) -> None: ...
    def write_attitude_states(self, batch: tuple[AttitudeState, ...]) -> None: ...
    def write_truth_maneuvers(self, batch: tuple[TruthManeuver, ...]) -> None: ...
    def commit(self, summary: SimulationOutputSummary) -> None: ...
    def abort(self, detail: ErrorDetail) -> None: ...
```

---

### Task 1: Add Core execution-result and configuration-hash contracts

**Files:**
- Create: `packages/sycasphere-core/src/sycasphere/core/execution_results.py`
- Create: `packages/sycasphere-core/tests/test_execution_results.py`
- Modify: `packages/sycasphere-core/src/sycasphere/core/execution.py`
- Modify: `packages/sycasphere-core/tests/test_execution.py`
- Modify: `packages/sycasphere-core/src/sycasphere/core/__init__.py`
- Modify: `packages/sycasphere-core/tests/test_public_api.py`
- Modify: `packages/sycasphere-core/tests/snapshots/core-schemas.json`

**Interfaces:**
- Produces: all Task 1 contracts in the Cross-Task Interface Map.
- Preserves: `SimulationExecutionManifest` schema and hash behavior.

- [ ] **Step 1: Write failing result state-matrix tests**

Create `test_execution_results.py` with the required header and these tests:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError
from sycasphere.core import Epoch, ErrorCategory, ErrorDetail, TimeScale
from sycasphere.core.execution_results import (
    SimulationExecutionResult,
    SimulationExecutionStatus,
    SimulationOutputSummary,
)

EPOCH = Epoch(value="2026-07-30T00:00:10Z", time_scale=TimeScale.UTC)
CANCELLED = ErrorDetail(
    category=ErrorCategory.CANCELLED,
    code="engine.cancelled",
    message="simulation execution was cancelled",
    retryable=False,
    component_ref="engine",
    context={},
)


def test_completed_result_has_counts_and_no_termination_detail() -> None:
    result = SimulationExecutionResult(
        manifest_content_hash="a" * 64,
        status=SimulationExecutionStatus.COMPLETED,
        final_epoch=EPOCH,
        output_summary=SimulationOutputSummary(
            truth_state_count=2,
            attitude_state_count=2,
            truth_maneuver_count=1,
        ),
    )
    assert result.termination_detail is None


def test_cancelled_result_requires_cancelled_detail() -> None:
    result = SimulationExecutionResult(
        manifest_content_hash="a" * 64,
        status=SimulationExecutionStatus.CANCELLED,
        final_epoch=EPOCH,
        output_summary=SimulationOutputSummary(),
        termination_detail=CANCELLED,
    )
    assert result.termination_detail.category is ErrorCategory.CANCELLED

    with pytest.raises(ValidationError, match="CANCELLED"):
        SimulationExecutionResult.model_validate(
            {
                **result.model_dump(mode="python"),
                "termination_detail": None,
            }
        )


@pytest.mark.parametrize("field", ["truth_state_count", "attitude_state_count", "truth_maneuver_count"])
def test_output_counts_reject_negative_and_coercible_values(field: str) -> None:
    with pytest.raises(ValidationError):
        SimulationOutputSummary(**{field: -1})
    with pytest.raises(ValidationError):
        SimulationOutputSummary(**{field: "1"})
```

- [ ] **Step 2: Run the focused test and verify missing imports**

Run:

```powershell
uv run pytest packages/sycasphere-core/tests/test_execution_results.py -q
```

Expected: collection fails with
`ModuleNotFoundError: sycasphere.core.execution_results`.

- [ ] **Step 3: Implement the frozen Core result models**

Create `execution_results.py` with the Task 1 signatures. Use
`ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")`, snapshot
`final_epoch`, `output_summary`, and `termination_detail`, and implement:

```python
@model_validator(mode="after")
def validate_status_detail(self) -> Self:
    if self.status is SimulationExecutionStatus.COMPLETED:
        if self.termination_detail is not None:
            raise ValueError("COMPLETED result must not contain termination_detail")
        return self
    if self.termination_detail is None:
        raise ValueError("CANCELLED result requires termination_detail")
    if self.termination_detail.category is not ErrorCategory.CANCELLED:
        raise ValueError("CANCELLED result requires CANCELLED error category")
    return self
```

- [ ] **Step 4: Add a failing canonical configuration-hash factory test**

Append to `test_execution.py`:

```python
def test_resolved_plugin_factory_hashes_canonical_configuration() -> None:
    record_a = ResolvedPluginRecord.create(
        component_id="science-backend",
        kind=PluginKind.SCIENCE_BACKEND,
        ref=make_request().backend.ref,
        configuration={"b": -0.0, "a": [1, True]},
    )
    record_b = ResolvedPluginRecord.create(
        component_id="science-backend",
        kind=PluginKind.SCIENCE_BACKEND,
        ref=make_request().backend.ref,
        configuration={"a": [1, True], "b": 0.0},
    )
    assert record_a.configuration_hash == record_b.configuration_hash
```

Run the test and expect `AttributeError: create`.

- [ ] **Step 5: Implement `ResolvedPluginRecord.create`**

Import `JsonValue`/`Mapping` already present in `execution.py` and add:

```python
@classmethod
def create(
    cls,
    *,
    component_id: str,
    kind: PluginKind,
    ref: PluginRef,
    configuration: Mapping[str, JsonValue],
) -> ResolvedPluginRecord:
    return cls(
        component_id=component_id,
        kind=kind,
        ref=ref,
        configuration_hash=sha256_canonical_json(configuration),
    )
```

- [ ] **Step 6: Publish and snapshot the result contracts**

Add the three result names to Core `__all__`, `EXPECTED_PUBLIC_CONTRACTS`, and
`_public_model_schemas()`. Regenerate `core-schemas.json` with the existing snapshot helper:

```powershell
uv run python -c "from pathlib import Path; from importlib.util import module_from_spec, spec_from_file_location; p=Path('packages/sycasphere-core/tests/test_public_api.py'); s=spec_from_file_location('schema_snapshot', p); m=module_from_spec(s); s.loader.exec_module(m); Path('packages/sycasphere-core/tests/snapshots/core-schemas.json').write_text(m._serialized_public_model_schemas(), encoding='utf-8')"
```

- [ ] **Step 7: Run focused quality gates and commit**

Run:

```powershell
uv run pytest packages/sycasphere-core/tests/test_execution_results.py `
  packages/sycasphere-core/tests/test_execution.py `
  packages/sycasphere-core/tests/test_public_api.py -q
uv run ruff format --check packages/sycasphere-core
uv run ruff check packages/sycasphere-core
uv run mypy
```

Expected: all commands pass.

```powershell
git add packages/sycasphere-core/src/sycasphere/core/execution_results.py `
  packages/sycasphere-core/src/sycasphere/core/execution.py `
  packages/sycasphere-core/src/sycasphere/core/__init__.py `
  packages/sycasphere-core/tests/test_execution_results.py `
  packages/sycasphere-core/tests/test_execution.py `
  packages/sycasphere-core/tests/test_public_api.py `
  packages/sycasphere-core/tests/snapshots/core-schemas.json
git commit -m "feat(core): define simulation execution results"
```

---

### Task 2: Create the Engine package, cancellation, and public errors

**Files:**
- Create: `packages/sycasphere-engine/pyproject.toml`
- Create: `packages/sycasphere-engine/LICENSE`
- Create: `packages/sycasphere-engine/src/sycasphere/engine/__init__.py`
- Create: `packages/sycasphere-engine/src/sycasphere/engine/cancellation.py`
- Create: `packages/sycasphere-engine/src/sycasphere/engine/errors.py`
- Create: `packages/sycasphere-engine/src/sycasphere/engine/py.typed`
- Create: `packages/sycasphere-engine/tests/test_cancellation_errors.py`
- Create: `tests/architecture/test_engine_dependency_boundary.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`

**Interfaces:**
- Consumes: Core `ErrorCategory` and `ErrorDetail`.
- Produces: `CancellationProbe`, `CancellationToken`, `SimulationEngineError`,
  `SimulationPreparationError`, `SimulationExecutionError`, and package-internal
  `make_error_detail(...) -> ErrorDetail`.

- [ ] **Step 1: Add failing package/cancellation/error tests**

Create `test_cancellation_errors.py`:

```python
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from sycasphere.core import ErrorCategory, ErrorDetail
from sycasphere.engine.cancellation import CancellationToken
from sycasphere.engine.errors import SimulationExecutionError


def test_cancellation_token_is_monotonic_and_thread_safe() -> None:
    token = CancellationToken()
    assert token.is_cancelled is False
    with ThreadPoolExecutor(max_workers=4) as pool:
        tuple(pool.map(lambda _: token.cancel(), range(20)))
    assert token.is_cancelled is True


def test_engine_exception_exposes_only_structured_detail() -> None:
    detail = ErrorDetail(
        category=ErrorCategory.NUMERICAL_FAILURE,
        code="backend.propagation_failed",
        message="propagation failed",
        retryable=False,
        component_ref="science-backend",
        context={"epoch": "2026-07-30T00:00:00Z"},
    )
    error = SimulationExecutionError(detail)
    assert error.detail is detail
    assert str(error) == "propagation failed"
```

- [ ] **Step 2: Add the Engine dependency-boundary test**

Copy the AST scanner pattern from `test_core_dependency_boundary.py`, point it at
`packages/sycasphere-engine/src/sycasphere/engine`, and set:

```python
FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "fastapi",
        "jpype",
        "orekit",
        "pyarrow",
        "redis",
        "sqlalchemy",
        "sqlite3",
    }
)
```

Also reject absolute imports rooted at `sycasphere.orekit` and `sycasphere.platform`.

- [ ] **Step 3: Run tests and verify package imports fail**

Run:

```powershell
uv run pytest packages/sycasphere-engine/tests/test_cancellation_errors.py `
  tests/architecture/test_engine_dependency_boundary.py -q
```

Expected: Engine module collection fails before package creation.

- [ ] **Step 4: Create package metadata and workspace configuration**

Create `packages/sycasphere-engine/pyproject.toml`:

```toml
[project]
name = "sycasphere-engine"
version = "0.1.0"
description = "Backend-neutral simulation runtime for SycaSphere"
license = "Apache-2.0"
license-files = ["LICENSE"]
requires-python = ">=3.12,<3.13"
dependencies = [
  "numpy>=2.0,<3",
  "sycasphere-core",
]

[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/sycasphere"]
```

Copy the root Apache-2.0 `LICENSE`. Add `sycasphere-engine` to the root dev group and
`[tool.uv.sources]`. Extend mypy:

```toml
packages = ["sycasphere.core", "sycasphere.engine"]
mypy_path = ["packages/sycasphere-core/src", "packages/sycasphere-engine/src"]
```

Run `uv lock --offline` and review that no production dependency other than Engine/Core/NumPy was
added.

- [ ] **Step 5: Implement cancellation and exceptions**

Use `threading.Event`:

```python
@runtime_checkable
class CancellationProbe(Protocol):
    @property
    def is_cancelled(self) -> bool: ...


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()
```

Implement the exception tree with `__slots__ = ("detail",)` and no traceback data in `detail`.
Implement the shared internal constructor with this exact signature:

```python
def make_error_detail(
    *,
    category: ErrorCategory,
    code: str,
    message: str,
    component_ref: str,
    context: Mapping[str, Any] | None = None,
    retryable: bool = False,
) -> ErrorDetail:
    return ErrorDetail(
        category=category,
        code=code,
        message=message,
        retryable=retryable,
        component_ref=component_ref,
        context={} if context is None else context,
    )
```

- [ ] **Step 6: Run tests, lint, type-check, and commit**

```powershell
uv run pytest packages/sycasphere-engine/tests/test_cancellation_errors.py `
  tests/architecture/test_engine_dependency_boundary.py -q
uv run ruff format --check packages/sycasphere-engine tests/architecture
uv run ruff check packages/sycasphere-engine tests/architecture
uv run mypy
git add pyproject.toml uv.lock packages/sycasphere-engine/pyproject.toml `
  packages/sycasphere-engine/LICENSE `
  packages/sycasphere-engine/src/sycasphere/engine/__init__.py `
  packages/sycasphere-engine/src/sycasphere/engine/cancellation.py `
  packages/sycasphere-engine/src/sycasphere/engine/errors.py `
  packages/sycasphere-engine/src/sycasphere/engine/py.typed `
  packages/sycasphere-engine/tests/test_cancellation_errors.py `
  tests/architecture/test_engine_dependency_boundary.py
git commit -m "feat(engine): create runtime package boundaries"
```

---

### Task 3: Define backend ports and immutable plugin registry

**Files:**
- Create: `packages/sycasphere-engine/src/sycasphere/engine/backend.py`
- Create: `packages/sycasphere-engine/src/sycasphere/engine/registry.py`
- Create: `packages/sycasphere-engine/tests/test_registry_backend.py`

**Interfaces:**
- Produces: every backend/registration interface in the Cross-Task Interface Map.
- Consumes: Task 2 cancellation and errors.

- [ ] **Step 1: Write failing registry tests**

```python
def test_registry_resolves_exact_backend_ref(fake_registration) -> None:
    registry = PluginRegistry((fake_registration,))
    assert registry.resolve(fake_registration.manifest.ref) is fake_registration


def test_registry_rejects_duplicates_and_non_backend_manifest(fake_registration) -> None:
    with pytest.raises(ValueError, match="duplicate"):
        PluginRegistry((fake_registration, fake_registration))

    invalid = replace(
        fake_registration,
        manifest=fake_registration.manifest.model_copy(
            update={"kind": PluginKind.MEASUREMENT_MODEL}
        ),
    )
    with pytest.raises(ValueError, match="SCIENCE_BACKEND"):
        PluginRegistry((invalid,))


def test_registry_is_not_mutable_after_construction(fake_registration) -> None:
    registry = PluginRegistry((fake_registration,))
    assert not hasattr(registry, "register")
    with pytest.raises(AttributeError):
        registry.registrations = ()
```

Define these local stubs and fixture in the same file; registry construction must leave every call
counter at zero:

```python
class StubValidator:
    def __init__(self) -> None:
        self.calls = 0

    def validate(self, request: SimulationRunRequest) -> None:
        self.calls += 1


class StubTimeAdapter:
    def compare(self, left: Epoch, right: Epoch) -> int:
        raise AssertionError("registry construction must not compare epochs")

    def seconds_between(self, start: Epoch, end: Epoch) -> float:
        raise AssertionError("registry construction must not compute durations")

    def add_seconds(self, epoch: Epoch, seconds: float) -> Epoch:
        raise AssertionError("registry construction must not add time")

    def same_instant(self, left: Epoch, right: Epoch) -> bool:
        raise AssertionError("registry construction must not compare instants")


class StubFactory:
    def __init__(self) -> None:
        self.create_calls = 0

    def create(
        self, manifest: SimulationExecutionManifest
    ) -> ScienceBackendRuntime:
        self.create_calls += 1
        raise AssertionError("registry construction must not create runtime")


@pytest.fixture
def fake_registration() -> ScienceBackendRegistration:
    manifest = PluginManifest(
        ref=PluginRef(
            plugin_id="sycasphere.testing.stub",
            implementation_version="0.1.0",
            interface_version=SchemaVersion(major=1, minor=0),
        ),
        kind=PluginKind.SCIENCE_BACKEND,
        capabilities=("output.truth",),
        configuration_schema={},
        deterministic=True,
        resources=ResourceRequirements(),
    )
    return ScienceBackendRegistration(
        manifest=manifest,
        configuration_validator=StubValidator(),
        time_adapter=StubTimeAdapter(),
        factory=StubFactory(),
    )
```

- [ ] **Step 2: Run tests and verify missing interfaces**

Run `uv run pytest packages/sycasphere-engine/tests/test_registry_backend.py -q`.
Expected: import failure for `sycasphere.engine.backend`.

- [ ] **Step 3: Implement typed backend ports**

Implement exactly the Cross-Task Interface Map. Validate `ManeuverExecution` in `__post_init__`:

```python
if self.state_before.entity_id != self.state_after.entity_id:
    raise ValueError("maneuver states must describe the same entity")
if self.state_before.epoch != self.executed_epoch:
    raise ValueError("state_before epoch must equal executed_epoch")
if self.state_after.epoch != self.executed_epoch:
    raise ValueError("state_after epoch must equal executed_epoch")
if len(self.actual_delta_v_j2000_mps) != 3:
    raise ValueError("actual delta-v must contain three components")
if any(type(component) is not float or not math.isfinite(component)
       for component in self.actual_delta_v_j2000_mps):
    raise ValueError("actual delta-v components must be finite built-in floats")
```

- [ ] **Step 4: Implement the registry**

Store a `MappingProxyType[PluginRef, ScienceBackendRegistration]`. Reject duplicate refs and manifests
whose kind is not `SCIENCE_BACKEND`. `resolve()` raises
`SimulationPreparationError(ErrorDetail(category=PLUGIN_MISSING, code="plugin.backend_missing", ...))`
with the requested ref serialized into finite context.

- [ ] **Step 5: Run focused gates and commit**

```powershell
uv run pytest packages/sycasphere-engine/tests/test_registry_backend.py -q
uv run ruff format --check packages/sycasphere-engine
uv run ruff check packages/sycasphere-engine
uv run mypy
git add packages/sycasphere-engine/src/sycasphere/engine/backend.py `
  packages/sycasphere-engine/src/sycasphere/engine/registry.py `
  packages/sycasphere-engine/tests/test_registry_backend.py
git commit -m "feat(engine): define backend plugin ports"
```

---

### Task 4: Implement same-scale time arithmetic and lazy scheduling

**Files:**
- Create: `packages/sycasphere-engine/src/sycasphere/engine/scheduling.py`
- Create: `packages/sycasphere-engine/tests/test_scheduling.py`

**Interfaces:**
- Consumes: `PreparationTimeAdapter`, Core schedule/manifest types.
- Produces:

```python
class SameScaleCalendarTimeAdapter:
    def compare(self, left: Epoch, right: Epoch) -> int: ...
    def seconds_between(self, start: Epoch, end: Epoch) -> float: ...
    def add_seconds(self, epoch: Epoch, seconds: float) -> Epoch: ...
    def same_instant(self, left: Epoch, right: Epoch) -> bool: ...


@dataclass(frozen=True, slots=True)
class ScheduledEventGroup:
    epoch: Epoch
    maneuvers: tuple[PreparedManeuverEntry, ...]
    sample_products: tuple[OutputProduct, ...]


iter_sampling_epochs(
    time_range: SimulationTimeRange,
    rule: SamplingRule,
    time_adapter: PreparationTimeAdapter,
) -> Iterator[Epoch]

iter_event_groups(
    manifest: SimulationExecutionManifest,
    time_adapter: PreparationTimeAdapter,
) -> Iterator[ScheduledEventGroup]
```

- [ ] **Step 1: Write failing exact time and sampling tests**

```python
def test_sampling_forces_closed_interval_end() -> None:
    adapter = SameScaleCalendarTimeAdapter()
    time_range = SimulationTimeRange(
        start=utc("2026-07-30T00:00:00Z"),
        end=utc("2026-07-30T00:00:10Z"),
    )
    rule = SamplingRule(product=OutputProduct.TRUTH_STATE, interval_s=3.0)
    assert tuple(epoch.value for epoch in iter_sampling_epochs(time_range, rule, adapter)) == (
        "2026-07-30T00:00:00Z",
        "2026-07-30T00:00:03Z",
        "2026-07-30T00:00:06Z",
        "2026-07-30T00:00:09Z",
        "2026-07-30T00:00:10Z",
    )


def test_time_adapter_rejects_cross_scale_and_utc_leap_second() -> None:
    adapter = SameScaleCalendarTimeAdapter()
    with pytest.raises(SimulationPreparationError, match="time scale"):
        adapter.compare(utc("2026-07-30T00:00:00Z"), tai("2026-07-30T00:00:37"))
    with pytest.raises(SimulationPreparationError, match="leap second"):
        adapter.add_seconds(utc("2016-12-31T23:59:60Z"), 1.0)
```

- [ ] **Step 2: Write failing event-merge tests**

Build a minimal manifest fixture with Truth interval 5 seconds, Attitude interval 10 seconds,
one PLANNED and one COMMAND entry at the same 5-second epoch. Assert one group at that epoch,
maneuvers `(PLANNED, COMMAND)`, and products sorted
`(ATTITUDE_STATE, TRUTH_STATE)` by enum value.

- [ ] **Step 3: Run tests and verify missing scheduler**

Run `uv run pytest packages/sycasphere-engine/tests/test_scheduling.py -q`.
Expected: module import failure.

- [ ] **Step 4: Implement exact same-scale arithmetic**

Parse calendar seconds into an integer day/second part plus `Decimal` fraction. Never call
`datetime.timestamp()` or float `total_seconds()`. Convert `interval_s` with
`Decimal(str(interval_s))`. Reject different time scales and any normalized value containing
`:60`. Serialize UTC with `Z`, TAI/TT without zone, and remove trailing fractional zeros.

- [ ] **Step 5: Implement lazy merge**

Use one look-ahead value per sampling iterator and one maneuver cursor. Never create a tuple of all
future sample epochs. At the selected minimum epoch, collect all equal maneuvers and due products.
For identical epochs, preserve the already assigned `order_index`.

- [ ] **Step 6: Run tests, type-check, and commit**

```powershell
uv run pytest packages/sycasphere-engine/tests/test_scheduling.py -q
uv run ruff format --check packages/sycasphere-engine
uv run ruff check packages/sycasphere-engine
uv run mypy
git add packages/sycasphere-engine/src/sycasphere/engine/scheduling.py `
  packages/sycasphere-engine/tests/test_scheduling.py
git commit -m "feat(engine): schedule deterministic event groups"
```

---

### Task 5: Implement transactional output sinks

**Files:**
- Create: `packages/sycasphere-engine/src/sycasphere/engine/sinks.py`
- Create: `packages/sycasphere-engine/tests/test_sinks.py`

**Interfaces:**
- Produces: `SimulationOutputSink`, `NullOutputSink`,
  `InMemoryOutputSink(max_records: int)`, `CompositeOutputSink`.
- Consumes: Task 1 summary models and Core scientific outputs.

- [ ] **Step 1: Write failing state-machine tests**

Define these local helpers at the top of `test_sinks.py`; sink unit tests do not inspect Manifest
content and therefore use a typed opaque sentinel rather than duplicating preparation fixtures:

```python
def make_manifest() -> SimulationExecutionManifest:
    return cast(SimulationExecutionManifest, object())


def make_truth_state() -> TruthState:
    epoch = Epoch(value="2026-07-30T00:00:00Z", time_scale=TimeScale.UTC)
    return TruthState(
        entity_id="spacecraft-1",
        cartesian_state=CartesianState(
            epoch=epoch,
            frame=FrameRef(kind=FrameKind.J2000),
            position_m=(7_000_000.0, 0.0, 0.0),
            velocity_mps=(0.0, 7_500.0, 0.0),
        ),
        mass_kg=500.0,
    )


def test_in_memory_sink_commits_bounded_records() -> None:
    manifest = make_manifest()
    truth_state = make_truth_state()
    sink = InMemoryOutputSink(max_records=3)
    sink.begin(manifest)
    sink.write_truth_states((truth_state,))
    sink.commit(SimulationOutputSummary(truth_state_count=1))
    assert sink.truth_states == (truth_state,)
    assert sink.status is SinkStatus.COMMITTED

    with pytest.raises(SimulationExecutionError, match="state"):
        sink.write_truth_states((truth_state,))


def test_in_memory_limit_aborts_and_clears() -> None:
    manifest = make_manifest()
    truth_state = make_truth_state()
    sink = InMemoryOutputSink(max_records=1)
    sink.begin(manifest)
    with pytest.raises(SimulationExecutionError) as caught:
        sink.write_truth_states((truth_state, truth_state))
    assert caught.value.detail.category is ErrorCategory.RESOURCE_EXHAUSTED
    assert sink.truth_states == ()
    assert sink.status is SinkStatus.ABORTED
```

Also reject `max_records` values `0`, `-1`, `True`, and `"10"`.

- [ ] **Step 2: Write failing composite order/rollback tests**

Use recording child sinks. Assert begin/write/commit order follows constructor order. If child 2
begin fails, assert child 1 receives abort and child 3 is untouched. Assert duplicate child object
references are rejected.

- [ ] **Step 3: Implement sink status and methods**

Use private mutable lists only in `InMemoryOutputSink`; expose tuples from properties. Every write
requires WRITING and a nonempty tuple of the exact Core type. `abort()` clears memory and is
idempotent only when already ABORTED with the same lifecycle; `commit()` succeeds once.

When Composite commit fails after earlier children committed, preserve the first failure and
best-effort abort only children that are still WRITING. Do not claim atomic rollback.

- [ ] **Step 4: Run focused gates and commit**

```powershell
uv run pytest packages/sycasphere-engine/tests/test_sinks.py -q
uv run ruff format --check packages/sycasphere-engine
uv run ruff check packages/sycasphere-engine
uv run mypy
git add packages/sycasphere-engine/src/sycasphere/engine/sinks.py `
  packages/sycasphere-engine/tests/test_sinks.py
git commit -m "feat(engine): add bounded output sinks"
```

---

### Task 6: Implement the deterministic FakeBackend

**Files:**
- Create: `packages/sycasphere-engine/src/sycasphere/engine/testing/__init__.py`
- Create: `packages/sycasphere-engine/src/sycasphere/engine/testing/fake_backend.py`
- Create: `packages/sycasphere-engine/tests/conftest.py`
- Create: `packages/sycasphere-engine/tests/test_fake_backend.py`

**Interfaces:**
- Produces:
  `FAKE_PLUGIN_MANIFEST`, `FakeBackendConfigurationValidator`,
  `FakeScienceBackendFactory`, `fake_backend_registration()`.
- Consumes: backend ports, same-scale time adapter and Core definitions.

- [ ] **Step 1: Create exact reusable Fake request fixtures**

In `conftest.py`, create `SchemaVersion(major=1, minor=0)` fixtures with:

```python
FAKE_BACKEND_ID = "sycasphere.testing.fake"
FAKE_DYNAMICS_ID = "sycasphere.testing.constant-velocity"
FAKE_ATTITUDE_ID = "sycasphere.testing.identity-attitude"
FAKE_PROPULSION_ID = "sycasphere.testing.impulsive-propulsion"
```

Construct one maneuver-capable spacecraft at
`r=(7_000_000.0, 0.0, 0.0) m`, `v=(0.0, 7_500.0, 0.0) m/s`,
mass `500.0 kg`, plus optional PLANNED/COMMAND J2000 Δv events.

- [ ] **Step 2: Write failing propagation and attitude tests**

```python
def test_fake_backend_propagates_constant_velocity_and_identity_attitude(
    fake_manifest,
) -> None:
    runtime = FakeScienceBackendFactory().create(fake_manifest)
    runtime.initialize()
    outcome = runtime.propagate_to(
        utc("2026-07-30T00:00:10Z"), CancellationToken()
    )
    truth = runtime.snapshot_truth()[0]
    attitude = runtime.snapshot_attitudes()[0]

    assert outcome is PropagationOutcome.REACHED_TARGET
    assert truth.cartesian_state.position_m == (7_000_000.0, 75_000.0, 0.0)
    assert truth.cartesian_state.velocity_mps == (0.0, 7_500.0, 0.0)
    assert attitude.rotation_reference_to_body_wxyz == (1.0, 0.0, 0.0, 0.0)
    assert attitude.angular_velocity_body_wrt_reference_rad_s == (0.0, 0.0, 0.0)
```

- [ ] **Step 3: Write failing impulse and mass tests**

At the runtime current epoch, execute a J2000 impulse `(1.0, -2.0, 0.5)`. Assert unchanged position
and mass, changed velocity, exact actual Δv, equal before/after epoch, and independent frozen Core
models. Reject finite burn, non-J2000 impulse, wrong entity, and wrong event epoch.

- [ ] **Step 4: Write failing validator/manifest tests**

Assert exact manifest identity/version/capabilities, empty backend/model configuration, empty
environment model/data refs, accepted GroundStation without Truth, and rejection of unknown
dynamics/attitude/propulsion IDs.

The exact Fake manifest is:

```python
PluginManifest(
    ref=PluginRef(
        plugin_id="sycasphere.testing.fake",
        implementation_version="0.1.0",
        interface_version=SchemaVersion(major=1, minor=0),
    ),
    kind=PluginKind.SCIENCE_BACKEND,
    capabilities=frozenset(
        {
            "attitude.identity-wxyz",
            "dynamics.constant-velocity",
            "frame.j2000",
            "maneuver.impulsive.j2000",
            "output.attitude",
            "output.truth",
            "time.same-scale",
        }
    ),
    configuration_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    deterministic=True,
    resources=ResourceRequirements(),
)
```

- [ ] **Step 5: Implement Fake validator, factory, and runtime**

Keep mutable numerical state in a private per-entity dataclass of independent NumPy `float64`
position/velocity arrays, mass, and epoch. `snapshot_truth()` reconstructs Core models sorted by
entity ID. Runtime initialization, propagation, maneuver, snapshot after close, and double close
must follow tested state rules; `close()` itself is idempotent.

- [ ] **Step 6: Run focused gates and commit**

```powershell
uv run pytest packages/sycasphere-engine/tests/test_fake_backend.py -q
uv run ruff format --check packages/sycasphere-engine
uv run ruff check packages/sycasphere-engine
uv run mypy
git add packages/sycasphere-engine/src/sycasphere/engine/testing `
  packages/sycasphere-engine/tests/conftest.py `
  packages/sycasphere-engine/tests/test_fake_backend.py
git commit -m "feat(engine): add deterministic fake backend"
```

---

### Task 7: Prepare immutable execution manifests

**Files:**
- Create: `packages/sycasphere-engine/src/sycasphere/engine/preparation.py`
- Create: `packages/sycasphere-engine/tests/test_preparation.py`

**Interfaces:**
- Produces:

```python
class ManifestPreparer:
    def __init__(self, registry: PluginRegistry) -> None: ...
    def prepare(self, request: SimulationRunRequest) -> SimulationExecutionManifest: ...
```

- Consumes: Registry, registration validator/time adapter, Core Manifest factory.

- [ ] **Step 1: Write failing happy-path and no-runtime tests**

In `test_preparation.py`, derive a recording registration from the public Fake helper:

```python
@dataclass
class RecordingFactory:
    delegate: ScienceBackendFactory
    create_calls: int = 0

    def create(
        self, manifest: SimulationExecutionManifest
    ) -> ScienceBackendRuntime:
        self.create_calls += 1
        return self.delegate.create(manifest)


@pytest.fixture
def recording_fake_registration() -> ScienceBackendRegistration:
    base = fake_backend_registration()
    return replace(base, factory=RecordingFactory(base.factory))
```

Then write:

```python
def test_prepare_resolves_backend_without_creating_runtime(
    fake_request, recording_fake_registration
) -> None:
    preparer = ManifestPreparer(PluginRegistry((recording_fake_registration,)))
    manifest = preparer.prepare(fake_request)

    assert manifest.source_request == fake_request
    assert manifest.resolved_plugins[0].component_id == "science-backend"
    assert manifest.resolved_external_data == ()
    assert manifest.derived_random_streams == ()
    assert recording_fake_registration.factory.create_calls == 0
```

Call `prepare()` twice and assert model dumps and `content_hash` are identical.

- [ ] **Step 2: Write failing scope and time tests**

Parameterize mutations and assert these exact `SimulationPreparationError` categories:

- observation schedules or link models -> `UNSUPPORTED_MEASUREMENT`;
- non-J2000 initial states or maneuvers -> `UNSUPPORTED_FRAME`;
- Geometry/Diagnostics outputs, finite burns, mixed time scales, UTC leap seconds, nonempty
  environment refs, or unknown Fake model IDs -> `PLUGIN_INCOMPATIBLE`;
- a deliberately bypass-constructed request whose output interval is non-positive ->
  `VALIDATION_ERROR` when `prepare()` revalidates the public boundary.

- [ ] **Step 3: Write failing maneuver ordering tests**

Create two PLANNED and two COMMAND events at one epoch in deliberately nonlexical ID order. Assert
prepared sources are `(PLANNED, PLANNED, COMMAND, COMMAND)`, each source preserves request tuple
order, and indices are exactly `0..3`. Add an earlier pre-start PLANNED event and assert it sorts
before the formal-start entries.

- [ ] **Step 4: Implement request snapshot, scope checks, and timeline**

Revalidate with:

```python
validated_request = SimulationRunRequest.model_validate(
    request.model_dump(mode="python")
)
```

Resolve the exact backend registration; call its configuration validator once. Compare all epochs
with its time adapter. Stable-sort `(source_priority, source_position)` only after primary absolute
epoch comparison. Build `ResolvedPluginRecord.create(...)`, copy exact external refs for generic
registrations, use no random streams for Fake, and call
`SimulationExecutionManifest.create(...)`.

Catch Pydantic/ValueError failures once at the public boundary and convert them to
`SimulationPreparationError`; never catch an already structured Engine error and recategorize it.

- [ ] **Step 5: Run focused gates and commit**

```powershell
uv run pytest packages/sycasphere-engine/tests/test_preparation.py -q
uv run ruff format --check packages/sycasphere-engine
uv run ruff check packages/sycasphere-engine
uv run mypy
git add packages/sycasphere-engine/src/sycasphere/engine/preparation.py `
  packages/sycasphere-engine/tests/test_preparation.py
git commit -m "feat(engine): prepare immutable run manifests"
```

---

### Task 8: Execute batch runs through the public SimulationEngine

**Files:**
- Create: `packages/sycasphere-engine/src/sycasphere/engine/execution.py`
- Create: `packages/sycasphere-engine/src/sycasphere/engine/api.py`
- Create: `packages/sycasphere-engine/tests/test_execution.py`

**Interfaces:**
- Produces:

```python
class SimulationEngine:
    def __init__(self, plugin_registry: PluginRegistry, *, batch_size: int = 256) -> None: ...
    def prepare(self, request: SimulationRunRequest) -> SimulationExecutionManifest: ...
    def run(
        self,
        manifest: SimulationExecutionManifest,
        sink: SimulationOutputSink,
        cancellation: CancellationProbe,
    ) -> SimulationExecutionResult: ...
```

- Consumes: Tasks 1–7.

- [ ] **Step 1: Write failing end-to-end Truth run test**

```python
def test_engine_runs_fake_backend_to_committed_truth(
    fake_request, fake_registration
) -> None:
    engine = SimulationEngine(
        PluginRegistry((fake_registration,)),
        batch_size=2,
    )
    manifest = engine.prepare(fake_request)
    sink = InMemoryOutputSink(max_records=100)
    result = engine.run(manifest, sink, CancellationToken())

    assert result.status is SimulationExecutionStatus.COMPLETED
    assert result.final_epoch == fake_request.time_range.end
    assert sink.status is SinkStatus.COMMITTED
    assert result.output_summary.truth_state_count == len(sink.truth_states)
    assert sink.truth_states[-1].epoch == fake_request.time_range.end
```

- [ ] **Step 2: Write failing post-maneuver and provenance tests**

Use one PLANNED then one COMMAND impulse at the same sample epoch. Assert two
`TruthManeuver` records, sources/IDs preserved, state chaining exact, and the ordinary Truth sample
contains the velocity after both impulses.

- [ ] **Step 3: Write failing cancellation tests**

Cover separately:

1. token cancelled before `run()`: no factory, runtime, or sink call; Result stops at
   `synchronization_epoch`;
2. cancellation returned from `propagate_to()`: sink aborts once, runtime closes once, Result uses
   runtime `current_epoch`;
3. cancellation set after the last group but before commit: no commit, one abort;
4. a same-epoch group with multiple maneuvers completes atomically before cancellation takes effect.

- [ ] **Step 4: Write failing error precedence and cleanup tests**

Use recording fakes for factory failure, initialize failure, sink begin/write/commit failure, runtime
close failure, and abort failure. Assert:

- sink is untouched before successful begin;
- runtime closes at most once;
- runtime closes before sink commit;
- the first causal `ErrorDetail` remains the raised `SimulationExecutionError.detail`;
- cleanup failures do not replace it;
- Java/Python exception objects and tracebacks never appear in public context.

- [ ] **Step 5: Implement batch buffers and event loop**

Create three typed buffers. Flush a buffer when it reaches `batch_size`; never change item order.
For each `ScheduledEventGroup`:

```python
outcome = runtime.propagate_to(group.epoch, cancellation)
if outcome is PropagationOutcome.CANCELLED:
    return cancel_after_begin(runtime.current_epoch)

for entry in group.maneuvers:
    physical = runtime.execute_impulsive_maneuver(entry)
    truth_maneuver = TruthManeuver(
        maneuver_event_id=entry.event_id,
        source_kind=ManeuverTruthSource(entry.source.value),
        source_id=entry.event_id,
        entity_id=entry.spacecraft_id,
        scheduled_epoch=entry.epoch,
        executed_epoch=physical.executed_epoch,
        actual_delta_v_j2000_mps=physical.actual_delta_v_j2000_mps,
        state_before=physical.state_before,
        state_after=physical.state_after,
    )
```

Emit snapshots only for due products. Count records when accepted into buffers, not when batches are
flushed. Flush, close runtime, then commit. On active-run cancellation, abort and return CANCELLED;
on failure, abort when begun and raise structured execution error.

- [ ] **Step 6: Implement the public facade and validate batch size**

Require `type(batch_size) is int and batch_size > 0`. `prepare()` delegates to one
`ManifestPreparer`; `run()` delegates to one stateless `BatchRunner` using the same immutable
registry.

- [ ] **Step 7: Verify batch-size invariance**

Run the same Manifest with batch sizes `1`, `2`, and `1024` into separate bounded memory sinks.
Assert each sink's three output tuples and each Result summary are equal.

Add a second test named `test_repeated_engine_instances_produce_identical_serialized_outputs`.
Construct two fresh registries, engines, tokens and sinks from the same request; assert Manifest
`model_dump_json()` values, Result `model_dump_json()` values, and each serialized sink record tuple
are equal.

- [ ] **Step 8: Run focused gates and commit**

```powershell
uv run pytest packages/sycasphere-engine/tests/test_execution.py -q
uv run ruff format --check packages/sycasphere-engine
uv run ruff check packages/sycasphere-engine
uv run mypy
git add packages/sycasphere-engine/src/sycasphere/engine/execution.py `
  packages/sycasphere-engine/src/sycasphere/engine/api.py `
  packages/sycasphere-engine/tests/test_execution.py
git commit -m "feat(engine): run cancellable truth simulations"
```

---

### Task 9: Publish Engine API, schemas, package docs, and distributions

**Files:**
- Modify: `packages/sycasphere-engine/src/sycasphere/engine/__init__.py`
- Create: `packages/sycasphere-engine/tests/test_public_api.py`
- Create: `packages/sycasphere-engine/tests/test_package.py`
- Create: `packages/sycasphere-engine/tests/fixtures/readme_fake_run.py`
- Create: `packages/sycasphere-engine/README.md`
- Modify: `README.md`
- Modify: `packages/sycasphere-core/README.md`
- Modify: `docs/architecture/core-data-model-v0.2.md`
- Modify: `docs/architecture/algorithm-integration-v0.2.md`
- Modify:
  `docs/superpowers/specs/2026-07-20-sycasphere-runtime-and-simulation-engine-design.md`

**Interfaces:**
- Produces: reviewed Engine `__all__`, version `0.1.0`, executable README example, truthful
  implementation status.

- [ ] **Step 1: Add failing exact public API tests**

Set the exact public set:

```python
EXPECTED_ENGINE_EXPORTS = {
    "CancellationProbe",
    "CancellationToken",
    "CompositeOutputSink",
    "InMemoryOutputSink",
    "ManeuverExecution",
    "NullOutputSink",
    "PluginRegistry",
    "PreparationTimeAdapter",
    "PropagationOutcome",
    "ScienceBackendFactory",
    "ScienceBackendRegistration",
    "ScienceBackendRuntime",
    "SimulationEngine",
    "SimulationEngineError",
    "SimulationExecutionError",
    "SimulationOutputSink",
    "SimulationPreparationError",
}
```

Assert `set(sycasphere.engine.__all__)` equals it and `__version__ == "0.1.0"`. Assert testing-only
Fake symbols are imported from `sycasphere.engine.testing`, not root Engine.

- [ ] **Step 2: Add failing README/package boundary tests**

Assert README documents:

- `prepare()` then synchronous `run()`;
- bounded `InMemoryOutputSink(max_records=...)`;
- FakeBackend is non-scientific;
- v0.1 J2000/same-scale/impulse limitations;
- Manifest excludes lifecycle state;
- Observation, Session and Orekit remain planned.

Add wheel metadata tests parallel to Core's `test_package.py`.

- [ ] **Step 3: Export the reviewed API and write an executable example**

The Engine README example must construct the exact Fake model IDs, call
`fake_backend_registration()`, prepare, run, and print Result counts. Do not show unlimited in-memory
collection.

- [ ] **Step 4: Synchronize authoritative status documents**

Change only evidence-backed status statements:

- Engine v0.1 prepare/run, explicit registry, FakeBackend and sinks are implemented;
- Observation pipeline, interactive Session, Orekit, Sim retention, Platform lifecycle and frontend
  remain planned;
- `SimulationExecutionResult` is not `RunOutcome`;
- Fake mass remains constant because current impulse input has no consumption quantity.

- [ ] **Step 5: Build and inspect Engine artifacts**

```powershell
$buildRoot = Join-Path '.build' ('engine-v0.1-' + [guid]::NewGuid().ToString('N'))
uv build --offline --no-build-isolation --package sycasphere-engine --out-dir $buildRoot
```

Verify wheel/sdist contain Engine modules, `py.typed`, LICENSE and metadata; wheel excludes tests,
repository docs, Core source, Orekit/JPype/Java, and `docs/assets/`.

Create an isolated Python 3.12 environment, install the built Core and Engine wheels, run
`uv pip check`, import all reviewed public names, and execute the README Fake run.

Use:

```powershell
$coreBuild = Join-Path $buildRoot 'core'
$engineBuild = Join-Path $buildRoot 'engine'
$isolated = Join-Path $buildRoot 'venv'
uv build --offline --no-build-isolation --package sycasphere-core --out-dir $coreBuild
uv build --offline --no-build-isolation --package sycasphere-engine --out-dir $engineBuild
uv venv --python 3.12 $isolated
$isolatedPython = Join-Path $isolated 'Scripts/python.exe'
$coreWheel = Get-ChildItem $coreBuild -Filter '*.whl' | Select-Object -First 1 -ExpandProperty FullName
$engineWheel = Get-ChildItem $engineBuild -Filter '*.whl' | Select-Object -First 1 -ExpandProperty FullName
uv pip install --offline --python $isolatedPython $coreWheel $engineWheel
uv pip check --python $isolatedPython
& $isolatedPython -c "import sycasphere.core, sycasphere.engine; print(sycasphere.engine.__version__)"
```

Move the README example body into
`packages/sycasphere-engine/tests/fixtures/readme_fake_run.py` and execute it both from pytest and
with `& $isolatedPython packages/sycasphere-engine/tests/fixtures/readme_fake_run.py`; the wheel
itself must not contain this test fixture.

- [ ] **Step 6: Run package gates and commit**

```powershell
uv run pytest packages/sycasphere-engine/tests/test_public_api.py `
  packages/sycasphere-engine/tests/test_package.py -q
uv run ruff format --check .
uv run ruff check .
uv run mypy
git add README.md packages/sycasphere-core/README.md `
  packages/sycasphere-engine/README.md `
  packages/sycasphere-engine/src/sycasphere/engine/__init__.py `
  packages/sycasphere-engine/tests/test_public_api.py `
  packages/sycasphere-engine/tests/test_package.py `
  docs/architecture/core-data-model-v0.2.md `
  docs/architecture/algorithm-integration-v0.2.md `
  docs/superpowers/specs/2026-07-20-sycasphere-runtime-and-simulation-engine-design.md
git commit -m "docs(engine): publish batch runtime v0.1"
```

---

### Task 10: Run full verification and independent review

**Files:**
- Modify only when a failing regression or review finding proves a defect.

**Interfaces:**
- Consumes: final Tasks 1–9 branch.
- Produces: release evidence and a review-clean branch ready for integration.

- [ ] **Step 1: Run the complete mandated quality gate**

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

Expected: all commands pass with no new warnings.

- [ ] **Step 2: Run determinism and installation tests from clean processes**

Run the determinism test twice in separate processes:

```powershell
uv run pytest packages/sycasphere-engine/tests/test_execution.py::test_repeated_engine_instances_produce_identical_serialized_outputs -q
uv run pytest packages/sycasphere-engine/tests/test_execution.py::test_repeated_engine_instances_produce_identical_serialized_outputs -q
```

Rebuild both Core and Engine sdist/wheel into a new `.build/<guid>` directory and repeat the exact
isolated installation/import/README execution from Task 9 Step 5.

- [ ] **Step 3: Review the complete branch diff**

```powershell
$implementationBase = git merge-base main HEAD
git diff --check "$implementationBase..HEAD"
git diff --stat "$implementationBase..HEAD"
git status -sb
```

Inspect every changed line for:

- frame or J2000 mapping mistakes;
- cross-scale or leap-second acceptance;
- incorrect SI units or quaternion ordering;
- Truth/Ideal/Reported leakage;
- Manifest mutation or lifecycle fields;
- mutable array/container escape;
- partial same-epoch maneuver execution;
- sink commit before runtime close;
- unlimited memory retention;
- accidental Orekit/JPype/infrastructure imports;
- unrequested Observation, Session, Platform or frontend implementation.

- [ ] **Step 4: Request independent code review**

Use `requesting-code-review` with:

- base commit: `git merge-base main HEAD`;
- head commit: current HEAD;
- requirements: the 2026-07-30 Engine design and this plan;
- focus: time arithmetic, event ordering, cancellation atomicity, error precedence, sink state
  transitions, plugin isolation, deterministic manifests, package boundaries.

- [ ] **Step 5: Resolve findings with regression tests**

For each Critical, Important or Minor finding:

1. add one focused test that fails for the reported behavior;
2. run it and record the expected failure;
3. make the smallest in-scope fix;
4. rerun the focused test and full gate;
5. commit the test and fix together.

Do not waive a finding without documenting concrete contradictory evidence.

- [ ] **Step 6: Finish the branch**

Confirm the tracked worktree is clean while leaving unrelated `docs/assets/` untouched. Use
`finishing-a-development-branch` to offer local merge, PR, keep or discard. Do not push `main`
directly; if publishing, push the feature branch and create a draft PR.

---

## Final Acceptance Checklist

After Task 10:

1. Core result models and configuration-hash factory are public, frozen and schema-tested.
2. Engine imports and Fake runs without JDK, JPype or Orekit.
3. `prepare()` never creates runtime and produces identical Manifest hashes for identical inputs.
4. `run()` is synchronous, bounded, cancellable and preserves post-maneuver sampling.
5. PLANNED/COMMAND provenance and same-epoch ordering are deterministic.
6. Fake dynamics, identity WXYZ attitude, unchanged mass and impulse behavior match the design.
7. Sink, runtime and error precedence state matrices pass.
8. Batch size does not alter scientific output.
9. Ruff, mypy, pytest, wheel/sdist and isolated installation all pass.
10. Documentation marks only implemented v0.1 capabilities complete.
11. Independent review has no unresolved findings.
12. No unrelated file, especially `docs/assets/`, was staged or modified.
