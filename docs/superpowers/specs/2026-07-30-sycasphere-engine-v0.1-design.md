# SycaSphere Engine v0.1 设计

日期：2026-07-30
状态：已确认

## 1. 目的

本阶段实现 `sycasphere-engine` 的首个可运行版本。它负责把 Core 已定义的
`SimulationRunRequest` 准备为不可变 `SimulationExecutionManifest`，再通过可插拔科学
后端执行可重复的批量 Truth 仿真。

v0.1 的重点不是提供真实轨道动力学，而是建立稳定的引擎边界并用确定性的
`FakeBackend` 验证：

- 插件解析和能力检查；
- `prepare()` 与 `run()` 的生命周期分离；
- 惰性时间调度；
- 预设机动和运行前命令；
- Truth、姿态和机动的流式输出；
- 取消、资源清理和结构化错误；
- Engine 在没有 JDK、JPype 和 Orekit 时可独立安装和运行。

真实轨道传播将在后续 `sycasphere-orekit` 包中实现，但必须复用本设计的公共 Engine
接口，不得把 Orekit 对象或 JVM 生命周期泄漏到 Engine/Core 边界。

## 2. 已选总体方案

采用“Engine 编排、科学后端负责物理计算”的架构。

Engine 统一负责请求准备、时间线、事件顺序、输出采样、取消、sink 生命周期和错误
转换。科学后端只负责初始化科学状态、传播到指定时刻、读取 Truth、执行机动以及释放
本次运行资源。

不采用以下方案：

- 后端整体接管整场运行：会导致每个后端重复实现调度、输出和错误语义；
- 通用事件总线微内核：v0.1 抽象过重，且会弱化科学事件的类型约束。

## 3. 范围

### 3.1 v0.1 包含

- 显式、构造后不可修改的 `PluginRegistry`；
- `SimulationEngine.prepare(request)`；
- 同步阻塞的 `SimulationEngine.run(manifest, sink, cancellation)`；
- 科学后端 factory/runtime Protocol；
- 准备期时间适配器 Protocol；
- 惰性采样和事件时间线；
- `SimulationDefinition.planned_maneuvers`；
- 运行开始前已经存在的 `SimulationRunRequest.command_timeline`；
- J2000 脉冲机动；
- Truth、姿态和 `TruthManeuver` 流式输出；
- `NullOutputSink`、有界 `InMemoryOutputSink` 和 `CompositeOutputSink`；
- 协作取消令牌；
- 轻量 `SimulationExecutionResult` 和结构化公共异常；
- 确定性的非科学 `FakeBackend`；
- Engine 包构建、隔离安装和公共导入验证。

### 3.2 v0.1 明确不包含

- Orekit、JPype 或 JVM 初始化；
- 真实轨道动力学、摄动力或坐标变换；
- 观测、误差、链路、交付和算法输入流水线；
- Derived Geometry；
- 有限推力机动；
- 运行中追加或取消命令；
- `SimulationSession`、暂停、步进、checkpoint 或恢复；
- 异步 `run()`；
- Parquet、SQLite、ArtifactStore、RunStore 或磁盘保留策略；
- Platform 的 `RunRecord`、`RunAttempt`、`RunOutcome` 和 `ResultBundle`；
- Python entry point 自动扫描；
- Redis、Kafka 或分布式任务基础设施。

## 4. 依赖方向与包结构

`sycasphere-engine` 只依赖 `sycasphere-core` 和仓库已批准的基础数值依赖。它不得导入
Orekit、JPype、FastAPI、SQLite、PyArrow 或 Platform。

建议结构：

```text
packages/sycasphere-engine/
├── pyproject.toml
├── README.md
├── src/sycasphere/engine/
│   ├── __init__.py
│   ├── api.py
│   ├── backend.py
│   ├── cancellation.py
│   ├── errors.py
│   ├── execution.py
│   ├── preparation.py
│   ├── registry.py
│   ├── scheduling.py
│   ├── sinks.py
│   └── testing/
│       ├── __init__.py
│       └── fake_backend.py
└── tests/
```

