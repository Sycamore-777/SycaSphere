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
uv sync
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
uv build --package sycasphere-core --out-dir .build/core
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
    epoch=Epoch(value="2026-07-20T00:00:00Z", scale=TimeScale.UTC),
    frame=FrameRef(kind=FrameKind.J2000),
    position_m=(7_000_000.0, 0.0, 0.0),
    velocity_mps=(0.0, 7_500.0, 0.0),
)

position_for_numerics = state.position_array()
```

The models are frozen and reject extra fields. Cartesian vectors must contain
exactly three finite floating-point values. `J2000` is the stable public
inertial-frame semantic; `WGS84` is a reference ellipsoid, not a frame.

## Time and backend boundary

Core validates and canonicalizes representations but performs no UTC/TAI/TT
scale conversion. UTC values are normalized to a `Z` suffix; TAI and TT
calendar values must not carry a zone or offset. Core has no Orekit, JPype, or
JDK dependency and never initializes a JVM. A future Orekit adapter owns those
runtime concerns and maps public frame semantics to its implementation.

## Compatibility and plugin selection

`SchemaVersion.satisfies(required)` is compatible only when the major versions
match and the provided minor version is at least the required minor version.

Plugin manifests are immutable, data-only declarations. Select a plugin only
when its declared capability is supported and its interface version satisfies
the caller's required schema version. Inspect `resources` separately to decide
whether an environment can satisfy declared requirements such as a JDK or
network access. Reading a manifest does not import, load, or initialize a
plugin implementation.

## Phase 1 exclusions

Core Phase 1 does not include observations, run requests, engine sessions,
propagation, persistence, an API, or a UI. Truth generation, observation
delivery, estimation, maneuver execution, scientific backend adapters, and
application orchestration belong to later phases.
