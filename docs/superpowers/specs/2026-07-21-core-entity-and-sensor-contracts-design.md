# SycaSphere Core 实体与传感器契约设计规范

| 项目 | 内容 |
| --- | --- |
| 状态 | 已确认设计 |
| 日期 | 2026-07-21 |
| 适用包 | `sycasphere-core` |
| 关联基线 | `core-data-model-v0.2.md`、`algorithm-integration-v0.2.md`、`2026-07-20-sycasphere-runtime-and-simulation-engine-design.md` |

## 1. 目标

本设计为 `sycasphere-core` 增加后端中立、不可变且可独立安装的实体与传感器领域契约。它固定航天器、其他空间对象、地面站和传感器的组合关系，验证物理边界和 SI 单位，并为后续 `SimulationDefinition`、Engine 和 Orekit adapter 提供稳定输入。

本阶段只定义和验证数据，不执行轨道传播、姿态计算、指向、视场、可见性或观测生成。

## 2. 核心设计决定

1. 实体、传感器、安装变换、地理位置和物理属性使用强类型 Pydantic v2 模型。
2. 动力学、姿态、指向、视场、可见性、测量、误差、环境和可用性等可替换科学子模型使用通用、不可变的 `ModelRef`。
3. `ModelRef` 只描述稳定模型身份、接口模式版本和配置，不导入插件，不绑定 Python 类，也不启动 JVM。
4. 传感器是航天器或地面站的嵌套子组件，不是 `EntityDefinition` 联合类型的成员，也不包含独立轨道状态。
5. 实体只描述身份和物理能力；目标、主传感器和观测平台等任务角色不得进入实体模型。
6. 四元数公共顺序固定为 `w, x, y, z`，字段名必须显式包含 `wxyz`，不提供 `xyzw` 兼容别名或顺序猜测。
7. 本子项目不定义 `SimulationDefinition`。环境、机动、基线真值事件和实体集合在后续独立设计中组合。

## 3. 模块边界

```text
packages/sycasphere-core/src/sycasphere/core/
├── model_refs.py  # 可插拔科学子模型的数据引用
├── geometry.py    # 安装变换、传感器轴和 WGS84 地理位置
├── sensors.py     # SensorDefinition
└── entities.py    # 实体公共字段、具体实体和 EntityDefinition 联合
```

现有 `_json.py` 继续负责有限 JSON 的复制、深度冻结与安全序列化。现有 `Epoch`、`FrameRef`、`SchemaVersion` 和 `CartesianState` 作为输入依赖，不复制同义类型。

每个模块只依赖 Core 内部模块、Pydantic、NumPy 或 Python 标准库。不得导入 Orekit、JPype、Java、SQLite、PyArrow、FastAPI 或前端库。

## 4. 共享边界规则

### 4.1 标识和定义元数据

实体、传感器和模型 ID 使用去除首尾空白后的非空字符串。首版不强制 UUID，因为外部定义可能使用带命名空间的稳定 ID；ID 的内容不得被业务逻辑解释为角色。

定义对象的公共字段为：

```text
id
name
revision
schema_version
tags
metadata
```

- `revision` 是从 1 开始的正整数；
- `schema_version` 使用现有 `SchemaVersion`；
- `tags` 冻结为不可变集合，只用于检索；
- `metadata` 是非控制性、有限且深度不可变的 JSON 对象；
- 输入集合或映射在构造后被调用方修改时，不得改变模型；
- 所有模型使用 `frozen=True` 和 `extra="forbid"`。

实体在上述字段之外保存 `capabilities`。能力值是稳定、非空的字符串集合，可以为空，不得包含重复值。Engine 不得依据显示名称推断能力。

### 4.2 数值边界

- 长度和高度使用 m；
- 质量使用 kg；
- 角度使用 rad；
- 三维向量使用严格的长度 3 有限浮点元组；
- 四元数使用严格的长度 4 有限浮点元组；
- 字符串、整数到浮点数的隐式转换不得通过严格边界校验；
- 缺失值使用 `None`，不得使用零、NaN 或无穷值表达缺失。

几何单位向量和四元数不自动归一化。模型使用绝对容差 `1e-9` 验证单位长度、正交和右手关系，使错误配置在边界处显式失败。

## 5. ModelRef

```text
ModelRef
├── model_id: str
├── interface_version: SchemaVersion
└── configuration: Mapping[str, JsonValue]
```

规则：

- `model_id` 是稳定、去除首尾空白后的非空字符串；
- `configuration` 默认空对象，必须是有限 JSON，并在模型内部深度冻结；
- 序列化时恢复为普通 JSON 对象和数组；
- 读取或构造引用不得发现、导入或初始化模型实现；
- 插件实现版本和实际资源要求在 Engine `prepare` 阶段由 manifest 解析，并进入不可变执行清单；
- 同一个模型引用集合内的 `model_id` 必须唯一，避免同一模型配置的选择语义不明确。

`ModelRef` 与现有 `PluginRef` 职责不同：前者属于定义中的模型配置引用，后者标识一次已解析插件实现及其实现版本。Core 不把二者合并。

## 6. 几何契约

### 6.1 RigidTransform