可序列化、跨 Engine/Sim/Platform 共享的稳定数据契约放入 Core。包含行为的方法、
Protocol、factory、运行器和 sink 实现放入 Engine。

## 5. 公共 API

首版公共调用方式为：

```python
engine = SimulationEngine(plugin_registry)

manifest = engine.prepare(request)
result = engine.run(manifest, sink, cancellation)
```

`prepare()` 和 `run()` 都是同步接口。CLI、FastAPI 或 Platform 若需要并发，应在上层
使用工作线程或独立进程；把接口声明为 `async` 不能使 CPU 密集传播自动变为非阻塞。

`SimulationEngine` 在构造后不修改注册表。一次 Engine 实例可以顺序执行多个 Manifest，
但每次 `run()` 必须创建独立 backend runtime，不能复用上一次运行的可变科学状态。

## 6. 插件注册与解析

### 6.1 显式注册表

`PluginRegistry` 由调用者显式注入，构造后不可修改。v0.1 的科学后端注册项包含：

- 数据化 `PluginManifest`；
- 纯配置校验器；
- 轻量准备期时间适配器；
- `ScienceBackendFactory`。

注册表按完整 `PluginRef` 精确解析，即插件 ID、实现版本和接口版本都必须匹配
`ScienceBackendBinding.ref`。缺失项产生 `PLUGIN_MISSING`；接口或能力不兼容产生
`PLUGIN_INCOMPATIBLE`。

读取 manifest、构造注册表、配置校验和时间适配不得启动 JVM，也不得创建传播器。
factory 只能在 `run()` 中创建 runtime。

Python entry point 发现不属于 v0.1。后续可增加一个独立装载器，把已安装 entry point
转换成同一种显式 `PluginRegistry`；`prepare()` 本身不得隐式扫描 Python 环境。

### 6.2 能力校验

Engine 从请求推导所需能力并与 `PluginManifest.capabilities` 比较，包括：

- 公共坐标系；
- 时间尺度组合；
- 动力学和姿态模型 ID；
- 输出产品；
- 脉冲或有限推力机动；
- 后端确定性声明。

配置校验器负责检查后端配置和该后端拥有的子模型配置，但不得初始化 runtime。
所有不支持的能力必须在 `prepare()` 失败，不能运行时静默忽略。

v0.1 进一步要求：

- `observation_schedules` 和 `link_models` 为空；
- `output_requirements` 必须包含 `TRUTH`，并且只能额外包含 `ATTITUDE`；
- `output_sampling` 必须包含 `TRUTH_STATE`；
- `ATTITUDE` 与 `ATTITUDE_STATE` 必须同时存在或同时不存在；
- `GEOMETRY`、观测、交付、命令 trace 和 diagnostics 输出均被拒绝；
- 所有相关 Epoch 使用同一 `TimeScale` 且不采用 UTC `:60`；
- 所有空间物体初始状态和脉冲机动都使用 J2000。

## 7. `prepare()` 生命周期

`prepare(request)` 按以下顺序执行：

1. 对 `SimulationRunRequest` 及所有嵌套模型重新验证和快照；
2. 精确解析科学后端注册项；
3. 校验配置、能力、坐标系、时间、模型、输出和机动类型；
4. 校验所有事件时刻并完成跨记录排序；
5. 合并 `planned_maneuvers` 和 `command_timeline`；
6. 生成稳定 `order_index` 和事件 ID；
7. 锁定外部数据引用；
8. 派生需要的随机流；
9. 创建并重新校验 `SimulationExecutionManifest`。

v0.1 的 FakeBackend 不需要随机流；`derived_random_streams` 因此为空。请求根随机种子仍
保存在 Manifest 中。对第三方 v0.1 后端，环境已经携带精确版本和 SHA-256 的
`ExternalDataRef` 可原样锁定到 `resolved_external_data`；本阶段不检查 artifact 文件
是否存在，因为 ArtifactStore 尚未进入范围。FakeBackend 要求环境模型和外部数据引用
均为空。

