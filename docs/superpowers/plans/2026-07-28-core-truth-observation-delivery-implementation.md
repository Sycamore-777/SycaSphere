# Core Truth、Observation 与 Delivery 契约实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development
> (recommended) or executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `sycasphere-core` 中交付已确认的姿态、真值、观测、不确定度和交付结果契约，
使后续后端中立 Engine 能直接产生严格、不可变、可追溯且算法安全的科学输出。

**Architecture:** Core 继续只承担不可变 Pydantic v2 边界模型和无需科学后端即可判断的
不变量。新代码按姿态、Truth、Observation 和 Delivery 四个领域职责拆分，并通过一个
私有验证模块复用严格数值、SHA-256 和嵌套模型快照逻辑；跨对象谱系、科学时间、插件执行
和 FIFO 交付留给后续 Engine。

**Tech Stack:** Python 3.12、Pydantic v2、NumPy、pytest、Ruff、mypy、uv、Hatchling。

## Global Constraints

- 权威设计为
  `docs/superpowers/specs/2026-07-28-core-truth-observation-delivery-design.md`。
- Core 运行时依赖仍只能是 Pydantic 与 NumPy。
- 不得导入 Orekit、JPype、Java、Engine、Platform、SQLite、PyArrow、FastAPI 或前端。
- 所有新 Python 文件使用准确的 Sycamore 文件头，创建和最后修改日期均为
  `2026-07-28`，首版版本号为 `v1.0.0`。
- 所有公开模型冻结、拒绝未知字段，并在嵌套边界复制和重新验证 Pydantic 实例。
- 所有公共函数、方法、模型和类型边界完整标注类型。
- 四元数顺序固定为 `(w, x, y, z)`，方向固定为 reference-to-BODY。
- SI 单位和 Frame 必须显式；未知值使用 None，不使用零或 NaN 表示缺失。
- Ideal、Reported、Truth 和 Delivery 必须保持分离。
- 每个行为变化先运行失败测试，再写最小实现。
- 每个 Task 结束时只提交该 Task 的相关文件。

---

## File Structure

### Production

- Create: `packages/sycasphere-core/src/sycasphere/core/_validation.py`
  - 私有严格数值、SHA-256、嵌套模型快照和集合快照工具。
- Create: `packages/sycasphere-core/src/sycasphere/core/attitudes.py`
  - `AttitudeState`。
- Create: `packages/sycasphere-core/src/sycasphere/core/truth.py`
  - `TruthState`、`TruthManeuver`、`ManeuverTruthSource`。
- Create: `packages/sycasphere-core/src/sycasphere/core/observations.py`
  - SubjectRef、MeasurementType、GeometryStatus、Event、Measurement、
    CustomMeasurementSchemaRef、MeasurementUncertainty、Ideal、Reported、ObservationChannel。
- Create: `packages/sycasphere-core/src/sycasphere/core/delivery.py`
  - DeliveryOutcome、DeliveryRecord、DeliverySummary、StreamingObservationEnvelope。
- Modify: `packages/sycasphere-core/src/sycasphere/core/execution.py`
  - 复用私有验证工具并新增 `DELIVERY_RECORDS` 输出要求。
- Modify: `packages/sycasphere-core/src/sycasphere/core/__init__.py`
  - 发布受审查的新增公共契约。

### Tests and schemas

- Create: `packages/sycasphere-core/tests/test_attitudes.py`
- Create: `packages/sycasphere-core/tests/test_truth.py`
- Create: `packages/sycasphere-core/tests/test_observations.py`
- Create: `packages/sycasphere-core/tests/test_delivery.py`
- Modify: `packages/sycasphere-core/tests/test_execution.py`
- Modify: `packages/sycasphere-core/tests/test_public_api.py`
- Modify: `packages/sycasphere-core/tests/test_package.py`
- Modify: `packages/sycasphere-core/tests/snapshots/core-schemas.json`
- Modify only if required by a real boundary gap:
  `tests/architecture/test_core_dependency_boundary.py`

### Documentation

- Modify: `README.md`
- Modify: `packages/sycasphere-core/README.md`
- Modify: `docs/architecture/core-data-model-v0.2.md`
- Modify: `docs/architecture/algorithm-integration-v0.2.md`
- Modify:
  `docs/superpowers/specs/2026-07-20-sycasphere-runtime-and-simulation-engine-design.md`

---

### Task 1: Centralize strict boundary validation helpers

**Files:**
- Create: `packages/sycasphere-core/src/sycasphere/core/_validation.py`
- Modify: `packages/sycasphere-core/src/sycasphere/core/execution.py`
- Test: `packages/sycasphere-core/tests/test_execution.py`

**Interfaces:**
- Produces: `StrictFiniteFloat`, `StrictNonNegativeInt`, `Sha256Hex`,
  `snapshot_model_input(value) -> Any`,
  `snapshot_model_collection(value) -> Any`,
  `require_builtin_float_sequence(value, field_name) -> Any`.
- Preserves: every existing `SimulationRunRequest` and `SimulationExecutionManifest` behavior.

- [ ] **Step 1: Add a regression test for the shared helper boundary**

Append to `test_execution.py`:

```python
from sycasphere.core._validation import (
    require_builtin_float_sequence,
    snapshot_model_collection,
    snapshot_model_input,
)


def test_shared_boundary_helpers_snapshot_models_and_reject_numeric_coercion() -> None:
    epoch = Epoch(value="2026-07-28T00:00:00Z", time_scale=TimeScale.UTC)

    assert snapshot_model_input(epoch) == epoch.model_dump(mode="python")
    assert snapshot_model_collection((epoch,)) == (epoch.model_dump(mode="python"),)
    assert require_builtin_float_sequence((1.0, 2.0), "values") == (1.0, 2.0)

    with pytest.raises(ValueError, match="built-in floats"):
        require_builtin_float_sequence((1, 2.0), "values")
    with pytest.raises(ValueError, match="list or tuple"):
        require_builtin_float_sequence("1.0,2.0", "values")
```

- [ ] **Step 2: Run the focused test and verify the missing module failure**

Run:

```powershell
& 'D:\program\github\my_github\SycaSphere\.venv\Scripts\python.exe' -m pytest `
  packages/sycasphere-core/tests/test_execution.py::test_shared_boundary_helpers_snapshot_models_and_reject_numeric_coercion -q
