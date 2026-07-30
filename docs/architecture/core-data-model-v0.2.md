# SycaSphere 核心数据模型设计规范

**副标题：仿真世界、任务、实验、运行与分析交互型三维工作台**

| 项目 | 内容 |
| --- | --- |
| 项目名称 | SycaSphere |
| 文档版本 | v0.2 |
| 状态 | 开发基线 |
| 日期 | 2026-07-17 |
| 作者 | Sycamore |
| 适用范围 | SycaSphere 首个可开发版本 |

## 文档约定

本文使用以下规范性词语：

- **必须**：实现不可省略；不满足即视为违反当前设计基线。
- **应当**：原则上实现；如需偏离，必须在代码或设计记录中说明原因。
- **可以**：可选能力，不影响当前基线验收。

本文是 Codex 和人工开发者实现 SycaSphere 领域模型、存储边界、Orekit 适配层、观测生成以及三维工作台数据投影时的主要依据。若实现发现文档存在矛盾，不得自行选择其中一项并静默编码，应先修订设计文档或记录明确的架构决策。

---

## 1. 目标与当前边界

SycaSphere 当前定位为：

> **面向空间态势感知算法的交互式三维仿真与验证平台。**

当前版本面向 1 个至数十个空间对象，重点支持：

- 高保真轨道真值生成；
- 地基和天基传感器；
- 无误差观测与有误差观测双通道；
- 精密定轨、机动检测和联合估计算法验证；
- 外部算法接入；
- 真值、观测、估计、残差、协方差和机动结果的分析交互型三维展示；
- 可重复、可追溯的实验运行。

当前版本明确不实现：

- 万级空间目标目录；
- 分布式任务集群；
- Redis、Kafka 等外部消息基础设施；
- 完整多用户权限和安全域；
- 强化学习环境；
- AI 辅助设计师；
- 运行级业务目录、交会告警或作战指挥系统；
- 自研三维渲染引擎。

这些能力可以在核心模型稳定后扩展，但不得提前污染当前领域边界。

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

上列 Core 类型只定义不可变、可序列化、后端中立的领域契约。Engine v0.1 已能通过
显式注册的科学后端准备并同步执行批量 Truth、姿态和 J2000 脉冲机动；它尚未生成
Observation 或提供交互式 Session。Orekit 科学实现，以及 Platform 的任务、实验、
运行生命周期和持久化仍未实现。不得把下文目标架构理解为已全部交付。

---

## 2. 总体分层

SycaSphere 必须把物理仿真、任务语义、实验配置和运行产物分开建模。

```mermaid
flowchart TB
    P[Project] --> S[SimulationDefinition\n物理世界]
    P --> M[MissionDefinition\n任务与角色]
    P --> E[ExperimentDefinition\n算法与试验配置]
    E --> S
    E --> M
    E --> Q[Platform RunRequest\n提交的运行意图，计划]
    Q --> SR[SimulationRunRequest\n完整 Engine 科学输入]
    SR --> R[SimulationExecutionManifest\n不可变 Engine 输入 provenance]
    R --> PM[Platform RunManifest\n可选的上层 provenance，计划]
    PM --> RR[RunRecord / RunAttempt\n可变操作状态，计划]
    RR --> O[RunOutcome\n一次性终态结果]
    O --> B[ResultBundle\n真值、观测、估计、指标和日志]
    B --> W[AnalysisWorkspaceState\n三维与图表交互状态]
```

### 2.1 Project

`Project` 是用户工作空间的逻辑容器，用于组织仿真定义、任务定义、算法注册、实验和运行记录。它不承载轨道状态或任务执行语义。

### 2.2 SimulationDefinition

`SimulationDefinition` 只描述**物理世界是什么**：

- 环境和外部数据；
- 空间对象；
- 地面站；
- 传感器及安装关系；
- 初始状态和姿态；
- 动力学模型；
- 预设真实机动和其他基线真值事件。

它不得包含“目标”“主传感器”“被跟踪对象”等任务角色。Engine 接收的
`SimulationRunRequest` 必须嵌入完整 `SimulationDefinition`，不得使用数据库或修订
引用替代。一次执行的确切时间范围、输出采样、观测计划和命令时间线属于
`SimulationRunRequest`，不得回写到可复用的 `SimulationDefinition`。

首版要求所有空间对象的 `initial_state.epoch` 与
`SimulationDefinition.synchronization_epoch` 完全相等。未来可兼容升级为允许每个
对象的初始时刻不晚于同步时刻，再由 Engine 分别预推进到同步时刻；该升级保留现有
字段和已满足严格规则的 JSON，不改变首版数据含义。

### 2.3 MissionDefinition

`MissionDefinition` 只描述**在本次任务中要做什么**：

- 任务目标；
- 任务步骤；
- 对象和传感器的角色；
- 观测计划；
- 时间窗口；
- 资源分配；
- 成功条件和评价重点。

同一个 `SimulationDefinition` 可以被多个不同任务复用。

### 2.4 ExperimentDefinition

`ExperimentDefinition` 描述**如何验证算法**：

- 使用哪一个仿真修订版；
- 使用哪一个任务修订版；
- 接入哪些算法；
- 使用无误差还是有误差观测；
- 噪声由平台还是算法负责；
- 随机种子；
- 评价指标；
- 输出采样；
- 可视化配置。

### 2.5 运行对象与 ResultBundle

Core 已实现的 `SimulationRunRequest` 保存独立 Engine 的完整科学输入；Engine v0.1
的 `prepare()` 解析它并生成 `SimulationExecutionManifest`。该 Manifest 是只描述解析后
科学输入的不可变 provenance，记录精确配置、插件与数据版本、输入校验值和预期输出，
不是运行状态对象。

Platform 后续若保留自己的 `RunRequest`/`RunManifest` 概念，必须使用
`Platform RunManifest` 等清晰限定名称，并引用或嵌入
`SimulationExecutionManifest` 的哈希，再增加 Mission、Experiment、算法和评价输入
provenance；不得与 Engine Manifest 混用。可变运行状态和重试索引只由未来
`RunRecord` 和 `RunAttempt` 维护；开始/结束时间、最终状态、错误、运行时命令日志哈希
和输出哈希只由终态一次性生成的 `RunOutcome` 保存。`ResultBundle` 保存经过验证的
科学与诊断产物。完成的运行不得原地修改。

### 2.6 AnalysisWorkspaceState