`prepare()` 不创建 runtime，不初始化传播器，不启动 JVM，也不在 Manifest 中保存
Python、Java 或进程内对象。成功生成的 Manifest 只包含不可变科学输入和解析后的
provenance，运行状态及最终输出永远不写回 Manifest。

## 8. 后端端口

### 8.1 准备期时间适配器

准备期时间适配器提供后端支持范围内的操作：

- 比较两个 `Epoch` 的绝对先后；
- 计算两个 `Epoch` 之间的 SI 秒差；
- 从一个 `Epoch` 增加严格有限的 SI 秒；
- 判断时刻是否表示同一个绝对瞬间。

该适配器必须是轻量、无运行状态的对象，不得启动 JVM。Fake 适配器只支持同一
`TimeScale` 内的非闰秒日历。跨 UTC/TAI/TT 或 UTC `:60` 输入在 `prepare()` 返回明确的
不兼容错误。

以后引入更完整的时间适配器时，不改变 `SimulationEngine.prepare/run` 顶层接口。

### 8.2 ScienceBackendFactory

factory 是无本次运行状态的对象，负责：

```text
create(manifest) -> ScienceBackendRuntime
```

它必须按 Manifest 已锁定的后端版本和配置创建 runtime，不得重新选择插件或读取未锁定
版本的科学配置。

### 8.3 ScienceBackendRuntime

runtime 提供窄行为边界：

```text
initialize()
current_epoch
propagate_to(target_epoch, cancellation_probe)
snapshot_truth()
snapshot_attitudes()
execute_impulsive_maneuver(prepared_entry)
close()
```

`snapshot_truth()` 返回按实体 ID 稳定排序的 Core `TruthState`。姿态使用 Core
`AttitudeState`，四元数固定采用 `w,x,y,z` 顺序。

后端执行机动后返回物理执行数据：实际 J2000 Δv、执行时刻以及前后 Truth 快照。
Engine 负责加入 `PLANNED`/`COMMAND` 来源和源 ID，再构造 `TruthManeuver`。这样后端只
负责物理结果，不重复实现 provenance 规则。

`current_epoch` 始终返回所有已初始化空间物体共同达到的时刻。runtime 只允许向前
传播；向过去时刻传播产生 `OUT_OF_ORDER`。若传播中响应取消，后端只能停在所有空间
物体已经同步的安全点，不能留下对象处于不同时刻的状态。

`close()` 必须幂等，Runner 仍保证每次 runtime 最多调用一次。关闭一次运行的 runtime
不等于关闭未来 Orekit 包中的进程级共享 JVM。

## 9. 调度与同刻事件顺序

采样时刻使用惰性迭代器生成，不把整个时间序列展开到内存。每种产品最多一个采样规则，
所有周期序列都包含正式运行的开始和结束时刻。周期不能整除总时长时，追加结束时刻；
例如 `[0,10]`、间隔 3 秒产生 `0,3,6,9,10`。

Engine 从 `synchronization_epoch` 初始化。若它早于正式 `time_range.start`，Engine
先进行预推进并执行该区间内的预设 Truth 机动，但不产生正式周期采样。

正式运行将所有产品采样和机动合并成按绝对时刻排序的事件组。一个同刻事件组是取消
不可打断的原子边界：

```text
传播所有空间物体到时刻 t
→ 按 order_index 顺序执行全部同刻机动
→ 为每个机动构造 TruthManeuver
→ 输出同刻的机动后 Truth 和姿态采样
→ 刷新达到上限的输出批次
→ 检查取消请求
```

同刻多个机动逐个串联：后一个机动的 `state_before` 等于前一个机动的 `state_after`。
同刻普通 `TruthState` 只表示全部机动执行后的状态。

