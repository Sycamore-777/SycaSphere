# Simulation Definition and Execution Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `sycasphere-core` 中交付已批准的仿真定义、机动、调度、执行请求和不可变执行清单契约，并使其可由后续独立 Engine 包直接使用。

**Architecture:** 新契约按机动、仿真场景、调度和执行四个职责拆分，复用现有冻结 Pydantic v2 边界模型；跨对象引用和不需要科学后端的约束在 Core 构造期校验。规范 JSON、SHA-256 和随机种子派生集中在私有标准库模块中，Engine 后续只负责插件、外部数据和跨时间尺度解析，不把 Orekit、JPype 或基础设施对象带入 Core。

**Tech Stack:** Python 3.12、Pydantic v2、NumPy（仅复用现有状态模型）、pytest、Ruff、mypy、标准库 `json`/`hashlib`、uv。

## Global Constraints

- 权威设计为 `docs/superpowers/specs/2026-07-26-simulation-definition-and-execution-input-design.md`，同时受三个项目权威架构文档约束。
- 本计划只修改 `sycasphere-core`、对应测试、公开模式快照和文档；不创建 Engine、Orekit、Sim、Platform 或前端实现。
- Core 不得依赖或导入 Orekit、JPype、Java、FastAPI、SQLite、PyArrow、Platform 或 Engine。
- 所有公开模型使用 Pydantic v2、`frozen=True`、`extra="forbid"`；集合输入复制后保存为不可变值。
- 严格数值字段拒绝 `bool`、整数冒充浮点数、字符串数值和非有限浮点数。
- 所有内部物理量使用 SI 单位；向量边界使用固定长度元组；四元数固定使用 `w, x, y, z`。
- 公共惯性系名称固定为 `J2000`；`WGS84` 仍是参考椭球，不是坐标系。
- `SimulationDefinition`、`SimulationRunRequest` 和 `SimulationExecutionManifest` 是不同模型；Manifest 不含墙上时间、运行状态、错误、输出哈希或本地路径。
- `SimulationRunRequest` 内嵌完整 `SimulationDefinition`，不接受数据库或修订引用。
- 测量模型和误差模型只从传感器选择；只有链路模型保留为运行级 `link_models`。
- 首版所有空间对象初始状态时刻必须与 `synchronization_epoch` 完全相等。
- 首版调度只支持 `PERIODIC` 和 `EXPLICIT`；首版命令时间线只支持机动。
- 首版稳定发布脉冲和恒定推力有限燃烧格式；真正执行有限燃烧不属于本批次。
- 规范化版本固定为 `SYCASPHERE_CANONICAL_JSON_V1`，随机派生版本固定为 `SYCASPHERE_SEED_V1`，哈希固定为 SHA-256。
- 不增加生产依赖；所有新 Python 文件必须使用项目规定的 Sycamore 文件头并准确写明用途、日期和功能。
- 每个行为遵循测试先行：先观察目标测试因缺少行为而失败，再写最小实现并观察通过。
- 不修改或提交用户未跟踪的 `docs/assets/`。

---

## File Structure

### Production modules

- Create `packages/sycasphere-core/src/sycasphere/core/_canonical.py`
  - 私有规范 JSON、SHA-256 和 64 位派生种子实现。
- Create `packages/sycasphere-core/src/sycasphere/core/maneuvers.py`
  - 机动能力、脉冲/有限燃烧载荷、预设机动和运行命令。
- Modify `packages/sycasphere-core/src/sycasphere/core/entities.py`
  - 为 `SpacecraftDefinition` 增加可选 `maneuver_capability`。
- Create `packages/sycasphere-core/src/sycasphere/core/simulations.py`
  - 中心天体、外部数据、环境和完整仿真定义。
- Create `packages/sycasphere-core/src/sycasphere/core/schedules.py`
  - 运行时间范围、输出采样和两类观测调度。
- Create `packages/sycasphere-core/src/sycasphere/core/execution.py`
  - 后端绑定、运行请求、准备记录和不可变执行清单。
- Modify `packages/sycasphere-core/src/sycasphere/core/__init__.py`
  - 显式发布经过审查的新公共契约。

### Tests and reviewed schemas

- Create `packages/sycasphere-core/tests/test_canonical.py`
- Create `packages/sycasphere-core/tests/test_maneuvers.py`
- Create `packages/sycasphere-core/tests/test_simulations.py`
- Create `packages/sycasphere-core/tests/test_schedules.py`
- Create `packages/sycasphere-core/tests/test_execution.py`
- Modify `packages/sycasphere-core/tests/test_entities.py`
- Modify `packages/sycasphere-core/tests/test_public_api.py`
- Modify `packages/sycasphere-core/tests/snapshots/core-schemas.json`
- Reuse `tests/architecture/test_core_dependency_boundary.py` without changing its forbidden-dependency policy.

### Documentation

- Modify `packages/sycasphere-core/README.md`
- Modify `README.md`
- Modify `docs/architecture/core-data-model-v0.2.md`
- Modify `docs/architecture/algorithm-integration-v0.2.md`
- Modify `docs/superpowers/specs/2026-07-20-sycasphere-runtime-and-simulation-engine-design.md`

---

### Task 1: Canonical JSON, hashing, and seed derivation

**Files:**
- Create: `packages/sycasphere-core/src/sycasphere/core/_canonical.py`
- Create: `packages/sycasphere-core/tests/test_canonical.py`

**Interfaces:**
- Consumes: `SchemaVersion`; Pydantic `BaseModel`; ordinary JSON-compatible values.
- Produces:
  - `CANONICALIZATION_VERSION: Final[str] = "SYCASPHERE_CANONICAL_JSON_V1"`
  - `RANDOM_DERIVATION_VERSION: Final[str] = "SYCASPHERE_SEED_V1"`
  - `canonical_json_bytes(value: BaseModel | JsonValue) -> bytes`
  - `sha256_canonical_json(value: BaseModel | JsonValue) -> str`
  - `derive_random_seed(master_seed: int, component_id: str, purpose: str, interface_version: SchemaVersion) -> int`

- [ ] **Step 1: Write failing canonicalization tests**

Create tests with these exact behaviors:

```python
def test_canonical_json_sorts_keys_preserves_unicode_and_has_no_spaces() -> None:
    value = {"z": "轨道", "a": {"y": 2.0, "x": 1.0}}
    assert canonical_json_bytes(value) == (
        '{"a":{"x":1.0,"y":2.0},"z":"轨道"}'.encode("utf-8")
    )


def test_canonical_json_normalizes_negative_zero_recursively() -> None:
    assert canonical_json_bytes({"values": [-0.0, {"x": -0.0}]}) == (
        b'{"values":[0.0,{"x":0.0}]}'
    )


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_canonical_json_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        canonical_json_bytes({"value": value})


def test_sha256_canonical_json_is_order_independent() -> None:
    assert sha256_canonical_json({"b": 2, "a": 1}) == sha256_canonical_json(
        {"a": 1, "b": 2}
    )


def test_seed_v1_has_a_locked_known_vector() -> None:
    seed = derive_random_seed(
        42,
        "sensor-1",
        "reported-noise",
        SchemaVersion(major=1, minor=0),
    )
    assert seed == 16_402_414_253_369_765_323


@pytest.mark.parametrize("master_seed", [-1, 2**64, True, 1.0])
def test_seed_derivation_rejects_values_outside_unsigned_64_bit(
    master_seed: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        derive_random_seed(
            master_seed,  # type: ignore[arg-type]
            "sensor-1",
            "reported-noise",
            SchemaVersion(major=1, minor=0),
        )
```