`AnalysisWorkspaceState` 保存当前时间游标、相机、图层、对象选择、算法对比和面板布局。它可以修改，但不得修改已完成运行的科学结果。

---

## 3. Python 数值表示策略

### 3.1 不定义重量级 Vector3 和 StateVector6

SycaSphere 不建立带大量方法的 `Vector3`、`StateVector6` 领域类。

原因是：

- Python 和 NumPy 已经提供成熟的向量运算；
- 重复封装会增加转换和维护成本；
- 单独的六维向量不能表达时刻、坐标系和业务语义；
- API、JSON、Parquet 和跨语言接口最终仍需转换为基础数组。

### 3.2 三层表示

| 层 | 表示方式 | 约束 |
| --- | --- | --- |
| JSON/YAML/API 边界 | `list[float]` 或嵌套 `list` | 使用模式校验长度、数值类型和有限性。 |
| Python 领域对象 | 冻结边界模型中的定长元组 | 例如 `CartesianState.position_m`，不单独包装 Vector3；序列化时仍输出 JSON 数组。 |
| 数值计算内部 | `numpy.ndarray` | 三维向量 shape 为 `(3,)`，六维数组 shape 为 `(6,)`。 |

### 3.3 数组校验规则

三维数值列表必须：

- 长度严格为 3；
- 元素必须是严格、有限的浮点值，不接受字符串等隐式数值转换；
- 默认不得包含 `NaN` 或无穷大；
- 不得用 `[0, 0, 0]` 表示“缺失”；缺失使用 `null`；
- 进入数值核心时转换为 `numpy.float64`；
- 跨层传递时不得依赖可变列表的共享引用。

六维状态数组只作为计算或算法交换的派生视图：

```python
state_vector = np.concatenate([state.position_m, state.velocity_mps])
```

公开领域模型仍然使用 `CartesianState`，而不是匿名的六维列表。

### 3.4 领域边界模型

建议使用 Pydantic v2 实现 JSON/YAML/API 边界校验；数值核心不依赖 Pydantic 对象执行矩阵运算。

```python
class CartesianState(BaseModel):
    epoch: Epoch
    frame: FrameRef
    position_m: tuple[float, float, float]
    velocity_mps: tuple[float, float, float]
```

字段名直接包含 SI 单位，避免每个向量对象重复携带单位对象。

---

## 4. 时间、标识与版本

### 4.1 标识

每个核心对象必须有稳定的字符串 ID。建议使用 UUID，但 ID 的实现形式不得泄漏为业务语义。

- `id`：不可变主键；
- `name`：可修改显示名称；
- `revision`：定义对象的修订号；
- `schema_version`：数据模式版本；
- `tags`：用户检索标签，不作为逻辑判断依据。

### 4.2 时间

`Epoch` 必须显式声明时间尺度。

```yaml
epoch:
  value: "2026-07-17T00:00:00.000000Z"
  time_scale: UTC
```

当前至少支持：

- UTC；
- TAI；
- TT。

在线交付必须区分：

- `measurement_epoch`：物理观测时刻；
- `delivery_epoch`：算法获得成功交付 payload 的时刻。

首版 `StreamingObservationEnvelope` 不包含 `arrival_time`、`sequence_number` 或其他
transport lifecycle 字段。未来若增加 transport 包装，不得改变 Core
`measurement_epoch`/`delivery_epoch` 的科学语义。

Python `datetime` 不能单独承担全部时间尺度语义。Orekit `AbsoluteDate` 只能存在于 Orekit 适配层，不得跨领域或算法接口传递。

### 4.3 单位

SycaSphere 内部和标准结果统一采用 SI：

| 量 | 单位 |
| --- | --- |
| 长度 | m |
| 速度 | m/s |
| 加速度 | m/s² |
| 角度 | rad |
| 角速度 | rad/s |
| 角加速度 | rad/s² |
| 质量 | kg |
| 时间间隔 | s |

用户界面可以显示 km、deg 等常用单位，但必须在显示层转换。

---

## 5. 坐标系规范

SycaSphere 对外公开的坐标系集合为：

- `J2000`；
- `EARTH_FIXED`；
- `LVLH`；
- `VVLH`；
- `BODY`；
- `SENSOR`。

不得在公共 API、配置或结果中使用模糊的 `ECI`、`ECEF` 字符串。

### 5.1 FrameRef

```yaml
frame:
  kind: LVLH
  owner_id: spacecraft-001
  convention: SYCASPHERE_LVLH_1
  reference_epoch:
    value: "2026-07-17T00:00:00Z"
    time_scale: UTC
```

不同坐标系需要不同的附加字段：

| kind | 必需附加字段 |
| --- | --- |
| J2000 | 无；Earth-centered 语义由公共名称隐含。 |
| EARTH_FIXED | `earth_fixed` 子对象内的 `itrf_realization`、`iers_conventions`、`eop_data_id`，以及 `representation: CARTESIAN` 或 `GEODETIC`；GEODETIC 还需 `ellipsoid: WGS84`。 |
| LVLH | `owner_id`、`convention`、`reference_epoch`。 |
| VVLH | `owner_id`、`convention`、`reference_epoch`。 |
| BODY | `owner_id`、`convention`、`reference_epoch`。 |
| SENSOR | `owner_id`（sensor_id）、`convention`、`reference_epoch`。 |

### 5.2 J2000

SycaSphere 的默认地心惯性坐标系名称统一为 `J2000`。

- 公共模型、UI、文件、API 和评价结果只使用 `J2000`；
- Orekit 适配器内部将 `J2000` 唯一映射为 Orekit `EME2000`；
- 该后端实现名称不得泄漏到公共模型；
- `J2000` 的 Earth-centered 语义由公共名称隐含，不重复保存 `center` 字段。

### 5.3 LVLH

SycaSphere 采用 STK 风格的右手 LVLH 约定：

\[
\hat{X}=\frac{\mathbf r}{\|\mathbf r\|}
\]

\[
\hat{Z}=\frac{\mathbf r\times\mathbf v}{\|\mathbf r\times\mathbf v\|}
\]

\[
\hat{Y}=\hat{Z}\times\hat{X}
\]

含义为：

- `+X`：径向向外；
- `+Y`：局部水平、沿轨方向；
- `+Z`：轨道法向。

LVLH 必须通过 `owner_id`、`convention` 和 `reference_epoch` 绑定参考对象、轴约定和构造时刻。定轨误差中的“径向、沿轨、法向”分别对应 LVLH 的 X、Y、Z 分量。

### 5.4 VVLH

