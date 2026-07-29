# SycaSphere

SycaSphere is an interactive 3D simulation and validation platform for space
situational-awareness algorithms. The independently installable,
backend-neutral Core package currently implements immutable contracts for time,
frames, Cartesian state, entities, sensors, reusable `SimulationDefinition`
objects, `ManeuverCommand` inputs, `PeriodicObservationSchedule` and
`ExplicitObservationSchedule` plans, self-contained `SimulationRunRequest`
objects, `SimulationExecutionManifest` provenance, `TruthState` and
`TruthManeuver` results, separated `IdealObservation` and
`ReportedObservation` payloads, per-event `ObservationDeliveryRecord` facts,
and aggregate `DeliverySummary` results.

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

## Truth, observation, and delivery contracts

Core keeps Truth, Ideal, and Reported data separate. Truth models describe
authoritative physical results. `IdealObservation` contains the error-free
algorithm-visible measurement, while `ReportedObservation` contains the
post-error-model measurement. Both observation channels use an algorithm-safe
`ObservationSubjectRef`: it can expose an authorized known-object identity, a
tracklet identity, or an unassociated detection, but never an internal Truth
target identity.

`MeasurementUncertainty` declares the effective covariance of the remaining
reported-minus-ideal error after deterministic corrections. It may represent
combined stochastic error and incompletely determined systematic error, but it
does not reveal a realized noise sample or true bias. `None` means covariance
is unavailable; an explicit all-zero covariance means the residual is declared
exactly zero.

One finalized `ObservationEvent` corresponds to each observation-schedule
occurrence, not each numerical integration step, Truth sampling instant, or
render frame. Every Event has exactly one terminal
`ObservationDeliveryRecord`. The initial delivery contract models delay and
drop only; it has no reordering, duplication, retransmission, or retry
semantics.

Request `DELIVERY_SUMMARY` for aggregate terminal counts. Request
`DELIVERY_RECORDS` when the per-Event records must also be persisted; omitting
that artifact does not authorize an execution layer to skip the selected Ideal
or Reported scientific pipeline.

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
