# SycaSphere 数值与 Sink 契约加固设计

| 项目 | 内容 |
| --- | --- |
| 状态 | 已确认设计 |
| 日期 | 2026-08-01 |
| 适用范围 | Core `MeasurementUncertainty` 标准差工厂与 Engine Sink 回归测试 |
| 关联基线 | `core-data-model-v0.2.md`、Engine v0.1 已验收实现 |

## 1. 目的

本维护项关闭三个已确认但不阻塞 Engine v0.1 发布的问题：

1. 非零标准差平方后可能下溢为 `0.0`，从而把非零不确定度错误声明为精确零；
2. Sink 测试尚未完整锁定已实现的稳定错误码与错误上下文；
3. Composite Sink 在 begin 回滚失败后的真实子状态尚未被回归测试明确保护。

本维护项不引入新产品能力，不与交互式 Session、Orekit 或 Observation 流水线实现混合。

## 2. 已选择方案

### 2.1 无法表示的方差必须拒绝

`MeasurementUncertainty.from_standard_deviations()` 继续接收严格的、非负、有限、内置
`float` 标准差。每个标准差使用当前确定性的十进制归一化路径计算平方，再转换为公共
协方差所使用的内置 `float`。

规则固定为：

- 标准差恰好为 `0.0` 时，方差 `0.0` 合法；
- 非零标准差的平方若转换为 `0.0`，视为下溢并拒绝；
- 平方若转换为 `inf`、`-inf`、`NaN` 或无法转换，视为不可表示并拒绝；
- 可表示的普通值和亚正规正方差继续接受；
- 不使用硬编码数量级阈值，由实际目标 `float` 表示结果决定是否合法。

每次平方均使用新建的运算 `Context`，因此不依赖活动 decimal context，也不依赖可变的
`DefaultContext`。该 Context 显式设置 `prec=40`、`rounding=ROUND_HALF_EVEN`、
`Emin=-999999`、`Emax=999999`、`capitals=1`、`clamp=0`、`flags=[]` 与 `traps=[]`，
并以该 Context 的 `multiply` 计算同一 `Decimal(str(value))` 的乘积。任何
`Decimal`／转换失败，以及转换后的零值或非有限值，均映射为已批准的 Pydantic 消息
`standard-deviation variance must be representable as a finite float`。精度 40 足以精确容纳
任意有限内置 `float` 的十进制字符串平方：该字符串最多有 17 个有效数字，乘积最多需要
34 个有效数字。

拒绝发生在 `StandardDeviations` 的 Pydantic 验证边界。因此公开工厂继续以
`ValidationError` 报告输入问题，不泄漏 `Decimal`、`OverflowError` 或其他内部异常。

该规则只约束“由标准差推导方差”的工厂路径。调用方直接提供的有限、可表示、满足
半正定约束的协方差保持原语义，包括值为 `5e-324` 的亚正规协方差分量。

### 2.2 不采用的方案

- 不把下溢结果截断为最小正浮点数，也不把上溢结果截断为最大有限浮点数；截断会改变
  用户声明的科学含义。
- 不把公共协方差 Schema 改为 `Decimal`；这会扩大 Core 序列化和 NumPy 边界，不符合
  本维护项的最小范围。
- 不继续接受非零标准差对应的零方差；零协方差明确表示残余误差被声明为精确零。

## 3. 数据流与错误语义

标准差工厂的数据流保持为：

```text
ObservationMeasurement snapshot/revalidation
    -> StandardDeviations strict validation
    -> representable finite variance validation
    -> diagonal covariance construction
    -> MeasurementUncertainty validation/freeze
```

错误语义如下：

- 非内置浮点、负值、非有限值、维度不一致继续使用现有验证错误；其中正无穷和 `NaN`
  不进入派生方差错误路径，而是继续由既有 `StrictFiniteFloat` 给出有限数错误；
- 负值仍先按既有顺序触发“必须非负”语义，未改变其验证顺序；
- 非零平方下溢和平方上溢使用明确的“方差无法表示为有限 float”验证错误；
- 不增加稳定机器错误码，因为 Core Pydantic 字段验证当前没有该类应用层错误包装；
- 不改变已有协方差对称性、半正定、公差和 NumPy `errstate` 规则。