SycaSphere 采用 STK 风格的惯性速度 VVLH：

- `+Z`：地心天底方向，即 `-r̂`；
- `+X`：速度在局部水平面内的投影方向；
- `+Y = +Z × +X`，完成右手系。

```text
Z = -normalize(r)
X = normalize(v - dot(v, Z) * Z)
Y = cross(Z, X)
```

VVLH 必须通过 `owner_id`、`convention` 和 `reference_epoch` 声明参考对象、包含速度参考语义的轴约定和构造时刻；首版不增加独立 `velocity_reference` 字段。

### 5.5 EARTH_FIXED 与 WGS84

`EARTH_FIXED` 是公共地固帧，必须显式声明 ITRF 实现、IERS 约定、EOP 数据版本和坐标表示。`WGS84` 只表示参考椭球，不是公共帧名：

```yaml
frame:
  kind: EARTH_FIXED
  earth_fixed:
    itrf_realization: ITRF2020
    iers_conventions: IERS_2010
    eop_data_id: iers-bulletin-a:2026-07-20
  representation: GEODETIC
  ellipsoid: WGS84
```

或：

```yaml
frame:
  kind: EARTH_FIXED
  earth_fixed:
    itrf_realization: ITRF2020
    iers_conventions: IERS_2010
    eop_data_id: iers-bulletin-a:2026-07-20
  representation: CARTESIAN
```

- `GEODETIC`：经度、纬度、椭球高；
- `CARTESIAN`：地心地固 X、Y、Z。

地面站的定义使用 `EARTH_FIXED`/`GEODETIC` 表示并声明 `ellipsoid: WGS84`。用于三维渲染时，后端生成 `EARTH_FIXED`/`CARTESIAN` 或 WGS84 经纬高数据。

### 5.6 BODY

`BODY` 坐标系依附于具体实体，由实体姿态定义。平台不假设所有航天器采用同一机体系轴向。

```yaml
frame:
  kind: BODY
  owner_id: spacecraft-001
  convention: attitude-law-001-rh
  reference_epoch:
    value: "2026-07-17T00:00:00Z"
    time_scale: UTC
```

地面站也具有本体系；模板可以提供 NED 等约定，但数据中必须显式记录具体轴定义。

### 5.7 SENSOR

`SENSOR` 坐标系依附于具体传感器，由安装变换和指向模型共同确定。

```text
J2000 → Platform BODY → Mount Transform → Gimbal/Pointing → SENSOR
```

传感器定义必须显式声明：

- 视轴方向；
- 横轴和纵轴；
- 安装位置偏移；
- 安装姿态；
- 转台或扫描模型；
- 像面约定（如适用）。

不得默认所有传感器都以 `+Z` 为视轴，除非所选模板明确这样规定。

### 5.8 坐标转换责任

- 科学计算坐标转换由后端完成；
- 三维前端不得自行实现简化的 `J2000`/`EARTH_FIXED` 帧转换或 WGS84 大地坐标转换；
- 所有转换必须保留源帧、目标帧、时刻和数据版本；
- 6×6 状态协方差在时变坐标系之间转换时，必须使用完整状态变换雅可比，不能只对位置和速度分别应用同一个 3×3 旋转矩阵。

---

## 6. 仿真实体与传感器层级

### 6.1 实体层级

```mermaid
classDiagram
    class EntityDefinition {
      +id
      +name
      +revision
      +metadata
    }
    class SpaceObjectDefinition {
      +initial_state
      +dynamics
      +physical_properties
      +attitude
    }
    class SpacecraftDefinition {
      +sensors[]
    }
    class OtherSpaceObjectDefinition
    class GroundStationDefinition {
      +wgs84_location
      +body_axes
      +sensors[]
    }
    class SensorDefinition {
      +mount_transform
      +pointing_model
      +field_of_view
      +measurement_models
      +error_profiles
    }
    EntityDefinition <|-- SpaceObjectDefinition
    SpaceObjectDefinition <|-- SpacecraftDefinition
    SpaceObjectDefinition <|-- OtherSpaceObjectDefinition
    EntityDefinition <|-- GroundStationDefinition
    SpacecraftDefinition *-- SensorDefinition
    GroundStationDefinition *-- SensorDefinition
```

### 6.2 EntityDefinition

实体只描述自身身份和物理能力，不描述本次任务角色。

| 字段 | 说明 |
| --- | --- |
| `id` | 稳定主键。 |
| `name` | 显示名称。 |
| `entity_type` | SPACECRAFT、OTHER_SPACE_OBJECT、GROUND_STATION。 |
| `metadata` | 非控制性的用户元数据。 |
| `capabilities` | 物理能力，例如可机动、可挂载传感器。 |
| `revision` | 实体定义修订版。 |

### 6.3 SpaceObjectDefinition

空间对象定义包含：

- 初始 `CartesianState` 或可转换的轨道元素；
- 传播模型引用；
- 质量、面积、阻力系数、光压系数等物理参数；
- 姿态模型；
- 可选机动能力；
- 可选传感器子组件。

空间碎片、箭体等不能搭载传感器的对象使用 `OtherSpaceObjectDefinition`。

### 6.4 GroundStationDefinition

地面站包含：

- `EARTH_FIXED`/`GEODETIC` 地理位置，并声明 WGS84 参考椭球；
- 站体坐标系定义；
- 可用时间；
- 可选环境属性；
- 传感器子组件。

### 6.5 SensorDefinition

传感器必须依附于 `SpacecraftDefinition` 或 `GroundStationDefinition`，不作为独立自由飞行实体。

序列化时建议嵌套保存：

```yaml
spacecraft:
  id: observer-spacecraft-001
  sensors:
    - id: optical-sensor-001
      sensor_type: OPTICAL
      mount_transform: mount-optical-001
```

数据库中可以使用 `parent_entity_id` 保存父子关系，但领域语义仍是组合关系。

传感器位置和姿态必须由父平台推导：

\[
\mathbf r_{sensor}^{J2000}=\mathbf r_{platform}^{J2000}
+\mathbf C_{BODY\rightarrow J2000}\,\mathbf r_{mount}^{BODY}
\]

传感器不得维护一套与父平台无关的轨道状态。

### 6.6 SensorDefinition 组成

