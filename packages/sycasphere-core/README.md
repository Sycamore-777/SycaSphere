# SycaSphere Core

`sycasphere-core` is the Phase 1 pure-domain foundation for SycaSphere. Its
Python import path is `sycasphere.core`:

```python
from sycasphere.core import CartesianState, Epoch, FrameKind, FrameRef, TimeScale
```

## Install

For development from this repository workspace, synchronize the root project
and run through `uv`:

```bash
uv sync --locked
uv run python -c "import sycasphere.core; print(sycasphere.core.__version__)"
```

To install the package itself from the checkout into the active environment,
use an editable install:

```bash
uv pip install -e packages/sycasphere-core
```

To build and install the published artifact, run the build from the workspace
root and install the generated wheel:

```bash
uv build --offline --no-build-isolation --package sycasphere-core --out-dir .build/core
uv pip install .build/core/sycasphere_core-0.1.0-py3-none-any.whl
```

The `.build/` directory is generated output and is intentionally ignored.

## Minimal state

All serialized physical state fields use SI units. `position_m` is metres and
`velocity_mps` is metres per second. An `Epoch` always declares its time scale,
and a `FrameRef` always identifies the state frame.

```python
from sycasphere.core import CartesianState, Epoch, FrameKind, FrameRef, TimeScale

state = CartesianState(
    epoch=Epoch(value="2026-07-20T00:00:00Z", time_scale=TimeScale.UTC),
    frame=FrameRef(kind=FrameKind.J2000),
    position_m=(7_000_000.0, 0.0, 0.0),
    velocity_mps=(0.0, 7_500.0, 0.0),
)

position_for_numerics = state.position_array()
```

The models are frozen and reject extra fields. Cartesian vectors must contain
exactly three finite floating-point values. `J2000` is the stable public
inertial-frame semantic; `WGS84` is a reference ellipsoid, not a frame.

## Minimal simulation run request

The following example is executable with `sycasphere-core` alone. It creates a
complete `SimulationDefinition` whose space-object state is synchronized,
selects the closed time range `[start, end]`, samples `TRUTH_STATE`, binds one
exact backend implementation, and creates a self-contained
`SimulationRunRequest`.

```python
from sycasphere.core import (
    CartesianState,
    CentralBody,
    EnvironmentDefinition,
    Epoch,
    FrameKind,
    FrameRef,
    ModelRef,
    OtherSpaceObjectDefinition,
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
    SpaceObjectPhysicalProperties,
    TimeScale,
)

version = SchemaVersion(major=1, minor=0)
synchronization_epoch = Epoch(
    value="2026-07-26T00:00:00Z",
    time_scale=TimeScale.UTC,
)


def model(model_id: str) -> ModelRef:
    return ModelRef(model_id=model_id, interface_version=version)


space_object = OtherSpaceObjectDefinition(
    id="target-1",
    name="Target",
    revision=1,
    schema_version=version,
    initial_state=CartesianState(
        epoch=synchronization_epoch,
        frame=FrameRef(kind=FrameKind.J2000),
        position_m=(7_000_000.0, 0.0, 0.0),
        velocity_mps=(0.0, 7_500.0, 0.0),
    ),
    physical_properties=SpaceObjectPhysicalProperties(
        mass_kg=500.0,
        cross_section_area_m2=8.0,
    ),
    dynamics_model=model("example.dynamics"),
    attitude_model=model("example.attitude"),
)

simulation = SimulationDefinition(
    id="minimal-simulation",
    name="Minimal synchronized world",
    revision=1,
    schema_version=version,
    synchronization_epoch=synchronization_epoch,
    environment=EnvironmentDefinition(
        id="earth-environment",
        name="Earth",
        revision=1,
        schema_version=version,
        central_body=CentralBody.EARTH,
    ),
    entities=(space_object,),
)

request = SimulationRunRequest(
    schema_version=version,
    simulation_definition=simulation,
    time_range=SimulationTimeRange(
        start=synchronization_epoch,
        end=Epoch(
            value="2026-07-26T00:10:00Z",
            time_scale=TimeScale.UTC,
        ),
    ),
    output_sampling=OutputSampling(
        rules=(
            SamplingRule(
                product=OutputProduct.TRUTH_STATE,
                interval_s=30.0,
            ),
        ),
    ),
    backend=ScienceBackendBinding(
        ref=PluginRef(
            plugin_id="example.science-backend",
            implementation_version="1.0.0",
            interface_version=version,
        ),
    ),
    random_seed=42,
    output_requirements=(OutputRequirement.TRUTH,),
)
```

