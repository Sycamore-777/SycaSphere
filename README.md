# SycaSphere

SycaSphere is an interactive 3D simulation and validation platform for space
situational-awareness algorithms. The independently installable,
backend-neutral Core package currently implements immutable contracts for time,
frames, Cartesian state, entities, sensors, reusable `SimulationDefinition`
objects, `ManeuverCommand` inputs, `PeriodicObservationSchedule` and
`ExplicitObservationSchedule` plans, self-contained `SimulationRunRequest`
objects, and `SimulationExecutionManifest` provenance.

The distribution is named `sycasphere-core`, while Python code imports it as
`sycasphere.core`. See the [Core package guide](packages/sycasphere-core/README.md)
for installation, a minimal executable run-request example, compatibility
rules, and the current implementation boundary.

Core validates and freezes these contracts but does not propagate. A planned
Engine `prepare()` operation will resolve plugins and external scientific data
and create a `SimulationExecutionManifest`. That Manifest is immutable input
provenance, not run status; mutable state belongs to future `RunRecord` and
`RunAttempt` contracts, while terminal data belongs to a future `RunOutcome`.
Engine sessions, observation and result generation, retention, persistence,
and Orekit execution remain separate planned packages or implementation
batches.

Core deliberately has no Orekit, JPype, or JDK dependency. `Epoch` exposes the
single public field `time_scale`; later adapters implement time-scale
conversion, frame transformations, propagation, and backend integration.
Structured errors carry optional run, attempt, and diagnostic-artifact
references while keeping their context finite, deeply immutable, and free of
exception or traceback payloads.

Development and release builds use the locked root environment:

```bash
uv sync --locked
uv build --offline --no-build-isolation --package sycasphere-core --out-dir .build/core
```

This uses the tracked Hatchling version without fetching an isolated backend.
