# Core Truth、Observation 与 Delivery 契约设计规范

| 项目 | 内容 |
| --- | --- |
| 状态 | 已确认，待书面复核 |
| 日期 | 2026-07-28 |
| 适用版本 | Core schema v0.1 的兼容扩展 |
| 关联基线 | `core-data-model-v0.2.md`、`algorithm-integration-v0.2.md`、`2026-07-20-sycasphere-runtime-and-simulation-engine-design.md`、`2026-07-26-simulation-definition-and-execution-input-design.md` |

## 1. 文档目的与效力

本文固定 `sycasphere-core` 下一批运行结果契约，包括姿态、真值状态、真实机动、
观测事件、Ideal/Reported 观测、测量不确定度、交付记录、交付汇总和流式交付信封。

本文只设计不可变、可序列化、后端中立的 Core 数据契约，不实现轨道传播、几何检查、
误差采样、链路模拟、Engine 会话、Orekit 适配、持久化或前端。后续 Engine 必须消费
本文契约，不得创建一套仅供内部使用的冲突结果格式。

当本文与关联基线存在表述精度差异时，以本文对本批次对象的字段、生命周期和验收规则
为准，并在实施时同步修订关联文档。

## 2. 已确认的设计决定

1. `IdealObservation` 与 `ReportedObservation` 是两个独立模型，共享 `event_id`，
   但拥有不同 `observation_id` 和测量值。
2. 不增加 `AlgorithmObservationView`。Ideal/Reported 本身只能包含允许算法读取的字段。
3. 算法可见目标采用 `KNOWN_OBJECT`、`TRACKLET` 或 `UNASSOCIATED` 引用；内部真实目标
   关联不得进入算法可见观测。
4. 标准测量采用统一 `ObservationMeasurement`，由测量类型驱动维度、单位、坐标系和
   数值范围校验；不为每个标准测量类型建立独立 Observation 类。
5. `MeasurementUncertainty` 表示确定性修正后剩余误差的算法可见有效协方差，可综合
   随机误差与未完全确定的系统误差，但不暴露实际抽样误差或真实偏差。
6. 每个观测计划触发恰好对应一个 `ObservationEvent`。先分配 `event_id`，完成几何检查
   后一次性创建不可变 Event，不创建可回填的半成品。
7. ObservationEvent 只由观测计划触发，不跟随数值积分步、Truth 输出采样或前端渲染帧
   自动生成。
8. 每个 Event 恰好产生一个终态 `ObservationDeliveryRecord`，包括几何拒绝、漏测、
   质量拒绝、链路丢包或成功交付。
9. 首版链路只模拟延迟和丢包，不模拟乱序、重复、重传或多次交付尝试。
10. 算法只接收成功交付的 Ideal 或 Reported；丢失观测不使用零值、NaN 或伪造
    Observation 表示。
11. 首版不实现 `NonDetectionReport`。
12. Truth、Observation 和 Delivery 对象均深度不可变；未知领域数据使用 `None`。
13. 四元数公共顺序固定为 `(w, x, y, z)`，姿态旋转方向固定为参考系到 BODY。
14. 所有机器字段和枚举使用稳定英文值；后续前端必须提供中文标签、说明和磁盘占用提示。
15. 逐事件交付记录通过显式 `DELIVERY_RECORDS` 输出要求控制，不要求全部常驻内存。

## 3. 包职责与代码组织

计划新增：

```text
packages/sycasphere-core/src/sycasphere/core/
├── attitudes.py       # AttitudeState
├── truth.py           # TruthState、TruthManeuver
├── observations.py    # Subject、Event、Measurement、Ideal、Reported、Uncertainty
└── delivery.py        # DeliveryRecord、DeliverySummary、StreamingEnvelope
```

计划修改：

```text
packages/sycasphere-core/src/sycasphere/core/__init__.py
packages/sycasphere-core/src/sycasphere/core/execution.py
packages/sycasphere-core/tests/snapshots/core-schemas.json
```