同刻事件组内部因达到 `batch_size` 触发的阈值刷新属于该原子组，不在刷新前读取取消
状态。事件组之外的最终残余批次按固定通道顺序处理，并在写入每个非空批次前重新读取
取消状态；某一残余写入触发取消后，不得继续写入后续通道。

批次大小是非科学执行参数，只影响 sink 调用次数，不能改变记录内容、顺序、时刻或
Manifest。

## 10. 取消语义

`CancellationToken` 是线程安全、只能从未取消转为已取消的协作令牌。Engine 在以下
位置读取取消状态：

- Manifest 校验完成后、创建 runtime 前；
- runtime 初始化完成后；
- 每个事件组开始前和完成后；
- 事件组之外每个非空残余批次刷新前；
- 完成所有事件后、提交输出前。

`propagate_to()` 同时接收只读取消探针，使耗时后端能够在自己的安全点停止。取消不能
使同一个事件组只执行部分机动。

正常取消返回 `SimulationExecutionResult(status=CANCELLED)`，不抛异常。它携带类别为
`CANCELLED` 的 `ErrorDetail`，调用 sink 的 `abort()`，并关闭 runtime。v0.1 不发布
取消运行的部分科学 artifact；已经被实时消费者看到的数据只能视为未提交预览。由于
取消路径总是 abort，Result 的 `SimulationOutputSummary` 使用全零已提交计数。

若调用 `run()` 前令牌已经取消，Engine 在 Manifest 校验后直接返回 CANCELLED，停止
时刻取 `synchronization_epoch`，不创建 runtime，也不调用尚未开始的 sink。若
`propagate_to()` 内部响应取消，Result 的停止时刻取 runtime 的 `current_epoch`，该次
目标事件组不执行。

## 11. 输出 sink

### 11.1 Protocol

`SimulationOutputSink` 使用严格生命周期：

```text
NEW → begin(manifest) → WRITING → commit(summary) → COMMITTED
                              └→ abort(detail)   → ABORTED
```

`begin()` 成功后必须且只能进入一次 `commit()` 或 `abort()`。sink 接收：

- `tuple[TruthState, ...]`；
- `tuple[AttitudeState, ...]`；
- `tuple[TruthManeuver, ...]`。

sink 不得回写、替换或修改这些不可变对象。

`commit()` 只有成功返回后才进入 COMMITTED；若提交调用失败，sink 仍视为 WRITING，
Engine 随后 best-effort 调用 `abort()`。`CompositeOutputSink` 按固定顺序 begin 子
sink；某个 begin 失败时，已经成功 begin 的子 sink 按逆序 abort。

成功路径先刷新最后批次并关闭 backend runtime，再调用 `sink.commit()`。这样 runtime
清理错误不会发生在科学输出已经提交之后。若 `begin()` 本身失败，则 sink 尚未进入
WRITING，Engine 不要求对它调用 `abort()`。

### 11.2 内置 sink

`NullOutputSink` 丢弃数据但统计生命周期，用于性能和 Runner 测试。

`InMemoryOutputSink` 为小型仿真和交互示例提供便捷访问，但构造时必须提供严格正整数
`max_records`。Truth、姿态和机动记录总数超过上限时，产生
`RESOURCE_EXHAUSTED`，清理未提交内存结果并进入 ABORTED。

`CompositeOutputSink` 按构造时固定的子 sink 顺序转发。它不提供跨文件系统、网络或
数据库的分布式原子提交保证。正式持久化必须由未来单一 staging sink 负责原子发布；
不能把多个不可回滚外部 sink 的组合误称为原子事务。

## 12. 执行结果与公共错误

Core 新增可序列化的 `SimulationExecutionStatus`、`SimulationOutputSummary` 和
`SimulationExecutionResult`。

`SimulationExecutionStatus` 在 v0.1 只有：

- `COMPLETED`；
- `CANCELLED`。

真正故障通过异常抛出，不构造 `FAILED` Result。

`SimulationOutputSummary` 保存非负的 Truth、姿态和机动记录数。

`SimulationExecutionResult` 保存：