```

Expected: collection fails with `ModuleNotFoundError: sycasphere.core._validation`.

- [ ] **Step 3: Create the private validation module and migrate execution imports**

Create `_validation.py` with the required Sycamore header and this exact public-private surface:

```python
from __future__ import annotations

from typing import Annotated, Any

from pydantic import (
    AllowInfNan,
    BaseModel,
    Field,
    Strict,
    StringConstraints,
)

type StrictFiniteFloat = Annotated[float, Strict(), AllowInfNan(False)]
type StrictNonNegativeInt = Annotated[int, Strict(), Field(ge=0)]
type Sha256Hex = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$"),
]


def snapshot_model_input(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    return value


def snapshot_model_collection(value: Any) -> Any:
    if isinstance(value, (frozenset, list, set, tuple)):
        return tuple(snapshot_model_input(item) for item in value)
    return value


def require_builtin_float_sequence(value: Any, field_name: str) -> Any:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be supplied as a list or tuple")
    if any(type(component) is not float for component in value):
        raise ValueError(f"{field_name} components must be built-in floats")
    return value
```

In `execution.py`:

- import `Sha256Hex`, `StrictNonNegativeInt`, `snapshot_model_collection`, and
  `snapshot_model_input` from `_validation`;
- retain the local `UInt64`;
- remove the duplicate local aliases and snapshot functions;
- rename all private calls to the imported non-underscored helpers;
- do not change serialized schemas or validation messages unrelated to the helper names.

- [ ] **Step 4: Run regression tests**

Run:

```powershell
& 'D:\program\github\my_github\SycaSphere\.venv\Scripts\python.exe' -m pytest `
  packages/sycasphere-core/tests/test_execution.py -q
```

Expected: all execution tests pass.

- [ ] **Step 5: Format, lint, type-check, and commit**

Run:

```powershell
$env:UV_CACHE_DIR='D:\program\github\my_github\SycaSphere\.uv-cache'
uv run --no-sync ruff format packages/sycasphere-core/src/sycasphere/core/_validation.py `
  packages/sycasphere-core/src/sycasphere/core/execution.py `
  packages/sycasphere-core/tests/test_execution.py
uv run --no-sync ruff check packages/sycasphere-core/src/sycasphere/core/_validation.py `
  packages/sycasphere-core/src/sycasphere/core/execution.py `
  packages/sycasphere-core/tests/test_execution.py
uv run --no-sync mypy
git add packages/sycasphere-core/src/sycasphere/core/_validation.py `
  packages/sycasphere-core/src/sycasphere/core/execution.py `
  packages/sycasphere-core/tests/test_execution.py
git commit -m "refactor(core): centralize boundary validation helpers"
```

---

### Task 2: Add immutable attitude state

**Files:**
- Create: `packages/sycasphere-core/src/sycasphere/core/attitudes.py`
- Create: `packages/sycasphere-core/tests/test_attitudes.py`

**Interfaces:**
- Consumes: `Epoch`, `FrameRef`, `FrameKind`, `CoordinateRepresentation`,
  `StrictFiniteFloat`, `snapshot_model_input`, `require_builtin_float_sequence`.
- Produces:

```python
class AttitudeState(BaseModel):
    epoch: Epoch
    reference_frame: FrameRef
    rotation_reference_to_body_wxyz: tuple[
        StrictFiniteFloat,
        StrictFiniteFloat,
        StrictFiniteFloat,
        StrictFiniteFloat,
    ]
    angular_velocity_body_wrt_reference_rad_s: tuple[
        StrictFiniteFloat,
        StrictFiniteFloat,
        StrictFiniteFloat,
    ] | None = None
```

- [ ] **Step 1: Write failing AttitudeState tests**

Create `test_attitudes.py` with the required header and these cases:

```python
from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from sycasphere.core.attitudes import AttitudeState
from sycasphere.core.epoch import Epoch, TimeScale
from sycasphere.core.frames import FrameKind, FrameRef

EPOCH = Epoch(value="2026-07-28T00:00:00Z", time_scale=TimeScale.UTC)


def test_attitude_state_is_reference_to_body_wxyz_and_frozen() -> None:
    state = AttitudeState(
        epoch=EPOCH,
        reference_frame=FrameRef(kind=FrameKind.J2000),
        rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
        angular_velocity_body_wrt_reference_rad_s=(0.0, 0.0, 0.01),
    )

    assert state.rotation_reference_to_body_wxyz == (1.0, 0.0, 0.0, 0.0)
    assert state.angular_velocity_body_wrt_reference_rad_s == (0.0, 0.0, 0.01)
    with pytest.raises(ValidationError):
        state.rotation_reference_to_body_wxyz = (0.0, 1.0, 0.0, 0.0)


@pytest.mark.parametrize(
    "rotation",
    [
        (2.0, 0.0, 0.0, 0.0),
        (math.nan, 0.0, 0.0, 0.0),
        (1, 0.0, 0.0, 0.0),
    ],
)
def test_attitude_state_rejects_invalid_quaternion(rotation: object) -> None:
    with pytest.raises(ValidationError):
        AttitudeState(
            epoch=EPOCH,
            reference_frame=FrameRef(kind=FrameKind.J2000),
            rotation_reference_to_body_wxyz=rotation,
        )


@pytest.mark.parametrize("kind", [FrameKind.BODY, FrameKind.SENSOR])
def test_attitude_state_rejects_body_and_sensor_reference_frames(kind: FrameKind) -> None:
    with pytest.raises(ValidationError, match="reference_frame"):
        AttitudeState(
            epoch=EPOCH,
            reference_frame=FrameRef(
                kind=kind,
                owner_id="owner-1",
                convention="RIGHT_HANDED",
                reference_epoch=EPOCH,
            ),
            rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
        )


def test_attitude_state_distinguishes_unknown_and_zero_angular_velocity() -> None:
    unknown = AttitudeState(
        epoch=EPOCH,
        reference_frame=FrameRef(kind=FrameKind.J2000),
        rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
    )
    zero = AttitudeState(
        epoch=EPOCH,
        reference_frame=FrameRef(kind=FrameKind.J2000),
        rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
        angular_velocity_body_wrt_reference_rad_s=(0.0, 0.0, 0.0),
    )

    assert unknown.angular_velocity_body_wrt_reference_rad_s is None
    assert zero.angular_velocity_body_wrt_reference_rad_s == (0.0, 0.0, 0.0)


def test_attitude_state_revalidates_nested_instances() -> None:
    invalid_frame = FrameRef.model_construct(kind=FrameKind.BODY)

    with pytest.raises(ValidationError):
        AttitudeState(
            epoch=EPOCH,
            reference_frame=invalid_frame,
            rotation_reference_to_body_wxyz=(1.0, 0.0, 0.0, 0.0),
        )
```

Also parametrize valid Cartesian J2000, EARTH_FIXED, LVLH and VVLH references so every allowed
reference-frame branch is protected by a positive test.

- [ ] **Step 2: Verify the tests fail because AttitudeState is absent**

Run:

```powershell
& 'D:\program\github\my_github\SycaSphere\.venv\Scripts\python.exe' -m pytest `
  packages/sycasphere-core/tests/test_attitudes.py -q
```

Expected: import failure for `sycasphere.core.attitudes`.

- [ ] **Step 3: Implement AttitudeState**

Use:

```python
_ATTITUDE_TOLERANCE = 1e-9
_ALLOWED_REFERENCE_KINDS = {
    FrameKind.J2000,
    FrameKind.EARTH_FIXED,
    FrameKind.LVLH,
    FrameKind.VVLH,
}
```

The implementation must:

- set `ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")`;
- snapshot `epoch` and `reference_frame` in before validators;
- call `require_builtin_float_sequence` for quaternion and non-None angular velocity;
- reject reference frames outside the exact allowed set or non-Cartesian representation;
- use `math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-9)`;
- reject legacy or ambiguous fields through `extra="forbid"`;
- expose no quaternion order aliases and perform no silent normalization.

- [ ] **Step 4: Run the focused tests**

Run:

```powershell
& 'D:\program\github\my_github\SycaSphere\.venv\Scripts\python.exe' -m pytest `
  packages/sycasphere-core/tests/test_attitudes.py -q
```

Expected: all attitude tests pass.

- [ ] **Step 5: Run quality checks and commit**

Run Ruff format/check, `uv run --no-sync mypy`, then:

```powershell
git add packages/sycasphere-core/src/sycasphere/core/attitudes.py `
  packages/sycasphere-core/tests/test_attitudes.py
git commit -m "feat(core): define immutable attitude states"
```

---

### Task 3: Add TruthState and TruthManeuver

**Files:**
- Create: `packages/sycasphere-core/src/sycasphere/core/truth.py`
- Create: `packages/sycasphere-core/tests/test_truth.py`

**Interfaces:**
- Consumes: `AttitudeState`, `CartesianState`, `Epoch`,
  `_is_strictly_before_same_scale`, `FrameKind`, and shared validation helpers.
- Produces:

```python
class ManeuverTruthSource(StrEnum):
    PLANNED = "PLANNED"
    COMMAND = "COMMAND"


class TruthState(BaseModel):
    entity_id: DefinitionString
    cartesian_state: CartesianState
    attitude_state: AttitudeState | None = None
    mass_kg: PositiveStrictFiniteFloat | None = None

    @property
    def epoch(self) -> Epoch:
        return self.cartesian_state.epoch


class TruthManeuver(BaseModel):
    maneuver_event_id: DefinitionString
    source_kind: ManeuverTruthSource
    source_id: DefinitionString
    entity_id: DefinitionString
    scheduled_epoch: Epoch
    executed_epoch: Epoch
    actual_delta_v_j2000_mps: Vector3
    state_before: TruthState
    state_after: TruthState
```

- [ ] **Step 1: Write failing Truth tests**

Create fixtures for a J2000 CartesianState and write tests that assert:

```python
def test_truth_state_uses_cartesian_epoch_without_serialized_duplicate() -> None:
    state = make_truth_state()

    assert state.epoch == EPOCH
    assert "epoch" not in state.model_dump(mode="json")


def test_truth_state_requires_matching_attitude_epoch() -> None:
    with pytest.raises(ValidationError, match="epoch"):
        make_truth_state(attitude_epoch=OTHER_EPOCH)


@pytest.mark.parametrize("mass", [0.0, -1.0, 1, math.nan])
def test_truth_state_rejects_invalid_mass(mass: object) -> None:
    with pytest.raises(ValidationError):
        TruthState(
            entity_id="spacecraft-1",
            cartesian_state=make_cartesian_state(),
            mass_kg=mass,
        )


def test_truth_maneuver_records_actual_j2000_jump_and_mass_loss() -> None:
    before = make_truth_state(velocity=(0.0, 7_500.0, 0.0), mass_kg=500.0)
    after = make_truth_state(velocity=(0.0, 7_501.0, 0.0), mass_kg=499.9)
    event = TruthManeuver(
        maneuver_event_id="truth-maneuver-1",
        source_kind="COMMAND",
        source_id="command-1",
        entity_id="spacecraft-1",
        scheduled_epoch=EPOCH,
        executed_epoch=EPOCH,
        actual_delta_v_j2000_mps=(0.0, 1.0, 0.0),
        state_before=before,
        state_after=after,
    )

    assert event.source_kind is ManeuverTruthSource.COMMAND
    assert event.state_after.mass_kg == 499.9


def test_truth_maneuver_rejects_entity_epoch_frame_and_mass_mismatches() -> None:
    valid = valid_truth_maneuver_data()
    invalid_cases = (
        {"state_after": make_truth_state(entity_id="other")},
        {"state_after": make_truth_state(epoch=OTHER_EPOCH)},
        {"state_after": make_truth_state(frame=valid_earth_fixed_frame())},
        {
            "state_before": make_truth_state(mass_kg=500.0),
            "state_after": make_truth_state(mass_kg=501.0),
        },
    )

    for update in invalid_cases:
        with pytest.raises(ValidationError):
            TruthManeuver.model_validate({**valid, **update})
```

Also test:

- both PLANNED and COMMAND sources with required nonblank source IDs;
- executed epoch earlier than scheduled epoch in the same TimeScale;
- cross-TimeScale ordering remains structurally valid for Engine;
- integer/NaN Δv components fail;
- nested `model_construct` instances are revalidated;
- both models are frozen and JSON round-trip exactly.

- [ ] **Step 2: Verify import failure**

Run:

```powershell
& 'D:\program\github\my_github\SycaSphere\.venv\Scripts\python.exe' -m pytest `
  packages/sycasphere-core/tests/test_truth.py -q
```

Expected: import failure for `sycasphere.core.truth`.

- [ ] **Step 3: Implement Truth models**

Use
`PositiveStrictFiniteFloat = Annotated[float, Strict(), AllowInfNan(False), Field(gt=0.0)]`
and an exact three-component tuple alias.

`TruthState` after validation:

```python
if self.attitude_state is not None:
    if self.attitude_state.epoch != self.cartesian_state.epoch:
        raise ValueError("attitude_state epoch must equal cartesian_state epoch")
```

`TruthManeuver` after validation must:

```python
states = (self.state_before, self.state_after)
if any(state.entity_id != self.entity_id for state in states):
    raise ValueError("truth maneuver states must match entity_id")
if any(state.epoch != self.executed_epoch for state in states):
    raise ValueError("truth maneuver states must match executed_epoch")
if any(state.cartesian_state.frame.kind is not FrameKind.J2000 for state in states):
    raise ValueError("truth maneuver states must use J2000")
if _is_strictly_before_same_scale(self.executed_epoch, self.scheduled_epoch) is True:
    raise ValueError("executed_epoch must not be before scheduled_epoch")
before_mass = self.state_before.mass_kg
after_mass = self.state_after.mass_kg
if before_mass is not None and after_mass is not None and after_mass > before_mass:
    raise ValueError("truth maneuver mass must not increase")
```

Snapshot every nested model before Pydantic validation. Do not compare actual Δv to the velocity
difference or silently calculate missing mass.

- [ ] **Step 4: Run Truth plus existing maneuver tests**

Run:

```powershell
& 'D:\program\github\my_github\SycaSphere\.venv\Scripts\python.exe' -m pytest `
  packages/sycasphere-core/tests/test_truth.py `
  packages/sycasphere-core/tests/test_maneuvers.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Run quality checks and commit**

```powershell
git add packages/sycasphere-core/src/sycasphere/core/truth.py `
  packages/sycasphere-core/tests/test_truth.py
git commit -m "feat(core): define truth state and maneuver results"
```

---

### Task 4: Define observation identity, events, and measurement payloads

**Files:**
- Create: `packages/sycasphere-core/src/sycasphere/core/observations.py`
- Create: `packages/sycasphere-core/tests/test_observations.py`

**Interfaces:**
- Produces:
  - `KnownObjectSubjectRef`, `TrackletSubjectRef`, `UnassociatedSubjectRef`;
  - discriminated `ObservationSubjectRef`;
  - `MeasurementType`, `GeometryStatus`, `CustomMeasurementSchemaRef`;
  - `ObservationMeasurement`, `ObservationEvent`.
- Consumes: `FrameRef`, `ModelRef`, `SchemaVersion`, frozen JSON helpers and shared validators.

- [ ] **Step 1: Write failing SubjectRef and Measurement tests**

Create `test_observations.py` with reusable model/frame fixtures and these exact behaviors:

```python
def test_subject_ref_union_supports_known_tracklet_and_unassociated_modes() -> None:
    adapter = TypeAdapter(ObservationSubjectRef)
    assert isinstance(
        adapter.validate_python({"kind": "KNOWN_OBJECT", "object_id": "public-1"}),
        KnownObjectSubjectRef,
    )
    assert isinstance(
        adapter.validate_python({"kind": "TRACKLET", "tracklet_id": "tracklet-1"}),
        TrackletSubjectRef,
    )
    assert isinstance(
        adapter.validate_python({"kind": "UNASSOCIATED"}),
        UnassociatedSubjectRef,
    )


def test_ra_dec_measurement_is_strict_self_describing_j2000() -> None:
    measurement = ObservationMeasurement(
        measurement_type="ANGLES_RA_DEC",
        values=(1.0, 0.2),
        component_names=("right_ascension", "declination"),
        component_units=("rad", "rad"),
        frame=FrameRef(kind=FrameKind.J2000),
        qualifiers={},
    )

    assert measurement.values == (1.0, 0.2)


@pytest.mark.parametrize(
    "data",
    [
        ra_dec_data(values=(2.0 * math.pi, 0.0)),
        ra_dec_data(values=(0.0, math.pi)),
        ra_dec_data(component_units=("deg", "deg")),
        ra_dec_data(frame=None),
        range_data(values=(-1.0,)),
        los_data(values=(1.0, 1.0, 0.0)),
        range_data(qualifiers={"path_kind": "ROUND_TRIP"}),
    ],
)
def test_standard_measurements_reject_invalid_values_and_semantics(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ObservationMeasurement.model_validate(data)


def test_custom_measurement_requires_exact_schema_reference() -> None:
    measurement = ObservationMeasurement(
        measurement_type="CUSTOM",
        values=(10.0, 20.0),
        component_names=("pixel_x", "pixel_y"),
        component_units=("pixel", "pixel"),
        frame=None,
        custom_type="org.example/PIXEL_CENTROID_V1",
        custom_schema_ref=CustomMeasurementSchemaRef(
            schema_id="org.example/PIXEL_CENTROID_SCHEMA",
            schema_version=SchemaVersion(major=1, minor=0),
            sha256="a" * 64,
        ),
        qualifiers={"detector": "primary"},
    )

    assert measurement.custom_schema_ref.sha256 == "a" * 64
```

Parametrize valid standard cases for:

- AZ/EL with SENSOR and BODY frames plus exact `angle_convention_id`;
- one-way and two-way RANGE;
- signed RANGE_RATE with positive integration interval;
- unit LOS in J2000 and SENSOR.

Reject:

- integer, bool, NaN and infinity values;
- wrong tuple lengths, names, units, frames or qualifiers;
- extra standard qualifier keys;
- CUSTOM without namespaced type/schema hash;
- non-CUSTOM with custom fields;
- blank IDs and unknown fields.

- [ ] **Step 2: Write failing ObservationEvent lifecycle tests**

Add:

```python
def test_observation_event_is_a_final_geometry_fact_with_internal_and_public_identity() -> None:
    event = make_event(
        geometry_status="OCCLUDED",
        public_subject_ref={"kind": "UNASSOCIATED"},
    )

    assert event.truth_target_entity_id == "truth-target-1"
    assert event.public_subject_ref.kind == "UNASSOCIATED"
    with pytest.raises(ValidationError):
        event.geometry_status = GeometryStatus.VISIBLE


def test_event_schema_has_no_pending_geometry_state() -> None:
    schema = ObservationEvent.model_json_schema()
    geometry_schema = schema["$defs"]["GeometryStatus"]

    assert "PENDING" not in geometry_schema["enum"]
```

Also verify Event rejects an invalid nested SubjectRef or ModelRef built with `model_construct`.

- [ ] **Step 3: Run the new file and verify import failure**

Run:

```powershell
& 'D:\program\github\my_github\SycaSphere\.venv\Scripts\python.exe' -m pytest `
  packages/sycasphere-core/tests/test_observations.py -q
```

Expected: import failure for `sycasphere.core.observations`.

- [ ] **Step 4: Implement identity, custom schema, measurement, and Event**

Use exact enum values from the design. Define unions with:

```python
type ObservationSubjectRef = Annotated[
    KnownObjectSubjectRef | TrackletSubjectRef | UnassociatedSubjectRef,
    Field(discriminator="kind"),
]
```

For qualifiers:

- normalize and deep-freeze with `_json` helpers;
- serialize back to ordinary JSON;
- enforce exact standard key sets;
- validate namespaced IDs with
  `r"^[A-Za-z0-9][A-Za-z0-9_.-]*(?:\.[A-Za-z0-9_.-]+)+/[A-Za-z0-9_.-]+$"`;
- require `type(integration_interval_s) is float` and value `> 0.0`.

The Measurement after validator must dispatch by MeasurementType to small private pure functions:

```python
_validate_ra_dec(self)
_validate_az_el(self)
_validate_range(self)
_validate_range_rate(self)
_validate_los(self)
_validate_custom(self)
```

Each helper compares the exact component tuple, units, allowed frame kinds, numeric range and qualifier
shape from design section 10. Do not silently normalize angles, vectors, names, units or qualifiers.

ObservationEvent snapshots all nested models and has no PENDING state or mutation method.

- [ ] **Step 5: Run focused tests and commit**

Run the observation tests, Ruff format/check, and mypy. Then:

```powershell
git add packages/sycasphere-core/src/sycasphere/core/observations.py `
  packages/sycasphere-core/tests/test_observations.py
git commit -m "feat(core): define observation events and measurements"
```

---

### Task 5: Add uncertainty and separate Ideal/Reported observations

**Files:**
- Modify: `packages/sycasphere-core/src/sycasphere/core/observations.py`
- Modify: `packages/sycasphere-core/tests/test_observations.py`

**Interfaces:**
- Produces: `ObservationChannel`, `MeasurementUncertainty`,
  `IdealObservation`, `ReportedObservation`.
- `MeasurementUncertainty.from_standard_deviations(
  measurement, standard_deviations) -> MeasurementUncertainty`.

- [ ] **Step 1: Add failing covariance tests**

```python
def test_uncertainty_factory_normalizes_standard_deviations_to_covariance() -> None:
    measurement = valid_ra_dec_measurement()
    uncertainty = MeasurementUncertainty.from_standard_deviations(
        measurement,
        (2.0e-5, 3.0e-5),
    )

    assert uncertainty.component_names == measurement.component_names
    assert uncertainty.component_units == measurement.component_units
    assert uncertainty.covariance == (
        (4.0e-10, 0.0),
        (0.0, 9.0e-10),
    )


@pytest.mark.parametrize(
    "covariance",
    [
        ((1.0,),),
        ((1.0, math.nan), (math.nan, 1.0)),
        ((1.0, 0.1), (0.2, 1.0)),
        ((1.0, 2.0), (2.0, 1.0)),
        ((-1.0, 0.0), (0.0, 1.0)),
    ],
)
def test_uncertainty_rejects_invalid_covariance(covariance: object) -> None:
    with pytest.raises(ValidationError):
        MeasurementUncertainty(
            semantics="EFFECTIVE_RESIDUAL_ERROR_COVARIANCE_V1",
            component_names=("right_ascension", "declination"),
            component_units=("rad", "rad"),
            covariance=covariance,
        )
```

Also test:

- strict nonnegative standard deviations;
- alias independence after mutating input rows;
- zero covariance differs from uncertainty None;
- symmetry and eigenvalue tolerances at accepted/rejected boundaries.

- [ ] **Step 2: Add failing Ideal/Reported separation tests**

```python
def test_ideal_and_reported_are_separate_discriminated_models() -> None:
    ideal = make_ideal()
    reported = make_reported()

    assert ideal.channel is ObservationChannel.IDEAL
    assert reported.channel is ObservationChannel.REPORTED
    assert ideal.event_id == reported.event_id
    assert ideal.observation_id != reported.observation_id
    assert TypeAdapter(Observation).validate_python(
        ideal.model_dump(mode="json")
    ) == ideal
    assert TypeAdapter(Observation).validate_python(
        reported.model_dump(mode="json")
    ) == reported


def test_algorithm_visible_observation_schemas_exclude_truth_and_realized_errors() -> None:
    forbidden = {
        "truth_target_entity_id",
        "truth_state",
        "actual_error",
        "noise_sample",
        "true_bias",
        "truth_residual",
    }

    assert forbidden.isdisjoint(IdealObservation.model_fields)
    assert forbidden.isdisjoint(ReportedObservation.model_fields)


def test_reported_uncertainty_must_match_measurement_components() -> None:
    with pytest.raises(ValidationError, match="uncertainty"):
        make_reported(
            uncertainty=MeasurementUncertainty(
                semantics="EFFECTIVE_RESIDUAL_ERROR_COVARIANCE_V1",
                component_names=("range",),
                component_units=("m",),
                covariance=((1.0,),),
            )
        )
```

Test `extra="forbid"` by attempting to submit `truth_target_entity_id` and `noise_sample`.
Test copied invalid ModelRef, SubjectRef, Measurement and Uncertainty instances are revalidated.

- [ ] **Step 3: Verify focused tests fail for missing models**

Run:

```powershell
& 'D:\program\github\my_github\SycaSphere\.venv\Scripts\python.exe' -m pytest `
  packages/sycasphere-core/tests/test_observations.py -q
```

Expected: imports or attribute lookups fail for the new models.

- [ ] **Step 4: Implement covariance and observation models**

Use:

```python
class ObservationChannel(StrEnum):
    IDEAL = "IDEAL"
    REPORTED = "REPORTED"


type Observation = Annotated[
    IdealObservation | ReportedObservation,
    Field(discriminator="channel"),
]
```

Covariance implementation:

- snapshot rows into immutable tuples before validation;
- require square matrix and component cardinality equality;
- require exact nonnegative diagonal;
- compute `scale = max(1.0, max(abs(value) for row in covariance for value in row))`;
- use `np.allclose(matrix, matrix.T, rtol=0.0, atol=1e-12 * scale)`;
- use `np.linalg.eigvalsh((matrix + matrix.T) / 2.0)`;
- reject minimum eigenvalue below `-1e-12 * scale`;
- return independent arrays only from explicitly named numerical helper methods.

Ideal/Reported share field shapes but remain separate classes. Do not introduce public inheritance that
publishes an abstract Observation base schema. Snapshot every nested model. Reported after validation
requires uncertainty component names and units to equal measurement when uncertainty is present.

- [ ] **Step 5: Run observation tests and commit**

Run focused tests, Ruff, and mypy. Then:

```powershell
git add packages/sycasphere-core/src/sycasphere/core/observations.py `
  packages/sycasphere-core/tests/test_observations.py
git commit -m "feat(core): separate ideal and reported observations"
```

---

### Task 6: Add delivery outcomes, summaries, envelopes, and output switch

**Files:**
- Create: `packages/sycasphere-core/src/sycasphere/core/delivery.py`
- Create: `packages/sycasphere-core/tests/test_delivery.py`
- Modify: `packages/sycasphere-core/src/sycasphere/core/execution.py`
- Modify: `packages/sycasphere-core/tests/test_execution.py`

**Interfaces:**
- Produces: `DeliveryOutcome`, `ObservationDeliveryRecord`,
  `DeliverySummary`, `StreamingObservationEnvelope`.
- Extends: `OutputRequirement.DELIVERY_RECORDS`.
- Consumes: `Observation`, `ObservationChannel`, Epoch comparator, `Sha256Hex`.

- [ ] **Step 1: Write failing DeliveryRecord state-matrix tests**

Create `test_delivery.py` with a valid-record factory and:

```python
@pytest.mark.parametrize(
    ("outcome", "channel", "ideal_id", "reported_id", "delivered"),
    [
        ("GEOMETRY_REJECTED", "IDEAL", None, None, False),
        ("GEOMETRY_REJECTED", "REPORTED", None, None, False),
        ("SENSOR_MISSED", "REPORTED", "ideal-1", None, False),
        ("QUALITY_REJECTED", "REPORTED", "ideal-1", None, False),
        ("LINK_DROPPED", "IDEAL", "ideal-1", None, False),
        ("LINK_DROPPED", "REPORTED", "ideal-1", "reported-1", False),
        ("DELIVERED", "IDEAL", "ideal-1", None, True),
        ("DELIVERED", "REPORTED", "ideal-1", "reported-1", True),
    ],
)
def test_delivery_record_accepts_exact_terminal_state_matrix(
    outcome: str,
    channel: str,
    ideal_id: str | None,
    reported_id: str | None,
    delivered: bool,
) -> None:
    record = make_delivery_record(
        outcome=outcome,
        selected_channel=channel,
        ideal_observation_id=ideal_id,
        reported_observation_id=reported_id,
        delivery_epoch=DELIVERY_EPOCH if delivered else None,
        latency_s=5.0 if delivered else None,
        observation_payload_sha256="a" * 64
        if outcome in {"LINK_DROPPED", "DELIVERED"}
        else None,
    )

    assert (record.delivery_epoch is not None) is delivered
```

Add explicit negative cases:

- geometry reject with any observation ID;
- sensor missed/quality rejected on IDEAL channel;
- delivered without epoch, latency, selected payload ID or hash;
- non-delivered with delivery epoch/latency;
- REPORTED link/drop without both Ideal and Reported IDs;
- IDEAL link/drop with Reported ID;
- negative/integer/NaN latency;
- invalid SHA-256 or reason namespace;
- delivery TimeScale mismatch or delivery before measurement.

- [ ] **Step 2: Write failing Summary and Envelope tests**

```python
def test_delivery_summary_counts_must_conserve_total_events() -> None:
    summary = DeliverySummary(
        total_events=5,
        delivered=1,
        geometry_rejected=1,
        sensor_missed=1,
        quality_rejected=1,
        link_dropped=1,
    )
    assert summary.total_events == 5

    with pytest.raises(ValidationError, match="sum"):
        DeliverySummary(
            total_events=6,
            delivered=summary.delivered,
            geometry_rejected=summary.geometry_rejected,
            sensor_missed=summary.sensor_missed,
            quality_rejected=summary.quality_rejected,
            link_dropped=summary.link_dropped,
        )


def test_streaming_envelope_wraps_only_matching_delivered_observation() -> None:
    observation = make_reported_observation()
    envelope = StreamingObservationEnvelope(
        event_id=observation.event_id,
        delivery_epoch=DELIVERY_EPOCH,
        observation=observation,
    )

    assert envelope.observation.channel is ObservationChannel.REPORTED

    with pytest.raises(ValidationError, match="event_id"):
        StreamingObservationEnvelope(
            event_id="other",
            delivery_epoch=DELIVERY_EPOCH,
            observation=observation,
        )
```

Also reject delivery before measurement and cross-TimeScale delivery.

- [ ] **Step 3: Add the failing output-switch test**

Append to `test_execution.py`:

```python
def test_delivery_records_is_a_distinct_output_requirement() -> None:
    assert OutputRequirement.DELIVERY_RECORDS.value == "DELIVERY_RECORDS"
    assert OutputRequirement.DELIVERY_RECORDS is not OutputRequirement.DELIVERY_SUMMARY
```

Run the two files and expect imports/enum lookup to fail.

- [ ] **Step 4: Implement delivery contracts and output enum**

Implement exact enums and strict model configs. Use small pure validators:

```python
_GEOMETRY_REASONS = frozenset(
    {
        "sycasphere.geometry/OCCLUDED",
        "sycasphere.geometry/OUT_OF_FIELD_OF_VIEW",
        "sycasphere.geometry/INSUFFICIENT_ILLUMINATION",
        "sycasphere.geometry/POINTING_UNAVAILABLE",
    }
)
```

The DeliveryRecord after validator must implement the exact table in design section 13 rather than
independent partial checks. `DELIVERED` and `LINK_DROPPED` require payload hash. Only `DELIVERED`
accepts delivery epoch and latency.

`DeliverySummary` uses `StrictNonNegativeInt` and validates:

```python
outcome_total = (
    self.delivered
    + self.geometry_rejected
    + self.sensor_missed
    + self.quality_rejected
    + self.link_dropped
)
if outcome_total != self.total_events:
    raise ValueError("delivery outcome counts must sum to total_events")
```

Envelope snapshots and revalidates the discriminated Observation and compares event/time fields.
Because the envelope intentionally contains no DeliveryRecord, Core cannot independently prove the
DELIVERED outcome; Engine may construct it only after a DELIVERED record has passed lineage checks.
Add `DELIVERY_RECORDS = "DELIVERY_RECORDS"` next to `DELIVERY_SUMMARY` in execution.py.

- [ ] **Step 5: Run focused and regression tests, then commit**

Run:

```powershell
& 'D:\program\github\my_github\SycaSphere\.venv\Scripts\python.exe' -m pytest `
  packages/sycasphere-core/tests/test_delivery.py `
  packages/sycasphere-core/tests/test_execution.py -q
```

Then Ruff/mypy and:

```powershell
git add packages/sycasphere-core/src/sycasphere/core/delivery.py `
  packages/sycasphere-core/src/sycasphere/core/execution.py `
  packages/sycasphere-core/tests/test_delivery.py `
  packages/sycasphere-core/tests/test_execution.py
git commit -m "feat(core): define observation delivery outcomes"
```

---

### Task 7: Publish the API, schemas, and package documentation

**Files:**
- Modify: `packages/sycasphere-core/src/sycasphere/core/__init__.py`
- Modify: `packages/sycasphere-core/tests/test_public_api.py`
- Modify: `packages/sycasphere-core/tests/snapshots/core-schemas.json`
- Modify: `packages/sycasphere-core/tests/test_package.py`
- Modify: `README.md`
- Modify: `packages/sycasphere-core/README.md`

**Interfaces:**
- Consumes: every public model from Tasks 2–6.
- Produces: exact reviewed import set and deterministic JSON Schema snapshot.

- [ ] **Step 1: Lock the new public import set before exporting it**

Extend `EXPECTED_PUBLIC_CONTRACTS` with exactly:

```python
{
    "AttitudeState",
    "CustomMeasurementSchemaRef",
    "DeliveryOutcome",
    "DeliverySummary",
    "GeometryStatus",
    "IdealObservation",
    "KnownObjectSubjectRef",
    "ManeuverTruthSource",
    "MeasurementType",
    "MeasurementUncertainty",
    "ObservationChannel",
    "ObservationDeliveryRecord",
    "ObservationEvent",
    "ObservationMeasurement",
    "ObservationSubjectRef",
    "ReportedObservation",
    "StreamingObservationEnvelope",
    "TrackletSubjectRef",
    "TruthManeuver",
    "TruthState",
    "UnassociatedSubjectRef",
}
```

Extend `_public_model_schemas()` with every concrete Pydantic model. Add:

```python
schemas["ObservationSubjectRef"] = TypeAdapter(
    core.ObservationSubjectRef
).json_schema()
```

Add discriminator assertions:

```python
assert schemas["ObservationSubjectRef"]["discriminator"]["propertyName"] == "kind"
assert (
    schemas["StreamingObservationEnvelope"]["properties"]["observation"]
    ["discriminator"]["propertyName"]
    == "channel"
)
```

Add schema leak assertions that Ideal/Reported properties exclude the forbidden Truth/error fields.

- [ ] **Step 2: Run the API test and verify exact export/snapshot failures**

Run:

```powershell
& 'D:\program\github\my_github\SycaSphere\.venv\Scripts\python.exe' -m pytest `
  packages/sycasphere-core/tests/test_public_api.py -q
```

Expected: public exports and snapshot fail until `__init__.py` and snapshot are updated.

- [ ] **Step 3: Export only the reviewed names**

Import from the four new modules and add the exact names to `__all__` in lexical order. Update the
Sycamore header purpose, feature list, version to `v1.3.0`, last-modified date, and changelog.

Do not export:

- private aliases or validation helpers;
- the internal `Observation` union alias;
- covariance tolerance constants;
- Truth authorization maps;
- error/link implementation objects.

- [ ] **Step 4: Regenerate and review the schema snapshot**

Use the existing `_serialized_public_model_schemas()` function:

```powershell
& 'D:\program\github\my_github\SycaSphere\.venv\Scripts\python.exe' -c `
  "from pathlib import Path; from importlib.util import module_from_spec, spec_from_file_location; p=Path('packages/sycasphere-core/tests/test_public_api.py'); s=spec_from_file_location('schema_snapshot', p); m=module_from_spec(s); s.loader.exec_module(m); Path('packages/sycasphere-core/tests/snapshots/core-schemas.json').write_text(m._serialized_public_model_schemas(), encoding='utf-8')"
```

Review the diff and assert:

- SubjectRef uses `kind` discriminator;
- Streaming envelope observation uses `channel` discriminator;
- no Truth target field appears under Ideal/Reported;
- no noise sample or realized bias field appears;
- `DELIVERY_RECORDS` appears in OutputRequirement;
- no Orekit/JPype/Java schema names appear.

- [ ] **Step 5: Add README contract tests and documentation**

Extend `DOCUMENTED_CONTRACTS` in `test_package.py` with:

```python
(
    "TruthState",
    "TruthManeuver",
    "IdealObservation",
    "ReportedObservation",
    "ObservationDeliveryRecord",
    "DeliverySummary",
)
```

Update both READMEs to explain:

- Truth/Ideal/Reported separation;
- algorithm-safe SubjectRef;
- effective residual covariance semantics;
- Event per schedule occurrence, not per render frame;
- one terminal DeliveryRecord per Event;
- delay/drop only, no reorder/duplicate/retry;
- `DELIVERY_SUMMARY` versus `DELIVERY_RECORDS`;
- Engine/Orekit execution remains planned.

- [ ] **Step 6: Run API/package tests and commit**

Run:

```powershell
& 'D:\program\github\my_github\SycaSphere\.venv\Scripts\python.exe' -m pytest `
  packages/sycasphere-core/tests/test_public_api.py `
  packages/sycasphere-core/tests/test_package.py -q
```

Then Ruff/mypy and:

```powershell
git add README.md packages/sycasphere-core/README.md `
  packages/sycasphere-core/src/sycasphere/core/__init__.py `
  packages/sycasphere-core/tests/test_public_api.py `
  packages/sycasphere-core/tests/test_package.py `
  packages/sycasphere-core/tests/snapshots/core-schemas.json
git commit -m "feat(core): publish truth observation delivery schemas"
```

---

### Task 8: Synchronize authoritative architecture and perform release verification

**Files:**
- Modify: `docs/architecture/core-data-model-v0.2.md`
- Modify: `docs/architecture/algorithm-integration-v0.2.md`
- Modify:
  `docs/superpowers/specs/2026-07-20-sycasphere-runtime-and-simulation-engine-design.md`
- Modify only for evidence-backed corrections:
  `docs/superpowers/specs/2026-07-28-core-truth-observation-delivery-design.md`

**Interfaces:**
- Consumes: final reviewed public API and schemas from Task 7.
- Produces: synchronized status claims and release evidence.

- [ ] **Step 1: Add documentation consistency tests first**

In `test_package.py`, add assertions that the authoritative documents:

- mark Truth/Observation/Delivery Core contracts implemented;
- continue marking Engine execution, Orekit, storage, algorithms and frontend as planned;
- contain `DELIVERY_RECORDS`;
- contain the Chinese-label requirement;
- contain no `AlgorithmObservationView`, `NonDetectionReport`, reorder, duplicate or retransmission
  claim in the implemented first-version scope.

Use exact stable phrases from the design rather than broad substring negation.

- [ ] **Step 2: Run package tests and verify documentation failures**

Run:

```powershell
& 'D:\program\github\my_github\SycaSphere\.venv\Scripts\python.exe' -m pytest `
  packages/sycasphere-core/tests/test_package.py -q
```

Expected: new documentation assertions fail before synchronization.

- [ ] **Step 3: Synchronize all three authoritative documents**

Update them to state:

- the design section 3 `schema.py` modification entry is removed because this batch reuses
  `SchemaVersion` unchanged and introduces no schema-version behavior there;
- Core now implements AttitudeState, TruthState, TruthManeuver, ObservationEvent,
  ObservationMeasurement, IdealObservation, ReportedObservation, MeasurementUncertainty,
  DeliveryRecord, DeliverySummary and StreamingEnvelope;
- Event is created once after geometry evaluation using a preallocated deterministic event ID;
- Observation occurs per schedule trigger, not per integration/output/render frame;
- schedule `error_profile_id` selects IDEAL versus REPORTED delivery channel;
- output requirements control artifact persistence, not scientific pipeline execution;
- algorithms receive only successful delivery payloads;
- the link first version supports delay/drop and FIFO only;
- detailed delivery output is optional and transient by default in future Sim;
- Chinese UI labels remain a frontend requirement, not hashed scientific data;
- Engine, Orekit, Sim retention and frontend implementations remain planned.

- [ ] **Step 4: Run the full quality gate**

From the worktree root:

```powershell
$env:UV_CACHE_DIR='D:\program\github\my_github\SycaSphere\.uv-cache'
uv run --no-sync ruff format --check .
uv run --no-sync ruff check .
uv run --no-sync mypy
uv run --no-sync pytest
```

Expected:

- Ruff format passes;
- Ruff lint passes;
- mypy reports no issues;
- all tests pass with no warnings introduced by this batch.

- [ ] **Step 5: Build and inspect Core distributions**

Create a unique ignored build directory under `.build`, then run:

```powershell
$env:UV_CACHE_DIR='D:\program\github\my_github\SycaSphere\.uv-cache'
$buildRoot = Join-Path '.build' (
  'core-truth-observation-final-' + [guid]::NewGuid().ToString('N')
)
uv build --offline --no-build-isolation packages/sycasphere-core `
  --out-dir $buildRoot
```

Inspect wheel/sdist members and verify:

- all four public new modules plus `_validation.py` are present;
- `LICENSE` and PEP 639 metadata remain correct;
- tests and repository docs are absent from wheel;
- Engine, Orekit, Platform, Sim, JPype and Java are absent;
- an isolated Python 3.12 environment can import every reviewed public contract;
- `uv pip check` reports compatible dependencies.

- [ ] **Step 6: Perform final diff review**

Review:

```powershell
$implementationBase = git merge-base main HEAD
git diff --check "$implementationBase..HEAD"
git diff --stat "$implementationBase..HEAD"
git status -sb
```

Inspect the complete branch diff for:

- time-scale and epoch comparison mistakes;
- J2000/BODY/SENSOR direction mistakes;
- quaternion order mistakes;
- non-SI values;
- Truth identity or realized-error leakage;
- mutable nested containers;
- DeliveryRecord state-matrix gaps;
- accidental lifecycle fields in Manifest;
- unrequested implementation scope.

- [ ] **Step 7: Commit synchronized documents**

Commit the synchronized documents before requesting the final independent review:

```powershell
git add docs/architecture/core-data-model-v0.2.md `
  docs/architecture/algorithm-integration-v0.2.md `
  docs/superpowers/specs/2026-07-20-sycasphere-runtime-and-simulation-engine-design.md `
  docs/superpowers/specs/2026-07-28-core-truth-observation-delivery-design.md `
  packages/sycasphere-core/tests/test_package.py
git commit -m "docs: align truth observation delivery contracts"
```

- [ ] **Step 8: Request independent code review**

Use the requesting-code-review skill with:

- base commit: `git merge-base main HEAD`;
- head commit: current branch HEAD after the synchronized-docs commit;
- requirements: the 2026-07-28 design and this plan;
- explicit review focus: frame/time/unit semantics, Truth authorization, covariance validation,
  Pydantic instance revalidation, delivery state matrix, schema compatibility and package isolation.

Resolve every Critical, Important and Minor finding with a failing regression test before the fix,
commit each correction, and repeat the full quality/build gates after the final correction.

---

## Final Review and Integration Gate

After Tasks 1–8:

1. Re-run Ruff format, Ruff lint, mypy and full pytest from a clean process.
2. Rebuild wheel/sdist and repeat isolated import checks from the final commit.
3. Confirm `git diff --check` and a clean tracked worktree.
4. Confirm the schema snapshot has no unexplained changes.
5. Confirm the final independent reviewer reports no unresolved findings.
6. Use `finishing-a-development-branch` to offer local merge, PR, keep, or discard.
7. Do not push `main` directly; if publishing, push the feature branch and create a draft PR.
