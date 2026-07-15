# APTDetectionAgent 研究与实现设计

版本：v0.6
状态：第一版实现基线

本文是 APTDetectionAgent 研究行为、数据边界、detector 生命周期、部署协议、配置空间、Memory、工具调用、SFT 和评价的当前 source of truth。

## 1. 项目背景与研究问题

PIDSMaker 是用于构建和比较 provenance-based intrusion detection systems（PIDSs）的统一框架。它将系统 provenance logs 构造成时间图，在 benign train/validation data 上学习正常行为，并在 test period 上输出 anomaly scores 与 thresholded alerts。

PIDSMaker 原始 pipeline 包含 construction、transformation、featurization、batching、training、evaluation 和 triage 等阶段。

APT 长期潜伏、持续活动且攻击行为稀疏。真实检测过程需要安全工程师长期监控 PIDS 的输出，判断当前 detector 是否仍适合环境、threshold 是否造成漏报或告警洪泛，以及是否应切换到其他已经准备好的 PIDS/configuration。这个过程人工成本高，也难以在长期时间流中保持一致。

本研究不把问题简化为“为一个 dataset 搜索一次最佳配置”，而是研究：

> 如何训练一个 LLM-based Agent，在按时间到达的 provenance construction graphs 上，以 test label 不可见方式持续运行 node-level PIDS，基于 benign 环境画像、当前与历史无标签状态以及已有 checkpoint 空间，判断何时保持当前配置、调整 threshold、切换 checkpoint 或安全回退。

检测性能、PIDS 运行成本、LLM 调用成本和 token 使用统一进入实验评价。第一版采用 SFT 学习 `observation -> thought -> tool call`，但运行时 LLM 是可替换组件，可以使用 base LLM、SFT 后的 LLM 或其他 provider/model 进行比较。

## 2. 第一版冻结结论

1. Construction graph 的时间窗口固定为 15 分钟。
2. 第一版执行 node-level detection：每张 graph 为原始 provenance node 输出 anomaly score 和 thresholded alert。
3. `graphs_per_state` 控制多少张 graph 聚合成一个 Agent state，第一版默认值为 `1`。
4. 每个 Agent state 调用一次 LLM，并要求输出一个 XML `agent_response` 和恰好一个 `tool_call`。
5. 第一版没有 trigger，也不区分 fast path/slow path。
6. Evaluation test 阶段不训练、重训或微调 PIDS，不使用 test graph 更新 detector 权重。
7. 所有可切换的 PIDS/configuration checkpoint 均在 test 开始前由外部流程准备好。
8. LLM 不能自由生成 PIDS、配置字段或数值；只能从 Harness 提供的有限、条件化合法选择空间中选择。
9. Threshold 只允许使用 validation-derived、no-snoop 的方式和值，不允许使用 test labels 或 test attack information。
10. 全项目 detector 实验固定 `seed: 42`。Seed 只写入 manifest，不进入 Agent observation/action，也不写入 checkpoint ID。
11. 第一版实现 Working Memory 和 Episode Memory；Long-Term Experience Memory（LTM）留作后续增强与消融，不进入第一版运行依赖。
12. 每张 graph 的正式结果只能提交一次；held-out labels 只由 episode 结束后的独立 evaluator 使用。

## 3. 数据边界与环境划分

### 3.1 两层数据划分

系统同时存在两种不同的数据划分：

- PIDSMaker 内部 train/validation/test 划分控制 detector lifecycle；
- Agent training/evaluation environments 划分控制 LLM Agent 的跨环境泛化。

两者不能互相替代。每个 held-out evaluation environment 仍使用自己的 benign train/validation data 完成部署初始化：

```text
environment train split
    -> train PIDS weights and generate epoch checkpoints

environment validation split
    -> select final model checkpoint
    -> run the selected checkpoint on benign validation data
    -> compute benign reference and no-snoop thresholds

environment test split
    -> frozen-checkpoint online detection
    -> Agent selects among prebuilt checkpoints/thresholds
    -> post-hoc hidden-label evaluation
```

Evaluation environment 的 train/validation data 是 deployment initialization data，不属于 test-label leakage。它们不能用于 SFT、LLM backend/model selection、LTM 构造或修改全局配置选择空间。最终检测指标只在该环境的 test period 上计算。

