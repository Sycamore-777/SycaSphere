# SycaSphere 仿真定义与执行输入设计规范

| 项目 | 内容 |
| --- | --- |
| 状态 | 已确认设计 |
| 日期 | 2026-07-26 |
| 适用范围 | `sycasphere-core` 的物理场景、机动、观测计划、执行请求与执行清单契约 |
| 关联基线 | `core-data-model-v0.2.md`、`algorithm-integration-v0.2.md`、`2026-07-20-sycasphere-runtime-and-simulation-engine-design.md` |

## 1. 文档目的与效力

本文细化 SycaSphere 首个可开发版本中的 `SimulationDefinition`、
`SimulationRunRequest` 和 `SimulationExecutionManifest`，并记录已经确认的字段、
不变量、包边界、准备流程、错误边界和验收条件。

本文是一个可独立实施和验收的设计批次。它只建立“物理场景能够被完整描述，
并能冻结为确定性执行输入”的契约，不实现轨道传播、交互会话、观测结果、
平台运行生命周期或持久化基础设施。

若本文与关联基线冲突，本批次实现必须同步修订关联文档，不能保留两套相互矛盾的
当前接口。本文明确细化以下早期描述：

1. Engine 的 `SimulationRunRequest` 携带完整 `SimulationDefinition`，不携带数据库引用。
2. 首版 `command_timeline` 只接受机动命令；姿态、云台、传感器模式和可用性命令延后。
3. 测量模型和误差模型只在 `SensorDefinition` 中保存；运行请求通过观测计划选择，不在
   顶层复制。数据链路模型仍是运行级配置。
4. `SimulationExecutionManifest` 使用紧凑计划，不展开全部周期事件。

## 2. 已确认的总体方案

采用“Core 强类型契约 + Engine 两阶段准备”：

```text
Platform / CLI / Python 用户
            │
            │ 构造自包含请求
            ▼
SimulationRunRequest              Core 定义
            │
            │ Engine.prepare()
            ▼
SimulationExecutionManifest       Core 定义、Engine 生成
            │
            │ 后续批处理或交互执行
            ▼
Simulation Engine                 后续批次实现
            │
            ▼
科学后端，例如 Orekit            后续批次实现
```

### 2.1 包职责

- `sycasphere-core` 定义不可变、可序列化、后端中立的数据契约。
- `sycasphere-engine` 负责解析模型实现、检查插件能力、转换和比较科学时刻、
  验证外部数据、派生随机流并生成执行清单。
- `sycasphere-orekit` 后续负责实际传播、权威坐标转换和 Orekit 对象适配。
- `sycasphere-platform` 可以接受数据库修订引用，但必须先解析为完整
  `SimulationRunRequest`，再调用 Engine。
- Core 和 Engine 均不得直接依赖 SQLite、Platform 或项目数据目录。
- Core 与 Engine 的导入和假后端测试不得要求 JDK、JPype 或 Orekit。

### 2.2 两层校验

Core 负责不需要科学后端即可判定的结构与领域不变量：

- 必填字段、严格类型、有限数值和 SI 单位；
- 集合非空、稳定 ID 和 ID 唯一性；
- 实体、传感器、模型、计划和命令的本地引用；
- 判别联合的合法类型；
- 数组维度、局部帧 owner 和参考时刻；
- 首版同步状态约束；
- 深度不可变和确定性序列化。

Engine `prepare()` 负责需要运行环境或科学时间服务才能判定的执行不变量：

- UTC、TAI 和 TT 之间的先后关系；
- 请求时间范围、计划和命令的科学时序；
- 插件是否安装、接口是否兼容、能力是否满足；
- 插件配置是否符合其 JSON Schema；
- 外部数据是否存在且哈希一致；
- 有限推力等后端能力；
- 机动、观测和采样计划是否冲突；
- 规范化时间线、随机流和内容哈希。

## 3. 物理世界契约

### 3.1 CentralBody

首版中心天体枚举只提供：

```text
EARTH
```

公共 `J2000` 继续表示 Earth-centered 惯性帧。月球、太阳等可以通过环境模型作为
第三体、光照源或遮挡体出现，不因此成为本次仿真的中心天体。未来增加其他中心天体时，
扩展 `CentralBody`，不改变现有 `EARTH` 数据形状。

### 3.2 ExternalDataRef

外部科学数据使用精确、位置无关的引用：

```text
ExternalDataRef
├── data_id
├── version
└── sha256
```

约束：

