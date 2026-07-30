# SycaSphere 运行生命周期与可插拔仿真引擎设计规范

| 项目 | 内容 |
| --- | --- |
| 状态 | 已确认设计 |
| 日期 | 2026-07-20 |
| 适用范围 | SycaSphere 首个可开发版本及其独立仿真引擎 |
| 关联基线 | `core-data-model-v0.2.md`、`algorithm-integration-v0.2.md` |

## 1. 文档目的与效力

本文记录对 v0.2 基线的已确认修订，解决运行清单生命周期、观测交付、科学时间与坐标、独立仿真引擎、交互控制和运行时机动等问题。本文只描述设计，不是实现计划。

在本文与 v0.2 基线冲突之处，后续必须有意修订 v0.2 文档和 `AGENTS.md`，不得在代码中静默选择。完成整合前，本文作为已批准的设计增量。

截至 2026-07-30，仓库实际交付边界如下：

- Core 已实现 `AttitudeState`、`TruthState`、`TruthManeuver`、`ObservationEvent`、`ObservationMeasurement`、`IdealObservation`、`ReportedObservation`、`MeasurementUncertainty`、`ObservationDeliveryRecord`、`DeliverySummary` 和 `StreamingObservationEnvelope`。
- Engine v0.1 已实现同步 `prepare()`/`run()`、显式 `PluginRegistry`、非科学 `FakeBackend` 和输出 sinks。
- Observation 流水线、交互式 Session、Orekit、Sim 保留、Platform 生命周期和前端仍为计划。
- `SimulationExecutionResult` 不是 `RunOutcome`。
- `FakeBackend` 质量保持不变，因为当前脉冲输入没有消耗量。
- 先分配 `event_id`，完成几何检查后一次性创建不可变 Event，不创建可回填的半成品。
- Event 只跟随 ObservationSchedule 触发。积分步、Truth 输出采样和前端渲染帧均不得隐式产生 Event。
- 每个 ObservationSchedule 的交付通道由 `error_profile_id` 唯一决定： `error_profile_id is None` 选择 IDEAL；`error_profile_id` 存在选择 REPORTED。
- OutputRequirement 只控制 artifact 持久化；Engine 仍必须生成所选交付通道需要的 Ideal 或 Reported payload，不能因为未请求对应 artifact 而跳过科学流水线。
- 算法只接收成功交付的 Ideal 或 Reported。
- 链路延迟和丢包属于 LinkModel，不属于 ErrorPipeline。
- 首版 `StreamingObservationEnvelope` 使用 `delivery_epoch`，不包含 `arrival_time` 或 `sequence_number`。
- 逐事件交付记录通过显式 `DELIVERY_RECORDS` 输出要求控制，不要求全部常驻内存。
- Sim 后续默认使用 TRANSIENT，只保留最近一次临时运行。
- 所有机器字段和枚举使用稳定英文值；后续前端必须提供中文标签、说明和磁盘占用提示。
- 中文文案不写入 Manifest、科学哈希或稳定数据库枚举。
- `IdealObservation` 与 `ReportedObservation` 是两个独立模型；算法直接读取被授权的模型，不增加 `AlgorithmObservationView`。
- 首版算法只接收成功交付的 Ideal/Reported，不提供 `NonDetectionReport`。
- 首版链路只模拟延迟和丢包，不模拟乱序、重复、重传或多次交付尝试。
- Engine 后续保证每个算法输入流 FIFO；链路延迟不改变测量顺序。

上列结果类型及其不可变 Schema 已在 Core 交付；Engine v0.1 已生成并通过 sink 交付
Truth、姿态和脉冲机动对象，但不持久化这些对象。Observation、交互式 Session、
Orekit 适配以及 Sim/Platform 运行生命周期和持久化均为后续计划。

## 2. 核心设计决定

1. Engine 科学输入拆分为 `SimulationRunRequest` 和
   `SimulationExecutionManifest`；Platform 后续若保留自己的
   `RunRequest`/`RunManifest`，必须明确限定为上层概念，并与 `RunRecord`、
   `RunAttempt`、`RunOutcome` 和 `ResultBundle` 分离。