| 组件 | 作用 |
| --- | --- |
| `mount_transform` | BODY 到传感器安装基准的固定位置和姿态。 |
| `pointing_model` | 固定、目标指向、扫描、转台或外部姿态序列。 |
| `field_of_view` | 圆锥、矩形、复杂掩膜等视场。 |
| `visibility_model` | 遮挡、地平、光照、太阳抑制角等。 |
| `measurement_models` | 可生成的理想观测类型。 |
| `error_profiles` | 可选的噪声、偏差、漏测和质量拒绝配置。 |
| `availability` | 工作时间、占用和故障窗口。 |

---

## 7. 任务模型与角色分配

### 7.1 为什么角色不放在实体上

“目标”“观测平台”“主传感器”等角色是任务上下文，不是实体固有属性。同一颗卫星在不同任务中可以承担不同角色。因此实体中禁止保存固定任务角色字段。

### 7.2 MissionDefinition

```yaml
mission:
  id: geo-maneuver-detection
  revision: 1
  objectives:
    - MANEUVER_DETECTION
    - PRECISE_ORBIT_DETERMINATION
  tasks:
    - id: collect-optical-observations
      task_type: OBSERVATION_COLLECTION
    - id: estimate-post-maneuver-orbit
      task_type: ORBIT_ESTIMATION
  role_assignments:
    - subject_ref: target-spacecraft-001
      role: sycasphere.mission/TRACKING_TARGET
    - subject_ref: optical-sensor-ground-001
      role: sycasphere.mission/PRIMARY_SENSOR
```

### 7.3 TaskDefinition

`TaskDefinition` 描述一个任务步骤：

- `task_type`；
- `time_window`；
- `target_refs`；
- `resource_refs`；
- `dependencies`；
- `parameters`；
- `success_criteria`。

### 7.4 RoleAssignment

```text
RoleAssignment
├── subject_ref
├── role
├── task_refs
├── valid_interval
└── parameters
```

角色可以指向：

- 空间对象；
- 地面站；
- 传感器；
- 算法绑定；
- 其他任务资源。

### 7.5 角色词汇表

当前不建设复杂的“角色管理系统”。

- 平台提供少量内置角色枚举；
- 自定义角色使用命名空间字符串；
- SQLite 可以单独保存 `role_assignments` 表；
- 以后确有需要时再增加 `RoleDefinition`，用于角色说明、颜色和约束。

实体的 `capabilities` 表示“能做什么”，任务角色表示“本次做什么”，两者不得混淆。

---

## 8. 真值状态与真实事件

### 8.1 CartesianState

```yaml
state:
  epoch:
    value: "2026-07-17T00:00:00Z"
    time_scale: UTC
  frame:
    kind: J2000
  position_m: [42164000.0, 1200.0, -800.0]
  velocity_mps: [-0.08, 3074.6, 0.12]
```

首版 `CartesianState` 只包含时刻、坐标系、位置和速度，不提供加速度兼容字段。加速度属于动力学输出或派生量；若未来需要进入公共边界，必须作为单独契约变更评审。

### 8.2 AttitudeState

Core 已实现的 `AttitudeState` 精确包含：

- `epoch`；
- `reference_frame`；
- `rotation_reference_to_body_wxyz`；
- 可选的 `angular_velocity_body_wrt_reference_rad_s`。

四元数的分量顺序固定为 `(w, x, y, z)`，旋转方向固定为 reference frame 到
BODY，并且范数必须在 `1e-9` 容差内等于 1，不得静默归一化。角速度未知时使用
`None`；零角速度必须显式使用三个 `0.0`。角加速度未进入首版公共契约。

### 8.3 TruthState

Core 已实现的 `TruthState` 是未来仿真引擎在某一时刻生成的真实状态快照，精确包含：

- `entity_id`；
- `cartesian_state`；
- 可选 `attitude_state`；
- 可选 `mass_kg`。

`epoch` 由 `cartesian_state.epoch` 提供，不重复序列化；存在姿态时，其 epoch 必须与
CartesianState 完全相等。传感器没有独立 TruthState，其状态由父平台 TruthState、
安装变换和指向模型推导。动力学参数、派生几何量、设备状态和真值事件状态若由未来
Engine 生成，使用独立结果契约，不向首版 TruthState 追加字段。

TruthState 只对仿真内核、评价器和授权调试视图可见，不能作为正式被测算法输入。

### 8.4 TruthManeuver

Core 已实现的真实机动事实和计划中的算法机动假设必须使用不同类型。

```text
TruthManeuver
├── maneuver_event_id
├── source_kind: PLANNED | COMMAND
├── source_id
├── entity_id
├── scheduled_epoch
├── executed_epoch
├── actual_delta_v_j2000_mps
├── state_before
└── state_after
```

实际 Δv 始终使用权威 J2000 分量。前后 TruthState 必须属于同一实体、使用 J2000
CartesianState 且时刻等于 `executed_epoch`；两边质量都存在时不得增加。原始
PlannedTruthManeuver 或 ManeuverCommand 继续由 Manifest/Command Journal 保存，
TruthManeuver 只通过 `source_kind + source_id` 保存谱系。执行失败不生成
TruthManeuver。

---

## 9. 观测模型与双接口

### 9.1 数据流

```mermaid
flowchart LR
    S[ObservationSchedule trigger] --> P[preallocate deterministic event_id]
    P --> G[geometry / visibility / pointing]
    T[TruthState] --> G
    G --> E[create immutable ObservationEvent once]
    E -->|GEOMETRY_REJECTED| D[ObservationDeliveryRecord\n终态事实]
    E -->|VISIBLE| M[Deterministic Measurement Model]
    T --> M
    M --> I[IdealObservation\n无误差接口]
    Q[ObservationSchedule.error_profile_id] --> C{选择唯一交付通道}
    I --> C
    C -->|None: IDEAL| L[LinkModel\ndelay / drop / FIFO]
    C -->|存在: REPORTED| X[ErrorPipeline]
    X -->|形成 Reported| R[ReportedObservation\n有误差接口]
    X -->|SENSOR_MISSED / QUALITY_REJECTED| D
    R --> L
    L -->|LINK_DROPPED| D
    L -->|DELIVERED| D
    L -->|DELIVERED payload| O[StreamingObservationEnvelope]
    O --> A[算法]
    T -.仅评价器可见.-> V[Evaluator]
    A --> V
```

几何、可见性和指向检查只判定 Event 的 `geometry_status`，不由 Deterministic
Measurement Model 产生。Engine 必须在几何检查后一次性创建不可变 Event；
`GEOMETRY_REJECTED` 直接形成终态交付事实，只有 `VISIBLE` Event 才调用确定性测量模型
形成 IdealObservation。

