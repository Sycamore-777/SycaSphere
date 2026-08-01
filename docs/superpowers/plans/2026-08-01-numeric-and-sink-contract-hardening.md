# Numeric and Sink Contract Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject nonzero standard deviations whose derived variances cannot be represented faithfully as finite Python floats, and lock the existing Engine Sink error and rollback contracts with regression tests.

**Architecture:** Keep the public Core and Engine APIs unchanged. Perform derived-variance representability validation inside the existing Pydantic `StandardDeviations` boundary, then construct the same diagonal `MeasurementUncertainty`; make no Engine production change and strengthen only its Sink tests.

**Tech Stack:** Python 3.12, Pydantic v2, `decimal.Decimal`, NumPy, pytest, Ruff, mypy, uv.

## Global Constraints

- Follow `AGENTS.md` and the authoritative architecture documents before changing domain behavior.
- Work only in the isolated `codex/numeric-sink-hardening` worktree.
- Use Python 3.12 and the locked uv environment; do not add a dependency or modify `uv.lock`.
- Preserve Core's existing public float covariance Schema and Engine's existing public Sink API.
- Standard deviation `0.0` remains valid and produces variance `0.0`.
- A nonzero standard deviation whose square becomes `0.0` or non-finite as a built-in float must fail through Pydantic validation.
- Square each finite standard deviation with a new, explicit `decimal.Context`: `prec=40`, `rounding=ROUND_HALF_EVEN`, `Emin=-999999`, `Emax=999999`, `capitals=1`, `clamp=0`, `flags=[]`, and `traps=[]`. Do not use ambient-context exponentiation.
- Positive infinity and `NaN` must continue to fail through the existing `StrictFiniteFloat` finite-number error; preserve the existing negative-value validation order.
- Directly supplied finite covariance values, including `5e-324`, retain their current semantics.
- Do not add Composite cleanup retry behavior.
- Update every modified Python file's Sycamore header accurately with date `2026-08-01`.
- Do not modify, stage, or delete `docs/assets/`.
- Run uv commands serially because concurrent `uv run` processes must not mutate one shared `.venv`.

---

## File Map

- `packages/sycasphere-core/src/sycasphere/core/observations.py`: validate that every derived variance has a faithful finite built-in-float representation.
- `packages/sycasphere-core/tests/test_observations.py`: reproduce nonzero-to-zero underflow, lock overflow rejection, and preserve valid subnormal variance behavior.
- `packages/sycasphere-engine/tests/test_sinks.py`: lock stable Sink error details and Composite begin-rollback state without changing Engine production behavior.
- `docs/superpowers/specs/2026-08-01-numeric-and-sink-contract-hardening-design.md`: approved requirements; read-only during implementation unless a proven contradiction is reported first.
- `docs/superpowers/plans/2026-08-01-numeric-and-sink-contract-hardening.md`: this execution plan.

---

### Task 1: Reject Unrepresentable Derived Variances

**Files:**
- Modify: `packages/sycasphere-core/src/sycasphere/core/observations.py:6-108`
- Test: `packages/sycasphere-core/tests/test_observations.py:6-32`
- Test: `packages/sycasphere-core/tests/test_observations.py:647-850`

**Interfaces:**
- Consumes: `MeasurementUncertainty.from_standard_deviations(measurement, standard_deviations)` and the existing `StandardDeviations` `TypeAdapter` boundary.
- Produces: unchanged public factory signature; strict `ValidationError` rejection with message `standard-deviation variance must be representable as a finite float` for derived underflow or non-finite variance.

- [ ] **Step 1: Add the failing underflow and boundary-regression tests**

Update the test header to `最后修改  : 2026-08-01`, version `v1.3.0`, add an accurate feature bullet for derived-variance representability, and add this update-log entry:

```text
v1.3.0 (2026-08-01): 增加标准差平方可表示性边界回归测试。
```

Add these tests beside the existing standard-deviation factory tests:

```python
@pytest.mark.parametrize("deviation", [1.0e-200, 1.0e200])
def test_uncertainty_factory_rejects_unrepresentable_derived_variance(
    deviation: float,
) -> None:
    """A nonzero deviation cannot become zero or non-finite covariance."""
    with pytest.raises(
        ValidationError,
        match="standard-deviation variance must be representable as a finite float",
    ):
        MeasurementUncertainty.from_standard_deviations(
            valid_ra_dec_measurement(),
            (deviation, 1.0),
        )


def test_uncertainty_factory_accepts_representable_subnormal_derived_variance() -> None:
    """A derived positive subnormal float remains a valid covariance entry."""
    uncertainty = MeasurementUncertainty.from_standard_deviations(
        valid_ra_dec_measurement(),
        (1.0e-160, 0.0),
    )

    assert uncertainty.covariance == ((1.0e-320, 0.0), (0.0, 0.0))
```