2. `SimulationExecutionManifest` 自生成起不可变，只描述解析后的科学输入；
   运行状态和最终输出不写回 Manifest。未来 Platform Manifest 也只能保存不可变
   provenance。
3. `IdealObservation` 与 `ReportedObservation` 是两个独立模型；算法直接读取被授权的模型，不增加 `AlgorithmObservationView`。
4. 每个 ObservationEvent 恰好生成一个终态 `ObservationDeliveryRecord`；几何拒绝、
   漏测、质量拒绝和链路丢包是内部结构化诊断事实，不向算法发送。
5. 仿真代码采用单仓库、多安装包；默认独立仿真产品安装 Orekit，高级用户可只安装后端中立的引擎内核。
6. 引擎使用分层插件体系，首版开放完整科学后端、测量模型、误差模型和只支持延迟、
   丢包与 FIFO 的数据链路模型。
7. 公共 `J2000` 唯一映射 Orekit `EME2000`；地固坐标系与 WGS84 椭球语义分离。
8. 计划中的交互式引擎支持暂停、继续、单步、调整单步推进量、改变执行节奏、推进到指定时刻、快照和恢复。
9. 数值积分器配置和输出采样在一次运行中冻结；运行时可调整的是单步推进量和执行节奏。
10. 后续运行时允许追加未来或当前时刻的机动命令，但必须写入追加式运行时命令日志。
11. 模型支持脉冲和有限推力机动；首版最低验收只要求完整实现脉冲机动。
12. 未来 Sim 默认运行是临时运行；只保留最近一次临时结果，用户可以显式转为保留或
    归档；该保留实现尚未交付。

## 3. 单仓库、多安装包

```text
SycaSphere/
├── packages/
│   ├── sycasphere-core/
│   ├── sycasphere-engine/
│   ├── sycasphere-orekit/
│   ├── sycasphere-sim/
│   └── sycasphere-platform/
├── frontend/
└── docs/
```

### 3.1 sycasphere-core

当前已实现。保存纯领域契约：`Epoch`、`FrameRef`、状态、实体、传感器、仿真定义、
机动、观测计划、执行请求、执行清单、公共异常和模式版本，以及姿态、Truth、
Observation、测量不确定度、交付终态/汇总和最小流式信封。Engine v0.1 已生成
`TruthState`、`AttitudeState` 和 `TruthManeuver`；Observation、delivery 和 Estimate
等仍未实现。Platform 生命周期也仍为计划。Core 不得依赖 Orekit、JPype、JVM、
数据库、FastAPI 或前端。

Core 的运行时依赖仍仅为 Pydantic 与 NumPy。根开发锁图显式包含 Hatchling；发布构建先以 `uv sync --locked` 同步，再以 `uv build --offline --no-build-isolation` 使用锁定后端，避免临时解析未跟踪的构建版本。

### 3.2 sycasphere-engine

已实现 v0.1 后端中立批运行内核：同步准备、惰性时间调度、Truth/姿态/J2000 脉冲机动执行、取消和输出端口。观测编排、误差与链路编排、交互会话仍为计划。它依赖 Core，但不得导入 Orekit。

### 3.3 sycasphere-orekit

计划实现默认科学后端：JVM 生命周期、传播、时间尺度、坐标转换、天体与星历、EOP 以及 Core 与 Orekit 对象的转换。Orekit、JPype 和 Java 对象不得越过该包的公共适配边界。

### 3.4 sycasphere-sim

计划面向独立用户提供完整仿真产品，默认安装 Engine 与 Orekit，并提供稳定 Python API、CLI、内存输出、本地 artifact 和临时/保留运行管理。未来 `pip install sycasphere-sim` 必须开箱可运行。

### 3.5 sycasphere-platform

计划保存任务、实验、算法、评价、元数据、ArtifactStore、API 和前端编排。Platform 使用 Engine；Engine 不得依赖或感知 Platform。

高级开发者可以只安装 `sycasphere-engine` 开发替代后端；只安装 Engine 不得要求 JDK。

## 4. 分层插件体系

首版开放以下插件类型：