### 3.2 Agent training environments

| Environment |
|---|
| CADETS_E3 |
| THEIA_E3 |
| CLEARSCOPE_E3 |
| FIVEDIRECTIONS_E3 |
| TRACE_E3 |
| optc_h201 |
| optc_h501 |

这些环境可用于：

- 准备结构化 checkpoint 空间；
- 执行 controlled PIDS runs；
- 构造 observation/action trajectories；
- 使用 hidden labels 和反事实结果生成 teacher targets；
- 构造 SFT 数据和执行 LLM model selection。

SFT validation 按 environment/scenario/run group 划分，不能把同一 trajectory 或同一 controlled-run group 同时放入 SFT train 和 validation。

### 3.3 Held-out evaluation environments

| Environment |
|---|
| CADETS_E5 |
| THEIA_E5 |
| CLEARSCOPE_E5 |
| FIVEDIRECTIONS_E5 |
| TRACE_E5 |
| optc_h051 |

这些环境不能用于 SFT、LLM backend/model selection、LTM 构造或全局配置空间设计。允许使用每个 evaluation environment 自己的 benign train/validation split，按照评估前冻结的选择空间准备 checkpoint、benign reference、validation metrics 和 threshold artifacts。

### 3.4 可见信号与特权信号

Deployment initialization 和 test-time Agent 可以看到：

- environment/schema/platform 描述；
- benign train/validation loss 和无标签模型指标；
- benign validation score distributions、quantiles 和 reference statistics；
- graph scale、density、event rate 和 node/edge type distributions；
- checkpoint 的结构化训练配置、兼容信息和资源成本；
- test 时间流中的 graph/scores/alerts 趋势；
- runtime、OOM、timeout、artifact 和 tool execution 状态；
- Working Memory、Episode Memory 和上一次 tool result。

Held-out Agent observation、上下文和 deployable memory 禁止包含：

- test labels 或当前 TP/FP/FN/TN；
- attack identity、attack time、malicious nodes 或 attack-to-window mapping；
- coverage、MCC、ADP 或其他 label-derived test metrics；
- 从 held-out test ground truth 选出的 checkpoint 或 threshold。

Training environments 的特权信号只能用于 teacher、offline evaluator 和 SFT target 构造。生成 deployable SFT input/thought 时必须删除特权字段，并检查 visible-evidence grounding。

## 4. PIDSMaker 集成与检测语义

### 4.1 代码所有权边界

`PIDSMaker/` 是不修改的上游参考 submodule。生产 Agent 不导入 `pidsmaker` package，也不调用 PIDSMaker CLI。

第一版需要的 node-level subset 迁移到：

```text
src/apt_detection_agent/tools/pidsmaker/
```

迁移后保留可识别的 upstream module boundaries，并记录 upstream commit、原路径和 material changes。第一版排除 triage、edge/queue evaluation、synthetic attacks、`ATLASV2_EDR` 和 `CARBANAKV2_EDR`。

### 4.2 固定和可选择的 pipeline 部分

| Pipeline 部分 | 第一版边界 |
|---|---|
| Construction | Scenario 固定；`time_window_size = 15 min`。 |
| Transformation | 按 environment/PIDS 预定义，不由 LLM 自由修改。 |
| Featurization | 绑定在合法 checkpoint configuration 中。 |
| Semantic batching/sampling | 固定，不允许以资源恢复名义改变检测语义。 |
| Training objective | PIDS-specific objective 绑定在 checkpoint 中；系统最终输出语义固定为 node-level detection。 |
| Encoder/decoder | 绑定在 PIDS-specific checkpoint configuration 中。 |
| Detector training | 只发生在 test 前的外部 checkpoint preparation。 |
| Inference | Test 时间流每张 graph 执行。 |
| Score aggregation | 绑定在合法 scoring configuration 中。 |
| Threshold | 从 validation-derived no-snoop 选择空间中选择。 |
| Node evaluation | 独立 evaluator 固定；不属于 Agent。 |
| Triage | 第一版排除。 |

执行 batch size、worker count 等参数只有在已经验证不会改变 score/output 语义时，才可作为工程运行设置。会改变 graph partition、temporal state、sampling 或最终输出的 batching 参数必须绑定在 checkpoint/configuration 中，不能视为纯资源参数。

