# SycaSphere

SycaSphere is an interactive 3D simulation and validation platform for space
situational-awareness algorithms. Phase 1 delivers the independently
installable, backend-neutral Core foundation: immutable domain contracts for
time, frames, Cartesian state, schema versions, structured errors, and plugin
manifests.

The distribution is named `sycasphere-core`, while Python code imports it as
`sycasphere.core`. See the [Core package guide](packages/sycasphere-core/README.md)
for installation, a minimal state example, compatibility rules, and the Phase 1
boundary.

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