- 完整科学后端：传播、时间、坐标、天体和星历；
- 测量模型：由 Truth 和传感器几何生成 IdealObservation；
- 误差模型：由 Ideal 生成 Reported 或传感器漏测结果；
- 数据链路模型：首版只对所选 Ideal/Reported payload 施加延迟或丢包，并保持每个
  算法输入流 FIFO。

每个插件必须提供机器可读 manifest，声明稳定 ID、实现版本、接口版本、能力、配置模式、确定性和资源要求。引擎依据能力声明选择插件，不得依据名称猜测。

抖动、乱序、重复、重传和多次交付尝试均延后，不能提前进入首版 Core Schema 或
Engine 验收。

## 5. 运行对象与生命周期

```text
SimulationRunRequest                 Core 契约已实现
    ↓ Engine.prepare()，v0.1 已实现
SimulationExecutionManifest         Core 契约与 Engine 生成均已实现
    ↓ 可选上层 provenance
Platform RunManifest                计划实现，不得与 Engine Manifest 混用
    ↓ 创建操作记录
RunRecord                           可变运行状态，计划实现
    ↓ 一个或多个执行尝试
RunAttempt                          可变尝试记录，计划实现
    ↓ 终态发布
RunOutcome                          一次性终态，计划实现
    ↓ 引用
ResultBundle / Artifacts            计划实现
```

### 5.1 SimulationRunRequest 与 Platform RunRequest

Core 已实现的 `SimulationRunRequest` 是独立 Engine 的完整科学输入，嵌入完整
`SimulationDefinition`，不包含数据库修订引用、运行状态、保留策略、输出路径或 UI
状态。

Platform 后续可以另设 `Platform RunRequest` 表示用户提交的 Experiment 修订、参数
覆盖、算法选择、超时、资源要求和幂等键。提交前的 UI 编辑内容只是草稿；调用 Engine
前，Platform 必须把定义引用解析为完整 `SimulationRunRequest`。

### 5.2 SimulationExecutionManifest 与 Platform RunManifest

Engine v0.1 的 `prepare()` 生成 `SimulationExecutionManifest`，记录完整源请求、
解析后的精确插件、实际外部数据、稳定派生随机流、紧凑时间线、事件顺序、预期输出和
内容哈希。Core Manifest 数据契约与 Engine 生成逻辑均已实现。

Platform 后续若保留自己的 `RunManifest`，必须明确区分为 Platform provenance：
引用或嵌入 `SimulationExecutionManifest` 哈希，再增加 Mission、Experiment、算法和
评价输入。两种 Manifest 生成后均不可修改，并且都不保存状态、墙上时间、错误、
输出哈希、本地路径或保留策略。

### 5.3 RunRecord 与 RunAttempt

`RunRecord` 和 `RunAttempt` 均为计划中的 Platform/Sim 生命周期契约。RunRecord 是
可变操作状态，允许 `CREATED → VALIDATING → QUEUED → RUNNING → FINALIZING →
终态`。RunAttempt 记录一次 worker 执行；可重试故障创建新 Attempt，但继续引用同一
`SimulationExecutionManifest` 及可选 Platform Manifest。修改科学输入必须创建新
Run。

### 5.4 RunOutcome 与 ResultBundle

`RunOutcome` 和 `ResultBundle` 均为计划契约。Outcome 在终态一次性生成，记录
Manifest 哈希、最终状态、开始/结束时间、输出哈希、实际环境、ResultBundle 和结构化
错误。失败和取消也必须产生 Outcome。只有经过校验的部分产物才能以 `PARTIAL`
发布；未经校验的临时文件不是科学结果。

## 6. 临时产物、保留策略与磁盘安全

本节均为未来 Sim/Platform 计划，当前没有 RunStore、临时发布或保留实现。计划中的
运行先写入按 `run_id/attempt_id` 隔离的临时产物区。前端和评价器不得读取该区域。
发布顺序为关闭与刷新、模式校验、数值校验、计算哈希、生成 ResultBundle、生成
Outcome、提交正式引用。

运行保留类为：

- `TRANSIENT`：默认，只保留最近一次临时运行；
- `RETAINED`：用户通过前端“保留此次运行”、CLI `--retain` 或明确输出目录保留；
- `ARCHIVED`：迁移到外部磁盘或对象存储，本地可只保留索引和摘要。