- `data_id` 和 `version` 是去除首尾空白后的非空严格字符串；
- `sha256` 是 64 位小写十六进制字符串；
- 不保存本地绝对路径、Java 对象或打开的文件句柄；
- Engine 通过数据解析端口按引用查找本地或远程副本并重新计算哈希；
- EOP、闰秒、重力场和星历等真正使用的数据必须进入执行清单。

### 3.3 EnvironmentDefinition

```text
EnvironmentDefinition
├── id / name / revision / schema_version
├── tags / metadata
├── central_body
├── model_refs[]
└── external_data_refs[]
```

`EnvironmentDefinition` 使用 Core 现有的不可变定义基类。`model_refs` 保存重力、
星历、大气、辐射和其他共享环境模型的后端中立配置；Core 不包含 Orekit 类名。

约束：

- 同一环境定义中的 `model_id` 唯一；
- 同一环境定义中的 `data_id` 唯一；
- Core 允许 `model_refs` 和 `external_data_refs` 为空，以支持最小假后端；
- 具体科学后端可以在 `prepare()` 阶段要求某些模型或数据。

### 3.4 SimulationDefinition

```text
SimulationDefinition
├── id / name / revision / schema_version
├── tags / metadata
├── synchronization_epoch
├── environment
├── entities[]
└── planned_maneuvers[]
```

它只描述可复用的物理场景，不包含运行起止时间、输出采样、观测计划、算法、
执行后端或保留策略。

约束：

- `entities` 至少包含一个空间对象；
- 实体 ID 在整个仿真定义中全局唯一；
- 所有嵌套传感器 ID 在整个仿真定义中全局唯一；
- GroundStation 不维护轨道状态；
- 首版所有空间对象的 `initial_state.epoch` 必须完全等于
  `synchronization_epoch`；
- 修改实体、环境、外部数据或预设机动必须创建新修订。

`synchronization_epoch` 是面向未来异步初始状态的稳定升级点。首版使用严格相等约束；
以后升级时保留字段和现有 JSON，只允许每个对象的初始状态时刻不晚于同步时刻，并由
Engine 分别预推进到同步时刻。旧数据无需迁移。

## 4. 机动契约

### 4.1 概念分离

```text
ManeuverCapability       航天器具备什么能力
PlannedTruthManeuver     场景定义中预设要发生什么
ManeuverCommand          某次运行要求执行什么
TruthManeuver            后端最终实际执行了什么
ManeuverHypothesis       算法认为发生了什么
```

本批次定义前三项。`TruthManeuver` 属于执行结果批次，`ManeuverHypothesis` 属于算法
结果契约；两者不得与命令或场景计划复用同一模型。

### 4.2 ManeuverCapability

`SpacecraftDefinition` 增加：

```text
maneuver_capability: ManeuverCapability | None
```

```text
ManeuverCapability
├── supported_types       IMPULSIVE / FINITE_BURN
└── propulsion_model      ModelRef
```

约束：

- `supported_types` 非空、无重复；
- `propulsion_model` 保存有限、深度不可变配置；
- 推力、比冲、燃料、方向和持续时间限制由推进模型的配置模式表达；
- Engine 通过推进模型插件能力和 JSON Schema 验证具体命令；
- `OtherSpaceObjectDefinition` 和 `GroundStationDefinition` 不提供机动能力。

这种边界不会把单台恒推力发动机写死为所有航天器的唯一结构，并允许以后支持
多推进器、分段推力和更复杂燃料模型。

### 4.3 机动载荷

```text
ImpulsiveManeuverSpec
├── maneuver_type: IMPULSIVE
├── delta_v_mps: (x, y, z)
└── frame
```

```text
FiniteBurnManeuverSpec
├── maneuver_type: FINITE_BURN
├── duration_s
├── thrust_n: (x, y, z)
└── frame
```

首个有限推力模式表示在声明帧中的恒定推力矢量。以后增加分段或时变推力时，
增加新的判别载荷，不改变现有两种载荷。

共同约束：

- 向量恰好三个严格、有限的内置浮点数；
- Δv 和推力矢量不得为零向量；
- `duration_s` 是严格、有限的正浮点数；
- 帧表示必须为 `CARTESIAN`；
- LVLH、VVLH 或 BODY 的 `owner_id` 必须等于被机动航天器 ID；
- 局部帧 `reference_epoch` 必须等于机动开始时刻；
- SENSOR 帧不用于航天器机动命令；
- 航天器必须声明匹配的 `ManeuverCapability`。