- [ ] **Step 2: Run the tests and verify the missing module failure**

Run:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv run pytest packages/sycasphere-core/tests/test_canonical.py -q
```

Expected: collection fails because `sycasphere.core._canonical` does not exist.

- [ ] **Step 3: Implement the exact V1 algorithms**

Implement the recursive normalizer and functions with these signatures and semantics:

```python
CANONICALIZATION_VERSION: Final = "SYCASPHERE_CANONICAL_JSON_V1"
RANDOM_DERIVATION_VERSION: Final = "SYCASPHERE_SEED_V1"
_UINT64_MAX: Final = 2**64 - 1


def _normalize_canonical_value(value: Any) -> JsonValue:
    if isinstance(value, BaseModel):
        return _normalize_canonical_value(value.model_dump(mode="json"))
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON floating-point values must be finite")
        return 0.0 if value == 0.0 else value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("canonical JSON object keys must be strings")
        return {
            key: _normalize_canonical_value(nested)
            for key, nested in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_canonical_value(item) for item in value]
    raise ValueError(f"value of type {type(value).__name__} is not JSON-compatible")


def canonical_json_bytes(value: BaseModel | JsonValue) -> bytes:
    normalized = _normalize_canonical_value(value)
    return json.dumps(
        normalized,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_canonical_json(value: BaseModel | JsonValue) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def derive_random_seed(
    master_seed: int,
    component_id: str,
    purpose: str,
    interface_version: SchemaVersion,
) -> int:
    if type(master_seed) is not int:
        raise TypeError("master_seed must be a built-in integer")
    if not 0 <= master_seed <= _UINT64_MAX:
        raise ValueError("master_seed must be an unsigned 64-bit integer")
    if not component_id.strip() or not purpose.strip():
        raise ValueError("component_id and purpose must not be blank")
    payload: JsonValue = [
        master_seed,
        component_id,
        purpose,
        interface_version.model_dump(mode="json"),
    ]
    digest = hashlib.sha256(canonical_json_bytes(payload)).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)
```

Keep this module private; do not add its functions or constants to `sycasphere.core.__all__`.

- [ ] **Step 4: Run focused tests and static checks**

Run:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv run pytest packages/sycasphere-core/tests/test_canonical.py -q
uv run ruff check packages/sycasphere-core/src/sycasphere/core/_canonical.py packages/sycasphere-core/tests/test_canonical.py
uv run mypy packages/sycasphere-core/src/sycasphere/core/_canonical.py
```

Expected: all commands exit `0`; canonical test count is at least 8.

- [ ] **Step 5: Commit**

```powershell
git add packages/sycasphere-core/src/sycasphere/core/_canonical.py packages/sycasphere-core/tests/test_canonical.py
git commit -m "feat(core): add canonical execution hashing"
```

---

### Task 2: Maneuver contracts and spacecraft capability

**Files:**
- Create: `packages/sycasphere-core/src/sycasphere/core/maneuvers.py`
- Create: `packages/sycasphere-core/tests/test_maneuvers.py`
- Modify: `packages/sycasphere-core/src/sycasphere/core/entities.py`
- Modify: `packages/sycasphere-core/tests/test_entities.py`

**Interfaces:**
- Consumes: `DefinitionString`, `Epoch`, `FrameRef`, `FrameKind`, `CoordinateRepresentation`, `ModelRef`.
- Produces:
  - `ManeuverType`
  - `ManeuverCapability`
  - `ImpulsiveManeuverSpec`
  - `FiniteBurnManeuverSpec`
  - `ManeuverSpec`
  - `PlannedTruthManeuver`
  - `ManeuverCommand`
  - `_validate_maneuver_binding(maneuver: ManeuverSpec, spacecraft_id: str, epoch: Epoch, capability: ManeuverCapability | None) -> None`
  - `SpacecraftDefinition.maneuver_capability`

- [ ] **Step 1: Write failing maneuver tests**

Cover these public shapes and invalid cases:

```python
def test_impulsive_and_finite_burn_are_discriminated_and_frozen() -> None:
    impulse = ImpulsiveManeuverSpec(
        maneuver_type="IMPULSIVE",
        delta_v_mps=(0.0, 1.0, 0.0),
        frame=FrameRef(kind=FrameKind.J2000),
    )
    burn = FiniteBurnManeuverSpec(
        maneuver_type="FINITE_BURN",
        duration_s=30.0,
        thrust_n=(0.0, 20.0, 0.0),
        frame=FrameRef(kind=FrameKind.J2000),
    )
    assert TypeAdapter(ManeuverSpec).validate_python(
        impulse.model_dump(mode="json")
    ) == impulse
    assert TypeAdapter(ManeuverSpec).validate_python(
        burn.model_dump(mode="json")
    ) == burn
    with pytest.raises(ValidationError):
        impulse.delta_v_mps = (1.0, 0.0, 0.0)


@pytest.mark.parametrize(
    ("model", "field_name", "invalid"),
    [
        (ImpulsiveManeuverSpec, "delta_v_mps", (0.0, 0.0, 0.0)),
        (ImpulsiveManeuverSpec, "delta_v_mps", (1, 0.0, 0.0)),
        (ImpulsiveManeuverSpec, "delta_v_mps", (math.nan, 0.0, 0.0)),
        (FiniteBurnManeuverSpec, "duration_s", 0.0),
        (FiniteBurnManeuverSpec, "duration_s", 1),
        (FiniteBurnManeuverSpec, "thrust_n", (0.0, 0.0, 0.0)),
    ],
)
def test_maneuver_payloads_reject_invalid_strict_values(
    model: type[BaseModel], field_name: str, invalid: object
) -> None:
    valid_data: dict[type[BaseModel], dict[str, object]] = {
        ImpulsiveManeuverSpec: {
            "maneuver_type": "IMPULSIVE",
            "delta_v_mps": (0.0, 1.0, 0.0),
            "frame": FrameRef(kind=FrameKind.J2000),
        },
        FiniteBurnManeuverSpec: {
            "maneuver_type": "FINITE_BURN",
            "duration_s": 30.0,
            "thrust_n": (0.0, 20.0, 0.0),
            "frame": FrameRef(kind=FrameKind.J2000),
        },
    }
    data = dict(valid_data[model])
    data[field_name] = invalid
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_local_maneuver_frame_must_match_spacecraft_and_command_epoch() -> None:
    with pytest.raises(ValidationError, match="owner_id"):
        ManeuverCommand(
            command_id="cmd-1",
            spacecraft_id="spacecraft-1",
            epoch=EPOCH,
            maneuver=ImpulsiveManeuverSpec(
                delta_v_mps=(0.0, 1.0, 0.0),
                frame=FrameRef(
                    kind=FrameKind.LVLH,
                    owner_id="other",
                    convention="TNW_RH",
                    reference_epoch=EPOCH,
                ),
            ),
        )


def test_spacecraft_maneuver_capability_is_optional_and_strict() -> None:
    spacecraft = make_spacecraft(
        maneuver_capability=ManeuverCapability(
            supported_types=("IMPULSIVE",),
            propulsion_model=model_ref("sycasphere.propulsion.impulsive"),
        )
    )
    assert spacecraft.maneuver_capability is not None
    assert spacecraft.maneuver_capability.supported_types == frozenset(
        {ManeuverType.IMPULSIVE}
    )
```