`schema.py` 不属于本批次修改范围：实现复用现有 `SchemaVersion` 且未引入任何
schema-version 行为。Schema 快照的新增内容来自公开模型注册，不需要修改版本类型。

职责边界：

- Core 定义数据形状和不依赖科学后端即可判定的不变量。
- Engine 后续负责跨对象谱系、插件输出、科学时间顺序、几何和交付 FIFO 约束。
- Orekit 后续负责权威传播、时间尺度、帧转换、姿态和地基/天基几何实现。
- Sim/Platform 后续负责 artifact、保留策略、算法授权和前端选项。
- Core 不得导入 Engine、Orekit、JPype、Java、SQLite、PyArrow、FastAPI 或前端代码。

## 4. 数值、时间、单位与不可变性

- 位置使用 `m`，速度和实际 Δv 使用 `m/s`，质量使用 `kg`，角度使用 `rad`，
  角速度使用 `rad/s`。
- JSON 数组边界使用固定或受约束的 tuple；数值计算助手返回独立
  `numpy.ndarray[float64]` 副本。
- 所有浮点分量必须是内置有限 `float`；不接受 bool、NaN、正负无穷或静默类型猜测。
- 嵌套 Pydantic 实例在公共边界必须复制并重新验证，不能信任已构造实例。
- 所有模型使用 `frozen=True`、`extra="forbid"` 和确定性序列化。
- 时间使用现有 `Epoch`。同一 TimeScale 可在 Core 比较；跨尺度顺序交给 Engine 时间服务。
- 同一运行生成的 observation `measurement_epoch` 与 `delivery_epoch` 使用相同 TimeScale。
- 已知测量和交付时刻时，`delivery_epoch` 不得早于 `measurement_epoch`。

## 5. AttitudeState

```text
AttitudeState
├── epoch: Epoch
├── reference_frame: FrameRef
├── rotation_reference_to_body_wxyz: tuple[float, float, float, float]
└── angular_velocity_body_wrt_reference_rad_s:
      tuple[float, float, float] | None
```

语义：

\[
\mathbf v_{BODY}
=
R(q_{\text{reference}\rightarrow BODY})
\mathbf v_{reference}
\]

约束：

- 四元数顺序只能是标量在前的 `(w, x, y, z)`。
- 字段名显式固定旋转方向，不提供 `xyzw`、`body_to_reference` 或模糊 `quaternion` 别名。
- 四元数范数必须在现有几何容差 `1e-9` 内等于 1，不静默归一化。
- `reference_frame` 必须采用 Cartesian 表示，首版允许 `J2000`、`EARTH_FIXED`、
  `LVLH` 或 `VVLH`，不允许 BODY 或 SENSOR 自引用。
- 角速度表示 BODY 相对 reference frame 的角速度，三个分量在 BODY 中表达。
- 角速度未知时使用 `None`；零角速度必须显式使用三个 `0.0`。

## 6. TruthState

```text
TruthState
├── entity_id: str
├── cartesian_state: CartesianState
├── attitude_state: AttitudeState | None
└── mass_kg: float | None
```

`CartesianState` 已经保存 `epoch` 和 `frame`。为避免重复字段相互矛盾，TruthState 不再
序列化第二个顶层 epoch，而提供只读属性：

```python
truth_state.epoch == truth_state.cartesian_state.epoch
```

约束：

- `entity_id` 是去除首尾空白后的非空稳定 ID。
- 存在 `attitude_state` 时，其 epoch 必须与 CartesianState epoch 完全相等。
- `mass_kg` 存在时必须是有限且严格大于零的 float。
- 地面站的时刻状态可以由后端根据 WGS84 站址生成 CartesianState。
- 传感器没有独立 TruthState；其状态由父平台 TruthState、安装变换和指向模型推导。
- 设备健康、传感器模式、云台状态和可用性不进入首版 TruthState。

## 7. TruthManeuver

```text
TruthManeuver
├── maneuver_event_id: str
├── source_kind: PLANNED | COMMAND
├── source_id: str
├── entity_id: str
├── scheduled_epoch: Epoch
├── executed_epoch: Epoch
├── actual_delta_v_j2000_mps: tuple[float, float, float]
├── state_before: TruthState
└── state_after: TruthState
```

