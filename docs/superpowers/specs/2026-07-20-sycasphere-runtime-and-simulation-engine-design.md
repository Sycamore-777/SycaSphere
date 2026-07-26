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

截至 2026-07-26，仓库实际完成的是 `sycasphere-core` 中的定义、机动、调度、
`SimulationRunRequest` 和 `SimulationExecutionManifest` 契约。本文的 Engine
`prepare()`/执行/会话、观测与结果、Orekit 适配以及 Sim/Platform 运行生命周期和
持久化均为后续计划，以下 API 不表示已经存在运行时实现。

## 2. 核心设计决定

1. Engine 科学输入拆分为 `SimulationRunRequest` 和
   `SimulationExecutionManifest`；Platform 后续若保留自己的
   `RunRequest`/`RunManifest`，必须明确限定为上层概念，并与 `RunRecord`、
   `RunAttempt`、`RunOutcome` 和 `ResultBundle` 分离。
2. `SimulationExecutionManifest` 自生成起不可变，只描述解析后的科学输入；
   运行状态和最终输出不写回 Manifest。未来 Platform Manifest 也只能保存不可变
   provenance。
3. `IdealObservation` 与 `ReportedObservation` 是两个独立模型；算法直接读取被授权的模型，不增加 `AlgorithmObservationView`。
4. 漏测、质量拒绝和链路丢包使用内部结构化交付记录；首版不向算法发送 `NonDetectionReport`。
5. 仿真代码采用单仓库、多安装包；默认独立仿真产品安装 Orekit，高级用户可只安装后端中立的引擎内核。
6. 引擎使用分层插件体系，首版开放完整科学后端、测量模型、误差模型和数据链路模型。
7. 公共 `J2000` 唯一映射 Orekit `EME2000`；地固坐标系与 WGS84 椭球语义分离。
8. 计划中的交互式引擎支持暂停、继续、单步、调整单步推进量、改变执行节奏、推进到指定时刻、快照和恢复。
9. 数值积分器配置和输出采样在一次运行中冻结；运行时可调整的是单步推进量和执行节奏。
10. 后续运行时允许追加未来或当前时刻的机动命令，但必须写入追加式运行时命令日志。
11. 模型支持脉冲和有限推力机动；首版最低验收只要求完整实现脉冲机动。
12. 默认运行是临时运行；只保留最近一次临时结果，用户可以显式转为保留或归档。

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
机动、观测计划、执行请求、执行清单、公共异常和模式版本。观测结果、Truth 执行结果
和 Platform 生命周期仍未实现。Core 不得依赖 Orekit、JPype、JVM、数据库、FastAPI
或前端。

Core 的运行时依赖仍仅为 Pydantic 与 NumPy。根开发锁图显式包含 Hatchling；发布构建先以 `uv sync --locked` 同步，再以 `uv build --offline --no-build-isolation` 使用锁定后端，避免临时解析未跟踪的构建版本。

### 3.2 sycasphere-engine

计划实现。保存后端中立的仿真内核：仿真准备、事件调度、时间推进、观测编排、误差与链路编排、交互会话和输出端口。它依赖 Core，但不得导入 Orekit。

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
- 数据链路模型：对已形成的报告施加延迟、抖动、乱序、重复和丢包。

每个插件必须提供机器可读 manifest，声明稳定 ID、实现版本、接口版本、能力、配置模式、确定性和资源要求。引擎依据能力声明选择插件，不得依据名称猜测。

## 5. 运行对象与生命周期

```text
SimulationRunRequest                 Core 契约已实现
    ↓ Engine.prepare()，计划实现
SimulationExecutionManifest         Core 契约已实现、Engine 生成计划实现
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

计划中的 Engine `prepare()` 生成 `SimulationExecutionManifest`，记录完整源请求、
解析后的精确插件、实际外部数据、稳定派生随机流、紧凑时间线、事件顺序、预期输出和
内容哈希。该 Core Manifest 数据契约已经实现；Engine 生成逻辑尚未实现。

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

运行期间先写入按 `run_id/attempt_id` 隔离的临时产物区。前端和评价器不得读取该区域。发布顺序为关闭与刷新、模式校验、数值校验、计算哈希、生成 ResultBundle、生成 Outcome、提交正式引用。

运行保留类为：

- `TRANSIENT`：默认，只保留最近一次临时运行；
- `RETAINED`：用户通过前端“保留此次运行”、CLI `--retain` 或明确输出目录保留；
- `ARCHIVED`：迁移到外部磁盘或对象存储，本地可只保留索引和摘要。

保留类属于未来 `RunRecord`/`RunStore` 的可变操作元数据，不进入
`SimulationExecutionManifest` 或可选 Platform Manifest 的科学输入哈希；改变保留类
不得复制或修改科学 artifact 内容。

新的运行成功发布后才清理旧的 TRANSIENT。若空间不足以同时容纳新旧运行，开始前必须提示用户删除、改用其他位置或取消。系统不得自动删除 RETAINED。运行前必须估算容量并检查最低剩余空间；临时产物、失败 Attempt 和日志采用独立清理/轮转策略。

不可变性表示一个仍存在的科学 artifact 不可被原地覆盖，不禁止通过显式管理操作删除整个运行。

## 7. 观测生成与交付

```text
ObservationEvent
    ↓ 几何、可见性和指向
