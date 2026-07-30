# SycaSphere Engine

`sycasphere-engine` is the backend-neutral synchronous batch runtime for
SycaSphere. It resolves an explicit, immutable plugin registry, prepares a
self-contained Core request into immutable scientific provenance, and runs
Truth simulation through a caller-provided output sink. Its Python import path
is `sycasphere.engine`.

Engine v0.1 provides a synchronous batch API: call `engine.prepare(request)`
first, then call `engine.run(manifest, sink, CancellationToken())`. A prepared
`SimulationExecutionManifest` records resolved scientific inputs and excludes
mutable lifecycle state, wall-clock timing, errors, output paths, artifact
hashes, and retention state. In short: Manifest excludes lifecycle state.
`SimulationExecutionResult` is a lightweight batch execution result, not the
future Platform `RunOutcome`.

## Install

For development from this repository workspace:

```bash
uv sync --locked
uv run python -c "import sycasphere.engine; print(sycasphere.engine.__version__)"
```

To build the independently installable package with the locked local build
backend:

```bash
uv build --offline --no-build-isolation --package sycasphere-engine --out-dir .build/engine
```

The Engine wheel depends on `sycasphere-core` and NumPy. It does not install or
initialize Orekit, JPype, Java, a JDK, a database, or a web service.

## Executable bounded FakeBackend example

The example below is copied exactly from
`tests/fixtures/readme_fake_run.py`, which is executed by the package tests and
isolated-wheel verification. It uses a finite ten-second time range and
`InMemoryOutputSink(max_records=32)`; do not use an unbounded in-memory
collector for long or high-rate simulations.

<!-- README_EXAMPLE_START -->
```python
from sycasphere.core import (
    CartesianState,
    CentralBody,
    EnvironmentDefinition,
    Epoch,
    FrameKind,
    FrameRef,
    ImpulsiveManeuverSpec,
    ManeuverCapability,
    ManeuverCommand,
    ManeuverType,
    ModelRef,
    OutputProduct,
    OutputRequirement,
    OutputSampling,
    PluginRef,
    SamplingRule,
    SchemaVersion,
    ScienceBackendBinding,
    SimulationDefinition,
    SimulationRunRequest,
    SimulationTimeRange,
    SpacecraftDefinition,
    SpaceObjectPhysicalProperties,
    TimeScale,
)
from sycasphere.engine import (
    CancellationToken,
    InMemoryOutputSink,
    PluginRegistry,
    SimulationEngine,
)
from sycasphere.engine.testing import fake_backend_registration


def main() -> None:
    """Run one bounded deterministic compatibility simulation."""
    version = SchemaVersion(major=1, minor=0)
    start = Epoch(value="2026-07-30T00:00:00Z", time_scale=TimeScale.UTC)

    def fake_model(model_id: str) -> ModelRef:
        return ModelRef(
            model_id=model_id,
            interface_version=version,
            configuration={},
        )

    spacecraft = SpacecraftDefinition(
        id="spacecraft-1",
        name="Fake spacecraft",
        revision=1,
        schema_version=version,
        initial_state=CartesianState(
            epoch=start,
            frame=FrameRef(kind=FrameKind.J2000),
            position_m=(7_000_000.0, 0.0, 0.0),
            velocity_mps=(0.0, 7_500.0, 0.0),
        ),
        physical_properties=SpaceObjectPhysicalProperties(
            mass_kg=500.0,
            cross_section_area_m2=10.0,
        ),
        dynamics_model=fake_model("sycasphere.testing.constant-velocity"),
        attitude_model=fake_model("sycasphere.testing.identity-attitude"),
        maneuver_capability=ManeuverCapability(
            supported_types=frozenset({ManeuverType.IMPULSIVE}),
            propulsion_model=fake_model("sycasphere.testing.impulsive-propulsion"),
        ),
    )
    request = SimulationRunRequest(
        schema_version=version,
        simulation_definition=SimulationDefinition(
            id="readme-fake-run",
            name="README FakeBackend run",
            revision=1,
            schema_version=version,
            synchronization_epoch=start,
            environment=EnvironmentDefinition(
                id="fake-earth",
                name="Fake Earth",
                revision=1,
                schema_version=version,
                central_body=CentralBody.EARTH,
            ),
            entities=(spacecraft,),
        ),
        time_range=SimulationTimeRange(
            start=start,
            end=Epoch(value="2026-07-30T00:00:10Z", time_scale=TimeScale.UTC),
        ),
        output_sampling=OutputSampling(
            rules=(
                SamplingRule(product=OutputProduct.TRUTH_STATE, interval_s=5.0),
                SamplingRule(product=OutputProduct.ATTITUDE_STATE, interval_s=5.0),
            )
        ),
        command_timeline=(
            ManeuverCommand(
                command_id="readme-impulse",
                spacecraft_id="spacecraft-1",
                epoch=Epoch(value="2026-07-30T00:00:05Z", time_scale=TimeScale.UTC),
                maneuver=ImpulsiveManeuverSpec(
                    delta_v_mps=(1.0, 0.0, 0.0),
                    frame=FrameRef(kind=FrameKind.J2000),
                ),
            ),
        ),
        backend=ScienceBackendBinding(
            ref=PluginRef(
                plugin_id="sycasphere.testing.fake",
                implementation_version="0.1.0",
                interface_version=version,
            ),
            configuration={},
        ),
        random_seed=20260730,
        output_requirements=frozenset(
            {
                OutputRequirement.TRUTH,
                OutputRequirement.ATTITUDE,
            }
        ),
    )

    registry = PluginRegistry((fake_backend_registration(),))
    engine = SimulationEngine(registry)
    manifest = engine.prepare(request)
    sink = InMemoryOutputSink(max_records=32)
    result = engine.run(manifest, sink, CancellationToken())

    print(f"Truth states: {result.output_summary.truth_state_count}")
    print(f"Attitude states: {result.output_summary.attitude_state_count}")
    print(f"Truth maneuvers: {result.output_summary.truth_maneuver_count}")


if __name__ == "__main__":
    main()
```
<!-- README_EXAMPLE_END -->

`FakeBackend` is a deterministic non-scientific compatibility backend for
tests, examples, and third-party backend development. It is not an orbit
propagator and makes no accuracy claim. Its v0.1 scientific limitations are
J2000 only, one same time scale without UTC leap-second input, constant-velocity
translation, identity attitude, and impulsive maneuvers only. Current impulse
input has no consumption quantity, so FakeBackend keeps mass constant rather
than inventing fuel use.

## Current boundary

Implemented in Engine v0.1:

- synchronous `prepare()` and blocking `run()`;
- explicit `PluginRegistry` and backend factory/runtime ports;
- lazy Truth/attitude sampling and pre-run J2000 impulse scheduling;
- cooperative cancellation and structured preparation/execution errors;
- `NullOutputSink`, bounded `InMemoryOutputSink`, and `CompositeOutputSink`;
- deterministic `FakeBackend` under `sycasphere.engine.testing`.

Observation remains planned, including measurement, error, link, delivery, and
algorithm-input pipelines. interactive Session remains planned, including
pause, step, checkpoint, restore, and runtime command injection. Orekit remains planned
as a separate adapter package. Sim retention and persistence, Platform run
lifecycle and algorithms, and the frontend also remain planned.