早期讨论中的 `source_command_id` 在正式模型中扩展为 `source_kind + source_id`，因为
真实机动既可能来自 `PlannedTruthManeuver`，也可能来自预置或运行时
`ManeuverCommand`。该调整只消除命名歧义，不改变已确认的谱系语义。

约束：

- 原始 PlannedTruthManeuver 或 ManeuverCommand 继续保存在 Manifest/Command Journal；
  TruthManeuver 不复制原始命令。
- `source_id` 指向对应 planned maneuver ID 或 command ID。
- 无论原命令采用 J2000、LVLH、VVLH 或 BODY，实际执行 Δv 都转换为权威 J2000 分量。
- 前后状态属于同一 `entity_id`，其 epoch 均等于 `executed_epoch`。
- 前后 CartesianState 必须使用 J2000 Cartesian FrameRef。
- 两个质量都存在时，`state_after.mass_kg <= state_before.mass_kg`。
- 同一 TimeScale 下，executed epoch 不得早于 scheduled epoch。
- 执行失败不生成 TruthManeuver；失败属于后续命令执行记录和结构化错误。

## 8. 算法安全的 ObservationSubjectRef

使用判别联合：

```text
KnownObjectSubjectRef
├── kind: "KNOWN_OBJECT"
└── object_id: str

TrackletSubjectRef
├── kind: "TRACKLET"
└── tracklet_id: str

UnassociatedSubjectRef
└── kind: "UNASSOCIATED"
```

公共联合名为 `ObservationSubjectRef`。

规则：

- KNOWN_OBJECT 只保存任务明确授权的公开对象 ID。
- TRACKLET 保存不承诺真实身份的算法可见 tracklet ID。
- UNASSOCIATED 不增加伪目标 ID；单次检测由 observation/event ID 标识。
- ObservationEvent 可以保存内部真实目标实体 ID，但 Ideal/Reported 只能保存
  `ObservationSubjectRef`。
- 正式算法不得通过 SubjectRef、metadata、ModelRef 或错误上下文获得隐藏 Truth ID。

## 9. ObservationEvent 生命周期

一次触发的精确定义：

```text
一个 schedule occurrence
+ 一个触发 epoch
+ 一个 sensor
+ 一个 target
+ 一个 measurement model invocation
= 一个 ObservationEvent
```

二维 RA/DEC 是一个原子测量，因此对应一个 Event。若同一时刻独立执行 RA/DEC 和
RANGE 两个测量模型，则对应两个 Event。

创建顺序：

```text
schedule trigger
→ allocate event_id
→ geometry / visibility / pointing evaluation
→ create immutable ObservationEvent once
```

```text
ObservationEvent
├── event_id: str
├── schedule_id: str
├── measurement_epoch: Epoch
├── sensor_id: str
├── platform_id: str
├── truth_target_entity_id: str
├── public_subject_ref: ObservationSubjectRef
├── measurement_model_ref: ModelRef
├── measurement_type: MeasurementType
└── geometry_status: GeometryStatus
```

首版 GeometryStatus 精确固定为：

- `VISIBLE`
- `OCCLUDED`
- `OUT_OF_FIELD_OF_VIEW`
- `INSUFFICIENT_ILLUMINATION`
- `POINTING_UNAVAILABLE`

Event 是内部科学事实，不直接成为算法输入。几何失败仍产生 Event，但不产生
IdealObservation。

Event 只跟随 ObservationSchedule 触发。积分步、Truth 输出采样和前端渲染帧均不得
隐式产生 Event。首版 Event 表示时刻型测量，不表示连续曝光区间。

## 10. ObservationMeasurement

首版 MeasurementType：

- `ANGLES_RA_DEC`
- `ANGLES_AZ_EL`
- `RANGE`
- `RANGE_RATE`
- `LOS_UNIT_VECTOR`
- `CUSTOM`

统一测量结构：