一次 Event 的 schedule `error_profile_id` 只选择一个交付通道：`None` 选择 Ideal，
存在时选择 Reported。所选 payload 必须经过 LinkModel 的延迟、丢包和 FIFO 处理；
只有 `DELIVERED` 创建 `StreamingObservationEnvelope` 并到达算法，其他终态只形成
`ObservationDeliveryRecord` 事实。TruthState 仍只对仿真内核、评价器和授权调试视图
可见，不进入正式算法输入。

### 9.2 ObservationEvent

Core 已实现的 `ObservationEvent` 表示一次由观测计划触发的内部科学事实，是理想观测
和报告观测的共同来源。一次 schedule occurrence、触发时刻、sensor、target 和
measurement model invocation 恰好对应一个 Event。Engine 后续必须预分配确定性
`event_id`，完成几何、可见性和指向检查后一次性构造不可变 Event。

| 字段 | 说明 |
| --- | --- |
| `event_id` | 双通道关联主键。 |
| `schedule_id` | 触发本次事件的观测计划。 |
| `measurement_epoch` | 物理观测时刻。 |
| `sensor_id` | 传感器子组件 ID。 |
| `platform_id` | 父平台 ID。 |
| `truth_target_entity_id` | 仅内部科学事实可见的真实目标实体 ID。 |
| `public_subject_ref` | 算法安全的 KNOWN_OBJECT、TRACKLET 或 UNASSOCIATED 引用。 |
| `measurement_type` | 观测类型。 |
| `geometry_status` | VISIBLE 或四种明确的几何拒绝终态。 |
| `measurement_model_ref` | 产生测量的完整确定性模型引用。 |

Event 只由 ObservationSchedule 触发，不随数值积分步、Truth 输出采样或前端渲染帧
自动产生。几何失败仍生成 Event，但不生成 IdealObservation。

### 9.3 IdealObservation：无误差接口

Core 已实现的 `IdealObservation` 是通过可见性、指向和确定性测量模型得到的算法安全
观测值，但未加入随机和系统误差。它保存独立 `observation_id`、共同 `event_id`、
测量时刻、sensor、算法安全 SubjectRef、measurement model ref 和
`ObservationMeasurement`；不得包含 Truth target、error model、uncertainty 或实际
误差字段。

无误差并不意味着忽略：

- 传感器位置和姿态；
- 视场；
- 地球或天体遮挡；
- 光照条件；
- 光行时；
- 站址运动；
- 由配置启用的确定性修正。

系统必须提供显式接口：

```text
generate_ideal_observation(event, truth_context) -> IdealObservation
```

### 9.4 ReportedObservation：有误差接口

Core 已实现的 `ReportedObservation` 表示未来 ErrorPipeline 由 Ideal 生成的算法安全
有误差观测。除共同谱系外，它保存独立 `observation_id`、error model ref 和可选
`MeasurementUncertainty`；不得包含实际噪声样本、真实偏差或 Truth 残差。

```text
apply_error_pipeline(ideal, error_profile, seed) -> ReportedObservation | None
```

误差管线可以包含：

1. 随机噪声；
2. 系统偏差；
3. 时钟偏差和抖动；
4. 量化；
5. 离群值；
6. 漏测或质量拒绝。

返回 `None` 表示误差模型没有形成可报告观测；未来 Engine 必须生成公开 Core
`ObservationDeliveryRecord` 契约的内部诊断事实，记录 `SENSOR_MISSED` 或
`QUALITY_REJECTED`。该记录不是 Observation，不发送给算法。
链路延迟和丢包只由后续 LinkModel 处理，不属于 ErrorPipeline。

### 9.5 双通道规则

- Ideal 和 Reported 必须共享 `event_id`；
- 两者拥有不同 `observation_id`，并共享 measurement epoch、sensor、SubjectRef 和
  measurement type；
- 系统可以按输出要求同时持久化两者，但一次 Event 的算法交付通道只由 schedule 的
  `error_profile_id` 选择；
- 算法端加噪时输入为 Ideal；
- 平台端加噪时输入为 Reported；
- 正式算法评测不得同时读取 Ideal、Reported 和 Truth；
- 每个 Event 恰好生成一个终态 `ObservationDeliveryRecord`，并聚合为
  `DeliverySummary`；
- 漏测、质量拒绝和链路丢包不得用零值、NaN 或伪造 Observation 表示。

### 9.6 地基与天基观测

地基和天基传感器共用同一 `ObservationEvent` 和 Observation 类型。差异来自父平台状态、姿态、可见性和误差配置，不应建立两套不兼容接口。

天基观测必须考虑：

- 观测航天器轨道和姿态；
- 传感器安装偏置；
- 地球、月球等遮挡；
- 太阳抑制角和光照；
- 目标和观察者的相对运动；
- 移动平台时钟和姿态误差。

### 9.7 标准观测类型

Core 使用统一 `ObservationMeasurement`，由测量类型固定维度、分量名、单位、Frame
和数值范围；不为每个标准类型建立独立 Observation 类。

| 类型 | 数值维度 | 默认表达坐标系 | 说明 |
| --- | ---: | --- | --- |
| `ANGLES_RA_DEC` | 2 | J2000 | 赤经、赤纬，单位 rad。 |
| `ANGLES_AZ_EL` | 2 | SENSOR 或站体局部系 | 方位、仰角，必须声明轴约定。 |
| `RANGE` | 1 | 标量 | 单程或双程必须在元数据中说明。 |
| `RANGE_RATE` | 1 | 标量 | 必须说明符号和积分时间。 |
| `LOS_UNIT_VECTOR` | 3 | J2000 或 SENSOR | 视线单位矢量。 |
| `CUSTOM` | 可变 | 显式 | 使用命名空间和独立模式。 |

标准测量拒绝未声明的 qualifier；CUSTOM 必须使用命名空间化 type 和带 schema ID、
SchemaVersion 与 SHA-256 的位置无关 schema 引用。

### 9.8 MeasurementUncertainty

Core 已实现的 `MeasurementUncertainty` 表示确定性修正后剩余误差的算法可见有效
协方差。它保存与 measurement 完全一致的 component names、units 和有限、对称、
半正定 covariance；不得保存本次实际误差样本、隐藏偏差或 Truth 残差。`None` 表示
未知不确定度，显式零 covariance 表示已知零不确定度，两者不得混用。

### 9.9 Delivery 与流式信封