保留类属于未来 `RunRecord`/`RunStore` 的可变操作元数据，不进入
`SimulationExecutionManifest` 或可选 Platform Manifest 的科学输入哈希；改变保留类
不得复制或修改科学 artifact 内容。

新的运行成功发布后才清理旧的 TRANSIENT。若空间不足以同时容纳新旧运行，开始前必须提示用户删除、改用其他位置或取消。系统不得自动删除 RETAINED。运行前必须估算容量并检查最低剩余空间；临时产物、失败 Attempt 和日志采用独立清理/轮转策略。

不可变性表示一个仍存在的科学 artifact 不可被原地覆盖，不禁止通过显式管理操作删除整个运行。

逐事件 `ObservationDeliveryRecord` artifact 只有请求 `DELIVERY_RECORDS` 时才保存，
并服从未来 Sim 的 TRANSIENT 默认保留策略；未请求时 Engine 仍需逐事件形成终态事实
并流式聚合 DeliverySummary。

## 7. 观测生成与交付

```text
schedule trigger
    ↓
preallocate deterministic event_id
    ↓
geometry / visibility / pointing
    ↓
create immutable ObservationEvent once
    ↓
branch on ObservationEvent.geometry_status
    ├─ GEOMETRY_REJECTED → ObservationDeliveryRecord → terminal
    └─ VISIBLE → Deterministic Measurement Model → IdealObservation
                    ↓ branch on schedule error_profile_id
                    ├─ None → select IDEAL → LinkModel
                    └─ present → ErrorPipeline
                                    ├─ SENSOR_MISSED / QUALITY_REJECTED → ObservationDeliveryRecord → terminal
                                    └─ ReportedObservation → select REPORTED → LinkModel
LinkModel (selected IDEAL or formed REPORTED only)
    ├─ LINK_DROPPED → ObservationDeliveryRecord → terminal
    └─ DELIVERED → ObservationDeliveryRecord
                 → StreamingObservationEnvelope → 算法输入
每个 Event 的终态 → DeliverySummary
```

### 7.1 ObservationEvent 与调度

Core 已实现的 `ObservationEvent` 是内部科学事实。每个 schedule occurrence、触发
epoch、sensor、target 和 measurement model invocation 恰好对应一个 Event。Engine
后续先预分配确定性 event ID，完成几何检查后一次性创建不可变 Event；Event 不随积分
步、Truth 输出采样或前端渲染帧产生。几何失败仍产生 Event，但不产生 Ideal。

### 7.2 ObservationMeasurement 与 MeasurementUncertainty

Core 使用统一 `ObservationMeasurement` 固定标准测量的维度、分量名、SI 单位、Frame、
qualifier 和数值范围；CUSTOM 使用内容哈希固定的 schema 引用。
`MeasurementUncertainty` 保存与 measurement 分量完全一致的有效残余误差 covariance，
必须有限、对称和半正定。它不保存实际抽样误差、真实偏差或 Truth 残差。

### 7.3 IdealObservation 与 ReportedObservation

`IdealObservation` 是独立、算法安全的公开模型，包含 observation/event ID、真实测量
时刻、传感器、公开 SubjectRef、测量类型、强类型 payload 和确定性模型来源。它不得
包含 Truth target、error model、uncertainty 或实际误差。

`ReportedObservation` 是独立、算法安全的公开模型，使用不同 observation ID，并增加
error model ref 和可选有效 uncertainty。它不得包含 Ideal 值、Truth、本次实际噪声
样本、隐藏偏差或评价器专用残差。

同一 Event 的 Ideal/Reported 共享 event ID、measurement epoch、sensor、SubjectRef
和 measurement type。`error_profile_id is None` 选择 IDEAL；存在时选择 REPORTED。
输出要求可以同时保存两种 artifact，但不得改变 Event 唯一交付通道。

### 7.4 ObservationDeliveryRecord 与 DeliverySummary

每个 Event 恰好产生一个不可变终态 `ObservationDeliveryRecord`：
`GEOMETRY_REJECTED`、`SENSOR_MISSED`、`QUALITY_REJECTED`、`LINK_DROPPED` 或
`DELIVERED`。该对象严格校验 selected channel、Ideal/Reported ID、payload hash、
delivery epoch、latency 和 reason code 的状态矩阵。它是可计算的结构化诊断事实，
不是日志，也不发送给算法。