```text
ObservationMeasurement
├── measurement_type: MeasurementType
├── values: tuple[float, ...]
├── component_names: tuple[str, ...]
├── component_units: tuple[str, ...]
├── frame: FrameRef | None
├── custom_type: str | None
├── custom_schema_ref: CustomMeasurementSchemaRef | None
└── qualifiers: FrozenJsonObject
```

CUSTOM schema 使用位置无关的精确引用：

```text
CustomMeasurementSchemaRef
├── schema_id: str
├── schema_version: SchemaVersion
└── sha256: str
```

`schema_id` 必须是命名空间化稳定字符串，sha256 必须是 64 位小写十六进制。该引用不保存
文件路径、URL、打开的句柄或插件对象；Engine 后续通过 schema/plugin resolver 查找并
重新校验内容哈希。

标准类型固定：

| 类型 | 分量名 | 单位 | Frame |
| --- | --- | --- | --- |
| ANGLES_RA_DEC | `right_ascension`, `declination` | `rad`, `rad` | J2000 |
| ANGLES_AZ_EL | `azimuth`, `elevation` | `rad`, `rad` | SENSOR 或 BODY |
| RANGE | `range` | `m` | None |
| RANGE_RATE | `range_rate` | `m/s` | None |
| LOS_UNIT_VECTOR | `los_x`, `los_y`, `los_z` | `1`, `1`, `1` | J2000 或 SENSOR |

标准类型的 component names 和 units 必须完全等于表中值，不接受大小写或同义词猜测。

数值约束：

- RA 属于 `[0, 2π)`。
- DEC 和 elevation 属于 `[-π/2, π/2]`。
- azimuth 属于 `[0, 2π)`。
- range 大于或等于零。
- range rate 可以是任意有限值。
- LOS 三维向量范数在 `1e-9` 内等于 1。

标准 qualifiers 使用精确键集合：

| 类型 | qualifiers |
| --- | --- |
| ANGLES_RA_DEC | 空对象 |
| ANGLES_AZ_EL | `angle_convention_id`：命名空间化稳定字符串 |
| RANGE | `path_kind`：`ONE_WAY` 或 `TWO_WAY` |
| RANGE_RATE | `path_kind`；`sign_convention`：`POSITIVE_RECEDING` 或 `POSITIVE_CLOSING`；`integration_interval_s`：有限正 float |
| LOS_UNIT_VECTOR | 空对象 |

标准类型拒绝表中未列出的 qualifier 键。这样单程/双程、符号、积分时间和角度轴约定
随 Observation 自描述，而不是依赖自由文本。Measurement model ref 仍保存产生该测量的
完整科学配置。

CUSTOM 规则：

- `custom_type` 必须是命名空间化稳定字符串，例如 `org.example/PIXEL_CENTROID_V1`。
- `custom_schema_ref` 必填。
- component names、units、frame、维度和 qualifiers 由独立 schema 与插件 manifest 校验。
- 非 CUSTOM 类型必须令 `custom_type` 和 `custom_schema_ref` 为 None。

## 11. MeasurementUncertainty

`MeasurementUncertainty` 表示：

\[
R_{\text{declared}}
=
\operatorname{Cov}
\left(
z_{\text{reported}}-z_{\text{ideal}}
\mid
\text{算法已知信息}
\right)
\]

它可以综合随机误差和未完全确定的残余系统误差，但不包含：

- 已知且已经应用的确定性修正；
- 本次仿真实际抽到的噪声样本；
- 隐藏的真实偏差；
- 直接计算出的 Truth 残差。

```text
MeasurementUncertainty
├── semantics: "EFFECTIVE_RESIDUAL_ERROR_COVARIANCE_V1"
├── component_names: tuple[str, ...]
├── component_units: tuple[str, ...]
└── covariance: tuple[tuple[float, ...], ...]
```

规则：