Also add four behavioral regressions: derived underflow, derived overflow, hostile active
decimal contexts (precision plus exponent/trap settings), and the positive-infinity/`NaN`
finite-number message. Add one `DefaultContext` mutation characterization that verifies the
same ordinary, subnormal, underflow, and nonfinite outcomes. The `DefaultContext` test is
immediate GREEN structural coverage of explicit Context construction, not a fabricated RED.

- [ ] **Step 2: Run the rejection test and verify the expected RED**

Run:

```powershell
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache pytest packages/sycasphere-core/tests/test_observations.py::test_uncertainty_factory_rejects_unrepresentable_derived_variance -q
```

Expected: both parameter cases are RED against the required boundary contract. The `1e-200`
case reports that no exception was raised; the `1e200` case is rejected later by covariance
validation (existing broad safety), rather than at the `StandardDeviations` boundary with the
approved unified representability message.

- [ ] **Step 3: Implement the minimum representability guard**

Update the production header to `最后修改  : 2026-08-01`, version `v1.3.0`, add an accurate feature bullet for rejecting unrepresentable derived variances, and add:

```text
v1.3.0 (2026-08-01): 拒绝无法表示为有限浮点数的标准差派生方差。
```

Replace the current standard-deviation helper block with:

```python
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException


_UNREPRESENTABLE_VARIANCE_MESSAGE = (
    "standard-deviation variance must be representable as a finite float"
)


def _square_standard_deviation(value: float) -> float:
    """Square one normalized decimal float and require faithful float representation."""
    try:
        operation_context = Context(
            prec=40,
            rounding=ROUND_HALF_EVEN,
            Emin=-999_999,
            Emax=999_999,
            capitals=1,
            clamp=0,
            flags=[],
            traps=[],
        )
        decimal_value = Decimal(str(value))
        variance = float(operation_context.multiply(decimal_value, decimal_value))
    except (DecimalException, OverflowError, ValueError):
        raise ValueError(_UNREPRESENTABLE_VARIANCE_MESSAGE) from None
    if not math.isfinite(variance) or (value != 0.0 and variance == 0.0):
        raise ValueError(_UNREPRESENTABLE_VARIANCE_MESSAGE)
    return variance


def _require_standard_deviation_sequence(value: Any) -> Any:
    """Require nonnegative finite floats whose derived variances are representable."""
    values = require_builtin_float_sequence(value, "standard_deviations")
    if any(component < 0.0 for component in values):
        raise ValueError("standard_deviations must be nonnegative")
    for component in values:
        if math.isfinite(component):
            _square_standard_deviation(component)
    return values
```

Keep `StandardDeviations` and `from_standard_deviations()` signatures unchanged. The
finite-only guard intentionally leaves positive infinity and `NaN` for `StrictFiniteFloat` to
reject with its established message. Precision 40 is sufficient because a finite built-in-float
decimal string has at most 17 significant digits, so its exact square has at most 34 product
digits. The factory may call `_square_standard_deviation()` again while building its diagonal
tuple; duplicating this tiny deterministic calculation is preferable to changing the validated
public input type.

- [ ] **Step 4: Run focused Core tests and verify GREEN**

Run serially:

```powershell
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache pytest packages/sycasphere-core/tests/test_observations.py::test_uncertainty_factory_rejects_unrepresentable_derived_variance packages/sycasphere-core/tests/test_observations.py::test_uncertainty_factory_isolates_decimal_precision_from_caller_context packages/sycasphere-core/tests/test_observations.py::test_uncertainty_factory_isolates_decimal_exponents_from_caller_context packages/sycasphere-core/tests/test_observations.py::test_uncertainty_factory_preserves_finite_number_error_for_nonfinite_deviation packages/sycasphere-core/tests/test_observations.py::test_uncertainty_factory_is_independent_of_mutated_default_decimal_context packages/sycasphere-core/tests/test_observations.py::test_uncertainty_factory_accepts_representable_subnormal_derived_variance packages/sycasphere-core/tests/test_observations.py::test_uncertainty_factory_accepts_zero_standard_deviation packages/sycasphere-core/tests/test_observations.py::test_uncertainty_accepts_subnormal_psd_with_strict_numpy_errstate -q
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache pytest packages/sycasphere-core/tests/test_observations.py -q
```

Expected: all selected cases pass, including the four behavioral regressions (underflow,
overflow, hostile active context, and nonfinite-message preservation) and the immediate-GREEN
`DefaultContext` structural characterization; then the complete observation test module passes
with no warnings.

- [ ] **Step 5: Format, lint, type-check, and commit Task 1**

Run serially:

```powershell
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache ruff format packages/sycasphere-core/src/sycasphere/core/observations.py packages/sycasphere-core/tests/test_observations.py
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache ruff check packages/sycasphere-core/src/sycasphere/core/observations.py packages/sycasphere-core/tests/test_observations.py
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache mypy
```