IdealObservation
    ↓ ErrorPipeline
ReportedObservation 或未形成报告
    ↓ 分配源序号
LinkModel
    ↓ 延迟、乱序、重复、丢包
算法输入
```

### 7.1 IdealObservation

独立公开模型，包含 event ID、真实测量时刻、传感器与目标引用、测量类型、帧、强类型载荷和确定性模型来源。IDEAL 通道算法可以直接读取该模型。

### 7.2 ReportedObservation

独立且算法安全的公开模型，包含 event ID、报告时刻、源序号、公开引用、测量类型、帧、报告测量值、不确定度和质量标志。不得包含 Ideal 值、Truth、本次真实噪声样本、隐藏偏差或评价器专用信息。

### 7.3 ObservationDeliveryRecord

这是可计算的结构化诊断事实，不是日志，也不发送给算法。默认只为 `SENSOR_MISSED`、`QUALITY_REJECTED`、`LINK_DROPPED` 等非正常结果保存稀疏记录，并保存按传感器、链路和时间窗口聚合的 DeliverySummary。正常成功交付不重复记录。

记录级别为 `SUMMARY_ONLY`、`FAILURES`、`FULL`，默认 `FAILURES`。日志只能引用或摘要这些事实，评价器不得解析日志文本计算漏测率或丢包率。

### 7.4 流式信封与丢包

StreamingObservationEnvelope 包含 session ID、序号、arrival_time、idempotency key 和 Ideal/Reported 观测。数据链路丢包通过不交付信封模拟；算法可以从源序号缺口推断丢包，但看不到丢失测量内容。首版算法只接收成功交付的 Ideal/Reported，不提供 NonDetectionReport。

### 7.5 存储

Parquet 按通道和标准测量类型分区，使用明确 SI 单位列；交付汇总和稀疏异常记录单独保存。上层依赖 `ObservationDatasetReader/Writer`、`MetadataRepository` 和 `ArtifactStore`，使 SQLite/本地目录能够演进为 PostgreSQL、对象存储和独立查询服务，而不改变领域与算法接口。

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
| `link_models` | 运行级报告交付模型，描述丢包、延迟、抖动、乱序和重复。 |
| `random_seed` | 主种子；引擎按组件稳定 ID 派生相互独立的随机流。 |
| `output_requirements` | 需要生成的 Truth、Ideal、Reported、交付汇总、姿态、几何和诊断产物。 |

测量模型和误差模型只保存在 `SensorDefinition`，由每个观测计划通过稳定 ID 选择；
请求顶层不得重复保存 `measurement_model_refs` 或 `error_model_refs`。数据链路是
运行级交付配置，因此保留 `link_models`。

首版所有空间对象的 `initial_state.epoch` 必须与
`simulation_definition.synchronization_epoch` 完全相等。未来的兼容升级可以允许每个
对象的初始时刻不晚于同步时刻，再由 Engine 分别预推进到同步时刻；严格首版数据无需
迁移，现有字段也不改变。

同一时刻的事件顺序固定为：传播到时刻、保存机动前状态、执行机动、生成机动事实并
保存机动后状态、使用机动后状态尝试观测、最后生成常规输出采样。因此同刻观测始终是
post-maneuver observation，不提供机动前观测开关。

计划中的 Engine `prepare()` 解析该请求并生成不可变的
`SimulationExecutionManifest`。Platform 后续若保留 `RunManifest`，只引用或嵌入该
Manifest 哈希，再增加 Mission、Experiment、算法和评价 provenance；可变状态进入
`RunRecord`/`RunAttempt`，终态时间、状态、错误和输出哈希进入 `RunOutcome`。

## 10. 交互式仿真 API

以下 Engine API 为后续计划，当前只存在其使用的 Core 请求和 Manifest 数据契约：

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

Ideal/Reported 结果类型和授权隔离属于后续观测结果批次。

### Engine（计划验收）

- 使用假后端验证 prepare/run/session/restore 生命周期；
- 固定种子和稳定派生随机流；
- 事件调度、暂停、单步、推进到指定时刻和取消；
- 漏测、质量拒绝、丢包、延迟、乱序和重复；
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

### 安装隔离（Core 当前适用，其余包计划验收）

- Core 可独立导入；
- Engine 在无 JDK 时可导入和运行假后端测试；
- Orekit 包安装后通过参考传播；
- `pip install sycasphere-sim` 开箱可运行；
- Platform 只通过公共 Engine API 编排仿真。

## 14. 明确延后

首版不实现显式 `NonDetectionReport`、完整有限推力执行、向后时间旅行、恶意插件安全沙箱、分布式任务系统和 GPU 大目录传播。这些能力不得提前污染首版接口之外的实现。