- covariance 必须是有限、方阵、对称和半正定矩阵。
- 行列数、component names 和 units 必须与 ObservationMeasurement 一致。
- 对角线不得为负；标准差工厂只接受有限且大于或等于零的值。
- 对称检查使用 `1e-12 * max(1.0, max_abs_entry)` 绝对容差和零相对容差。
- 半正定检查使用对称化矩阵的 `numpy.linalg.eigvalsh`；最小特征值不得小于
  `-1e-12 * max(1.0, max_abs_entry)`。
- 标准差输入通过
  `MeasurementUncertainty.from_standard_deviations(measurement, standard_deviations)`
  工厂方法平方并规范化为完整对角协方差；序列化只保留一种 covariance 格式。
- Core 允许 Reported uncertainty 为 None，以支持未来导入未标定真实数据。
- SycaSphere 标准仿真生成的 ReportedObservation 必须提供 uncertainty；该跨对象规则由
  Engine 强制。
- 跨多条观测的时间相关误差不由单条 covariance 表达，留给后续相关误差模型。

## 12. IdealObservation 与 ReportedObservation

```text
IdealObservation
├── channel: "IDEAL"
├── observation_id: str
├── event_id: str
├── measurement_epoch: Epoch
├── sensor_id: str
├── subject_ref: ObservationSubjectRef
├── measurement_model_ref: ModelRef
└── measurement: ObservationMeasurement
```

```text
ReportedObservation
├── channel: "REPORTED"
├── observation_id: str
├── event_id: str
├── measurement_epoch: Epoch
├── sensor_id: str
├── subject_ref: ObservationSubjectRef
├── measurement_model_ref: ModelRef
├── error_model_ref: ModelRef
├── measurement: ObservationMeasurement
└── uncertainty: MeasurementUncertainty | None
```

本地规则：

- Ideal 不包含 error model、uncertainty、实际误差或 Truth 字段。
- Reported 不包含实际噪声样本、真实偏差或 Truth 残差。
- channel 是固定 Literal，并作为 Ideal/Reported 判别联合的 discriminator。
- observation ID 与 event ID 必须是非空稳定 ID。
- 所有嵌套对象复制并重新验证。

Engine 跨对象规则：

- 同一 Event 的 Ideal/Reported 共享 event ID、measurement epoch、sensor ID、subject ref
  和 measurement type。
- Ideal 与 Reported 拥有不同 observation ID。
- 只有 Event.geometry_status 为 VISIBLE 才能产生 Ideal。
- Error pipeline 返回 None 时不得伪造 Reported。
- 正式算法一次只获得所选 Ideal 或 Reported 通道，不得同时读取另一通道与 Truth。
- 不增加 ObservationPair 公共容器；谱系在发送和 Sink 写入前验证。

每个 ObservationSchedule 的交付通道由 `error_profile_id` 唯一决定：

- `error_profile_id is None`：交付通道为 IDEAL；
- `error_profile_id` 存在：交付通道为 REPORTED。

`OutputRequirement.IDEAL_OBSERVATIONS` 和 `REPORTED_OBSERVATIONS` 只控制哪些科学 artifact
需要保存，不选择交付通道。即使两个 artifact 都要求保存，一个 Event 仍然只有一个
DeliveryRecord 和一个交付通道。

## 13. ObservationDeliveryRecord

每个 Event 恰好产生一个终态记录：

```text
ObservationDeliveryRecord
├── event_id: str
├── selected_channel: IDEAL | REPORTED
├── outcome: DeliveryOutcome
├── measurement_epoch: Epoch
├── delivery_epoch: Epoch | None
├── latency_s: float | None
├── ideal_observation_id: str | None
├── reported_observation_id: str | None
├── observation_payload_sha256: str | None
└── reason_code: str
```

首版 DeliveryOutcome：

- `GEOMETRY_REJECTED`
- `SENSOR_MISSED`
- `QUALITY_REJECTED`
- `LINK_DROPPED`
- `DELIVERED`

一致性矩阵：