## 4. Sink 契约测试加固

Engine Sink 生产实现保持不变，只扩充测试断言。

### 4.1 稳定错误详情

回归测试必须同时锁定 category、code 和 context。非法批次的锁定覆盖三种公开 Sink
实现（`NullOutputSink`、`InMemoryOutputSink`、`CompositeOutputSink`）及三个写入通道：

- 非法批次：`engine.sink.invalid_batch`，包含 `channel` 和 `expected_type`；
- 非法生命周期操作：`engine.sink.invalid_state`，包含 `operation` 和当前 `status`；
- 内存容量耗尽：`engine.sink.memory_limit_exceeded`，包含 `max_records`、
  `retained_count` 和 `batch_count`。

测试不得把人类可读 message 当作稳定机器接口。

### 4.2 begin 回滚失败

当 Composite 的后续子 Sink begin 失败，同时先前已开始子 Sink 的 abort 也失败时，测试
固定以下语义：

- 对外重新抛出最初的 begin 失败，清理失败不得替换首因；
- abort 失败的子 Sink 保持 `WRITING`，不得被错误标记为 `ABORTED`；
- Composite 自身的 begin 未完成，因此保持 `NEW`；
- begin 失败的子 Sink 和尚未访问的后续子 Sink 保持 `NEW`；
- 调用顺序保持“正向 begin、逆向回滚”。

本维护项不新增 Composite 自动重试清理 API。现有公共生命周期没有一个合法入口能够从
`NEW` Composite 重新驱动残留的 `WRITING` 子 Sink；测试只描述真实状态，不虚构可重试
保证。未来若要提供恢复接口，必须作为独立行为设计。

## 5. 测试策略

实现遵循逐项 RED/GREEN：

1. 增加 `1e-200` 标准差回归，确认现状错误地产生零方差，形成 RED；
2. 增加足以使平方溢出的有限标准差回归，锁定现有最终模型会拒绝非有限方差的安全
   行为；该项可能从基线即为 GREEN，不伪造 RED；
3. 实现最小可表示性检查，使下溢测试转为 GREEN，并把上下溢统一收口到标准差验证
   边界；
4. 增加 hostile 活动 decimal context（精度、指数与 trap）回归，并证明 `0.0`、普通
   标准差、可表示亚正规方差和直接协方差路径不回归；
5. 增加被篡改 `DefaultContext` 的表征回归，以及正无穷／`NaN` 仍使用
   `StrictFiniteFloat` 有限数消息的回归；
6. 增加 Sink 稳定 detail 断言；
7. 增加 begin 回滚失败后的完整状态矩阵断言。

独立审查后已接受上述 Context 隔离、非有限消息与 Sink 参数化覆盖的最终修订；该记录仅
同步已接受的审查结论，不替代或声称任何未记录的命令执行结果。

最终执行：

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

## 6. 修改范围

预计只修改：

- `packages/sycasphere-core/src/sycasphere/core/observations.py`；
- `packages/sycasphere-core/tests/test_observations.py`；
- `packages/sycasphere-engine/tests/test_sinks.py`；
- 本设计及后续实施计划。

若 RED 测试证明 Sink 生产实现与上述既定语义不一致，必须先报告冲突并修订设计，不能
静默扩大实现范围。

## 7. 明确非目标

- 不修改公开 Core 或 Engine API；
- 不修改 JSON Schema 结构或版本；
- 不增加生产依赖；
- 不增加 Composite 清理重试 API；
- 不实现 Session、Orekit、Observation、Sim、Platform 或前端；
- 不修改、暂存或删除 `docs/assets/`。

## 8. 验收条件

1. 非零标准差不得被静默转换为零或非有限方差；
2. 可表示输入和直接协方差路径保持兼容；
3. Sink 的稳定错误详情和失败状态矩阵受到测试保护；
4. Ruff、mypy 和完整 pytest 全部通过；
5. 最终 diff 不包含未请求的生产行为、依赖、Schema 或外层功能变化。