The parameterized test must instantiate each model from a known-valid dictionary, replace the named field, and assert `ValidationError`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv run pytest packages/sycasphere-core/tests/test_maneuvers.py packages/sycasphere-core/tests/test_entities.py -q
```

Expected: collection fails on missing maneuver exports/module.

- [ ] **Step 3: Implement maneuver types**

Use these exact public declarations:

```python
type FiniteManeuverComponent = Annotated[
    float,
    Strict(),
    AllowInfNan(False),
]
type PositiveFiniteManeuverFloat = Annotated[
    float,
    Strict(),
    AllowInfNan(False),
    Field(gt=0.0),
]


class ManeuverType(StrEnum):
    IMPULSIVE = "IMPULSIVE"
    FINITE_BURN = "FINITE_BURN"


class ManeuverCapability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    supported_types: frozenset[ManeuverType]
    propulsion_model: ModelRef


class ImpulsiveManeuverSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    maneuver_type: Literal[ManeuverType.IMPULSIVE] = ManeuverType.IMPULSIVE
    delta_v_mps: tuple[FiniteManeuverComponent, FiniteManeuverComponent, FiniteManeuverComponent]
    frame: FrameRef


class FiniteBurnManeuverSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    maneuver_type: Literal[ManeuverType.FINITE_BURN] = ManeuverType.FINITE_BURN
    duration_s: PositiveFiniteManeuverFloat
    thrust_n: tuple[FiniteManeuverComponent, FiniteManeuverComponent, FiniteManeuverComponent]
    frame: FrameRef


type ManeuverSpec = Annotated[
    ImpulsiveManeuverSpec | FiniteBurnManeuverSpec,
    Field(discriminator="maneuver_type"),
]