`DeliverySummary` 聚合所有五类终态并保持总数守恒。评价器不得解析日志文本计算漏测
率或丢包率。`DELIVERY_SUMMARY` 控制汇总 artifact；`DELIVERY_RECORDS` 控制逐事件
artifact。即使未保存逐事件记录，Engine 也必须在处理过程中形成每个终态并完成汇总。

### 7.5 流式信封与丢包

只有 `DELIVERED` 产生 `StreamingObservationEnvelope`。Core 信封只包含 `event_id`、
`delivery_epoch` 和成功交付的 Ideal/Reported Observation；不包含 session、sequence、
attempt、idempotency、duplicate 或 retransmission 字段。数据链路丢包通过不创建信封
模拟，算法看不到丢失测量内容。首版 Engine 保证 FIFO，链路延迟不改变测量顺序。

### 7.6 存储（计划）

未来 Parquet 按通道和标准测量类型分区，使用明确 SI 单位列；交付汇总和可选逐事件
记录单独保存。上层依赖 `ObservationDatasetReader/Writer`、
`MetadataRepository` 和 `ArtifactStore`，使 SQLite/本地目录能够演进为
PostgreSQL、对象存储和独立查询服务，而不改变领域与算法接口。该存储实现不属于当前
Core 批次。

## 8. 时间与坐标系

### 8.1 Epoch

`Epoch` 的公共字段固定为 `value` 和 `time_scale`，不提供 `scale` 兼容别名。UTC 序列化必须携带 `Z` 或明确偏移，持久化时规范化为 `Z`；`Z` 表示 UTC+00:00。TAI 和 TT 使用对应时间尺度的日历值，不附加 `Z`。绝对时间使用字符串边界表示，时间间隔使用 SI 秒。`SimulationExecutionManifest` 通过实际外部数据 provenance 记录闰秒和时间数据版本。

### 8.2 帧定义

- 公共 `J2000` 隐含 Earth-centered 语义，并唯一映射 Orekit `EME2000`，公共模型不重复保存中心天体字段；
- GCRF 未来需要时作为独立公共帧增加；
- 地固帧使用 `EARTH_FIXED`，在 `earth_fixed` 子对象内显式声明 ITRF realization、IERS conventions 和 EOP 数据；
- WGS84 只表示参考椭球；
- GEODETIC/CARTESIAN 是坐标表示，不是模糊帧名；
- LVLH、VVLH、BODY 和 SENSOR 统一绑定 `owner_id`、`convention` 和 `reference_epoch`。

权威转换只由科学后端完成。6×6 状态协方差必须使用完整状态变换 Jacobian。

Core 首版 `CartesianState` 只包含 `epoch`、`frame`、`position_m` 和 `velocity_mps`；不增加可选加速度字段。加速度属于动力学输出或派生量，后续若成为边界契约必须单独评审。

## 9. SimulationRunRequest

`SimulationRunRequest` 是独立 Engine 能够理解的完整科学输入：

| 字段 | 职责 |
| --- | --- |
| `schema_version` | 请求契约版本。 |
| `simulation_definition` | 完整 `SimulationDefinition`，包含实体、环境、同步初始状态、动力学、传感器能力和基线真值事件；不得替换为数据库或修订引用。 |
| `time_range` | 本次运行的确切闭区间开始和结束时刻；只筛选事件，不承载机动。 |
| `output_sampling` | Truth、姿态、几何等输出的固定采样策略；它与数值积分步长和容差独立，不改变积分精度。 |
| `observation_schedules` | 首版只接受 `PeriodicObservationSchedule`（`PERIODIC`）和 `ExplicitObservationSchedule`（`EXPLICIT`），用于声明观测尝试。 |
| `command_timeline` | 首版只接受 `ManeuverCommand`；姿态、云台、传感器模式和可用性命令延后。 |
| `backend` | `ScienceBackendBinding`，固定完整科学后端的确切实现版本和积分器配置。 |
| `link_models` | 运行级交付模型；首版只描述延迟、丢包和 FIFO。 |
| `random_seed` | 主种子；引擎按组件稳定 ID 派生相互独立的随机流。 |
| `output_requirements` | 需要持久化的 Truth、Ideal、Reported、交付汇总/逐事件记录、姿态、几何和诊断 artifact。 |

