# AGENTS.md

## Project purpose

SycaSphere is an interactive 3D simulation and validation platform for space situational awareness algorithms. The current development scope is high-fidelity truth generation, ground- and space-based observations, orbit determination, maneuver detection, external algorithm integration, repeatable experiments, and synchronized 3D/analytical visualization for 1 to tens of space objects.

## Authoritative design documents

Read these before making architectural or domain changes:

1. `docs/architecture/core-data-model-v0.2.md`
2. `docs/architecture/algorithm-integration-v0.2.md`
3. `docs/superpowers/specs/2026-07-20-sycasphere-runtime-and-simulation-engine-design.md`

When code and documentation disagree, do not silently preserve the code. Identify the conflict, update the design or implementation intentionally, and add tests for the final decision.

## Current non-goals

Do not implement these unless the task explicitly changes the scope:

- reinforcement-learning environments;
- AI-assisted scenario design;
- large catalogues or GPU-scale propagation;
- Redis, Kafka, Kubernetes, or distributed task infrastructure;
- full multi-user security and authorization;
- a custom 3D rendering engine;
- MATLAB Engine or a stable C ABI plugin layer.

## Technical baseline

- Python 3.12
- JDK 21
- `orekit-jpype==13.1.7.0`
- `uv` for dependency and environment management
- NumPy for numerical arrays
- Pydantic v2 for boundary/domain validation
- pytest for tests
- Ruff for formatting and linting
- mypy for static type checking
- SQLite for metadata
- Parquet/PyArrow for scientific time-series artifacts
- FastAPI for the Python service boundary when the API layer is introduced
- React + TypeScript + CesiumJS + Apache ECharts for the web workspace

Pin resolved dependencies in `uv.lock`. Do not add a production dependency without explaining why the standard library or an existing dependency is insufficient.

## Expected repository layout

```text
packages/
├── sycasphere-core/src/sycasphere/core/         # Pure domain contracts and invariants
├── sycasphere-engine/src/sycasphere/engine/     # Backend-neutral simulation runtime
├── sycasphere-orekit/src/sycasphere/orekit/     # The only package allowed to import Orekit/JPype
├── sycasphere-sim/src/sycasphere/sim/           # Standalone Python API and CLI product
└── sycasphere-platform/src/sycasphere/platform/ # Experiments, algorithms, evaluation, persistence and API
frontend/                                        # React/TypeScript/CesiumJS/ECharts
examples/
tests/
docs/
```

Keep dependency direction inward: Engine depends on Core but not Orekit; Orekit implements Engine/Core ports; Sim and Platform depend on public Engine/Core interfaces. Core must not depend on infrastructure, FastAPI, Cesium, JPype, SQLite, or PyArrow.

## Architecture invariants

- Separate `SimulationDefinition`, `MissionDefinition`, `ExperimentDefinition`, `RunManifest`, and `ResultBundle`.
- Entities describe identity and physical capabilities. Mission roles belong to `MissionDefinition` through `RoleAssignment`; never store fixed task roles on entities.
- Sensors are child components of a spacecraft or ground station. A sensor must not maintain an independent orbit.
- Public inertial-frame name is `J2000`. Only the Orekit adapter may map it to Orekit's internal frame API.
- Supported public frames are `J2000`, `EARTH_FIXED`, `LVLH`, `VVLH`, `BODY`, and `SENSOR`. `WGS84` is a reference ellipsoid, not a frame.
- Do not create heavyweight `Vector3` or `StateVector6` classes. Use validated JSON arrays at serialization boundaries, immutable fixed-length tuples inside frozen boundary models, and `numpy.ndarray` inside numerical code. Use semantic containers such as `CartesianState`.
- Use SI units internally. Put units in field names or explicit measurement metadata.
- Keep Truth, IdealObservation, ReportedObservation, and Estimate strictly separated.
- Ideal and Reported observations from the same event share an event ID.
- Batch and Streaming algorithms use separate protocols and lifecycles.
- Never pass Orekit, JPype, or Java objects across domain or algorithm boundaries.
- Completed run inputs and scientific artifacts are immutable.
- Redis is not part of the current runtime. Use repository/event-bus interfaces so infrastructure can change later.
- The backend performs authoritative `J2000`/`EARTH_FIXED` transformations and WGS84 geodetic conversions. The frontend does not implement scientific frame transformations.

## Python source-file format

New Python files must use this Sycamore header, adapted accurately to the file's actual content:

```python
# -*- coding: utf-8 -*-
# Copyright 2026 Sycamore
# SPDX-License-Identifier: Apache-2.0
# %%
"""
文件名    : <filename.py>
创建者    : Sycamore
创建日期  : YYYY-MM-DD
最后修改  : YYYY-MM-DD
版本号    : v1.0.0

■ 用途说明:
  简要描述程序的主要功能和用途

■ 主要函数功能:
  - 函数1: 描述
  - 函数2: 描述

■ 功能特性:
  ✓ 已完成功能1
  ✓ 已完成功能2
  ⚠ 未完成功能

■ 待办事项:
  - [ ] 待办事项1
  - [ ] 待办事项2

■ 更新日志:
  v1.0.0 (YYYY-MM-DD): 初始版本

"心之所向，素履以往；生如逆旅，一苇以航。"
"""

# =============================👐Seperate👐=============================
# 顶层功能标题
# =============================👐Seperate👐=============================
```

Use this separator between small steps inside a function:

```python
## -------------- step: 准备输入数据 ---------
```

Do not add inaccurate placeholder claims. Keep headers updated when a file's purpose changes materially.

## Coding rules

- Use `from __future__ import annotations` in Python modules unless a concrete incompatibility exists.
- Type all public functions, methods, and models.
- Prefer small pure functions in domain/evaluation code.
- Validate array shapes and finite values at boundaries.
- Use `None` for missing domain data; do not use zero or NaN as a missing-value convention.
- Avoid global mutable state.
- Initialize the JVM in one dedicated runtime component. Do not start or stop the JVM from domain modules or plugin imports.
- Do not import Java/Orekit classes before JVM initialization.
- Use structured exceptions with stable error categories at application boundaries.
- Keep comments focused on intent, assumptions, coordinate conventions, and numerical pitfalls.

## Testing expectations

Every behavior change must add or update tests. At minimum run:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

For Orekit-dependent work, include tests for:

- JVM initialization and single-lifecycle behavior;
- J2000 adapter mapping;
- frame transformations against known reference cases;
- ground- and space-based sensor geometry;
- Ideal/Reported observation pairing;
- deterministic repeatability with a fixed seed.

For frontend work, add unit/component tests and verify the relevant Cesium interaction in a running development build.

## Done criteria

A task is complete only when:

- implementation matches the two architecture specifications;
- tests for new behavior pass;
- lint, formatting, and type checks pass;
- public schemas or interfaces are documented;
- no unrequested scope expansion was introduced;
- the final diff is reviewed for frame, time, unit, truth-access, and mutability errors.
