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

Core deliberately has no Orekit, JPype, or JDK dependency. It declares public
scientific semantics only; later adapters implement time-scale conversion,
frame transformations, propagation, and backend integration.