### 4.4 预设机动和运行命令

```text
PlannedTruthManeuver
├── maneuver_id
├── spacecraft_id
├── epoch
└── maneuver
```

```text
ManeuverCommand
├── command_id
├── spacecraft_id
├── epoch
└── maneuver
```

- `PlannedTruthManeuver` 属于可复用场景；
- `ManeuverCommand` 属于某次运行的命令覆盖；
- 两者只能引用 `SpacecraftDefinition`；
- 预设机动不得早于同步时刻；
- 运行开始前的预设机动参与预推进但不生成正式采样；
- `prepare()` 合并两者并要求合并后的稳定 ID 唯一；
- 同一航天器、同一时刻的多个脉冲命令视为冲突；
- 首版同一航天器的有限推力时间段不得互相重叠，脉冲也不得落在有限推力闭区间内；
- 不同航天器可以在同一时刻分别机动；
- 首版 Engine 完整执行脉冲机动；
- 有限推力模式稳定发布，但后端未声明能力时必须在 `prepare()` 阶段拒绝。

以后交互会话追加机动时复用 `ManeuverCommand`，由
`RuntimeCommandJournal` 记录追加、取消和哈希链，不创建第二套机动格式。

## 5. SimulationRunRequest

```text
SimulationRunRequest
├── schema_version
├── simulation_definition
├── time_range
├── output_sampling
├── observation_schedules[]
├── command_timeline[]
├── backend
├── link_models[]
├── random_seed
└── output_requirements
```

它是独立 Engine 的完整科学输入，不包含数据库修订引用、运行状态、保留策略、
墙上时间、输出路径或 UI 状态。Platform 可以另有保存用户意图的 `RunRequest`，
但调用 Engine 前必须完成定义解析。

### 5.1 SimulationTimeRange

```text
SimulationTimeRange
├── start
└── end
```

- 科学语义是闭区间 `[start, end]`；
- 必须满足 `synchronization_epoch <= start < end`；
- 不同时间尺度的比较由 Engine 时间服务在 `prepare()` 中完成；
- 预推进区间只执行动力学和预设机动，不生成正式采样或观测。

### 5.2 OutputSampling

```text
OutputSampling
└── rules[]
    ├── product
    └── interval_s
```

首版可定期采样的产品为：

- `TRUTH_STATE`；
- `ATTITUDE_STATE`；
- `DERIVED_GEOMETRY`。

约束：

- 一个产品最多一条规则；
- `interval_s` 是严格、有限的正浮点数；
- 启用的定期时间序列必须同时存在对应采样规则；
- 所有定期序列强制输出开始和结束时刻；
- 周期不能整除总时长时，最后额外输出结束时刻；
- 输出采样不等于数值积分步长，也不改变积分器精度；
- 观测、机动和诊断事件不是固定采样产品。

例如 `[0, 10]` 秒、间隔 3 秒的输出时刻为 `0, 3, 6, 9, 10`。

### 5.3 ObservationSchedule

首版使用判别联合：

```text
ObservationSchedule
├── PeriodicObservationSchedule
└── ExplicitObservationSchedule
```

共同字段：

```text
schedule_id
sensor_id
target_id
measurement_model_id
error_profile_id | None
link_model_id | None
```

周期计划额外包含 `start_epoch`、`end_epoch` 和 `cadence_s`；显式计划包含非空
`epochs[]`。

Core 结构约束：

- `schedule_id` 在请求中唯一；
- `sensor_id` 指向完整仿真定义中的传感器；
- `target_id` 指向 Spacecraft 或 OtherSpaceObject；
- `measurement_model_id` 来自该传感器的 `measurement_models`；
- `error_profile_id` 来自该传感器的 `error_profiles`；
- `link_model_id` 来自请求的 `link_models`；
- `cadence_s` 是严格、有限的正浮点数；
- 显式时刻不包含完全相同的 `Epoch`。

Engine 科学时序约束：

- 周期起止时刻和所有显式时刻位于正式运行闭区间；
- 周期开始严格早于结束；
- 显式时刻按输入顺序严格递增；
- 混合时间尺度通过记录版本的时间服务比较；
- 转换后相同的绝对时刻视为重复并拒绝。

计划只表示“尝试观测”。运行时仍需检查传感器可用性、指向、视场、遮挡和光照。
首版不提供 `ACCESS_DRIVEN` 计划；以后以新的判别类型增加。

### 5.4 测量、误差与链路模型