`ObservationDeliveryRecord` 记录一个 Event 的
`GEOMETRY_REJECTED`、`SENSOR_MISSED`、`QUALITY_REJECTED`、`LINK_DROPPED` 或
`DELIVERED` 终态，严格校验通道、Ideal/Reported ID、payload hash、delivery epoch 和
latency 组合。`DeliverySummary` 的五类 outcome 计数之和必须等于 total events。

只有 DELIVERED 产生 `StreamingObservationEnvelope`。该信封只包含 `event_id`、
`delivery_epoch` 和被成功交付的 Ideal/Reported Observation，不包含 sequence、
attempt、duplicate 或 retransmission 字段。首版链路执行只支持延迟、丢包和 FIFO。
逐事件记录是否持久化由 `DELIVERY_RECORDS` 控制，不能影响科学流水线是否执行。

### 9.10 LOS 派生几何量

仿真内部可以保存：

- 距离；
- 距离率；
- LOS 单位矢量；
- LOS 角速度；
- LOS 角加速度。

这些量默认属于 `DerivedGeometry` 或真值诊断，不自动作为真实传感器观测提供给算法。只有测量模型明确声明时，才转换为 Observation。

---

## 10. 估计、协方差、机动和误差

### 10.1 TrackEstimate

```text
TrackEstimate
├── track_id
├── epoch
├── state
├── covariance
├── validity_interval
├── source_observation_refs
├── algorithm_ref
└── quality
```

轨迹 ID 不等于真值目标 ID。是否公开关联关系由任务和实验策略决定。

### 10.2 CovarianceMatrix

协方差必须声明：

- 矩阵数值；
- 状态分量顺序；
- 时刻；
- 坐标系；
- 参考状态；
- 每个分量的单位；
- 是否为估计协方差、预测协方差或经验协方差。

协方差必须通过对称性和数值有效性检查。严重非正定不得静默修复。

### 10.3 ManeuverHypothesis

算法输出的机动使用 `ManeuverHypothesis`：

- 估计时刻或时间窗；
- 瞬时或有限时长；
- 可选 Δv；
- Δv 坐标系；
- 置信度；
- 检测统计量；
- 证据引用；
- 算法版本。

### 10.4 残差和误差符号

平台统一规定：

- 测量残差：`observed - predicted`；
- 状态误差：`estimate - truth`。

外部算法使用其他符号时，适配器必须转换并记录来源定义。

### 10.5 定轨误差坐标系

当前必须支持：

- `J2000`：X、Y、Z 位置和速度误差；
- `LVLH`：径向、沿轨、法向误差。

可以支持：

- VVLH；
- `EARTH_FIXED`/`CARTESIAN`；
- BODY；
- SENSOR。

局部坐标误差必须绑定参考对象、参考轨迹和构造时刻。默认以 TruthState 构造 LVLH；其他基准必须在评价配置中显式选择。

---

## 11. 实验、运行和可追溯性

### 11.1 ExperimentDefinition

```yaml
experiment:
  id: geo-optical-maneuver-validation
  simulation_revision: geo-truth-world@2
  mission_revision: geo-maneuver-mission@1
  observation_policy:
    channel: REPORTED
    noise_responsibility: PLATFORM
  algorithm_bindings:
    - algorithm_id: sycasphere.baseline/batch-od
    - algorithm_id: user.example/maneuver-detector
  random_seed: 20260717
  evaluation_profile: geo-od-md-default
  visualization_profile: interactive-ssa-default
```

### 11.2 SimulationRunRequest 与 SimulationExecutionManifest

Core 已实现的 `SimulationRunRequest` 是完整、后端中立的 Engine 科学输入：

- 嵌入完整 `SimulationDefinition`；
- `time_range` 是闭区间；
- `output_sampling` 的采样周期独立于科学后端的数值积分步长和容差；
- 首版 `command_timeline` 只包含 `ManeuverCommand`；
- 首版 `observation_schedules` 只包含 `PERIODIC` 和 `EXPLICIT`；
- 测量模型和误差模型从 `SensorDefinition` 选择，不在请求顶层重复保存引用；
- 数据链路仍通过运行级 `link_models` 配置；首版执行语义只允许延迟、丢包和 FIFO；
- 主随机种子和输出要求随请求冻结。

ObservationSchedule 的 `error_profile_id` 唯一决定 IDEAL 或 REPORTED 算法交付通道。
`OutputRequirement.IDEAL_OBSERVATIONS`、`REPORTED_OBSERVATIONS`、
`DELIVERY_SUMMARY` 和 `DELIVERY_RECORDS` 只决定 artifact 持久化；它们不得选择通道或
跳过交付通道所需的测量、误差和链路科学流水线。

同一时刻的权威事件顺序为：传播到时刻、保存机动前状态、执行机动、保存机动后事实与
状态、使用机动后状态尝试观测、最后生成该时刻的常规采样。因此同刻观测是
post-maneuver observation，不提供可切换的机动前观测解释。

Engine v0.1 的 `prepare()` 成功后生成不可变
`SimulationExecutionManifest`，记录：

- 完整源请求及其哈希；
- `SimulationDefinition` 哈希；
- 解析后的精确插件实现与配置哈希；
- EOP、闰秒、重力场、星历等实际外部数据版本和哈希；
- 稳定派生的随机流；
- 紧凑的机动、观测和采样时间线；
- 版本化同刻事件顺序和预期输出；
- Manifest 内容哈希。

`SimulationExecutionManifest` 自生成起不可变，不包含准备、开始或结束墙上时间、
运行状态、错误、输出产物哈希、本地路径或运行时追加命令。相同请求、插件版本和
外部数据必须产生等价 Manifest。

Platform 后续若保留 `RunManifest`，它是独立的上层 provenance：引用
`SimulationExecutionManifest` 哈希并增加 Mission、Experiment、算法和评价输入。
Platform Manifest 同样不得承载可变状态或终态输出。

### 11.3 RunRecord 与 RunAttempt

`RunRecord` 保存可变的操作状态和保留策略；状态按照 `CREATED → VALIDATING → QUEUED → RUNNING → FINALIZING → 终态` 推进。`RunAttempt` 表示一次实际执行尝试。可重试故障必须创建新的 Attempt，并继续引用同一个 `SimulationExecutionManifest` 及可选 Platform Manifest；修改科学输入必须创建新的 Run。

### 11.4 RunOutcome 与 ResultBundle

`RunOutcome` 在运行进入终态时一次性生成，必须记录：