### 4.3 Node-level detection 语义

对每张 15 分钟 construction graph `G_t`，系统为每个原始 provenance node `v` 产生：

```text
node_score:  s_t(v)
node_alert:  a_t(v) = 1[s_t(v) >= threshold]
identity:    (scenario_id, graph_id, node_id)
```

原生 node-objective PIDS 可以直接产生 node score。原生 edge-objective PIDS 必须使用配置中固定的 incident-edge aggregation 规则把 edge losses 转换为当前 graph 内的 node score。该 aggregation 规则是 detector scoring semantics 的一部分，不能在 test 中任意生成。

在线系统按 graph 保存 node scores 和 committed alerts。不得使用上游跨全部 test windows 聚合同一 node 的离线行为替代在线逐 graph 输出。

## 5. Detector checkpoint 与 threshold 生命周期

### 5.1 Checkpoint 的产生时间

模型权重只由 train split 更新。Validation split 可以用于 early stopping 和最佳 epoch 选择，但不能继续更新模型权重。因此最终模型的准确表述是：

> Final detector checkpoint is trained on the train split and selected on the validation split.

固定流程为：

```text
train split updates model weights
    -> epoch checkpoints
    -> validation-based checkpoint selection
    -> final frozen model checkpoint
```

Final checkpoint manifest 至少记录：

```yaml
checkpoint_id: kairos_hd100_lr1e-4
pids: kairos
train_config:
  hidden_dim: 100
  learning_rate: 0.0001
reproducibility:
  seed: 42
checkpoint_hash: ...
```

`seed` 不拼入 `checkpoint_id`，也不是 Agent 的选择字段。

### 5.2 Threshold 在 checkpoint 之后校准

Final checkpoint 确定后，使用它在 benign validation split 上执行 inference，得到 validation scores 或更细粒度的 losses，再生成 no-snoop threshold artifacts：

```text
final checkpoint
    -> validation inference
    -> validation score/loss reference
    -> threshold method + allowed method value
    -> resolved threshold value
```

同一个 checkpoint 可以关联多个合法 threshold options。选择或切换 threshold 不修改 checkpoint 权重，也不需要重新训练 detector。

配置必须区分：

```yaml
scoring:
  node_aggregation: max_incident_edge_loss
threshold:
  method: validation_quantile
  parameter:
    quantile: 0.999
  resolved_value: 8.42
```

Agent 选择的是评估前提供的 `method + parameter` 组合；`resolved_value` 由 Harness 从 validation artifact 解析，LLM 不能自由生成。

如果只切换 scalar threshold，可以直接对已有 node scores 重新 threshold。如果 threshold method 同时要求不同的 score aggregation，则必须从保存的原始 inference outputs 重新聚合；它仍不更新模型权重，但不能把不同 aggregation 下的 scores 当作同一序列直接重 threshold。

### 5.3 可部署 detector configuration

一个完整、可提交的 detector configuration 包含：

```text
PIDS
+ transformation/featurization
+ model architecture and train hyperparameters
+ frozen checkpoint
+ temporal inference state policy
+ scoring/aggregation rule
+ validation-derived threshold option
+ execution settings verified to preserve semantics
```

Checkpoint 和 threshold 是不同 artifact；Harness 在提交时将它们解析成一个完整 committed detector configuration。

## 6. 有限、条件化配置选择空间

### 6.1 选择空间不是自由参数生成

LLM 只能从 Harness 放入 observation/context 的显式选择空间中选择。选择空间按 PIDS 条件化，列出真实存在且已验证兼容的完整配置元组，而不是分别给出字段后允许任意笛卡尔积组合。

示例：

```yaml
pids:
  kairos:
    checkpoint_configurations:
      - checkpoint_id: kairos_hd100_lr1e-4
        train_config:
          hidden_dim: 100
          learning_rate: 0.0001
        scoring_options:
          - node_aggregation: max_incident_edge_loss
        threshold_options:
          - method: validation_quantile
            parameter:
              quantile: 0.995
          - method: validation_quantile
            parameter:
              quantile: 0.999

      - checkpoint_id: kairos_hd200_lr1e-4
        train_config:
          hidden_dim: 200
          learning_rate: 0.0001
        scoring_options:
          - node_aggregation: max_incident_edge_loss
        threshold_options:
          - method: validation_quantile
            parameter:
              quantile: 0.999

  magic:
    checkpoint_configurations:
      - checkpoint_id: magic_hd64_l3
        train_config:
          hidden_dim: 64
          num_layers: 3
        scoring_options:
          - node_aggregation: direct_node_loss
        threshold_options:
          - method: validation_quantile
            parameter:
              quantile: 0.999
```