测量模型和误差模型已经完整嵌入 `SensorDefinition`。观测计划只选择该传感器已有的
模型，因此请求顶层不再保存重复的 `measurement_model_refs` 和
`error_model_refs`。

链路是某次运行的交付配置，不是传感器固有能力，因此请求保留：

```text
link_models: tuple[ModelRef, ...]
```

同一请求中的链路 `model_id` 必须唯一。`SimulationExecutionManifest` 汇总本次真正
使用的测量、误差和链路模型，并记录解析后的确切插件版本。

`ModelRef.model_id` 与实现它的 `PluginManifest.ref.plugin_id` 使用同一个稳定标识。
`prepare()` 按模型所在的语义槽检查所需 `PluginKind`，并要求已安装实现的接口版本
满足 `ModelRef.interface_version`。`ModelRef` 本身不固定实现版本；最终选中的确切
`PluginRef` 只写入 `SimulationExecutionManifest`。

通道一致性：

- 只要求 Ideal 时，不强制配置误差或链路；
- 要求 Reported 时，每个相关计划必须选择有效误差配置；
- 需要链路模拟时选择有效链路模型；
- 未选择的误差或链路模型不得静默执行。

### 5.5 ScienceBackendBinding

```text
ScienceBackendBinding
├── ref: PluginRef
└── configuration
```

- `PluginRef` 固定精确实现版本和接口版本；
- `configuration` 是有限、深度不可变 JSON；
- 数值积分器、容差和其他后端科学配置放在此处；
- `prepare()` 验证对应 PluginManifest 的 kind 为 `SCIENCE_BACKEND`；
- 数值积分配置在一次执行中冻结。

### 5.6 随机种子

`random_seed` 是无符号 64 位整数。Engine 按以下稳定输入派生组件随机流：

```text
主种子 + 组件稳定 ID + 用途 + 接口版本
```

派生使用版本化加密哈希，不得使用 Python 的进程随机化 `hash()`。每个误差模型、
链路模型和其他随机组件获得独立随机流；派生结果进入执行清单。

首版派生算法为 `SYCASPHERE_SEED_V1`：

1. 将主种子、组件稳定 ID、用途和接口版本组成固定顺序 JSON 数组；
2. 使用 `SYCASPHERE_CANONICAL_JSON_V1` 编码；
3. 计算 SHA-256；
4. 取摘要前 8 字节，按无符号大端整数解释为组件种子。

相同输入必须产生相同 64 位组件种子；改变任何派生输入必须重新计算。

### 5.7 输出要求

`output_requirements` 是非空、去重集合，首版值为：

- `TRUTH`；
- `ATTITUDE`；
- `GEOMETRY`；
- `IDEAL_OBSERVATIONS`；
- `REPORTED_OBSERVATIONS`；
- `DELIVERY_SUMMARY`；
- `COMMAND_TRACE`；
- `DIAGNOSTICS`。

保留策略、输出目录和 artifact 生命周期不属于科学请求，后续由 Sim 或 Platform 的
RunRecord/RunStore 管理。

## 6. 同刻事件顺序

所有后端必须遵守同一事件边界：

```text
1. 将所有对象传播到时刻 t
2. 保存机动前状态
3. 执行 t 时刻命令
4. 生成机动事实并保存机动后状态
5. 使用机动后状态尝试观测
6. 输出 t 时刻的 Truth、姿态和几何采样
```

因此事件时刻表示“命令生效后的时刻”。脉冲机动的普通 Truth 采样保存机动后状态，
`TruthManeuver` 后续保存跳变前后状态。运行请求不提供可切换的“机动前观测”选项，
避免后端产生不同解释。

## 7. SimulationExecutionManifest

`Engine.prepare()` 成功后生成：

```text
SimulationExecutionManifest
├── schema_version
├── source_request
├── source_request_hash
├── simulation_definition_hash
├── resolved_plugins[]
├── resolved_external_data[]
├── derived_random_streams[]
├── random_derivation_version
├── prepared_timeline
├── event_ordering_policy
├── expected_outputs[]
├── canonicalization_version
└── content_hash
```

### 7.1 内容

- `source_request` 是完整、已通过 Core 校验的 `SimulationRunRequest`；
- `resolved_plugins` 记录后端、推进、动力学、环境、测量、误差和链路插件的确切
  实现与接口版本，以及规范化配置哈希；