- `SimulationExecutionManifest` 哈希及可选 Platform Manifest 哈希；
- 最终状态；
- 开始和结束时间；
- 实际运行环境摘要；
- 输出产物哈希；
- 最终运行时命令日志哈希；
- `ResultBundle` 引用；
- 可选结构化错误。

失败和取消也必须产生 Outcome。只有经过模式与数值校验的部分产物才能以 `PARTIAL` 发布；未验证的临时文件不是科学结果。

### 11.5 不可变运行

- 已提交的 ExperimentDefinition 不得被运行过程修改；
- `SimulationExecutionManifest`、可选 Platform Manifest、RunOutcome、
  ResultBundle 和已经发布的科学产物不得原地覆盖；
- RunRecord 的状态、保留级别和 Attempt 索引可以按照状态机更新，但不得回写科学输入；
- 用户在三维工作台中修改机动、任务或算法参数时，创建新的实验修订或运行分支；
- 分析注释和视图状态可以单独修改。

---

## 12. 本地优先存储架构

### 12.1 计划方案

```mermaid
flowchart LR
    APP[SycaSphere Application] --> META[SQLite\n定义、关系、运行索引]
    APP --> STORE[Local Artifact Store\n项目文件目录]
    STORE --> CFG[YAML/JSON\n定义和清单]
    STORE --> DATA[Parquet\n真值、观测、估计、残差]
    STORE --> LOG[NDJSON/Text\n结构化日志]
    APP --> BUS[In-process Event Bus\nasyncio/进程内队列]
```

以下均为后续 Platform/Sim 存储计划，当前仓库尚未实现：

- **SQLite**：项目元数据、版本关系、算法注册、任务、实验和运行索引；
- **YAML/JSON**：可审阅的定义、清单和小型结果；
- **Parquet**：真值、观测、估计、残差、协方差和指标等时间序列；
- **本地文件目录**：报告、模型、日志、外部数据和其他 artifact；
- **进程内事件总线**：运行进度和前端推送。

计划中的本地单机运行不使用 Redis。

### 12.2 为什么首个计划不使用 Redis

当前范围是本地单机、少量并发和 1 至数十个对象。Redis 会引入额外服务、端口、部署和一致性成本，而目前没有必须由分布式缓存或消息代理解决的问题。

### 12.3 端口抽象

上层代码必须依赖接口，而不是直接依赖 SQLite 或本地路径：

```text
MetadataRepository
ArtifactStore
RuntimeEventBus
```

首个计划实现分别是 SQLite、本地文件系统和进程内事件总线。以后进入多用户或多实例
部署时，可以替换为 PostgreSQL、对象存储和 Redis/其他消息系统，而不改变领域模型。

### 12.4 计划项目数据目录

```text
project-data/
├── sycasphere.db
├── definitions/
│   ├── simulations/
│   ├── missions/
│   └── experiments/
├── assets/
│   ├── models/
│   └── external-data/
└── runs/
    └── <run-id>/
        ├── manifest.json
        ├── outcome.json
        ├── truth.parquet
        ├── ideal-observations.parquet
        ├── reported-observations.parquet
        ├── estimates.parquet
        ├── maneuvers.parquet
        ├── residuals.parquet
        ├── metrics.parquet
        └── logs.ndjson
```

---

## 13. 分析交互型三维工作台

### 13.1 技术基线

三维前端采用：

- React；
- TypeScript；
- CesiumJS；
- Apache ECharts；
- REST 用于定义、历史结果和查询；
- WebSocket 用于运行状态和时间动态更新。

### 13.2 交互能力

首个三维工作台必须支持：

- 开始、暂停、继续、停止；
- 单步推进；
- 时间跳转；
- 加速和减速；
- 仿真速度与数值积分精度分离；
- 点击空间对象和传感器；
- 相机跟随、锁定和自由浏览；
- 显示真值、估计和预测轨道；
- 显示地面站和天基观察者；
- 显示传感器视场和 LOS；
- 显示观测窗口和观测事件；
- 显示协方差椭球及放大比例；
- 显示真实机动和算法检测机动；
- 多算法图层开关和对比；
- 三维时间游标与残差、误差、协方差和检测统计图同步。

### 13.3 科学数据与渲染数据分离

```text
J2000 科学结果
      ↓ 后端高精度转换
EARTH_FIXED/CARTESIAN 渲染采样
      ↓ REST / WebSocket / CZML 导出
CesiumJS
```

CesiumJS 数据不是科学主存储。前端不得反向修改已完成运行中的 TruthState 或 TrackEstimate。

### 13.4 工作台状态

`AnalysisWorkspaceState` 可以保存：

- 当前时间；
- 播放速度；
- 相机状态；
- 当前选中对象；
- 可见图层；
- 算法颜色映射；
- 图表布局；
- 标注和分析书签。

用户通过交互修改科学输入时，必须产生新的 `SimulationRevision`、`MissionRevision` 或 `ExperimentRevision`。

---

## 14. 核心对象清单

### 领域定义

- `ProjectDefinition`
- `SimulationDefinition`
- `EnvironmentDefinition`
- `EntityDefinition`
- `SpaceObjectDefinition`
- `SpacecraftDefinition`
- `GroundStationDefinition`
- `SensorDefinition`
- `MissionDefinition`
- `TaskDefinition`
- `RoleAssignment`
- `ExperimentDefinition`

### 状态与事件

- `Epoch`
- `FrameRef`
- `CartesianState`
- `AttitudeState`（Core 已实现）
- `TruthState`（Core 已实现）
- `TruthManeuver`（Core 已实现）
- `ObservationSubjectRef`（Core 已实现）
- `ObservationEvent`（Core 已实现）
- `ObservationMeasurement`（Core 已实现）
- `MeasurementUncertainty`（Core 已实现）
- `IdealObservation`（Core 已实现）
- `ReportedObservation`（Core 已实现）
- `ObservationDeliveryRecord`（Core 已实现）
- `DeliverySummary`（Core 已实现）
- `StreamingObservationEnvelope`（Core 已实现）

### 算法与评价结果

- `TrackEstimate`
- `CovarianceMatrix`
- `ManeuverHypothesis`
- `MeasurementResidualSeries`
- `StateErrorSeries`
- `MetricResult`

### 运行与展示