`ManeuverCommand` is the only v1 command-timeline entry type. Observation
attempts use either `PeriodicObservationSchedule` or
`ExplicitObservationSchedule`; measurement and error models are selected from
the scheduled sensor, while data-link models remain run-level inputs.

## Truth, observation, and delivery result contracts

Core publishes immutable result shapes without executing them:

- `TruthState` and `TruthManeuver` describe authoritative physical truth.
- `IdealObservation` contains an error-free, algorithm-visible measurement.
- `ReportedObservation` contains the post-error-model measurement supplied to
  algorithms.
- `ObservationDeliveryRecord` captures one terminal delivery outcome for one
  observation Event.
- `DeliverySummary` conserves the aggregate counts of all terminal outcomes.

Truth, Ideal, and Reported remain strictly separate. The algorithm-visible
observation models carry an `ObservationSubjectRef`, which discriminates an
authorized known-object identity, a tracklet identity, or an unassociated
detection. The internal Truth target identity used to form an
`ObservationEvent` is not copied into either observation payload.

`MeasurementUncertainty` is the effective covariance of the remaining
reported-minus-ideal error after deterministic corrections. It can combine
stochastic error with incompletely determined systematic error, but it never
contains a realized noise sample or true bias. A missing uncertainty (`None`)
means covariance is unavailable; an explicit zero covariance declares a
known-zero residual covariance.

An `ObservationEvent` is finalized once for each observation-schedule
occurrence. Numerical integration steps, Truth output samples, and frontend
render frames do not create extra Events. Each Event produces exactly one
terminal `ObservationDeliveryRecord`, whether it is geometry-rejected, missed,
quality-rejected, link-dropped, or delivered. The first delivery contract
models delay and drop only; reordering, duplication, retransmission, and
multiple retry attempts are outside its scope.

`OutputRequirement.DELIVERY_SUMMARY` requests aggregate terminal counts.
`OutputRequirement.DELIVERY_RECORDS` additionally requests persistent
per-Event records and may require streamed artifact writing rather than
retaining every record in memory. Output requirements control artifact
persistence only: a future Engine must still run the selected Ideal or Reported
scientific pipeline.

## Entity and sensor definitions

The following examples validate definitions only; they do not propagate an
orbit or generate observations.

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

## Time and backend boundary

Core validates and canonicalizes representations but performs no UTC/TAI/TT
scale conversion. UTC values are normalized to a `Z` suffix; TAI and TT
calendar values must not carry a zone or offset. Core has no Orekit, JPype, or
JDK dependency and never initializes a JVM. A future Orekit adapter owns those
runtime concerns and maps public frame semantics to its implementation.

## Structured errors and immutable JSON

`ErrorDetail` uses stable machine identifiers for `code` and `component_ref`.
Its `run_id`, `attempt_id`, and `diagnostic_artifact_ref` fields are optional
because validation can fail before those resources exist. Diagnostic context
and plugin configuration schemas are copied and deeply frozen, reject
non-finite numbers and exception/traceback payloads, and serialize back to
ordinary JSON objects and arrays. Plugin capabilities serialize as a sorted
array so equivalent manifests have stable JSON output.

## Compatibility and plugin selection

`SchemaVersion.satisfies(required)` is compatible only when the major versions
match and the provided minor version is at least the required minor version.

Plugin manifests are immutable, data-only declarations. Select a plugin only
when its declared capability is supported and its interface version satisfies
the caller's required schema version. Inspect `resources` separately to decide
whether an environment can satisfy declared requirements such as a JDK or
network access. Reading a manifest does not import, load, or initialize a
plugin implementation.

## Current implementation boundary

Core currently implements the immutable input and result contracts shown
above. It validates and freezes definitions, schedules, commands, run
requests, execution-manifest data, Truth results, observation payloads, and
delivery facts, but it does not generate or execute them, propagate an orbit,
or resolve a scientific backend.

A planned Engine `prepare()` operation will resolve plugins and external data
and create a `SimulationExecutionManifest`. The Manifest is immutable input
provenance, not run status. Mutable execution state belongs to future
`RunRecord` and `RunAttempt` contracts, while terminal status, errors, and
output hashes belong to a future `RunOutcome`. Engine sessions, observation
and result generation, retention, persistence, and Orekit execution remain
separate planned packages or implementation batches.