测量模型和误差模型只保存在 `SensorDefinition`，由每个观测计划通过稳定 ID 选择；
请求顶层不得重复保存 `measurement_model_refs` 或 `error_model_refs`。数据链路是
运行级交付配置，因此保留 `link_models`。

每个 schedule 的 `error_profile_id` 决定 IDEAL 或 REPORTED 交付通道。
`IDEAL_OBSERVATIONS`、`REPORTED_OBSERVATIONS`、`DELIVERY_SUMMARY` 和
`DELIVERY_RECORDS` 只控制 artifact 持久化，不能关闭所选通道需要的科学流水线。
算法只消费最终 DELIVERED payload。

首版所有空间对象的 `initial_state.epoch` 必须与
`simulation_definition.synchronization_epoch` 完全相等。未来的兼容升级可以允许每个
对象的初始时刻不晚于同步时刻，再由 Engine 分别预推进到同步时刻；严格首版数据无需
迁移，现有字段也不改变。

同一时刻的事件顺序固定为：传播到时刻、保存机动前状态、执行机动、生成机动事实并
保存机动后状态、使用机动后状态尝试观测、最后生成常规输出采样。因此同刻观测始终是
post-maneuver observation，不提供机动前观测开关。

Engine v0.1 的 `prepare()` 解析该请求并生成不可变的
`SimulationExecutionManifest`。Platform 后续若保留 `RunManifest`，只引用或嵌入该
Manifest 哈希，再增加 Mission、Experiment、算法和评价 provenance；可变状态进入
`RunRecord`/`RunAttempt`，终态时间、状态、错误和输出哈希进入 `RunOutcome`。

## 10. 交互式仿真 API

Engine v0.1 已实现前两个同步批运行 API；交互式 Session 和恢复仍为后续计划：

```text
prepare(request) -> SimulationExecutionManifest
run(manifest, sink, cancellation) -> SimulationExecutionResult
open_session(manifest, sinks) -> SimulationSession
restore_session(checkpoint, sinks) -> SimulationSession
```

计划中的 `SimulationSession` 支持 `status`、`current_epoch`、`resume`、`pause`、`step`、`step_by`、`advance_to`、`set_control_step`、`set_pacing_rate`、`snapshot`、`cancel` 和 `close`。

必须区分：

- 数值积分步长和容差：后端内部科学配置，一次运行中冻结；
- 单步推进量：一次 `step` 前进的仿真时间，可在 PAUSED 中调整；
- 输出采样间隔：持久化频率，一次运行中冻结；
- 执行节奏：墙上时间与仿真时间的倍率，可运行中调整，不改变物理精度。

未来会话默认从 PAUSED 开始。暂停在安全事件边界生效并刷新临时输出；首版只允许向前推进。运行时科学控制变化写入 `SimulationControlTrace`。

## 11. 机动模型与运行时注入

机动语义分为：

- `ManeuverCapability`：航天器的推力、比冲、燃料、方向和持续时间能力；
- `PlannedTruthManeuver`：SimulationDefinition 中预设的真实场景事件；
- `ManeuverCommand`：准备后进入 command timeline 的统一执行命令；
- `TruthManeuver`：后端实际执行后生成的事实，包含命令引用、实际时刻、实际 Δv、前后状态和质量变化；
- `ManeuverHypothesis`：算法输出，始终与 TruthManeuver 分离。

计划中的交互会话支持 `schedule_command`、`schedule_maneuver`、`cancel_scheduled_command`、`list_scheduled_commands` 和 `get_command_status`。首版只允许在 PAUSED 状态添加当前或未来时刻命令；过去命令必须恢复 checkpoint 后创建新运行分支。

运行时命令追加到不可变、哈希链接的 `RuntimeCommandJournal`。原始 SimulationExecutionManifest 不回写。完整复现条件为 Manifest 加 RuntimeCommandJournal；Outcome 保存最终 journal hash。取消未来命令通过追加 CANCEL 记录实现，已执行命令不能原地撤销。