| outcome | Ideal ID | Reported ID | delivery epoch / latency | payload hash |
| --- | --- | --- | --- | --- |
| GEOMETRY_REJECTED | None | None | None | None |
| SENSOR_MISSED | 必须存在 | None | None | 可为 Ideal hash |
| QUALITY_REJECTED | 必须存在 | None | None | 可为 Ideal hash |
| LINK_DROPPED | 按通道存在 | 按通道可存在 | None | 待交付 payload hash |
| DELIVERED | 按通道存在 | 按通道可存在 | 必须存在 | 已交付 payload hash |

补充规则：

- reason code 是稳定机器码，不保存自由格式堆栈。
- 默认 reason code 使用命名空间：
  `sycasphere.geometry/OCCLUDED`、
  `sycasphere.geometry/OUT_OF_FIELD_OF_VIEW`、
  `sycasphere.geometry/INSUFFICIENT_ILLUMINATION`、
  `sycasphere.geometry/POINTING_UNAVAILABLE`、
  `sycasphere.error/SENSOR_MISSED`、
  `sycasphere.error/QUALITY_REJECTED`、
  `sycasphere.link/DROPPED` 和
  `sycasphere.delivery/DELIVERED`。
- DELIVERED 的 latency 必须有限且大于或等于零。
- delivery epoch 必须与 measurement epoch 同 TimeScale 且不早于它。
- SENSOR_MISSED 和 QUALITY_REJECTED 只允许用于 REPORTED 交付通道，因为二者发生在
  Ideal 已经形成之后的 error pipeline。
- selected channel 为 REPORTED 时，成功或链路丢包必须存在 reported observation ID。
- selected channel 为 IDEAL 时，不要求产生 Reported。
- Record 不复制 Observation payload；必要时只保存 ID 和 SHA-256。
- Core Record 不持有 SimulationTimeRange，因此不对 delivery epoch 设置运行结束上界；
  是否排空结束时刻后的待交付队列由后续 Engine session 设计单独固定。

## 14. DeliverySummary 与 StreamingObservationEnvelope

```text
DeliverySummary
├── total_events: int
├── delivered: int
├── geometry_rejected: int
├── sensor_missed: int
├── quality_rejected: int
└── link_dropped: int
```

所有计数为非负整数，并满足各 outcome 计数之和等于 total events。

```text
StreamingObservationEnvelope
├── event_id: str
├── delivery_epoch: Epoch
└── observation: IdealObservation | ReportedObservation
```

规则：

- 只有 DELIVERED 才产生 Envelope。
- Envelope event ID 必须等于 observation event ID。
- Envelope delivery epoch 不早于 observation measurement epoch。
- 首版不包含 delivery sequence、attempt ID、duplicate ID 或 retransmission count。
- Engine 后续保证每个算法输入流 FIFO；链路延迟不改变测量顺序。
- 批算法默认读取最终成功交付集合并按 measurement epoch 规范排序。

## 15. 确定性 ID 与同刻事件顺序

不得使用无种子的随机 UUID。Engine 后续使用带版本的 domain separation 生成 ID：

```text
event_id
  = sha256("SYCASPHERE_OBSERVATION_EVENT_V1", manifest_hash,
           schedule_id, occurrence_index)

ideal_observation_id
  = sha256("SYCASPHERE_IDEAL_OBSERVATION_V1", event_id)

reported_observation_id
  = sha256("SYCASPHERE_REPORTED_OBSERVATION_V1", event_id)
```

精确字节拼接和编码在 Engine 设计中固定，并提供 golden vectors。Core 本批次只固定 ID
语义、稳定性和非空格式，不实现尚不存在的 Engine manifest 执行器。

同一时刻顺序保持：

```text
propagate to epoch
→ save pre-maneuver state
→ execute maneuver
→ create TruthManeuver
→ save post-maneuver state
→ attempt observation with post-maneuver Truth
→ emit regular sampled outputs
```

因此同刻 Observation 始终使用机动后状态，不提供 pre-maneuver observation 开关。

## 16. 错误边界

下列属于正常科学结果，不抛异常：

- 几何拒绝；
- 传感器漏测；
- 质量拒绝；
- 链路丢包。

下列属于结构化错误：