LLM 不得：

- 输出选择空间中不存在的 PIDS；
- 输出未列出的字段或值；
- 把一个 PIDS 的参数用于另一个 PIDS；
- 拼装未验证的跨配置组合；
- 生成不存在的 checkpoint；
- 生成任意 threshold method、method parameter 或 resolved threshold。

### 6.2 Registry 与 resolver

Agent-owned registry 保存结构化配置空间和 artifact 定位信息。它至少记录：

- `checkpoint_id`、版本、路径和 hash；
- environment/schema compatibility；
- PIDS-specific 完整 train configuration；
- transformation、featurization、encoder/decoder 和 scoring semantics；
- threshold options 及其 validation artifacts；
- temporal state initialization/restore requirements；
- runtime/resource profile；
- fallback configuration。

LLM 输出有语义的 PIDS/configuration/threshold 选择。Harness validator 检查完整元组的 membership 和 compatibility，resolver 再定位实际 checkpoint 和 threshold artifact。

## 7. Agent 状态与时间流程

### 7.1 Detection window 与 Agent state

Detection window 固定为一张 15 分钟 construction graph。Agent state 由最近 `graphs_per_state` 张 graph 的可见信息构成：

```yaml
agent:
  graphs_per_state: 1
```

第一版默认 `graphs_per_state = 1`，即每张 graph 形成一个 state 并调用一次 LLM。该值可以作为评估前冻结的实验超参数，用于比较不同决策频率。

当 `graphs_per_state = H > 1` 时：

- PIDS 仍然对每张 15 分钟 graph 执行 inference；
- Agent observation 汇总最近 H 张 graph；
- 每 H 张 graph 调用一次 LLM；
- 未到 decision boundary 的 graph 使用当前 committed configuration 直接提交；
- decision-boundary graph 在本次 LLM action 后提交。

系统不使用事件 trigger，不根据 anomaly、attack 或 failure 动态决定是否调用 LLM。

### 7.2 每个 Agent state 的执行顺序

以默认 `graphs_per_state = 1` 为例，对 `G_t`：

1. Harness 完成 construction、固定 transformation/featurization 和必要 batching。
2. 当前 committed checkpoint 对 `G_t` 执行 inference。
3. 固定 scoring rule 生成 node anomaly scores。
4. 当前 committed threshold 生成 provisional alerts。
5. Harness 更新 Working Memory、Episode Memory 和无标签趋势统计。
6. Harness 构造当前权威 observation，并附上当前合法配置选择空间和上一次 tool result。
7. Harness 调用一次当前实验配置指定的 LLM。
8. LLM 输出一个 XML `agent_response`，其中包含 `thought` 和恰好一个 `tool_call`。
9. Harness 依次执行 XML parsing、tool JSON parsing、schema validation、choice membership 和 compatibility validation。
10. Harness 执行一个 action，记录确定性的 `tool_result`；当前 state 不再次调用 LLM。
11. Harness 提交 `G_t` 的正式 node scores 和 alerts。
12. Tool result、最新 committed/pending configuration 和运行状态进入下一 state 的 observation/context。

### 7.3 Action 生效时间

| Action | 对当前 decision-boundary graph | 后续 graph |
|---|---|---|
| `KEEP_CURRENT_CONFIGURATION` | 提交 provisional outputs | 保持当前配置 |
| `SET_THRESHOLD` | 在 scoring rule 不变且原始 score 可用时，可重新 threshold 后提交 | 新 threshold 持续生效 |
| `SWITCH_CHECKPOINT` | 不重新训练；默认不替换当前 checkpoint 已产生的 scores | 从下一张 graph 使用新 checkpoint |
| `FALLBACK_CONFIGURATION` | 按工具定义提交当前安全输出或失败状态 | 从下一张 graph 使用 fallback |

已经 committed 的历史 graph 不得回写。离线 debugging 可以重跑，但不能替换正式 evaluation outputs。