模型支持 `IMPULSIVE` 与 `FINITE_BURN`；首版最低验收完整实现脉冲机动，有限推力保留稳定模式与后端能力声明。

## 12. 结构化错误与资源边界

公共错误类别只使用一套稳定枚举：`VALIDATION_ERROR`、`PLUGIN_MISSING`、`PLUGIN_INCOMPATIBLE`、`BACKEND_INITIALIZATION`、`EXTERNAL_DATA`、`UNSUPPORTED_FRAME`、`UNSUPPORTED_MEASUREMENT`、`UNAUTHORIZED_DATA_ACCESS`、`OUT_OF_ORDER`、`NUMERICAL_FAILURE`、`RESOURCE_EXHAUSTED`、`TIMEOUT`、`CANCELLED` 和 `INTERNAL_ERROR`，不提供同义兼容别名。错误包含稳定类别、机器可读代码、用户信息、是否可重试和组件引用；`run_id`、`attempt_id` 与 `diagnostic_artifact_ref` 在对应资源尚未创建时可以为空，存在时必须非空。错误上下文使用有限、深度不可变 JSON，拒绝异常/回溯对象和保留的异常负载键。

Java 异常不得泄漏为公共类型；Orekit adapter 转换为结构化错误，完整堆栈只进入诊断 artifact。JVM 由单一 runtime 组件启动一次；插件导入和 manifest 读取不得启动 JVM。

## 13. 验收测试

### Core（当前已实现契约）

- Epoch、FrameRef、数组、单位和序列化不变量；
- 模式版本兼容；
- SimulationDefinition 同步初始状态、机动、时间范围、采样和两类观测计划；
- 完整 SimulationRunRequest、不可变 SimulationExecutionManifest、哈希与公开模式。
- Attitude、Truth、Observation、MeasurementUncertainty、DeliveryRecord/Summary 和
  StreamingEnvelope 的公开模式、状态矩阵、深度不可变与授权隔离；
- `DELIVERY_RECORDS` 输出要求。

### Engine v0.1 批运行（已验收）

- 使用假后端验证 prepare/run 生命周期；
- 固定种子、确定性结果和惰性时间调度；
- 取消、runtime 关闭和 sink commit/abort 生命周期；
- J2000 脉冲机动以及 Truth、姿态和机动输出；
- Engine wheel/sdist 构建和 Core + Engine 隔离安装。

### Session 与 Observation（计划验收）

- session/restore、暂停、单步和推进到指定时刻；
- 每个 schedule trigger 的确定性 Event、漏测、质量拒绝、丢包、延迟和 FIFO；
- 运行时脉冲机动、命令日志和 checkpoint 分支。

### Orekit（计划验收）

- JVM 单生命周期；
- J2000/EME2000 唯一映射；
- Earth-fixed/ITRF/EOP、UTC/TAI/TT 和闰秒；
- 传播、地基/天基几何、状态/姿态/协方差转换；
- Core/Orekit 边界无 Java 对象泄漏。

### Sim 与 Platform（计划验收）

- 临时产物安全发布和崩溃恢复；
- 默认临时运行、显式保留和新运行成功后清理旧临时运行；
- 磁盘不足预检；
- Parquet 模式和 repository/artifact 端口契约；
- `SimulationExecutionManifest`、可选 Platform Manifest、`RunOutcome` 和
  `ResultBundle` 不可变；
- 算法只能读取授权观测通道。

### 安装隔离

Core 和 Engine 已完成独立安装验证；Orekit、Sim、Platform 和前端安装仍为计划。

- Core 可独立导入；
- Engine 在无 JDK 时可导入和运行假后端测试；
- Orekit 包安装后通过参考传播；
- `pip install sycasphere-sim` 开箱可运行；
- Platform 只通过公共 Engine API 编排仿真。

## 14. 明确延后

首版不实现 `AlgorithmObservationView`、`NonDetectionReport`、链路抖动、乱序、重复、
重传、多次交付尝试、完整有限推力执行、向后时间旅行、恶意插件安全沙箱、分布式任务
系统和 GPU 大目录传播。这些能力不得提前污染首版接口之外的实现。