| 条件 | ErrorCategory |
| --- | --- |
| 非法维度、单位、Frame、协方差、ID 或身份引用 | VALIDATION_ERROR |
| 插件返回不符合 Core 契约的对象 | PLUGIN_INCOMPATIBLE |
| 请求或插件不支持测量类型 | UNSUPPORTED_MEASUREMENT |
| 数值模型无法产生有限结果 | NUMERICAL_FAILURE |
| 未分类内部缺陷 | INTERNAL_ERROR |

Core 使用 Pydantic ValidationError 表达边界失败。Engine 后续在应用边界转换为现有
`ErrorDetail`，不得泄漏 Java/Python 异常对象或隐藏 Truth 数据。

## 17. 输出要求、磁盘安全与中文前端

现有 `OutputRequirement.DELIVERY_SUMMARY` 保留；新增：

```text
DELIVERY_RECORDS
```

语义：

- 未请求 DELIVERY_RECORDS 时，Engine Sink 可以边处理边聚合，最终只保存 Summary。
- 请求 DELIVERY_RECORDS 时，逐事件记录写入临时 artifact，不要求全部常驻内存。
- OutputRequirement 只控制 artifact 持久化；Engine 仍必须生成所选交付通道需要的
  Ideal 或 Reported payload，不能因为未请求对应 artifact 而跳过科学流水线。
- Core 只表达需要哪些科学输出，不保存路径、保留类型或清理策略。
- Sim 后续默认使用 TRANSIENT，只保留最近一次临时运行。
- 用户通过前端“保留此次运行”、CLI `--retain` 或显式输出目录转为 RETAINED。
- 新运行成功发布后才能清理旧 TRANSIENT；不得自动删除 RETAINED。

前端必须使用稳定英文值与中文展示映射：

| 英文机器值 | 中文标签 |
| --- | --- |
| DELIVERY_SUMMARY | 保存交付汇总 |
| DELIVERY_RECORDS | 保存逐事件交付记录 |
| IDEAL | 理想观测（无误差） |
| REPORTED | 报告观测（含误差） |
| TRANSIENT | 临时保存 |
| RETAINED | 保留此次运行 |
| LINK_DROPPED | 链路丢包 |
| QUALITY_REJECTED | 质量检查未通过 |

前端还必须显示：

- “仅保存交付汇总（推荐，占用空间较小）”；
- “保存每次观测的详细交付记录（便于排查漏测和丢包，占用空间较大）”；
- “临时运行将在下一次成功仿真后清理”；
- “保留的运行不会被自动删除”。

中文文案不写入 Manifest、科学哈希或稳定数据库枚举。

## 18. 公共 API 与 Schema

本批次所有公共模型和枚举必须加入 `sycasphere.core.__all__` 和 reviewed JSON Schema
快照。新增公共集合精确包括：

- `AttitudeState`
- `TruthState`
- `TruthManeuver`
- `ManeuverTruthSource`
- 三种 SubjectRef 与 `ObservationSubjectRef`
- `MeasurementType`
- `GeometryStatus`
- `ObservationEvent`
- `ObservationMeasurement`
- `CustomMeasurementSchemaRef`
- `MeasurementUncertainty`
- `IdealObservation`
- `ReportedObservation`
- `ObservationChannel`
- `DeliveryOutcome`
- `ObservationDeliveryRecord`
- `DeliverySummary`
- `StreamingObservationEnvelope`

公共 schema 必须拒绝未知字段，并固定判别联合 discriminator。不得公开内部验证助手、
Truth 授权映射或插件对象。

## 19. 测试设计

### 19.1 Attitude 与 Truth

- `(w,x,y,z)` 顺序、单位范数、有限值和非法别名拒绝；
- reference-to-BODY 字段与允许 Frame；
- angular velocity 的 None/零值区分；
- TruthState epoch 一致性、质量正值和深度不可变；
- TruthManeuver 前后 entity/epoch/frame、J2000 Δv、质量非增加和 source 谱系；
- copied nested Pydantic instance revalidation。

### 19.2 Measurement 与 Observation