class PlannedTruthManeuver(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    maneuver_id: DefinitionString
    spacecraft_id: DefinitionString
    epoch: Epoch
    maneuver: ManeuverSpec


class ManeuverCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    command_id: DefinitionString
    spacecraft_id: DefinitionString
    epoch: Epoch
    maneuver: ManeuverSpec
```

Required validators:

- Normalize `supported_types` before frozenset conversion, reject empty/duplicate values, and serialize sorted by enum value.
- Apply a `mode="before"` validator that rejects anything whose concrete type is not built-in `float` for every vector element and `duration_s`; the annotated types then reject non-finite values.
- Reject non-finite values and zero vectors using `math.isclose(norm, 0.0, abs_tol=0.0)`.
- Require maneuver frames to use `CARTESIAN`; reject `SENSOR`.
- For `LVLH`, `VVLH`, and `BODY`, require `owner_id == spacecraft_id` and `reference_epoch == epoch`.
- `_validate_maneuver_binding` accepts `maneuver`, `spacecraft_id`, `epoch`, and `capability`; it rejects absent capability or an unsupported maneuver type and reuses the frame checks.

- [ ] **Step 4: Add capability to spacecraft**

Add only this field to `SpacecraftDefinition`:

```python
maneuver_capability: ManeuverCapability | None = None
```

Importing `ManeuverCapability` into `entities.py` must not introduce an import cycle; `maneuvers.py` must not import entity classes.

- [ ] **Step 5: Run focused tests and quality checks**

Run:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv run pytest packages/sycasphere-core/tests/test_maneuvers.py packages/sycasphere-core/tests/test_entities.py -q
uv run ruff check packages/sycasphere-core/src/sycasphere/core/maneuvers.py packages/sycasphere-core/src/sycasphere/core/entities.py packages/sycasphere-core/tests/test_maneuvers.py packages/sycasphere-core/tests/test_entities.py
uv run mypy packages/sycasphere-core/src/sycasphere/core/maneuvers.py packages/sycasphere-core/src/sycasphere/core/entities.py
```

Expected: all commands exit `0`.

- [ ] **Step 6: Commit**

```powershell
git add packages/sycasphere-core/src/sycasphere/core/maneuvers.py packages/sycasphere-core/src/sycasphere/core/entities.py packages/sycasphere-core/tests/test_maneuvers.py packages/sycasphere-core/tests/test_entities.py
git commit -m "feat(core): define maneuver contracts"
```

---

### Task 3: Environment and simulation definitions

**Files:**
- Create: `packages/sycasphere-core/src/sycasphere/core/simulations.py`
- Create: `packages/sycasphere-core/tests/test_simulations.py`

**Interfaces:**
- Consumes: `_DefinitionBase`, `EntityDefinition`, entity concrete classes, `Epoch`, `ModelRef`, `PlannedTruthManeuver`, `_validate_maneuver_binding`.
- Produces:
  - `CentralBody`
  - `ExternalDataRef`
  - `EnvironmentDefinition`
  - `SimulationDefinition`

- [ ] **Step 1: Write failing simulation-definition tests**

Cover at least these exact behaviors:

```python
def test_environment_and_simulation_definition_round_trip() -> None:
    definition = make_simulation_definition()
    restored = SimulationDefinition.model_validate(
        definition.model_dump(mode="json")
    )
    assert restored == definition
    assert restored.environment.central_body is CentralBody.EARTH


@pytest.mark.parametrize(
    "sha256",
    ["", "A" * 64, "a" * 63, "g" * 64, "/tmp/eop.dat"],
)
def test_external_data_ref_requires_lowercase_sha256(sha256: str) -> None:
    with pytest.raises(ValidationError):
        ExternalDataRef(
            data_id="iers-eop",
            version="2026-07-26",
            sha256=sha256,
        )


def test_simulation_requires_at_least_one_space_object() -> None:
    data = make_simulation_definition().model_dump(mode="python")
    data["entities"] = [make_ground_station()]
    with pytest.raises(ValidationError, match="space object"):
        SimulationDefinition.model_validate(data)


def test_simulation_rejects_global_entity_or_sensor_id_collisions() -> None:
    definition = make_simulation_definition()
    duplicate_entity_data = definition.model_dump(mode="python")
    duplicate_entity_data["entities"] = (
        definition.entities[0],
        definition.entities[0],
    )
    with pytest.raises(ValidationError, match="entity"):
        SimulationDefinition.model_validate(duplicate_entity_data)

    sensor_collision_data = definition.model_dump(mode="python")
    entities = list(definition.entities)
    sensor_owner = entities[0].model_copy(update={"id": "sensor-1"})
    sensor_collision_data["entities"] = (sensor_owner, *entities[1:])
    with pytest.raises(ValidationError, match="sensor"):
        SimulationDefinition.model_validate(sensor_collision_data)


def test_simulation_rejects_asynchronous_initial_state_in_v1() -> None:
    definition = make_simulation_definition()
    data = definition.model_dump(mode="python")
    spacecraft = definition.entities[0]
    changed_state = spacecraft.initial_state.model_copy(
        update={
            "epoch": Epoch(
                value="2026-07-26T00:00:01Z",
                time_scale=TimeScale.UTC,
            )
        }
    )
    data["entities"] = (
        spacecraft.model_copy(update={"initial_state": changed_state}),
        *definition.entities[1:],
    )
    with pytest.raises(ValidationError, match="synchronization_epoch"):
        SimulationDefinition.model_validate(data)


def test_planned_maneuver_requires_existing_capable_spacecraft() -> None:
    definition = make_simulation_definition()
    data = definition.model_dump(mode="python")
    planned = definition.planned_maneuvers[0]
    data["planned_maneuvers"] = (
        planned.model_copy(update={"spacecraft_id": "missing-spacecraft"}),
    )
    with pytest.raises(ValidationError, match="spacecraft"):
        SimulationDefinition.model_validate(data)
```

Also test:

- duplicate environment `model_id`;
- duplicate external `data_id`;
- duplicate planned `maneuver_id`;
- a planned maneuver targeting a ground station or missing entity;
- a planned maneuver type not listed in the spacecraft capability;
- local-frame owner/reference-epoch mismatch through the simulation boundary;
- mutation of source entity/model/data lists cannot change the stored definition.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv run pytest packages/sycasphere-core/tests/test_simulations.py -q
```

Expected: collection fails because `sycasphere.core.simulations` does not exist.

- [ ] **Step 3: Implement physical-world contracts**

Use these public fields:

```python
class CentralBody(StrEnum):
    EARTH = "EARTH"


class ExternalDataRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    data_id: DefinitionString
    version: DefinitionString
    sha256: Annotated[
        str,
        StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$"),
    ]


class EnvironmentDefinition(_DefinitionBase):
    central_body: CentralBody
    model_refs: tuple[ModelRef, ...] = ()
    external_data_refs: tuple[ExternalDataRef, ...] = ()


class SimulationDefinition(_DefinitionBase):
    synchronization_epoch: Epoch
    environment: EnvironmentDefinition
    entities: tuple[EntityDefinition, ...] = Field(min_length=1)
    planned_maneuvers: tuple[PlannedTruthManeuver, ...] = ()
```

`EnvironmentDefinition` validators reject duplicate `model_id` and duplicate `data_id`.

`SimulationDefinition` uses one `model_validator(mode="after")` that:

1. rejects duplicate entity IDs;
2. collects every nested sensor and rejects duplicate sensor IDs or a sensor ID equal to an entity ID;
3. requires at least one `SpacecraftDefinition` or `OtherSpaceObjectDefinition`;
4. requires every space object's `initial_state.epoch` to equal `synchronization_epoch`;
5. rejects duplicate `maneuver_id`;
6. resolves each planned target to a `SpacecraftDefinition`;
7. calls `_validate_maneuver_binding` with the target capability;
8. when maneuver epoch and synchronization epoch use the same `TimeScale`, compares their canonical calendar strings and rejects a maneuver earlier than synchronization; cross-scale ordering remains Engine `prepare()` work.

- [ ] **Step 4: Run focused tests and quality checks**

Run:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv run pytest packages/sycasphere-core/tests/test_simulations.py packages/sycasphere-core/tests/test_maneuvers.py packages/sycasphere-core/tests/test_entities.py -q
uv run ruff check packages/sycasphere-core/src/sycasphere/core/simulations.py packages/sycasphere-core/tests/test_simulations.py
uv run mypy packages/sycasphere-core/src/sycasphere/core/simulations.py
```

Expected: all commands exit `0`.

- [ ] **Step 5: Commit**

```powershell
git add packages/sycasphere-core/src/sycasphere/core/simulations.py packages/sycasphere-core/tests/test_simulations.py
git commit -m "feat(core): define simulation worlds"
```

---

### Task 4: Time range, output sampling, and observation schedules

**Files:**
- Create: `packages/sycasphere-core/src/sycasphere/core/schedules.py`
- Create: `packages/sycasphere-core/tests/test_schedules.py`

**Interfaces:**
- Consumes: `DefinitionString`, `Epoch`.
- Produces:
  - `SimulationTimeRange`
  - `OutputProduct`
  - `SamplingRule`
  - `OutputSampling`
  - `ObservationScheduleKind`
  - `PeriodicObservationSchedule`
  - `ExplicitObservationSchedule`
  - `ObservationSchedule`
  - `_is_strictly_before_same_scale(left: Epoch, right: Epoch) -> bool | None`

- [ ] **Step 1: Write failing schedule tests**

Lock the public enum sets and key behaviors:

```python
def test_output_product_values_are_exact() -> None:
    assert {value.value for value in OutputProduct} == {
        "TRUTH_STATE",
        "ATTITUDE_STATE",
        "DERIVED_GEOMETRY",
    }


def test_sampling_rules_reject_duplicate_products_and_invalid_intervals() -> None:
    rule = SamplingRule(product="TRUTH_STATE", interval_s=3.0)
    with pytest.raises(ValidationError, match="product"):
        OutputSampling(rules=(rule, rule))
    for invalid in (0.0, -1.0, math.nan, math.inf, 3, True, "3"):
        with pytest.raises(ValidationError):
            SamplingRule(product="TRUTH_STATE", interval_s=invalid)


def test_periodic_schedule_round_trips_through_discriminated_union() -> None:
    schedule = PeriodicObservationSchedule(
        schedule_id="schedule-1",
        sensor_id="sensor-1",
        target_id="target-1",
        measurement_model_id="sycasphere.measurement.angles",
        start_epoch=EPOCH_0,
        end_epoch=EPOCH_10,
        cadence_s=2.0,
    )
    assert TypeAdapter(ObservationSchedule).validate_python(
        schedule.model_dump(mode="json")
    ) == schedule


def test_explicit_schedule_requires_unique_ordered_epochs() -> None:
    with pytest.raises(ValidationError):
        ExplicitObservationSchedule(
            schedule_id="schedule-1",
            sensor_id="sensor-1",
            target_id="target-1",
            measurement_model_id="sycasphere.measurement.angles",
            epochs=(EPOCH_10, EPOCH_0),
        )


def test_simulation_time_range_is_a_nonempty_closed_interval() -> None:
    assert SimulationTimeRange(start=EPOCH_0, end=EPOCH_10).start == EPOCH_0
    with pytest.raises(ValidationError):
        SimulationTimeRange(start=EPOCH_10, end=EPOCH_0)
```

Also test:

- `ObservationScheduleKind` exposes only `PERIODIC` and `EXPLICIT`;
- explicit epochs are nonempty and reject exact duplicates;
- periodic start is strictly before end when scales match;
- mixed time scales remain structurally valid for Engine comparison;
- optional `error_profile_id` and `link_model_id` round-trip as `None`;
- every model is frozen and rejects unknown fields.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv run pytest packages/sycasphere-core/tests/test_schedules.py -q
```

Expected: collection fails because `sycasphere.core.schedules` does not exist.

- [ ] **Step 3: Implement schedule contracts**

Use these exact fields:

```python
type PositiveStrictFiniteFloat = Annotated[
    float,
    Strict(),
    AllowInfNan(False),
    Field(gt=0.0),
]


class SimulationTimeRange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    start: Epoch
    end: Epoch


class OutputProduct(StrEnum):
    TRUTH_STATE = "TRUTH_STATE"
    ATTITUDE_STATE = "ATTITUDE_STATE"
    DERIVED_GEOMETRY = "DERIVED_GEOMETRY"


class SamplingRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    product: OutputProduct
    interval_s: PositiveStrictFiniteFloat


class OutputSampling(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rules: tuple[SamplingRule, ...] = ()


class ObservationScheduleKind(StrEnum):
    PERIODIC = "PERIODIC"
    EXPLICIT = "EXPLICIT"


class _ObservationScheduleBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schedule_id: DefinitionString
    sensor_id: DefinitionString
    target_id: DefinitionString
    measurement_model_id: DefinitionString
    error_profile_id: DefinitionString | None = None
    link_model_id: DefinitionString | None = None


class PeriodicObservationSchedule(_ObservationScheduleBase):
    schedule_type: Literal[ObservationScheduleKind.PERIODIC] = ObservationScheduleKind.PERIODIC
    start_epoch: Epoch
    end_epoch: Epoch
    cadence_s: PositiveStrictFiniteFloat


class ExplicitObservationSchedule(_ObservationScheduleBase):
    schedule_type: Literal[ObservationScheduleKind.EXPLICIT] = ObservationScheduleKind.EXPLICIT
    epochs: tuple[Epoch, ...] = Field(min_length=1)


type ObservationSchedule = Annotated[
    PeriodicObservationSchedule | ExplicitObservationSchedule,
    Field(discriminator="schedule_type"),
]
```

`_is_strictly_before_same_scale` returns `None` for different scales and otherwise compares canonical `Epoch.value` strings. Use it to reject reversed/equal same-scale ranges and explicit same-scale out-of-order epochs. Exact duplicate epochs are always rejected.

Apply a `mode="before"` validator to `interval_s` and `cadence_s` that requires concrete built-in `float`; this is what rejects integers before Pydantic can widen them.

- [ ] **Step 4: Run focused tests and quality checks**

Run:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv run pytest packages/sycasphere-core/tests/test_schedules.py -q
uv run ruff check packages/sycasphere-core/src/sycasphere/core/schedules.py packages/sycasphere-core/tests/test_schedules.py
uv run mypy packages/sycasphere-core/src/sycasphere/core/schedules.py
```

Expected: all commands exit `0`.

- [ ] **Step 5: Commit**

```powershell
git add packages/sycasphere-core/src/sycasphere/core/schedules.py packages/sycasphere-core/tests/test_schedules.py
git commit -m "feat(core): define simulation schedules"
```

---

### Task 5: Self-contained simulation run request

**Files:**
- Create: `packages/sycasphere-core/src/sycasphere/core/execution.py`
- Create: `packages/sycasphere-core/tests/test_execution.py`

**Interfaces:**
- Consumes: immutable JSON helpers, `ManeuverCommand`, `PluginRef`, `ModelRef`, schedule contracts, `SimulationDefinition`, `SchemaVersion`.
- Produces in this task:
  - `ScienceBackendBinding`
  - `OutputRequirement`
  - `SimulationRunRequest`

- [ ] **Step 1: Write failing request tests**

Build one reusable valid fixture containing:

- one maneuver-capable observer spacecraft with a sensor;
- one target space object;
- one `PERIODIC` observation schedule;
- a `TRUTH_STATE` sampling rule;
- an exact science-backend `PluginRef`;
- unsigned seed `42`;
- `TRUTH` and `IDEAL_OBSERVATIONS` output requirements.

Test these behaviors:

```python
def test_request_is_self_contained_and_round_trips() -> None:
    request = make_request()
    serialized = request.model_dump(mode="json")
    assert "simulation_definition" in serialized
    assert "simulation_definition_ref" not in serialized
    assert "measurement_model_refs" not in serialized
    assert "error_model_refs" not in serialized
    assert SimulationRunRequest.model_validate(serialized) == request


@pytest.mark.parametrize("random_seed", [-1, 2**64, True, 1.0, "42"])
def test_request_requires_unsigned_64_bit_seed(random_seed: object) -> None:
    data = make_request().model_dump(mode="python")
    data["random_seed"] = random_seed
    with pytest.raises(ValidationError):
        SimulationRunRequest.model_validate(data)


def test_reported_output_requires_error_profile_on_every_schedule() -> None:
    data = make_request().model_dump(mode="python")
    data["output_requirements"] = ("REPORTED_OBSERVATIONS",)
    with pytest.raises(ValidationError, match="error_profile"):
        SimulationRunRequest.model_validate(data)


def test_request_resolves_every_schedule_reference() -> None:
    request = make_request()
    data = request.model_dump(mode="python")
    schedule = request.observation_schedules[0]
    data["observation_schedules"] = (
        schedule.model_copy(update={"sensor_id": "missing-sensor"}),
    )
    with pytest.raises(ValidationError, match="sensor"):
        SimulationRunRequest.model_validate(data)


def test_request_rejects_command_id_colliding_with_planned_maneuver() -> None:
    request = make_request()
    planned = request.simulation_definition.planned_maneuvers[0]
    data = request.model_dump(mode="python")
    data["command_timeline"] = (
        ManeuverCommand(
            command_id=planned.maneuver_id,
            spacecraft_id=planned.spacecraft_id,
            epoch=planned.epoch,
            maneuver=planned.maneuver,
        ),
    )
    with pytest.raises(ValidationError, match="command_id"):
        SimulationRunRequest.model_validate(data)
```

Also cover:

- empty or duplicate output requirements;
- duplicate schedule IDs;
- duplicate link-model IDs;
- missing sensor or target;
- target must be a space object;
- measurement/error model must belong to the selected sensor;
- link model must exist in request `link_models`;
- command target must be an existing capable spacecraft;
- command type must be supported;
- command IDs are unique and do not collide with planned maneuver IDs;
- `synchronization_epoch <= start < end` when scales match;
- schedule epochs remain inside the closed request interval when scales match;
- `TRUTH`, `ATTITUDE`, or `GEOMETRY` requires the corresponding sampling rule, and an existing sampling rule requires its corresponding output;
- backend configuration is deeply immutable and JSON-safe;
- request is frozen and rejects infrastructure/UI fields such as `output_path`, `retention_policy`, `run_status`, and `database_ref`.

- [ ] **Step 2: Run request tests and verify RED**

Run:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv run pytest packages/sycasphere-core/tests/test_execution.py -q
```

Expected: collection fails because the execution contracts do not exist.

- [ ] **Step 3: Implement backend binding and request enums**

Use:

```python
class ScienceBackendBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ref: PluginRef
    configuration: Mapping[str, JsonValue] = Field(default_factory=dict)


class OutputRequirement(StrEnum):
    TRUTH = "TRUTH"
    ATTITUDE = "ATTITUDE"
    GEOMETRY = "GEOMETRY"
    IDEAL_OBSERVATIONS = "IDEAL_OBSERVATIONS"
    REPORTED_OBSERVATIONS = "REPORTED_OBSERVATIONS"
    DELIVERY_SUMMARY = "DELIVERY_SUMMARY"
    COMMAND_TRACE = "COMMAND_TRACE"
    DIAGNOSTICS = "DIAGNOSTICS"
```

Normalize/freeze/serialize backend configuration with the same finite, alias-independent behavior as `ModelRef.configuration`.

- [ ] **Step 4: Implement `SimulationRunRequest` and cross-reference validation**

Use these exact fields:

```python
type UInt64 = Annotated[
    int,
    Strict(),
    Field(ge=0, le=2**64 - 1),
]


class SimulationRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: SchemaVersion
    simulation_definition: SimulationDefinition
    time_range: SimulationTimeRange
    output_sampling: OutputSampling
    observation_schedules: tuple[ObservationSchedule, ...] = ()
    command_timeline: tuple[ManeuverCommand, ...] = ()
    backend: ScienceBackendBinding
    link_models: tuple[ModelRef, ...] = ()
    random_seed: UInt64
    output_requirements: frozenset[OutputRequirement]
```

Before validators must reject `bool`/coercion for `random_seed`, preserve duplicate detection before frozenset conversion, and serialize `output_requirements` sorted by enum value.

The after validator resolves lookup dictionaries once and applies every invariant listed in Step 1. For time comparisons, reject invalid ordering only when the relevant epochs share a time scale; mixed-scale scientific ordering remains Engine work.

Use this exact sampling/output map:

```python
_SAMPLING_REQUIREMENTS = {
    OutputProduct.TRUTH_STATE: OutputRequirement.TRUTH,
    OutputProduct.ATTITUDE_STATE: OutputRequirement.ATTITUDE,
    OutputProduct.DERIVED_GEOMETRY: OutputRequirement.GEOMETRY,
}
```

- [ ] **Step 5: Run focused tests and quality checks**

Run:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv run pytest packages/sycasphere-core/tests/test_execution.py packages/sycasphere-core/tests/test_simulations.py packages/sycasphere-core/tests/test_schedules.py -q
uv run ruff check packages/sycasphere-core/src/sycasphere/core/execution.py packages/sycasphere-core/tests/test_execution.py
uv run mypy packages/sycasphere-core/src/sycasphere/core/execution.py
```

Expected: all commands exit `0`.

- [ ] **Step 6: Commit**

```powershell
git add packages/sycasphere-core/src/sycasphere/core/execution.py packages/sycasphere-core/tests/test_execution.py
git commit -m "feat(core): define simulation run requests"
```

---

### Task 6: Immutable simulation execution manifest

**Files:**
- Modify: `packages/sycasphere-core/src/sycasphere/core/execution.py`
- Modify: `packages/sycasphere-core/tests/test_execution.py`

**Interfaces:**
- Consumes: Task 1 hashing/seed constants, `ExternalDataRef`, `ObservationSchedule`, `OutputSampling`, `ManeuverSpec`, `PluginKind`, `PluginRef`, `SimulationRunRequest`.
- Produces:
  - `ResolvedPluginRecord`
  - `DerivedRandomStream`
  - `PreparedManeuverSource`
  - `PreparedManeuverEntry`
  - `PreparedTimeline`
  - `EventOrderingPolicy`
  - `SimulationExecutionManifest`

- [ ] **Step 1: Write failing manifest tests**

Use a valid request fixture and lock these behaviors:

```python
def test_manifest_create_computes_all_three_hashes_and_fixed_versions() -> None:
    manifest = make_manifest()
    assert manifest.source_request_hash == sha256_canonical_json(
        manifest.source_request
    )
    assert manifest.simulation_definition_hash == sha256_canonical_json(
        manifest.source_request.simulation_definition
    )
    assert manifest.canonicalization_version == "SYCASPHERE_CANONICAL_JSON_V1"
    assert manifest.random_derivation_version == "SYCASPHERE_SEED_V1"
    assert manifest.content_hash == sha256_canonical_json(
        manifest.model_dump(mode="json", exclude={"content_hash"})
    )


def test_equivalent_inputs_create_byte_equivalent_manifests() -> None:
    first = make_manifest()
    second = make_manifest()
    assert first.model_dump_json() == second.model_dump_json()
    assert first.content_hash == second.content_hash


def test_manifest_rejects_tampered_source_or_content_hash() -> None:
    manifest = make_manifest()
    data = manifest.model_dump(mode="python")
    data["source_request_hash"] = "0" * 64
    with pytest.raises(ValidationError, match="source_request_hash"):
        SimulationExecutionManifest.model_validate(data)


def test_manifest_contains_no_runtime_lifecycle_or_path_fields() -> None:
    fields = set(SimulationExecutionManifest.model_fields)
    assert fields.isdisjoint(
        {
            "prepared_at",
            "started_at",
            "ended_at",
            "status",
            "error",
            "output_hashes",
            "output_path",
            "runtime_command_journal",
        }
    )


def test_prepared_timeline_is_compact_for_periodic_schedules() -> None:
    manifest = make_manifest()
    serialized = manifest.prepared_timeline.model_dump(mode="json")
    assert serialized["observation_schedules"][0]["schedule_type"] == "PERIODIC"
    assert "expanded_epochs" not in serialized
```

Also cover:

- all hash fields require 64 lowercase hexadecimal characters;
- resolved-plugin component IDs are unique and records sort by component ID;
- derived stream `(component_id, purpose)` pairs are unique and sort deterministically;
- prepared maneuver `order_index` values must be exactly `0..n-1`;
- prepared schedule IDs are unique and sort deterministically;
- expected outputs equal the source request output requirements;
- manifest/source request are frozen;
- changing plugin version, external-data hash, seed, or backend configuration changes `content_hash`;
- changing `-0.0` to `0.0` in equivalent configuration does not change canonical hashes.

- [ ] **Step 2: Run manifest tests and verify RED**

Run:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv run pytest packages/sycasphere-core/tests/test_execution.py -q
```

Expected: new tests fail because manifest types and `create` do not exist.

- [ ] **Step 3: Implement prepared and resolved record types**

Use these exact public fields:

```python
type Sha256Hex = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$"),
]
type StrictNonNegativeInt = Annotated[
    int,
    Strict(),
    Field(ge=0),
]


class ResolvedPluginRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    component_id: DefinitionString
    kind: PluginKind
    ref: PluginRef
    configuration_hash: Sha256Hex


class DerivedRandomStream(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    component_id: DefinitionString
    purpose: DefinitionString
    interface_version: SchemaVersion
    derived_seed: UInt64


class PreparedManeuverSource(StrEnum):
    PLANNED = "PLANNED"
    COMMAND = "COMMAND"


class PreparedManeuverEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    order_index: StrictNonNegativeInt
    source: PreparedManeuverSource
    event_id: DefinitionString
    spacecraft_id: DefinitionString
    epoch: Epoch
    maneuver: ManeuverSpec


class EventOrderingPolicy(StrEnum):
    POST_MANEUVER_OBSERVATION_V1 = "POST_MANEUVER_OBSERVATION_V1"


class PreparedTimeline(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    maneuvers: tuple[PreparedManeuverEntry, ...] = ()
    observation_schedules: tuple[ObservationSchedule, ...] = ()
    output_sampling: OutputSampling
```

`PreparedTimeline` validates consecutive maneuver indices, unique maneuver event IDs, and unique observation schedule IDs. It sorts observation schedules by `schedule_id` but preserves Engine-supplied maneuver order through `order_index`.

- [ ] **Step 4: Implement manifest construction and integrity validation**

Use these exact fields and classmethod:

```python
class SimulationExecutionManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: SchemaVersion
    source_request: SimulationRunRequest
    source_request_hash: Sha256Hex
    simulation_definition_hash: Sha256Hex
    resolved_plugins: tuple[ResolvedPluginRecord, ...]
    resolved_external_data: tuple[ExternalDataRef, ...]
    derived_random_streams: tuple[DerivedRandomStream, ...]
    random_derivation_version: Literal["SYCASPHERE_SEED_V1"]
    prepared_timeline: PreparedTimeline
    event_ordering_policy: Literal[
        EventOrderingPolicy.POST_MANEUVER_OBSERVATION_V1
    ]
    expected_outputs: frozenset[OutputRequirement]
    canonicalization_version: Literal["SYCASPHERE_CANONICAL_JSON_V1"]
    content_hash: Sha256Hex

    @classmethod
    def create(
        cls,
        *,
        schema_version: SchemaVersion,
        source_request: SimulationRunRequest,
        resolved_plugins: tuple[ResolvedPluginRecord, ...],
        resolved_external_data: tuple[ExternalDataRef, ...],
        derived_random_streams: tuple[DerivedRandomStream, ...],
        prepared_timeline: PreparedTimeline,
    ) -> SimulationExecutionManifest:
        ordered_plugins = tuple(
            sorted(resolved_plugins, key=lambda item: item.component_id)
        )
        ordered_data = tuple(
            sorted(
                resolved_external_data,
                key=lambda item: (item.data_id, item.version, item.sha256),
            )
        )
        ordered_streams = tuple(
            sorted(
                derived_random_streams,
                key=lambda item: (item.component_id, item.purpose),
            )
        )
        source_hash = sha256_canonical_json(source_request)
        definition_hash = sha256_canonical_json(
            source_request.simulation_definition
        )
        payload: dict[str, Any] = {
            "schema_version": schema_version,
            "source_request": source_request,
            "source_request_hash": source_hash,
            "simulation_definition_hash": definition_hash,
            "resolved_plugins": ordered_plugins,
            "resolved_external_data": ordered_data,
            "derived_random_streams": ordered_streams,
            "random_derivation_version": RANDOM_DERIVATION_VERSION,
            "prepared_timeline": prepared_timeline,
            "event_ordering_policy": (
                EventOrderingPolicy.POST_MANEUVER_OBSERVATION_V1
            ),
            "expected_outputs": sorted(
                source_request.output_requirements,
                key=lambda item: item.value,
            ),
            "canonicalization_version": CANONICALIZATION_VERSION,
        }
        payload["content_hash"] = sha256_canonical_json(payload)
        return cls.model_validate(payload)
```

`create` must:

1. sort resolved plugins by `component_id`;
2. sort external data by `(data_id, version, sha256)`;
3. sort random streams by `(component_id, purpose)`;
4. set `expected_outputs` from `source_request.output_requirements`;
5. calculate source and simulation-definition hashes;
6. build an ordinary JSON payload without `content_hash`;
7. calculate `content_hash`;
8. return the validated frozen model.

The after validator recalculates all hashes, verifies expected outputs, rejects duplicate record identities, and raises field-specific messages for tampering. It also requires the prepared sampling rules to equal the source request rules and the prepared schedule-ID set to equal the source schedule-ID set. Serializers output `expected_outputs` in enum-value order.

- [ ] **Step 5: Run focused tests and quality checks**

Run:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv run pytest packages/sycasphere-core/tests/test_execution.py packages/sycasphere-core/tests/test_canonical.py -q
uv run ruff check packages/sycasphere-core/src/sycasphere/core/execution.py packages/sycasphere-core/tests/test_execution.py
uv run mypy packages/sycasphere-core/src/sycasphere/core/execution.py
```

Expected: all commands exit `0`.

- [ ] **Step 6: Commit**

```powershell
git add packages/sycasphere-core/src/sycasphere/core/execution.py packages/sycasphere-core/tests/test_execution.py
git commit -m "feat(core): define execution manifests"
```

---

### Task 7: Public API and reviewed JSON Schemas

**Files:**
- Modify: `packages/sycasphere-core/src/sycasphere/core/__init__.py`
- Modify: `packages/sycasphere-core/tests/test_public_api.py`
- Modify: `packages/sycasphere-core/tests/snapshots/core-schemas.json`

**Interfaces:**
- Consumes: all public classes and unions from Tasks 2–6.
- Produces: one reviewed `sycasphere.core` import surface and deterministic schema snapshot.

- [ ] **Step 1: Add failing public-contract assertions**

Extend `EXPECTED_PUBLIC_CONTRACTS` with exactly these names:

```text
CentralBody
DerivedRandomStream
EnvironmentDefinition
EventOrderingPolicy
ExplicitObservationSchedule
ExternalDataRef
FiniteBurnManeuverSpec
ImpulsiveManeuverSpec
ManeuverCapability
ManeuverCommand
ManeuverSpec
ManeuverType
ObservationSchedule
ObservationScheduleKind
OutputProduct
OutputRequirement
OutputSampling
PeriodicObservationSchedule
PlannedTruthManeuver
PreparedManeuverEntry
PreparedManeuverSource
PreparedTimeline
ResolvedPluginRecord
SamplingRule
ScienceBackendBinding
SimulationDefinition
SimulationExecutionManifest
SimulationRunRequest
SimulationTimeRange
```

Add every concrete Pydantic model to `_public_model_schemas()`. Add `ManeuverSpec` and `ObservationSchedule` through `TypeAdapter(...).json_schema()`. Add assertions that the two discriminated schemas expose their discriminator properties and that `SimulationExecutionManifest` has no runtime lifecycle fields.

- [ ] **Step 2: Run public API tests and verify RED**

Run:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv run pytest packages/sycasphere-core/tests/test_public_api.py -q
```

Expected: public export and schema snapshot assertions fail.

- [ ] **Step 3: Publish exact imports**

Import every approved type into `sycasphere.core.__init__`, append the names to `__all__`, keep private helpers/constants unexported, and update the module header/version log accurately. Do not export `_ObservationScheduleBase`, `_validate_maneuver_binding`, hash helpers, or private type aliases.

- [ ] **Step 4: Regenerate the deterministic snapshot**

Use the test module's `_serialized_public_model_schemas()` function with the repository Python environment to rewrite only:

`packages/sycasphere-core/tests/snapshots/core-schemas.json`

Then inspect the diff for:

- no Orekit/JPype/Java schemas;
- discriminators use `maneuver_type` and `schedule_type`;
- strict tuple cardinality appears for three-component maneuver vectors;
- `SimulationRunRequest` embeds `SimulationDefinition`;
- `SimulationExecutionManifest` excludes lifecycle/output-result fields.

- [ ] **Step 5: Run focused tests and quality checks**

Run:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv run pytest packages/sycasphere-core/tests/test_public_api.py tests/architecture/test_core_dependency_boundary.py -q
uv run ruff check packages/sycasphere-core/src/sycasphere/core/__init__.py packages/sycasphere-core/tests/test_public_api.py
uv run mypy packages/sycasphere-core/src/sycasphere/core/__init__.py
```

Expected: all commands exit `0`.

- [ ] **Step 6: Commit**

```powershell
git add packages/sycasphere-core/src/sycasphere/core/__init__.py packages/sycasphere-core/tests/test_public_api.py packages/sycasphere-core/tests/snapshots/core-schemas.json
git commit -m "feat(core): publish simulation input schemas"
```

---

### Task 8: Documentation synchronization and full release verification

**Files:**
- Modify: `packages/sycasphere-core/README.md`
- Modify: `README.md`
- Modify: `packages/sycasphere-core/tests/test_package.py`
- Modify: `docs/architecture/core-data-model-v0.2.md`
- Modify: `docs/architecture/algorithm-integration-v0.2.md`
- Modify: `docs/superpowers/specs/2026-07-20-sycasphere-runtime-and-simulation-engine-design.md`

**Interfaces:**
- Consumes: the final reviewed public API from Task 7.
- Produces: one non-contradictory documented contract and verified source/wheel distribution.

- [ ] **Step 1: Write a failing documentation consistency test**

Add a parametrized test to `packages/sycasphere-core/tests/test_package.py` that reads the two README files and asserts all of these approved public names appear:

```python
DOCUMENTED_CONTRACTS = (
    "SimulationDefinition",
    "SimulationRunRequest",
    "SimulationExecutionManifest",
    "ManeuverCommand",
    "PeriodicObservationSchedule",
    "ExplicitObservationSchedule",
)
```

Also assert the Core README no longer says run requests are excluded.

- [ ] **Step 2: Run the documentation test and verify RED**

Run:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv run pytest packages/sycasphere-core/tests/test_package.py -q
```

Expected: the new documentation assertions fail.

- [ ] **Step 3: Synchronize user-facing READMEs**

Add one minimal executable example that creates:

1. a `SimulationDefinition` with a synchronized space object;
2. a closed `SimulationTimeRange`;
3. `OutputSampling` for `TRUTH_STATE`;
4. an exact `ScienceBackendBinding`;
5. a `SimulationRunRequest`.

State explicitly:

- Core validates contracts but does not propagate;
- Engine `prepare()` will resolve plugins/data and create a Manifest;
- `SimulationExecutionManifest` is immutable input provenance, not run status;
- sessions, observations/results, retention, persistence, and Orekit execution remain separate packages/batches.

- [ ] **Step 4: Reconcile the three architecture documents**

Make these exact semantic corrections wherever older wording conflicts:

- replace “completed RunManifest containing end status/errors/output hashes” with immutable `SimulationExecutionManifest` plus subsequent `RunRecord`/`RunOutcome`;
- state that Engine receives the full `SimulationDefinition`;
- state that the first command timeline contains maneuver commands only;
- state that the first schedule types are `PERIODIC` and `EXPLICIT`;
- remove top-level measurement/error model reference duplication;
- retain run-level link models;
- state the same-epoch post-maneuver observation order;
- state that sampling step is independent of numerical integration settings;
- state the strict v1 synchronization rule and compatible future per-object pre-roll upgrade;
- mark actual Core contracts as implemented and Engine/session/observation/platform contracts as planned, avoiding claims that unimplemented runtime behavior already exists.

- [ ] **Step 5: Run the complete repository quality gate**

Run from the repository root:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

If the repository has no root `src` directory and the configured `mypy` command rejects the literal path, record that evidence and run the configuration-equivalent command:

```powershell
uv run mypy
```

Expected: all applicable commands exit `0`, with no skipped failure.

- [ ] **Step 6: Build and inspect distributions**

Use a unique ignored output directory and isolated virtual environment:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
$buildRoot = Join-Path (Get-Location) ".build"
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
$verificationRoot = Join-Path $buildRoot ("core-verify-" + [guid]::NewGuid())
$artifactDir = Join-Path $verificationRoot "artifacts"
$venvDir = Join-Path $verificationRoot "venv"
New-Item -ItemType Directory -Path $artifactDir | Out-Null
uv build --offline --no-build-isolation --package sycasphere-core --out-dir $artifactDir
$wheel = Get-ChildItem -LiteralPath $artifactDir -Filter "*.whl"
$sdist = Get-ChildItem -LiteralPath $artifactDir -Filter "*.tar.gz"
if ($wheel.Count -ne 1 -or $sdist.Count -ne 1) {
    throw "expected exactly one wheel and one sdist"
}
tar -tf $wheel.FullName
tar -tf $sdist.FullName
uv venv --python 3.12 $venvDir
uv pip install --offline --python (Join-Path $venvDir "Scripts/python.exe") $wheel.FullName
& (Join-Path $venvDir "Scripts/python.exe") -c "from sycasphere.core import SimulationDefinition, SimulationRunRequest; assert SimulationDefinition.model_json_schema(); assert SimulationRunRequest.model_json_schema()"
```

Inspect wheel and sdist member lists and assert:

- wheel contains only `sycasphere/core/**`, license and package metadata;
- wheel contains no tests, Engine, Orekit, Platform, JPype or Java files;
- sdist contains expected Core sources and project metadata;
- a clean temporary Python 3.12 environment can install the wheel without JDK/Orekit/JPype and run:

```python
from sycasphere.core import SimulationDefinition, SimulationRunRequest

assert SimulationDefinition.model_json_schema()
assert SimulationRunRequest.model_json_schema()
```

- [ ] **Step 7: Review the final diff for scientific boundary errors**

Inspect every changed production line and explicitly check:

- time scales are never silently converted in Core;
- local maneuver frame owner and reference epoch are validated;
- SI unit suffixes are present;
- no Truth/Ideal/Reported/Estimate result types were accidentally merged into request models;
- no mutable input aliases survive;
- hash inputs exclude only `content_hash`;
- no wall-clock/lifecycle/output-result field enters Manifest;
- no unrequested Engine/session/observation/platform implementation was added.

- [ ] **Step 8: Commit**

```powershell
git add README.md packages/sycasphere-core/README.md packages/sycasphere-core/tests/test_package.py docs/architecture/core-data-model-v0.2.md docs/architecture/algorithm-integration-v0.2.md docs/superpowers/specs/2026-07-20-sycasphere-runtime-and-simulation-engine-design.md
git commit -m "docs: align simulation execution contracts"
```

---

## Final Review and Integration Gate

After Tasks 1–8:

1. Generate one whole-branch review package from the merge base through `HEAD`.
2. Dispatch the `requesting-code-review` reviewer using the complete package and the Global Constraints above.
3. Resolve every Critical, Important, and Minor finding; rerun covering tests after fixes and request re-review.
4. Rerun the complete quality gate and distribution checks with fresh output.
5. Use `finishing-a-development-branch` to present or perform the approved local integration path.