Stateful PIDS 的 checkpoint switch 必须遵循 registry 中固定的 temporal-state policy，例如预热、合法历史 replay 或 state snapshot restore。模型权重冻结不代表 temporal inference state 必须静态；但任何 state update 都必须是该 PIDS 原生 inference 语义的一部分，不能执行梯度更新。

### 7.4 无同状态 Agent loop

第一版每个 state 固定：

```text
one LLM call
one agent_response
one tool_call
zero same-state LLM retries
```

工具执行失败时，Harness 执行确定性安全回退并记录错误。错误和 fallback 状态进入下一 observation，由下一 state 的一次 LLM 调用继续处理。

Token、latency、tool cost 和 switching cost是评价指标，不用于允许同一 state 内反复调用 LLM。Provider 的 timeout、最大输出长度和 XML 大小限制属于运行安全上限，不是 Agent 决策预算。

## 8. Observation 与上下文回填

### 8.1 Observation 内容

每个 Agent state 的 observation 至少包含：

| Block | 内容 |
|---|---|
| Environment | scenario、platform、provenance schema、node/edge types、benign workload profile、resource constraints |
| Current state | 当前 graph 或最近 H 张 graph 的规模、密度、类型分布和时间范围 |
| Detection state | node score distribution、tail statistics、alert volume 和无标签趋势 |
| Committed configuration | 当前 PIDS、checkpoint、train config、scoring、threshold 和 temporal-state status |
| Configuration space | 当前 environment 下所有允许的完整 PIDS/checkpoint/scoring/threshold 选择 |
| Memory | Working Memory window 和 Episode summary |
| Execution | 上一次 tool result、runtime、failure、pending/effective configuration 状态 |

Observation 必须由 Harness 从真实状态重新构造，经过 typed schema validation 和 privileged-data sanitization。LLM 不能把自己的上一轮输出当作已执行事实。

### 8.2 XML 上下文包络

每次 LLM 调用的当前输入使用明确的 XML 区块：

```xml
<agent_context>
  <observation observation_id="obs_0007" state_id="state_0007">
    {"environment": {}, "current_state": {}, "detection_state": {}}
  </observation>
  <configuration_space version="configuration_space_v1">
    {"pids": {}}
  </configuration_space>
  <previous_tool_result call_id="call_0006" status="success">
    {"effective_configuration": {}}
  </previous_tool_result>
</agent_context>
```

XML 标签划分语义区块；区块内部动态数据使用 canonical JSON，并分别通过 XML Parser 和 JSON Parser 校验。写入 XML text node 前必须转义 XML 特殊字符，XML Parser 还原 text 后才能交给 JSON Parser。

### 8.3 Tool result 与新 observation 回填

LLM action 执行后，Harness 生成确定性的 tool result：

```xml
<tool_result call_id="call_0007" status="success">
  {
    "resolved_checkpoint_id": "kairos_hd200_lr1e-4",
    "effective_from_graph": "G_8"
  }
</tool_result>
```

当前 state 不再次调用 LLM。下一 state 到达时，Harness 根据执行后的真实状态重新生成 `<observation>`，并把上一 `<tool_result>` 一起放回 LLM context。这样形成：

```text
observation_t
    -> LLM response_t
    -> parsed tool_call_t
    -> tool_result_t
    -> authoritative observation_t+1 containing the result
```

上下文只保留固定数量的最近 state transcript。更早内容由 Working Memory/Episode Memory 摘要替代，避免 context 和 token 随 episode 无限增长。

## 9. XML Response 与 Tool Contract

### 9.1 固定输出格式

项目固定：

```python
tool_call_start: str = "<tool_call>"
tool_call_end: str = "</tool_call>"
```

LLM 输出必须符合：

```xml
<agent_response>
  <thought>
    当前 score tail 与 alert volume 稳定，现有配置仍然适用。
  </thought>
  <tool_call>
    {"name": "keep_current_configuration", "arguments": {}}
  </tool_call>
</agent_response>
```

`thought` 只能引用 observation 中存在的 visible evidence。`tool_call` 内必须是单个 JSON object。

### 9.2 Parser 和安全边界

Harness 必须：