- Manifest 内容哈希；
- 执行状态；
- 实际停止的仿真时刻；
- `SimulationOutputSummary`；
- 取消时的 `ErrorDetail`。

完成结果不得携带错误；取消结果必须携带类别为 `CANCELLED` 的错误。Result 不包含运行
墙钟开始/结束时间、artifact 哈希、输出路径、保留状态、数据库 ID 或 Platform 引用。
这些信息属于未来 `RunOutcome`/`ResultBundle`。

Engine 公共异常为：

```text
SimulationEngineError
├── SimulationPreparationError
└── SimulationExecutionError
```

每个异常只公开一个 Core `ErrorDetail`。未知 Python、Java 或第三方异常必须在应用边界
转换为稳定类别和机器代码；异常对象、回溯和 Java 堆栈不得进入公共 JSON 上下文。

若失败发生在 `sink.begin()` 成功之后，Engine 调用 `sink.abort()` 再抛出
`SimulationExecutionError`；factory 创建、runtime 初始化或 `sink.begin()` 自身失败时，
不得对尚未开始的 sink 调用 abort。若 backend、sink 或清理同时失败，最先导致运行
失败的错误作为主错误，其余错误只进入内部诊断，不能覆盖主错误。

## 13. FakeBackend

FakeBackend 是公开 `sycasphere.engine.testing` 命名空间中的确定性兼容性后端。它仅供
Engine 测试、示例和第三方插件开发，不是默认科学后端，不宣称轨道精度。

它的稳定测试身份为：

```text
plugin_id               = sycasphere.testing.fake
implementation_version  = 0.1.0
interface_version       = 1.0
dynamics_model_id       = sycasphere.testing.constant-velocity
attitude_model_id       = sycasphere.testing.identity-attitude
propulsion_model_id     = sycasphere.testing.impulsive-propulsion
```

backend binding 及上述三个模型的 configuration 必须为空对象。

### 13.1 支持能力

- J2000 Cartesian 初始状态；
- 同一时间尺度内、非 UTC 闰秒的时刻；
- 匀速直线动力学模型；
- 固定单位姿态模型；
- J2000 脉冲机动；
- Truth 和姿态采样；
- `PLANNED` 与 `COMMAND` 来源；
- 确定性运行。

FakeBackend 使用明确的测试模型 ID，并拒绝其他动力学、姿态和推进模型 ID，避免静默
忽略请求所声明的科学模型。它同时要求 `EnvironmentDefinition.model_refs` 和
`external_data_refs` 为空。GroundStation 可以存在于场景中，但不生成独立
`TruthState`；没有观测计划时，其传感器定义不会参与本次计算。

### 13.2 数学语义

对于相邻时刻：

```text
r(t) = r(t0) + v(t0) * Δt
v(t) = v(t0)
```

内部数值计算使用 NumPy `float64`，公共边界重新构造严格有限的 Core 元组模型。

固定姿态是从 J2000 到 BODY 的：

```text
rotation_reference_to_body_wxyz = (1.0, 0.0, 0.0, 0.0)
angular_velocity_body_wrt_reference_rad_s = (0.0, 0.0, 0.0)
```

J2000 脉冲机动满足：

```text
r+ = r-
v+ = v- + requested_delta_v_j2000
actual_delta_v_j2000 = requested_delta_v_j2000
```

当前 `ImpulsiveManeuverSpec` 不包含燃料消耗，`ManeuverCapability` 只引用推进模型。
FakeBackend 因此保持实体质量不变，不引入任意耗油公式。Core `TruthManeuver` 已允许
以后真实后端根据推进模型产生质量下降。

## 14. 确定性与不可变性

相同请求、相同显式注册表和相同执行参数必须产生：

- 相同 Manifest 内容和内容哈希；
- 相同事件顺序和记录顺序；
- 相同 Truth、姿态和机动数值；
- 相同输出计数；
- 与批次大小无关的科学记录。

Manifest 自创建起不可变。运行状态、取消、错误、计数和 sink 结果不得写回 Manifest。