```text
RigidTransform
├── translation_m: tuple[float, float, float]
└── rotation_parent_to_child_wxyz: tuple[float, float, float, float]
```

- `translation_m` 表示子坐标系原点相对父坐标系原点的位置，分量在父坐标系中表达；
- `rotation_parent_to_child_wxyz` 把父坐标系中的向量分量转换为子坐标系中的向量分量；
- 四元数顺序固定为标量在前的 `w, x, y, z`；
- 四元数范数必须在 `1 ± 1e-9` 内；
- 零四元数、非单位四元数、错误长度和非有限分量必须拒绝；
- Core 不静默重新归一化四元数。

### 6.2 SensorAxes

```text
SensorAxes
├── boresight: tuple[float, float, float]
├── horizontal: tuple[float, float, float]
└── vertical: tuple[float, float, float]
```

三个轴均在 SENSOR 坐标系中表达。每个轴必须是单位向量，任意两轴必须正交，并满足：

```text
horizontal × vertical = boresight
```

比较使用绝对容差 `1e-9`。该模型使传感器视轴约定成为数据的一部分，不默认视轴为 `+Z`。

### 6.3 GeodeticLocation

```text
GeodeticLocation
├── frame: FrameRef
├── longitude_rad: float
├── latitude_rad: float
└── ellipsoid_height_m: float
```

- `frame` 必须为 `EARTH_FIXED`、`GEODETIC`、`WGS84` 组合，并携带 ITRF、IERS 和 EOP 元数据；
- 经度范围为 `[-π, π]`；
- 纬度范围为 `[-π/2, π/2]`；
- 椭球高可以为负，但必须有限；
- Core 只验证表示，不执行大地坐标转换。

## 7. SensorDefinition

```text
SensorDefinition
├── id
├── name
├── revision
├── schema_version
├── tags
├── metadata
├── sensor_type
├── mount_transform
├── axes
├── pointing_model
├── field_of_view_model
├── visibility_model
├── measurement_models[]
├── error_profiles[]
└── availability_model
```

`sensor_type` 首版固定为：

- `OPTICAL`；
- `RADAR`；
- `RADIO`；
- `CUSTOM`。

规则：

- `mount_transform` 表示父平台 BODY 到传感器安装基准的固定变换；
- `axes` 明确 SENSOR 坐标系的视轴和像面方向；
- pointing、field-of-view 和 visibility 引用必填，即使首版采用最简单固定模型也必须显式声明；
- `measurement_models` 至少包含一个引用，且 `model_id` 唯一；
- `error_profiles` 可以为空，但存在时 `model_id` 必须唯一；
- `availability_model` 可为 `None`，表示没有额外可用性限制；
- 不定义 `initial_state`、轨道元素或独立姿态状态字段；未知的此类输入通过 `extra="forbid"` 拒绝。

传感器对象可以先被单独构造和校验，但只能作为 `SpacecraftDefinition.sensors` 或 `GroundStationDefinition.sensors` 进入实体和后续仿真定义。

## 8. 实体契约

### 8.1 EntityType 与公共字段

`EntityType` 只有：

- `SPACECRAFT`；
- `OTHER_SPACE_OBJECT`；
- `GROUND_STATION`。

三个具体实体共享定义元数据、`entity_type` 和 `capabilities`。公共的 `EntityDefinition` 是以下三个具体模型按 `entity_type` 判别的联合类型，不允许创建第四种无约束实体：

```text
SpacecraftDefinition
| OtherSpaceObjectDefinition
| GroundStationDefinition
```

固定任务角色字段不属于任何实体。`target_role`、`mission_role`、`primary_sensor` 等未知输入必须被拒绝。

### 8.2 SpaceObjectPhysicalProperties

```text
SpaceObjectPhysicalProperties
├── mass_kg
├── cross_section_area_m2
├── drag_coefficient
└── solar_radiation_pressure_coefficient
```

- `mass_kg` 和 `cross_section_area_m2` 必须为正且有限；
- 阻力系数和光压系数可以为 `None` 或非负有限浮点数；
- Core 不根据这些字段选择传播器，也不执行单位转换。

### 8.3 SpacecraftDefinition

```text
SpacecraftDefinition
├── 公共实体字段
├── initial_state: CartesianState
├── physical_properties: SpaceObjectPhysicalProperties
├── dynamics_model: ModelRef
├── attitude_model: ModelRef
└── sensors: tuple[SensorDefinition, ...]
```

传感器可以为空；非空时同一航天器内的 sensor ID 必须唯一。

### 8.4 OtherSpaceObjectDefinition

```text
OtherSpaceObjectDefinition
├── 公共实体字段
├── initial_state: CartesianState
├── physical_properties: SpaceObjectPhysicalProperties
├── dynamics_model: ModelRef
└── attitude_model: ModelRef
```

该模型不声明 `sensors` 字段。碎片、箭体和其他不能搭载传感器的对象使用此类型；传入 `sensors` 必须作为未知字段失败。

### 8.5 GroundStationDefinition