1. 使用正式 XML Parser 解析完整 `agent_response`，不能只依赖正则表达式；
2. 禁止 `DOCTYPE`、外部实体和 entity expansion；
3. 限制 response 字节长度、XML 深度和节点数量；
4. 要求根节点为 `agent_response`；
5. 要求恰好一个 `thought` 和一个 `tool_call`；
6. 拒绝未知顶层标签和多个 tool calls；
7. 对 `tool_call` 内容执行 JSON parsing 和 typed schema validation；
8. 验证所有配置字段和值属于当前 observation 提供的选择空间；
9. 验证完整配置兼容性、artifact 存在性和 action stage；
10. 只把通过校验的 typed request 交给工具执行层。

SFT 可以教会 LLM 正确输出 XML、选择工具和填写参数，但不能替代 Parser、schema、membership 和 compatibility validation。

### 9.3 第一版工具

| Tool | 作用 | 约束 |
|---|---|---|
| `select_initial_configuration` | 从 initialization configuration space 选择第一套 committed detector configuration | 只允许在 test stream 开始前调用 |
| `keep_current_configuration` | 保持当前 committed detector configuration | 默认安全动作 |
| `set_threshold` | 选择当前 checkpoint/scoring 支持的 validation-derived threshold option | 不能生成自由数值或使用 test labels |
| `switch_checkpoint` | 选择另一个完整合法 PIDS/checkpoint/scoring/threshold configuration | 必须存在于当前配置空间，默认下一 graph 生效 |
| `fallback_configuration` | 使用 registry 预定义的安全 fallback | 工具失败、artifact 不可用或输出无法解析时可由 Harness 确定性执行 |

第一版不开放：

- detector training、retraining 或 fine-tuning tool；
- 任意 shell/CLI 或 PIDSMaker internal function；
- construction window、transformation、objective 或 semantic batching 搜索；
- 任意 featurization/encoder/decoder 拼装；
- 任意自由数值超参数或 threshold；
- test-label evaluation、attack tracing 或 triage tool；
- 同一 state 的多轮 tool-use loop。

## 10. Memory

### 10.1 第一版 Memory

| Layer | 内容 | 生命周期 |
|---|---|---|
| Working Memory | 最近 N 张 graphs 的 graph/scores/alerts、当前配置、action、tool result 和运行状态 | 高频滚动；按 scenario 隔离 |
| Episode Memory | 当前 scenario 的 benign 环境画像、长期趋势、已尝试配置、配置变化和失败摘要 | 从 Working Memory 周期归纳；仅当前 episode 有效 |

Working Memory 和 Episode Memory 的 schema、更新和压缩由 Harness 固定。LLM 可以读取 observation 中提供的 memory 内容，但不直接写数据库或生成任意持久化记录。

### 10.2 LTM 后续扩展

Long-Term Experience Memory 不进入第一版实现依赖。后续版本可以从 Agent training environments 构造静态、held-out 只读的经验库，存储 environment signature、observable situation、结构化 action、适用条件和部署可见 outcome 摘要。

保留 LTM 的研究问题是：

> 当 LLM 已经在 training environments 上完成 SFT 后，显式检索具体历史经验是否仍能提高 held-out environments 上的长期决策质量？

后续必须通过 `SFT LLM without LTM` 与 `SFT LLM with LTM` 消融回答，不能把 checkpoint registry 当成 LTM，也不能把 hidden labels 或 label-derived metrics写入 deployable LTM。

## 11. LLM 与 SFT

### 11.1 运行时抽象

Agent 定义为：

```text
Agent = Harness + LLM
```

运行时统一描述为“调用一次 LLM”，而不是“调用 SFT policy”。Provider-neutral LLM interface 负责 transport、timeout、generation settings、token accounting 和 response normalization。

Harness、observation、配置空间、XML Parser 和工具不随 LLM 变化。实验可以替换：

- base LLM；
- SFT 后的同一 base LLM；
- 不同开源 LLM；
- 不同 provider 的兼容 LLM。

不得静默从一个 provider/model fallback 到另一个 provider/model。

### 11.2 SFT 学习目标

第一版 SFT 学习：

```text
observation + finite configuration space + recent context
    -> grounded thought
    -> one valid XML tool call
```

SFT 同时学习：