- 每个标准类型的维度、component names、units、Frame 和数值范围；
- RA/DEC、AZ/EL 边界；
- range 非负和 range rate 有符号；
- LOS 单位长度；
- CUSTOM namespace/schema 组合；
- SubjectRef 判别和未关联模式；
- Ideal/Reported 中不存在 truth target、实际误差、真实偏差和残差字段；
- Ideal/Reported 本地深度不可变和序列化 round trip。

### 19.3 Uncertainty

- standard deviation 工厂产生正确对角 covariance；
- covariance 维度、有限值、对称、非负对角和半正定；
- component order/units 与 measurement 一致；
- 不可变数组快照；
- uncertainty None 与显式零 covariance 的语义区分。

### 19.4 Delivery

- 每种 outcome 的合法和非法字段组合；
- 一个 Event 一个终态 Record 的 Engine 契约测试接口准备；
- delivered epoch、latency、channel、observation ID 和 payload hash；
- Summary 守恒；
- Envelope 只接受 Ideal/Reported 且 event ID 一致；
- schema 不包含乱序、重复或重传字段。

### 19.5 发布边界

- 公共 `__all__` 精确集合；
- JSON Schema 快照；
- wheel/sdist 许可证与内容；
- wheel 不包含测试、Engine、Orekit、Platform、Sim、JPype 或 Java；
- 无 JDK、Orekit 和 JPype 时 Core 独立导入；
- Ruff format、Ruff lint、mypy 和完整 pytest。

## 20. 明确不在本批次实现

- Engine 事件循环、prepare、run、session、pause、step、snapshot 和 restore；
- RuntimeCommandJournal、运行时命令取消和 checkpoint 分支；
- Orekit/JVM、传播、科学时间和帧转换；
- Observation 测量、误差和链路插件执行；
- NonDetectionReport；
- 链路乱序、重复、重传和多次交付尝试；
- 连续曝光、扫描和区间型测量；
- 跨观测时间相关 covariance；
- 算法 Gateway、Batch/Streaming Protocol 和评价；
- SQLite、Parquet、ArtifactStore、保留策略实现和前端代码；
- ACCESS_DRIVEN schedule；
- 完整有限推力执行。

## 21. 完成标准

本批次只有在以下条件全部满足时完成：

1. 本设计和对应详细实施计划已提交。
2. 新模型与三份权威架构文档一致，差异已主动修订。
3. 每个行为变化先有失败测试，再有最小实现。
4. 所有公共模型具有正向、反向、边界、不可变、复制重验证和序列化测试。
5. Truth 身份和实际误差不会通过算法可见 schema 泄漏。
6. ObservationEvent、Ideal、Reported 和 DeliveryRecord 生命周期无回填矛盾。
7. `DELIVERY_RECORDS` 与 `DELIVERY_SUMMARY` 的语义和磁盘边界已记录。
8. 公共 API 与 JSON Schema 快照已审阅。
9. Core 发行包仍只依赖 Pydantic 与 NumPy，并通过隔离构建和安装验证。
10. Ruff format、Ruff lint、mypy 和完整 pytest 全部通过。
11. 最终代码审查没有未解决的 Critical、Important 或 Minor 问题。
12. 未引入本节列出的延后功能。

## 22. 后续依赖顺序

本批次通过后，后续按以下独立设计与实施批次推进：

1. `sycasphere-engine` package、prepare ports、插件解析和 Manifest 生成；
2. Fake backend 事件调度、批量 run、Truth/Observation/Delivery Sink；
3. 交互式 session、暂停、单步、推进到时刻、控制步长和执行节奏；
4. RuntimeCommandJournal、运行时脉冲机动、取消未来命令和 checkpoint 分支；
5. measurement/error/link pipeline 的实际插件执行与确定性随机流；
6. Orekit backend、JVM、时间/帧、传播、几何和脉冲机动；
7. 独立 Sim Python API、CLI、Parquet/artifact、临时发布和保留策略；
8. Platform、算法 Gateway、评价、API 和中文前端。