- `resolved_external_data` 记录真正使用的数据 ID、版本和 SHA-256；
- `derived_random_streams` 记录组件 ID、用途和派生种子；
- `random_derivation_version` 首版固定为 `SYCASPHERE_SEED_V1`；
- `expected_outputs` 是解析并校验后的输出产品集合。

Manifest 不保存：

- 准备、开始或结束的墙上时间；
- 当前执行状态；
- 错误；
- 输出 artifact 哈希；
- 本地路径；
- 运行时追加命令。

相同请求、插件版本和外部数据必须产生字节等价的 Manifest。

### 7.2 紧凑 PreparedTimeline

Manifest 不物化全部周期事件：

- 显式机动按科学时刻和稳定 ID 规范排序；
- 显式观测时刻完成科学时序验证；
- 周期观测保留起止时刻和周期；
- 输出采样保留规则和强制结束时刻语义；
- 同刻顺序保存版本化策略 ID。

Engine 运行时按紧凑规则惰性产生事件。长时间、高频率运行不会因 Manifest 展开而
占用与事件数量线性增长的清单空间。

### 7.3 哈希与规范化

首版固定：

```text
hash_algorithm: SHA-256
canonicalization_version: SYCASPHERE_CANONICAL_JSON_V1
```

`SYCASPHERE_CANONICAL_JSON_V1` 定义为：

1. 使用 Pydantic `model_dump(mode="json")` 获得普通 JSON 值；
2. 递归拒绝非 JSON 值和非有限浮点数；
3. 递归把 `-0.0` 规范化为 `0.0`；
4. 集合字段由各模型序列化器输出稳定排序数组；
5. JSON 对象键按字符串排序；
6. 使用 UTF-8、非 ASCII 字符原样编码、无额外空白；
7. SHA-256 输出 64 位小写十六进制。

具体 Python 序列化参数为：

```text
sort_keys=True
ensure_ascii=False
allow_nan=False
separators=(",", ":")
```

哈希关系：

- `source_request_hash = SHA256(canonical(source_request))`；
- `simulation_definition_hash = SHA256(canonical(simulation_definition))`；
- `content_hash = SHA256(canonical(manifest_without_content_hash))`。

未来改变规范化算法时必须使用新的 `canonicalization_version`，不得静默改变 V1。

### 7.4 与运行时命令的关系

原始 Manifest 始终不可变。以后交互会话追加或取消未来命令时：

```text
完整复现输入
= SimulationExecutionManifest
+ RuntimeCommandJournal
```

最终 `RunOutcome` 保存 journal 终止哈希；不得回写 Manifest。

## 8. 错误边界

Core 模型构造失败保留标准 Pydantic `ValidationError`，便于 Python 用户定位字段。
Engine `prepare()` 将应用边界失败转换为现有 `ErrorDetail`。

| 情况 | ErrorCategory |
| --- | --- |
| 时间范围、引用、ID 或命令冲突 | `VALIDATION_ERROR` |
| 后端或模型插件未安装 | `PLUGIN_MISSING` |
| 版本、能力或配置模式不兼容 | `PLUGIN_INCOMPATIBLE` |
| 外部数据缺失或哈希不符 | `EXTERNAL_DATA` |
| 不支持坐标系 | `UNSUPPORTED_FRAME` |
| 不支持测量类型 | `UNSUPPORTED_MEASUREMENT` |
| 请求中的数值配置或物理限制无效 | `VALIDATION_ERROR` |
| 科学后端初始化预检失败 | `BACKEND_INITIALIZATION` |

稳定机器错误代码至少包含：

```text
simulation.time_range.before_synchronization_epoch
simulation.reference.sensor_not_found
observation.measurement_model_not_available
maneuver.conflicting_impulses
plugin.finite_burn_unsupported
external_data.hash_mismatch
```

Python、Java、Orekit 异常和回溯对象不得进入公共错误上下文。
`NUMERICAL_FAILURE` 保留给实际执行阶段的积分、优化或传播失败，不用于表示准备阶段
可以提前发现的无效输入。

## 9. 代码组织

本批次按职责拆分，避免单个大文件承载全部模型：

```text
sycasphere/core/
├── maneuvers.py
├── simulations.py
├── schedules.py
├── execution.py
├── entities.py
├── __init__.py
└── _canonical.py
```

- `maneuvers.py`：能力、载荷、计划和命令；
- `simulations.py`：中心天体、外部数据、环境和仿真定义；
- `schedules.py`：时间范围、采样和观测计划；
- `execution.py`：后端绑定、请求、解析记录和执行清单；
- `entities.py`：在现有 `SpacecraftDefinition` 上增加可选机动能力；
- `__init__.py`：发布经过审查的新公共契约；
- `_canonical.py`：私有规范 JSON 与哈希实现。