- `SimulationRunRequest`（Core 已实现的完整 Engine 输入）
- `SimulationExecutionManifest`（Core 已实现的不可变 Engine 输入 provenance）
- Platform `RunRequest` / `RunManifest`（计划中的上层审计与 provenance）
- `RunRecord`（计划中的可变状态）
- `RunAttempt`（计划中的执行尝试）
- `RunOutcome`（计划中的一次性终态）
- `ResultBundle`（计划）
- `ArtifactRef`（计划）
- `AnalysisWorkspaceState`（计划）

---

## 15. 开发阶段

### 当前已实现：Core 契约

- Pydantic v2 冻结边界模型、严格类型和深度不可变输入；
- `Epoch`、公共帧、`CartesianState`、实体、传感器和父子关系；
- `SimulationDefinition`、机动、闭区间时间范围、输出采样以及
  `PERIODIC`/`EXPLICIT` 观测计划；
- 完整 `SimulationRunRequest` 和不可变 `SimulationExecutionManifest` 数据契约；
- 姿态、Truth、Observation、测量不确定度、逐事件交付终态、交付汇总和最小流式
  信封契约；
- `DELIVERY_RECORDS` 输出要求以及 Ideal/Reported 判别联合的公开 Schema；
- 公开 API、JSON Schema 快照、单元测试和独立 Core 分发。

### 当前已实现：Engine v0.1 批量 Truth 执行

- 同步 Engine `prepare()`/`run()`、显式不可变插件注册表和结构化错误；
- 惰性批量 Truth/姿态采样、J2000 脉冲机动、取消和输出 sink 生命周期；
- 确定性的非科学 `FakeBackend`，用于测试、示例和第三方后端兼容性开发。

### 计划：Observation、交互式 Session 与 Orekit

- 几何、Ideal/Reported 测量、误差、延迟/丢包与 FIFO 交付管线；
- 交互式 Session、恢复和运行时命令日志；
- JVM 生命周期、J2000 后端映射和高保真空间对象传播；
- Observation 和诊断结果写入。

### 计划：任务、实验、Platform 运行生命周期与持久化

- `MissionDefinition`、`TaskDefinition` 和 `RoleAssignment`；
- `ExperimentDefinition`；
- Platform `RunRequest`/`RunManifest`、`RunRecord`、`RunAttempt`、
  `RunOutcome` 和 `ResultBundle`；
- SQLite repository、本地 artifact store 和 Parquet 表模式；
- 运行状态机、Sim 默认 TRANSIENT/显式 RETAINED 保留策略和可重复运行编排；
- Algorithm Gateway、Batch/Streaming 生命周期、评价和只读成功交付 payload 授权。

### 计划：分析交互型三维工作台

- CesiumJS 场景、时间控制、对象树和选择；
- 轨迹、传感器、LOS、协方差和机动图层；
- ECharts 同步分析和多算法结果对比。
- 稳定英文机器值对应的中文标签、说明、保留提示和磁盘占用提示；中文文案不得进入
  Manifest、科学哈希或稳定数据库枚举。

---

## 16. 数据不变量与验收条件

### 16.1 数据不变量

1. 所有状态必须包含时刻和坐标系。
2. J2000 是唯一公共惯性坐标系名称。
3. LVLH、VVLH、BODY 和 SENSOR 必须绑定 owner。
4. Sensor 必须属于 Spacecraft 或 GroundStation。
5. 实体不得保存任务角色。
6. MissionDefinition 不得修改物理真值。
7. Ideal 和 Reported 必须共享 observation event ID。
8. TruthState 和 TruthManeuver 不得进入正式算法输入。
9. 状态误差为 estimate - truth；残差为 observed - predicted。
10. 完成运行的输入和结果不可原地修改。
11. Redis 不属于当前运行依赖。
12. 前端不得承担权威坐标转换。
13. ObservationEvent 每个 schedule occurrence 创建一次，不随积分、输出或渲染帧生成。
14. 每个 ObservationEvent 恰好对应一个终态 ObservationDeliveryRecord。
15. 算法只读取所选通道中成功交付的 payload，不读取失败记录或丢失内容。
16. OutputRequirement 只控制 artifact 持久化，不控制科学流水线执行。

### 16.2 验收条件

- 同一个物理仿真可绑定两个不同任务，不修改实体定义。
- 同一个空间对象在不同任务中可被赋予不同角色。
- 地面站和卫星均可嵌套传感器，并正确推导传感器状态。
- 理想观测和报告观测可分别生成、关联和选择性提供给算法。
- 定轨误差能够在 J2000 和 LVLH 中输出。
- 后续运行时可通过 `SimulationExecutionManifest` 与最终
  `RuntimeCommandJournal` 重建其关键科学配置和运行时命令，并通过
  `RunOutcome` 校验终态和输出哈希。
- 真值、估计、传感器、LOS、协方差和机动可在 CesiumJS 工作台中交互查看。
- 存储层在不引入 Redis 的情况下支持当前单机运行。

---

## 17. 延后设计

以下能力只保留扩展方向，不进入当前实现：

- 强化学习动作和环境协议；
- 多智能体对抗；
- AI 辅助设计师；
- 分布式任务调度；
- Redis 或其他外部消息系统；
- PostgreSQL 和对象存储；
- 多用户安全、权限、审计和安全域；
- 万级空间目标和 GPU 批量传播；
- 完整目标目录、数据关联和交会业务服务。

---

## 18. 参考资料

1. Orekit FramesFactory：J2000/EME2000 后端对应关系。<https://www.orekit.org/static/apidocs/org/orekit/frames/FramesFactory.html>
2. Ansys STK Components：LVLH 轴定义。<https://help.agi.com/STKComponentsJava/Javadoc/agi-foundation-geometry-AxesLocalVerticalLocalHorizontal.html>
3. Ansys STK Components：VVLH 轴定义。<https://help.agi.com/STKComponentsJava/Javadoc/agi-foundation-geometry-AxesVehicleVelocityLocalHorizontal.html>
4. Ansys STK Object Model Tutorial：Sensor 作为 Satellite 等对象的子对象。<https://help.agi.com/stk/13.0.0/LinkedDocuments/STKTutorial.pdf>
5. CesiumJS Fundamentals。<https://cesium.com/learn/cesiumjs-fundamentals/>
6. CesiumJS Entity API。<https://cesium.com/learn/cesiumjs-learn/cesiumjs-creating-entities/>
7. SQLite 官方说明。<https://www.sqlite.org/about.html>
8. Apache Arrow / Parquet Python 文档。<https://arrow.apache.org/docs/python/parquet.html>
9. Orekit Orbit Determination Architecture。<https://www.orekit.org/site-orekit-latest/architecture/estimation.html>