```text
GroundStationDefinition
├── 公共实体字段
├── location: GeodeticLocation
├── body_axes_convention: str
├── environment_models: tuple[ModelRef, ...]
├── availability_model: ModelRef | None
└── sensors: tuple[SensorDefinition, ...]
```

- `body_axes_convention` 是去除首尾空白后的非空稳定约定；
- `environment_models` 可以为空，存在时 `model_id` 必须唯一；
- `availability_model=None` 表示没有额外站级可用性限制；
- 同一地面站内的 sensor ID 必须唯一；
- 地面站不保存 `CartesianState`，其权威状态由后端根据 WGS84 位置、地固帧元数据和时刻推导。

## 9. 数据流与运行时责任

```text
JSON / YAML / Python mappings
        ↓
Pydantic 边界校验
        ↓
冻结的 EntityDefinition / SensorDefinition
        ↓
稳定 JSON 与后续 SimulationDefinition
        ↓
Engine prepare 解析 ModelRef
        ↓
插件 manifest / Orekit adapter
```

Core 负责：

- 字段、类型、长度、有限性和单位边界；
- 四元数、轴、WGS84 位置和组合关系不变量；
- 深层不可变和稳定序列化。

Core 不负责：

- 判断插件是否已经安装；
- 执行动力学、姿态、指向、视场或可见性；
- 把地面站转换为 J2000 状态；
- 启动 JVM 或构造 Orekit/Java 对象。

## 10. 错误语义

直接构造领域模型时，边界错误使用 Pydantic `ValidationError`，使调用方获得精确字段路径。Engine 或 API 在应用边界可以把验证错误转换为现有 `ErrorDetail(category=VALIDATION_ERROR, ...)`。

以下问题必须在 Core 构造时失败：

- 错误向量长度、字符串数值、NaN 或无穷值；
- 非单位四元数、非正交轴或左手轴；
- 不符合 WGS84 地理位置要求的 FrameRef；
- 非正质量或面积、负物理系数；
- 重复传感器 ID 或重复模型 ID；
- 空必填模型集合；
- 传感器独立轨道字段；
- 其他空间对象携带传感器；
- 实体混入任务角色；
- 非 JSON、异常、回溯或非有限 configuration/metadata。

插件缺失、接口不兼容和科学模型能力不足不在 Core 构造时判断，分别由 Engine 准备阶段产生 `PLUGIN_MISSING`、`PLUGIN_INCOMPATIBLE` 或稳定的能力校验错误。

## 11. 测试与验收

### 11.1 单元测试

必须覆盖：

- `ModelRef` 配置的深层不可变、有限 JSON 和稳定 JSON 往返；
- `RigidTransform` 的 `wxyz` 顺序、单位范数和错误兼容字段拒绝；
- `SensorAxes` 的单位、正交和右手约束；
- `GeodeticLocation` 的帧、椭球、角度范围和有限高度；
- `SensorDefinition` 的必填模型、唯一模型 ID、未知轨道字段和冻结行为；
- 三个实体类型的判别、物理参数和禁止角色字段；
- Spacecraft/GroundStation 的嵌套传感器与同父重复 ID；
- OtherSpaceObject 拒绝传感器；
- 输入集合和映射别名修改不会改变已构造模型。

### 11.2 契约测试

- 更新公共 `__all__` 精确导出测试；
- 更新 JSON Schema 快照，固定字段名和 `wxyz` 顺序；
- JSON dump/validate 往返保持模型相等；
- Core 依赖边界测试继续禁止 Orekit、JPype、数据库、API 和 UI 依赖；
- 根级 Ruff、mypy 和 pytest 全部通过；
- 构建 wheel 后在隔离环境中不安装 JDK 也可以导入新模型。

### 11.3 文档示例

Core README 增加两个可执行示例：

1. 航天器嵌套一个具有非默认视轴的传感器；
2. WGS84 地面站嵌套一个传感器。

示例只构造、序列化和检查模型，不声称执行传播或观测生成。

## 12. 完成条件

本子项目完成时：

1. 三个实体类型和传感器具有稳定、冻结、可序列化的公共契约；
2. 传感器不能作为自由飞行实体，也不能维护独立轨道；
3. 四元数公共顺序唯一为 `w, x, y, z`；
4. 地面站位置唯一使用带完整地固元数据的 WGS84 大地表达；
5. 可替换科学子模型通过 `ModelRef` 声明且不会触发实现加载；
6. 所有新增不变量具有失败与成功测试；
7. Core 仍可在没有 JDK/Orekit 的环境中独立安装和导入。

## 13. 明确不在本阶段实现

- `SimulationDefinition`、EnvironmentDefinition 和实体集合级唯一性；
- ManeuverCapability、PlannedTruthManeuver 和运行时命令；
- AttitudeState 和 TruthState 输出；
- 轨道传播和姿态计算；
- 固定指向、目标指向、扫描或转台算法；
- 圆锥、矩形或复杂视场几何计算；
- 遮挡、地平、光照或太阳抑制角计算；
- IdealObservation、ReportedObservation 和链路交付；
- 数据库、Parquet、API、CLI 或前端。

这些能力分别进入后续 SimulationDefinition、Observation、Engine、Orekit、Sim 和 Platform 子项目。