公共模型通过 `sycasphere.core` 的 `__all__` 显式导出；私有规范化工具不公开。
公共 API 与 JSON Schema 快照必须随实现同步审阅。
规范 JSON、SHA-256 和随机种子派生只需要标准库 `json` 与 `hashlib`，本批次不增加
生产依赖。

## 10. 测试设计

### 10.1 Core

必须覆盖：

- 模型冻结、输入别名隔离和确定性序列化；
- 严格内置浮点与有限值；
- 环境、实体、传感器、模型、计划和命令 ID 唯一性；
- 至少一个空间对象；
- 首版同步时刻规则，以及异步初始状态当前明确被拒绝；
- `ExternalDataRef` 精确哈希格式；
- 周期计划和显式计划；
- 采样规则、闭区间和强制始末端点契约；
- 脉冲、有限推力、非零向量、帧 owner 和参考时刻；
- 机动能力与目标实体匹配；
- 请求中所有跨对象引用；
- Ideal/Reported 输出要求与误差模型选择的一致性；
- 公共导出和 JSON Schema 快照。

### 10.2 Engine 准备契约

后续 Engine 批次使用假插件注册表、假时间服务和假外部数据解析器验证：

- 相同输入产生字节等价 Manifest 和相同哈希；
- 墙上时间不影响 Manifest；
- 插件版本、数据哈希、主种子或科学配置变化会改变哈希；
- `-0.0` 与 `0.0` 具有相同规范哈希；
- 周期计划保持紧凑，不展开全部事件；
- 派生随机流稳定且组件间独立；
- 同刻事件顺序固定；
- 不同时间尺度经指定时间数据正确排序；
- 不支持有限推力时在 `prepare()` 阶段失败；
- 所有应用边界失败映射为稳定 `ErrorDetail`。

### 10.3 安装与构建隔离

- Core 可独立导入；
- Core wheel 不包含 Engine、Orekit、Platform 或测试源码；
- 无 JDK、JPype 和 Orekit 时 Core 全套测试通过；
- sdist 与 wheel 离线构建通过；
- 隔离 Python 3.12 环境安装 wheel 后公共导入和模式生成通过。

## 11. 文档同步

实现本批次时必须同步：

- `docs/architecture/core-data-model-v0.2.md`；
- `docs/architecture/algorithm-integration-v0.2.md` 的相关引用；
- `docs/superpowers/specs/2026-07-20-sycasphere-runtime-and-simulation-engine-design.md`；
- 根 README 与 Core README；
- 公共模式快照。

开发阶段章节中表示计划交付的“完成”统一改为“本阶段应完成”或明确状态清单，
避免把未来阶段误写成已经实现。

## 12. 明确不在本批次实现

- 轨道传播和 Orekit 适配；
- `SimulationSession` 的暂停、步进、恢复和执行节奏；
- 运行时命令追加、取消与 `RuntimeCommandJournal`；
- `TruthState`、`TruthManeuver` 的执行结果；
- `IdealObservation`、`ReportedObservation`、交付和丢包结果；
- `RunRecord`、`RunAttempt`、`RunOutcome` 和 `ResultBundle`；
- SQLite、Parquet、ArtifactStore 和保留策略；
- 姿态、云台、传感器模式和可用性命令；
- `ACCESS_DRIVEN` 观测计划；
- 完整有限推力执行；
- 异步对象初始状态。

这些能力按已经确认的依赖顺序进入后续独立设计与实施批次。

## 13. 完成标准

本批次只有在以下条件全部满足时完成：

1. 本设计规范和详细实施计划已提交。
2. 实现与三份权威架构文档一致，冲突已主动修订。
3. 所有新公开契约具有正向、反向、边界、不可变和序列化测试。
4. Ruff format、Ruff lint、mypy 和 pytest 全部通过。
5. sdist/wheel 构建与隔离安装验证通过。
6. Core 在无 JDK、Orekit 和 JPype 时可独立导入。
7. 公共 API 与 JSON Schema 快照已经审阅。
8. 最终 diff 已检查时间、帧、单位、真值访问、哈希和可变性错误。
9. 最终代码审查没有未解决的 Critical、Important 或 Minor 问题。
10. 未把 Observation、Engine session 或 Platform 运行生命周期并入本批次。