Expected: Ruff reports no errors and mypy reports no issues.

Commit only the two Task 1 files:

```powershell
git add packages/sycasphere-core/src/sycasphere/core/observations.py packages/sycasphere-core/tests/test_observations.py
git commit -m "fix(core): reject unrepresentable derived variances"
```

---

### Task 2: Lock Stable Sink Error Details

**Files:**
- Modify: `packages/sycasphere-engine/tests/test_sinks.py:6-32`
- Modify: `packages/sycasphere-engine/tests/test_sinks.py:185-365`

**Interfaces:**
- Consumes: existing `SimulationExecutionError.detail`, `_LifecycleOutputSink`, `_validate_batch()`, and `InMemoryOutputSink` behavior.
- Produces: test-only protection for the existing stable category/code/context contract; no Engine source change.

- [ ] **Step 1: Update the test header for stable error-detail coverage**

Set `最后修改  : 2026-08-01`, version `v1.1.0`, add a feature bullet for stable Sink error details, and add:

```text
v1.1.0 (2026-08-01): 锁定 Sink 验证与容量错误的稳定详情。
```

- [ ] **Step 2: Lock invalid-state details in the existing lifecycle test**

Replace the first uncaptured `write_truth_states` assertion in `test_sink_lifecycle_rejects_calls_outside_writing()` with:

```python
    with pytest.raises(SimulationExecutionError) as caught:
        sink.write_truth_states((truth_state,))
    assert caught.value.detail.category is ErrorCategory.VALIDATION_ERROR
    assert caught.value.detail.code == "engine.sink.invalid_state"
    assert caught.value.detail.context == {
        "operation": "write_truth_states",
        "status": "NEW",
    }
```

Leave the remaining lifecycle assertions intact so all existing transition coverage remains.

- [ ] **Step 3: Lock invalid-batch details for every channel**

Inside `test_writes_require_nonempty_exact_tuples()`, derive exact expected values before the invalid-batch loop and add assertions inside it:

Parameterize the factory as `NullOutputSink`, `lambda: InMemoryOutputSink(max_records=10)`,
and `lambda: CompositeOutputSink(())`; annotate it as
`Callable[[], NullOutputSink | InMemoryOutputSink | CompositeOutputSink]`. This locks every
invalid-batch category/code/context combination for all three public Sink implementations and
all three channels.

```python
    expected_channel = method_name.removeprefix("write_")
    expected_type = type(valid_item).__name__

    for invalid_batch in ([], (), (object(),)):
        with pytest.raises(SimulationExecutionError) as caught:
            write(invalid_batch)
        assert caught.value.detail.category is ErrorCategory.VALIDATION_ERROR
        assert caught.value.detail.code == "engine.sink.invalid_batch"
        assert caught.value.detail.context == {
            "channel": expected_channel,
            "expected_type": expected_type,
        }
        assert sink.status is SinkStatus.WRITING
```

- [ ] **Step 4: Lock bounded-memory exhaustion details**

Add these assertions to `test_in_memory_limit_aborts_and_clears()` immediately after the existing category assertion:

```python
    assert caught.value.detail.code == "engine.sink.memory_limit_exceeded"
    assert caught.value.detail.context == {
        "max_records": 1,
        "retained_count": 0,
        "batch_count": 2,
    }
```

- [ ] **Step 5: Run the focused test-only contract gate**

Run:

```powershell
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache pytest packages/sycasphere-engine/tests/test_sinks.py -k "lifecycle_rejects_calls_outside_writing or writes_require_nonempty_exact_tuples or in_memory_limit_aborts_and_clears" -q
```

Expected: 13 selected parameter cases pass. These tests are expected to be GREEN immediately because they lock already-implemented behavior; do not modify Engine production code to manufacture a RED phase.

- [ ] **Step 6: Format, lint, and commit Task 2**

Run:

```powershell
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache ruff format packages/sycasphere-engine/tests/test_sinks.py
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache ruff check packages/sycasphere-engine/tests/test_sinks.py
```

Expected: both commands pass with no errors.

Commit only the Sink test file:

```powershell
git add packages/sycasphere-engine/tests/test_sinks.py
git commit -m "test(engine): lock sink error details"
```

---

### Task 3: Lock Composite Begin-Rollback State

**Files:**
- Modify: `packages/sycasphere-engine/tests/test_sinks.py:6-32`
- Modify: `packages/sycasphere-engine/tests/test_sinks.py:452-475`

**Interfaces:**
- Consumes: existing `CompositeOutputSink.begin()`, `RecordingSink.status`, and first-cause cleanup behavior.
- Produces: test-only state-matrix protection after a begin failure plus a rollback failure; no cleanup retry API and no Engine source change.