- XML 标签和 tool-call JSON 格式；
- 什么时候保持、调整 threshold、切换 checkpoint 或 fallback；
- 在 PIDS-specific 条件配置空间中选择合法值；
- 使用 observation 中真实存在的 evidence；
- 理解 action 的生效时间和成本。

Harness orchestration、XML/JSON parsing、配置 membership、compatibility validation、tool execution、Memory 更新和 hidden evaluator 不由 SFT 学习。

### 11.3 Offline trajectory 构造

只在 Agent training environments 上执行：

1. 按冻结的结构化配置空间准备多个 PIDS/checkpoint/threshold configurations，detector seed 固定为 42。
2. 在 training-environment test streams 上运行不同 configuration 和切换序列。
3. 使用 hidden labels、完整 outcomes 和 controlled counterfactuals 生成 teacher thought/action。
4. 从 observation、thought 和可部署 context 中删除 privileged fields。
5. 把所有配置值转换为当时 configuration space 中存在的显式选择。
6. 生成与运行时一致的单状态 XML transcript；每个 target 恰好包含一个 tool call。
7. 按 environment/scenario/run group 划分 SFT train 和 validation。

Offline run table 可以保存 hidden teacher/evaluation fields，但该表不得在 held-out deployment 中被 Agent 查询。

### 11.4 SFT sample

| Part | 内容 |
|---|---|
| System | Agent role、XML grammar、tool definitions、安全边界 |
| Input | 当前 XML observation、有限 configuration space、Working/Episode Memory、previous tool result |
| Target | XML `agent_response`：grounded thought + exactly one tool call |
| Teacher only | attack chain、labels、TP/FP/FN、coverage、MCC、ADP 和 counterfactual outcomes |

### 11.5 SFT 质量指标

- XML parse-valid rate；
- exactly-one-tool-call rate；
- tool JSON/schema-valid rate；
- configuration-space membership rate；
- compatibility-valid rate；
- forbidden-action/value rate；
- thought visible-evidence grounding rate；
- action accuracy 和 per-action macro-F1；
- privileged-field leakage rate；
- base LLM 与 SFT LLM 的端到端差异。

第一版不预设 RL。只有当 SFT 单状态质量足够、但端到端长期决策仍出现明确瓶颈时，才把 RL 作为后续独立研究阶段。

## 12. Evaluation Protocol

### 12.1 Evaluation scenario 初始化

Test 开始前，外部 checkpoint-preparation 流程：

1. 使用 evaluation environment 的 train split 训练评估前声明的配置，seed 固定为 42；
2. 使用 validation split 选择 final checkpoints；
3. 使用每个 final checkpoint 在 validation split 上生成 benign reference 和 threshold artifacts；
4. 记录 train/validation 可见指标、runtime 和 resource profile；
5. 构造该 environment 的有限、条件化 configuration space；
6. 冻结所有 artifacts、schema 和选择空间；
7. Harness 构造 initialization observation；
8. 由同一 Harness + 当前实验 LLM 调用 `select_initial_configuration`，选择初始 committed configuration。

这个流程不由 Agent 训练 PIDS。Agent 只选择已有 checkpoint 和 threshold option。

### 12.2 正式 test deployment

Test graphs 严格按时间顺序处理。正式结果只使用在线 committed outputs。Agent 始终看不到 test labels，不能根据当前检测指标回写或选择 configuration。

### 12.3 主目标

Attack-level coverage 是可行性硬约束：

```text
attack_coverage = detected_attack_campaigns / total_attack_campaigns
```

若 `attack_coverage < 100%`，该 run 对主约束记为 infeasible，但仍报告所有指标。在满足 coverage 的 runs 中，比较 committed node-level precision、recall、MCC、TP evidence recovery、detection delay 和系统成本。

不使用 held-out labels 扫描 threshold 生成主结果。Oracle threshold curve 只能作为明确标记的 post-hoc diagnostic upper bound。

### 12.4 检测指标

- TP、FP、FN、TN；
- node-level precision、recall 和 MCC；
- attack-level coverage；
- recovered malicious entities/evidence nodes；
- per-campaign first detection 和 detection delay；
- alert volume 和 FP rate；
- 跨 environment/scenario/window 的稳定性；
- ADP 等 threshold-independent 指标，仅作为 post-hoc diagnostic。

### 12.5 Agent 与系统指标