Engine 不保存跨运行的可变科学状态。所有公开 Core 模型在跨边界时重新验证；数值代码
可以使用独立 NumPy 数组，但不得让可变数组逃逸到公共接口。

## 15. 测试策略

### 15.1 Registry 和 prepare

- 注册表构造后不可修改；
- 精确 `PluginRef` 解析；
- 缺失、版本不兼容和能力不足错误；
- 配置校验不创建 runtime；
- `prepare()` 不调用 factory；
- 请求和 Manifest 的深度不可变性；
- 相同输入产生相同 Manifest；
- planned/command 合并、稳定 ID 和 `order_index`；
- 不支持的观测、链路、几何、有限推力、帧、时间和模型在 prepare 失败。

### 15.2 调度

- `[0,10]`、间隔 3 秒产生 `0,3,6,9,10`；
- 多产品不同周期的惰性合并；
- 开始和结束时刻强制输出；
- 预推进不产生正式采样；
- 预推进机动影响正式开始状态；
- 同刻多个机动顺序；
- 同刻采样只读取机动后 Truth；
- 不允许向过去传播。

### 15.3 输出和生命周期

- begin/commit/abort 的合法状态矩阵；
- 正常完成只 commit 一次；
- 运行已经开始后的取消只 abort 一次并返回 CANCELLED；
- 运行前已取消时不创建 runtime 或启动 sink；
- 传播中取消只停在所有对象同步的 `current_epoch`；
- backend、sink、关闭失败的主错误选择；
- runtime 最多关闭一次；
- InMemory 上限产生 `RESOURCE_EXHAUSTED` 并清理结果；
- Composite 固定转发顺序；
- 不同批次大小输出内容一致。

### 15.4 FakeBackend

- 匀速位置和速度；
- 固定 WXYZ 姿态；
- J2000 脉冲机动；
- `PLANNED`/`COMMAND` provenance；
- 多机动前后状态串联；
- 质量保持不变；
- 固定输入重复运行完全一致；
- GroundStation 不产生 TruthState；
- 非 J2000、跨尺度、闰秒和未知模型拒绝。

### 15.5 工程质量

至少执行：

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

还必须验证：

- Engine sdist/wheel 离线构建；
- 隔离环境安装 Core + Engine；
- 没有 JDK、JPype 和 Orekit 时公共导入和 FakeBackend 运行成功；
- Core 和 Engine 的公共 JSON Schema 快照；
- 最终 diff 的帧、时间、单位、Truth 访问、哈希和可变性审查。

## 16. 文档同步

实现本设计时同步：

- `docs/architecture/core-data-model-v0.2.md`；
- `docs/architecture/algorithm-integration-v0.2.md` 中的 Engine/算法边界引用；
- `docs/superpowers/specs/2026-07-20-sycasphere-runtime-and-simulation-engine-design.md`；
- 根 README；
- `packages/sycasphere-core/README.md`；
- `packages/sycasphere-engine/README.md`；
- 公共 schema 快照。

文档必须区分已实现的 Engine v0.1 与仍为计划的 Observation、Session、Orekit、Sim 和
Platform 能力。

## 17. 完成标准

Engine v0.1 只有在以下条件全部满足时完成：

1. 代码符合本设计和三份权威架构文档；
2. `prepare()` 生成可重复、不可变、可保存重放的 Manifest；
3. `run()` 通过 FakeBackend 完成批量 Truth、姿态和脉冲机动执行；
4. 取消、错误、sink 和 runtime 生命周期均有测试；
5. 不支持能力在 `prepare()` 明确失败；
6. Engine 在无 JDK/Orekit 环境中可构建、安装、导入和运行；
7. Ruff、mypy、pytest、构建和隔离安装全部通过；
8. 公共接口、Schema 和文档已同步；
9. 没有实现 Observation、Session、Orekit 或 Platform 等未请求范围；
10. 最终审查没有未解决的时间、帧、单位、Truth 泄漏、哈希或可变性问题。