- [ ] **Step 1: Extend the rollback-failure fixture and assertions**

Update the test header to version `v1.2.0`, retain date `2026-08-01`, add a feature bullet for failed begin rollback state, and add:

```text
v1.2.0 (2026-08-01): 锁定 Composite begin 回滚失败后的真实状态矩阵。
```

Change `test_composite_begin_failure_preserves_error_when_rollback_also_fails()` so its child tuple includes an untouched third child:

```python
    children = (
        RecordingSink(
            "1",
            events,
            failure_method="abort",
            failure=rollback_failure,
        ),
        RecordingSink("2", events, failure_method="begin", failure=begin_failure),
        RecordingSink("3", events),
    )
```

Keep the existing first-cause and event-order assertions, then add:

```python
    assert children[0].status is SinkStatus.WRITING
    assert children[1].status is SinkStatus.NEW
    assert children[2].status is SinkStatus.NEW
    assert sink.status is SinkStatus.NEW
```

Do not call private Composite helpers and do not add a public retry path.

- [ ] **Step 2: Run the focused rollback test**

Run:

```powershell
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache pytest packages/sycasphere-engine/tests/test_sinks.py::test_composite_begin_failure_preserves_error_when_rollback_also_fails -q
```

Expected: one test passes immediately because the assertions expose and lock existing behavior.

- [ ] **Step 3: Run the complete Sink module and quality checks**

Run serially:

```powershell
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache pytest packages/sycasphere-engine/tests/test_sinks.py -q
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache ruff format packages/sycasphere-engine/tests/test_sinks.py
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache ruff check packages/sycasphere-engine/tests/test_sinks.py
```

Expected: the complete Sink module and both Ruff commands pass.

- [ ] **Step 4: Commit Task 3**

```powershell
git add packages/sycasphere-engine/tests/test_sinks.py
git commit -m "test(engine): lock composite begin rollback state"
```

---

### Task 4: Full Verification and Scope Audit

**Files:**
- Verify only; modify a file only if a failing regression or review finding proves a contradiction with the approved design.

**Interfaces:**
- Consumes: the three independently committed tasks.
- Produces: a clean, review-ready branch with complete verification evidence.

- [ ] **Step 1: Run the mandated quality gate serially**

```powershell
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache ruff format --check .
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache ruff check .
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache mypy
uv run --offline --cache-dir D:/program/github/my_github/SycaSphere/.uv-cache pytest
```

Expected: 71 Python files are formatted, Ruff reports no lint errors, mypy reports no issues in 36 source files, and pytest reports 1068 passed.

- [ ] **Step 2: Audit the complete branch diff**

```powershell
git diff --check a8cb653..HEAD
git diff --stat a8cb653..HEAD
git status -sb
git diff --exit-code a8cb653..HEAD -- packages/sycasphere-engine/src
```

Expected:

- no whitespace errors;
- only the approved design/plan, Core observations source/test, and Engine Sink test are changed;
- the tracked worktree is clean;
- Engine production source has no diff;
- `docs/assets/` is absent from the branch diff.

- [ ] **Step 3: Request independent review**

Review `a8cb653..HEAD` against:

- `docs/superpowers/specs/2026-08-01-numeric-and-sink-contract-hardening-design.md`;
- this implementation plan;
- Core float/Decimal/Pydantic boundaries;
- Sink category/code/context and lifecycle state semantics;
- frame, time, unit, Truth separation, mutability, dependency, and scope invariants from `AGENTS.md`.

The reviewer must classify findings as Critical, Important, or Minor and explicitly state whether the branch is ready to merge. Do not waive a finding without concrete contradictory code evidence. Any accepted behavior fix requires a focused regression test, recorded RED/GREEN, a separate commit, and a repeat of Step 1.

**Accepted final-review follow-up:** Independent review accepted the explicit per-operation
Context, finite-only guard, nonfinite-message preservation, `DefaultContext` characterization,
and complete Sink factory/channel parameterization. This plan records that accepted review
outcome only; it does not assert unrecorded command execution.

---

## Final Acceptance Checklist

1. `1e-200` no longer becomes declared zero covariance.
2. A finite standard deviation whose square is non-finite fails at the same strict validation boundary.
3. `0.0`, ordinary values, representable subnormal derived variance, and direct subnormal covariance remain accepted.
4. No public Schema, API, dependency, `uv.lock`, or Engine source changes occur.
5. Stable Sink categories, codes, and contexts are regression-tested.
6. Composite begin rollback failure preserves first cause and the exact `WRITING/NEW` state matrix.
7. Ruff, mypy, and 1068 pytest cases pass.
8. Independent review has no unresolved findings.
9. `docs/assets/`, Session, Orekit, Observation runtime, Sim, Platform, and frontend remain untouched.