- input/output/total tokens；
- LLM calls、calls per graph、tokens per graph 和 tokens per Agent state；
- context length 和 context truncation/summary statistics；
- LLM latency、XML/schema invalid rate 和 deterministic fallback count；
- PIDS 总 runtime 和各 stage runtime；
- CPU/GPU memory、OOM、timeout 和 artifact failures；
- KEEP、threshold change、checkpoint switch 和 fallback counts；
- checkpoint load、state warm-up/replay 和 switching cost；
- scenario wall-clock。

Token、runtime 和资源成本是评价指标，不进入第一版 SFT loss，也不触发同一 state 的追加 LLM 调用。

### 12.6 Baselines 与消融

第一版至少比较：

- static tuned PIDS/checkpoint；
- validation-selected static configuration；
- rule-based controller；
- base LLM Agent；
- SFT LLM Agent；
- SFT LLM Agent without thought target；
- 不同 `graphs_per_state`；
- 后续扩展中的 SFT LLM Agent with/without LTM。

所有 LLM 消融共享同一 Harness、observation schema、configuration space、Parser、工具和 evaluator。

## 13. Reproducibility 与运行记录

每次 checkpoint preparation、controlled run、SFT run 和 held-out evaluation 必须记录：

- dataset/environment 和原生 split；
- detector `seed: 42`；
- configuration-space version 和完整结构；
- checkpoint ID/path/hash、threshold artifact 和 resolved configuration；
- provider、LLM model/revision、tokenizer 和 serving mode；
- generation parameters 和 context limit；
- `graphs_per_state`；
- commands、stage hashes、cache/state status；
- XML observations/responses、parsed tool requests/results 和 fallbacks；
- input/output tokens、LLM latency、PIDS runtime 和 resource usage；
- graph-level committed scores/alerts、post-hoc metrics 和最终报告。

不得静默切换 provider、LLM、checkpoint、scoring、threshold 或 fallback。Generated data、checkpoints、logs 和 run outputs 不进入 Git。

## 14. 第一版实现顺序

1. 定义 environment、checkpoint manifest、threshold artifact 和条件 configuration-space schemas。
2. 定义 observation、Working Memory、Episode Memory 和 privileged-data sanitization contracts。
3. 定义 XML context/response/tool-result grammar 和安全 Parser。
4. 定义 typed tool requests、configuration membership/compatibility validator 和 deterministic fallback。
5. 迁移 PIDSMaker node-level subset，并记录 upstream provenance 和 material changes。
6. 实现 15 分钟 graph-level inference、node scoring 和 committed output protocol。
7. 实现 checkpoint preparation、validation selection 和 threshold calibration pipeline。
8. 实现 `graphs_per_state` 调度、每状态一次 LLM 调用和上下文回填。
9. 实现 Working Memory 和 Episode Memory；第一版不实现 LTM。
10. 构造 offline run table、XML SFT trajectories 和 leakage/format quality checks。
11. 训练并验证 SFT LLM。
12. 在 held-out evaluation environments 上执行端到端评估、baselines 和消融。

## 15. 实现前仍需冻结的配置

以下属于待配置项，不改变本文架构边界：

- 第一版支持的 PIDS 集合；
- 每个 PIDS 的完整 checkpoint configuration 选择空间；
- score/edge-to-node aggregation 规则；
- no-snoop threshold methods 和 method-specific value space；
- stateful PIDS 的 warm-up/replay/snapshot policy；
- `graphs_per_state` 的主实验值和消融值；
- Working Memory 长度和 Episode summary 周期；
- observation 字段、归一化和上下文保留轮数；
- XML/JSON 长度、深度、schema 和 parser failure policy；
- SFT base model、数据规模、训练超参数和 quality-control thresholds；
- provider timeout、generation max tokens 和系统资源安全上限。

这些设置必须通过版本化 YAML/schema 固定，并在 held-out evaluation 开始前冻结。

## References

- PIDSMaker documentation: https://ubc-provenance.github.io/PIDSMaker/
- PIDSMaker pipeline: https://ubc-provenance.github.io/PIDSMaker/pipeline/
- PIDSMaker datasets: https://ubc-provenance.github.io/PIDSMaker/datasets/
- PIDSMaker tuned systems: https://ubc-provenance.github.io/PIDSMaker/tuned_systems/
