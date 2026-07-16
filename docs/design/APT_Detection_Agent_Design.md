# APTDetectionAgent 研究与实现设计

版本：v0.8
状态：第一版实现基线

本文是 APTDetectionAgent 研究行为、数据边界、detector 生命周期、部署协议、配置空间、Memory、工具调用、SFT 和评价的当前 source of truth。

## 1. 项目背景与研究问题

PIDSMaker 是用于构建和比较 provenance-based intrusion detection systems（PIDSs）的统一框架。它将系统 provenance logs 构造成时间图，在 benign train/validation data 上学习正常行为，并在 test period 上输出 anomaly scores 与 thresholded alerts。

PIDSMaker 原始 pipeline 包含 construction、transformation、featurization、batching、training、evaluation 和 triage 等阶段。

APT 长期潜伏、持续活动且攻击行为稀疏。真实检测过程需要安全工程师长期监控 PIDS 的输出，判断当前 detector 是否仍适合环境、threshold 是否造成漏报或告警洪泛，以及是否应切换到其他已经准备好的 PIDS/configuration。这个过程人工成本高，也难以在长期时间流中保持一致。

本研究不把问题简化为“为一个 dataset 搜索一次最佳配置”，而是研究：

> 如何训练一个 LLM-based Agent，在按时间到达的 provenance construction graphs 上，以 test label 不可见方式持续运行 node-level PIDS，基于 benign 环境画像、当前与历史无标签状态以及有限的 PIDS-specific 配置空间，判断何时保持当前配置、调整哪个配置 decision unit、选择什么合法值或安全回退。

检测性能、PIDS 运行成本、LLM 调用成本和 token 使用统一进入实验评价。第一版采用 SFT 学习 `observation -> thought -> tool call`，但运行时 LLM 是可替换组件，可以使用 base LLM、SFT 后的 LLM 或其他 provider/model 进行比较。

## 2. 第一版冻结结论

1. Construction graph 的时间窗口固定为 15 分钟。
2. 第一版执行 node-level detection：每张 graph 为原始 provenance node 输出 anomaly score 和 thresholded alert。
3. `graphs_per_state` 控制多少张 graph 聚合成一个 Agent state，第一版默认值为 `1`。
4. 每个 Agent state 调用一次 LLM，并要求输出一个 XML `agent_response` 和恰好一个 `tool_call`。
5. 第一版没有 trigger，也不区分 fast path/slow path。
6. Evaluation test 阶段不训练、重训或微调 PIDS，不使用 test graph 更新 detector 权重。
7. 每个合法 train configuration 对应的 detector checkpoint 均在 test 开始前由外部流程准备好；LLM 需要比较并选择这些 checkpoint 所对应的结构化配置，但 action 不填写内部 `checkpoint_id`，由 Harness 确定性解析。
8. LLM 不能自由生成 PIDS、配置字段或数值；只能从 Harness 提供的有限、条件化合法选择空间中选择。
9. 每个 PIDS 的 Agent-selectable threshold 至少包含 validation-derived、no-snoop 的 `validation_quantile`、`max_val_loss` 和 `mean_val_loss`；FLASH/THREATRACE 还保留各自固定-scalar 原生 method 的有限邻域值，MAGIC 的 snooped 原生 method 不进入 Agent 空间。只有声明了数值分支的 method 才继续选择 `value`。
10. 全项目 detector 实验固定 `seed: 42`。Seed 只写入 manifest，不进入 Agent observation/action，也不写入 checkpoint ID。
11. 第一版实现 Working Memory 和 Episode Memory；Long-Term Experience Memory（LTM）留作后续增强与消融，不进入第一版运行依赖。
12. 每张 graph 的正式结果只能提交一次；held-out labels 只由 episode 结束后的独立 evaluator 使用。
13. 第一版支持 FLASH、KAIROS、MAGIC、NODLINK、ORTHRUS、R-CAID、THREATRACE 和 VELOX 八个 PIDS；MAGIC 保留为 Agent 可选 PIDS，但其 threshold 只能从 benign validation scores 校准。

## 3. 数据边界与环境划分

### 3.1 两层数据划分

系统同时存在两种不同的数据划分：

- PIDSMaker 内部 train/validation/test 划分控制 detector lifecycle；
- Agent training/evaluation environments 划分控制 LLM Agent 的跨环境泛化。

两者不能互相替代。每个 held-out evaluation environment 仍使用自己的 benign train/validation data 完成部署初始化：

```text
for each declared detector configuration
    -> train one epoch on environment train split and update weights
    -> evaluate that epoch checkpoint on environment validation split without weight updates
    -> repeat Train epoch -> Validation pass
    -> select final checkpoint by the frozen validation-selection rule
    -> run the selected checkpoint on benign validation data
    -> compute benign reference and no-snoop threshold artifacts

environment test split
    -> frozen-checkpoint online detection
    -> Agent selects structured configurations
    -> Harness resolves configurations to prebuilt checkpoints/threshold artifacts
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

- 准备结构化 configuration space 及其 artifact mappings；
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
- PIDS-specific train/threshold configurations、compatibility 信息和对应的无标签 reference/cost；
- test 时间流中的 graph/scores/alerts 趋势；
- runtime、OOM、timeout、artifact 和 tool execution 状态；
- Working Memory、Episode Memory 和上一次 tool response。

Held-out Agent observation、上下文和 deployable memory 禁止包含：

- test labels 或当前 TP/FP/FN/TN；
- attack identity、attack time、malicious nodes 或 attack-to-window mapping；
- coverage、MCC、ADP 或其他 label-derived test metrics；
- 从 held-out test ground truth 选出的 checkpoint 或 threshold。

Training environments 的特权信号只能用于 teacher、offline evaluator 和 SFT target 构造。生成 deployable SFT input/thought 时必须删除特权字段，并检查 visible-evidence grounding。

## 4. PIDSMaker 集成与检测语义

### 4.1 代码所有权边界

`PIDSMaker/` 是不修改的上游参考 submodule。生产 Agent 不导入 `pidsmaker` package，也不调用 PIDSMaker CLI。

第一版需要的 node-level subset 迁移到仓库顶层的独立可运行目录：

```text
APTDetectionAgent/
└── pidsmaker_adapter/
```

`pidsmaker_adapter/` 由本项目拥有，包含 checkpoint preparation、validation inference、threshold artifact generation 和 test inference 所需的可运行入口。直接运行该目录下的入口可以产生各种 PIDS/configuration checkpoints 及其 train/validation artifacts；大文件输出仍必须写入规定的数据盘路径，不能写入 Git。

迁移后保留可识别的 upstream module boundaries，并记录 upstream commit、原路径和 material changes。第一版排除 triage、edge/queue evaluation、synthetic attacks、`ATLASV2_EDR` 和 `CARBANAKV2_EDR`。

### 4.2 固定和可选择的 pipeline 部分

| Pipeline 部分 | 第一版边界 |
|---|---|
| Construction | Scenario 固定；`time_window_size = 15 min`。 |
| Transformation | 按 environment/PIDS 预定义，不由 LLM 自由修改。 |
| Featurization | 由 PIDS-specific configuration 决定，并随执行 artifact 一起解析。 |
| Semantic batching/sampling | 固定，不允许以资源恢复名义改变检测语义。 |
| Training objective | 由 PIDS-specific configuration 决定；系统最终输出语义固定为 node-level detection。 |
| Encoder/decoder | 由 PIDS-specific configuration 决定，不由 LLM 越过配置空间自由拼装。 |
| Detector training | 只发生在 test 前的外部 checkpoint preparation。 |
| Inference | Test 时间流每张 graph 执行。 |
| Score aggregation | 由 PIDS/configuration 固定并由 Harness 解析，不作为独立在线 decision unit。 |
| Threshold | 从 validation-derived no-snoop 选择空间中选择。 |
| Node evaluation | 独立 evaluator 固定；不属于 Agent。 |
| Triage | 第一版排除。 |

执行 batch size、worker count 等参数只有在已经验证不会改变 score/output 语义时，才可作为工程运行设置。会改变 graph partition、temporal state、sampling 或最终输出的 batching 参数必须绑定在 resolved execution configuration 中，不能视为纯资源参数。

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

代码执行按 epoch 交替执行 Train 和 Validation，而不是完成全部 Train 后只执行一次 Validation：

```text
for epoch in configured_epochs:
    train_one_epoch(train split)
        -> forward / loss / backward / optimizer step
        -> candidate epoch checkpoint
    validate(candidate checkpoint, validation split)
        -> validation inference / validation loss
        -> no backward and no weight update
    update best-checkpoint selection state

after the final epoch:
    -> select final checkpoint using the frozen validation-selection rule
    -> freeze final checkpoint weights
```

Train pass 的输出包括更新后的候选权重、train loss/history、runtime/resource 和候选 epoch checkpoint。每个 epoch 后的 Validation pass 输出 validation loss 和 checkpoint-selection record，但不修改权重。Final checkpoint 确定后，还要再执行一次独立的 benign-validation inference，以生成最终 score reference 和 threshold artifacts；该步骤不是训练循环中的 optimizer update。

Final checkpoint manifest 至少记录：

```yaml
checkpoint_id: kairos_hd128_lr1e-4
pids: kairos
train_config:
  training.node_hid_dim: 128
  training.lr: 0.0001
reproducibility:
  seed: 42
checkpoint_hash: ...
```

`seed` 不拼入 `checkpoint_id`，也不是 Agent 的选择字段。

### 5.2 Threshold 在 checkpoint 之后解析

Final checkpoint 确定后，使用它在 benign validation split 上执行 inference，得到 validation scores 或更细粒度的 losses，再生成 no-snoop threshold artifacts：

```text
final checkpoint
    -> validation inference
    -> validation score/loss reference
    -> allowed validation-derived method
    -> quantile value when method=validation_quantile
    -> resolved threshold value
```

同一个 checkpoint 可以关联多个合法 threshold configurations，但第一版不提供独立的在线 threshold-only transition，也不对当前 graph 重新 threshold。Threshold method/value 在初始化时随完整 detector configuration 一起选择；在线切换 train/PIDS configuration 时，新 checkpoint 绑定的 threshold artifact 从下一张 graph 生效。

配置必须区分：

```yaml
scoring:
  node_aggregation: max_incident_edge_loss
threshold:
  method: validation_quantile
  value: 0.95
  resolved_value: 8.42
```

LLM 先从当前 PIDS 的 `method.values` 选择 method。`validation_quantile` 继续选择 quantile value；NODLINK 围绕原生默认 `0.90` 使用 `[0.85, 0.90, 0.95]`，其余 PIDS 的项目 quantile 邻域为 `[0.90, 0.95, 0.99]`。FLASH 的 `flash` method 使用 `[0.30, 0.53, 0.70]`，THREATRACE 的 `threatrace` method 使用 `[1.0, 1.5, 2.0]`，均包含 PIDSMaker 默认值。`max_val_loss` 和 `mean_val_loss` 没有 value 字段。Harness 从该 checkpoint 的 benign-validation score distribution 解析或验证 `resolved_value`。Quantile `q` 对应的 benign-validation 经验超阈率约为 `1-q`，但受有限样本、重复分数和比较方向影响，不保证恰好相等，更不保证 held-out test 上具有相同 false-positive rate。LLM 不能自由生成 method、value 或 `resolved_value`。

同一个 PIDS/checkpoint 的所有 Agent-selectable threshold values 必须消费完全相同的 node-score definition、score aggregation、temporal aggregation、normalization 和比较方向，只能改变最终 scalar threshold。任何会改变 scoring/aggregation contract 的 threshold method 都不得进入同一 threshold value space；第一版不支持为切换 threshold 重新聚合 inference outputs。

PIDSMaker 原生 threshold 方法和值必须在对应 PIDS 配置中以行尾默认注释保留，用于说明 baseline provenance。FLASH/THREATRACE 的固定 scalar 可在不使用 test labels 的情况下应用，因此作为 PIDS-specific method 的中心值进入有限邻域；使用 held-out test score distribution 的 MAGIC 原生行为仍不进入主实验：

```yaml
# upstream_reference_only:
#   flash:
#     method: fixed
#     values: [0.53]
#     eligible_for_agent: [true]
#   threatrace:
#     method: fixed
#     values: [1.5]
#     eligible_for_agent: [true]
#   magic_upstream_snooped:
#     method: test_score_mean
#     eligible_for_agent: [false]
#     eligible_for_primary_evaluation: [false]
```

Agent-compatible MAGIC 使用三种 validation-derived 方法之一，从 benign validation 的 MAGIC anomaly scores 解析 threshold。NODLINK 原生 90% quantile 直接表示为 `method: validation_quantile, value: 0.90`，并标注为 PIDSMaker 默认值；`0.85` 和 `0.95` 是上下邻域 variants。

### 5.3 可部署 detector configuration

必须区分 LLM 的决策对象和 Harness 的执行对象。

LLM 可选择的 decision configuration 只包含：

```text
PIDS
+ PIDS-specific train configuration values
+ validation threshold method/value
```

Harness 将合法 decision configuration 解析为 resolved execution configuration：

```text
decision configuration
    -> transformation/featurization
    -> model architecture and train hyperparameters
    -> prebuilt frozen checkpoint
    -> temporal inference state policy
    -> scoring/aggregation rule
    -> validation-derived threshold artifact
    -> execution settings verified to preserve semantics
```

LLM 在语义上需要比较和选择不同 checkpoint，但选择依据和 action 字段是产生 checkpoint 的结构化 `PIDS + train_config`，而不是不透明的内部 `checkpoint_id`。Harness 将合法结构化配置确定性地解析到预生成 checkpoint；observation 可以同时展示该配置对应的 checkpoint availability、无标签 validation reference 和 cost，使 LLM 知道自己将切换到哪类 checkpoint。Threshold artifact 由 `checkpoint + threshold_config` 解析。最终 committed detector configuration 是 resolved execution configuration。

对 validation-derived threshold，`threshold_config` 表示计算规则而不是最终 scalar。同一个 quantile value 应用于不同 checkpoint 的 validation score distributions 时，可能解析出不同的 `resolved_threshold`；这属于 checkpoint-specific threshold resolution，不是一次独立 threshold change。固定 reference 阈值则不会随 checkpoint 改变，但它们不作为 Agent 实际阈值。

## 6. 有限、条件化配置选择空间

### 6.1 PIDS-specific decision configuration

LLM 只能从 Harness 放入 observation/context 的显式选择空间中选择。不同 PIDS 可以开放不同的 train hyperparameters 和合法值；threshold configuration 也只能从对应 PIDS/train configuration 支持的 method/value 中选择。

选择空间必须同时提供：

- 当前完整 decision configuration；
- 每个 PIDS 支持的 train configuration fields；
- 每个 field 或耦合 field group 的有限合法 options；
- 完整 decision configuration 的 compatibility constraints；
- 每个合法 train configuration 支持的 threshold method/value options；
- 当前 state 允许改变的 decision units。

LLM 不能分别挑选字段后构造未经验证的笛卡尔积，也不能主要依赖 Harness 在输出后反复拒绝非法组合。选择空间以 PIDS 为根构造层次化条件树：上层选择决定下层可见字段和值，LLM 选择一条合法路径。Harness 仍执行最终 membership/compatibility validation，但 observation 和 typed schema 应先把不可达分支从 LLM 可见空间中裁掉。

字段选择空间统一采用 `field: {values: [...]}` 风格。简单字段直接列出有限值；必须耦合的多个字段使用一个结构化 field，其 `values` 中列出完整合法组合。每一种数值字段在不同 PIDS 中统一采用 3 个或统一采用 5 个候选，必须包含 PIDSMaker 默认值，并以默认值为中心选择上下邻域；默认只写在对应 `values` 行尾注释中，不成为可选字段。合法组合很多时不在 prompt 中平铺所有完整 configuration，而由树形分支、耦合 value 和条件约束紧凑表达；内部 artifact registry 仍可索引所有已经准备好的叶节点。

LLM-facing、Harness resolver 和人工审计产物必须分离：

- `agent_configuration_space.json` 只含 action 可选字段、条件分支和 `values`，不得包含默认注释、来源、alias、override、checkpoint path/hash、cache 或 resolved scalar；
- `configuration_registry.json` 只供 Harness 使用，保存合法叶子到 checkpoint/threshold artifact 的解析映射，并通过 ref 指向 Agent 选择空间；
- versioned YAML、manifest 和 resolved config 用于人工审计与复现，可包含 PIDSMaker 来源、默认注释、兼容 alias 和执行细节，但不得原样放入 LLM context。

示例：

```yaml
current_configuration:
  pids: kairos
  train_config:
    training.lr: 0.0001
    training.node_hid_dim: 128
    featurization.used_method: hierarchical_hashing
  threshold_config:
    method: validation_quantile
    value: 0.95

configuration_space:
  pids:
    kairos:
      fields:
        training.lr:
          values: [0.001, 0.0001]
        training.node_hid_dim:
          values: [32, 64, 128, 256]
        featurization.used_method:
          values: [hierarchical_hashing, fasttext, word2vec]
        threshold:
          method:
            values: [validation_quantile, max_val_loss, mean_val_loss]  # PIDSMaker default: max_val_loss
          value:
            by_method:
              validation_quantile:
                values: [0.90, 0.95, 0.99]  # project default: 0.95

      decision_units:
        training.lr:
          fields: [training.lr]
        training.node_hid_dim:
          fields: [training.node_hid_dim]
        featurization.used_method:
          fields: [featurization.used_method]

      constraints:
        membership: reachable_prebuilt_leaf_only

    nodlink:
      fields:
        training.lr:
          values: [0.001, 0.0001]
        training.node_hid_dim:
          values: [32, 64, 128, 256]
        featurization.used_method:
          values: [fasttext, word2vec]
        threshold:
          method:
            values: [validation_quantile, max_val_loss, mean_val_loss]  # PIDSMaker default: validation_quantile
          value:
            by_method:
              validation_quantile:
                values: [0.85, 0.90, 0.95]  # PIDSMaker default: 0.90

    flash:
      fields:
        threshold:
          method:
            values: [flash, validation_quantile, max_val_loss, mean_val_loss]  # PIDSMaker default: flash
          value:
            by_method:
              flash:
                values: [0.30, 0.53, 0.70]  # PIDSMaker default: 0.53
              validation_quantile:
                values: [0.90, 0.95, 0.99]  # project default: 0.95

    threatrace:
      fields:
        threshold:
          method:
            values: [threatrace, validation_quantile, max_val_loss, mean_val_loss]  # PIDSMaker default: threatrace
          value:
            by_method:
              threatrace:
                values: [1.0, 1.5, 2.0]  # PIDSMaker default: 1.5
              validation_quantile:
                values: [0.90, 0.95, 0.99]  # project default: 0.95

    magic:
      fields:
        threshold:
          method:
            values: [validation_quantile, max_val_loss, mean_val_loss]  # PIDSMaker default: magic/test-score mean (reference only)
          value:
            by_method:
              validation_quantile:
                values: [0.90, 0.95, 0.99]  # project default: 0.95
      # magic_upstream_snooped:
      #   threshold.method:
      #     values: [test_score_mean]
      #   eligible_for_agent:
      #     values: [false]
```

LLM 不得：

- 输出选择空间中不存在的 PIDS；
- 输出未列出的字段或值；
- 把一个 PIDS 的参数用于另一个 PIDS；
- 拼装未验证的跨配置组合；
- 生成任意 threshold method、method parameter 或 resolved threshold。

### 6.2 Decision unit 与单次调整边界

初始化时没有 current configuration，`switch_configuration` 必须选择一套完整 target configuration。

Test 时间流中，每次 `switch_configuration` 只允许改变一个合法 decision unit：

| Decision unit | 可改变内容 | 不可同时改变 |
|---|---|---|
| `initial_configuration` | Test stream 开始前选择完整 PIDS/train/threshold configuration | 只用于初始化，不用于在线 state |
| `train_config.<unit_name>` | 当前 PIDS 下该 unit 声明的一个字段或一组耦合字段；threshold option 的语义值保持不变，新 checkpoint 的 resolved scalar 由 Harness 重新解析 | 其他独立 train decision units、threshold option 和 PIDS |
| `pids_configuration` | 目标 PIDS 以及该 PIDS 下完整的 train/threshold configuration | 不允许再叠加独立的第二次调整语义 |

第一版没有独立 `threshold_config` 在线 decision unit。Threshold option 只在 `initial_configuration` 中选择，或作为目标 `pids_configuration` 的组成部分选择；保持同一 PIDS 时不能只改变 threshold，也不能借修改 train configuration 同时改变 threshold option。一个 train decision unit 可以包含多个字段，但只有 registry 明确声明这些字段必须耦合选择时才允许同时变化。例如一个 `model_capacity` unit 可以把 `training.node_hid_dim + training.node_out_dim` 作为一个不可拆分的结构化 value。LLM 不能自行决定把任意多个超参数放进同一次修改。

因此，“一次只调整一个 decision unit”不等于“永远只改变一个标量字段”。它表示一次 action 只有一个可解释、可验证的配置干预原因。

### 6.3 `switch_configuration` 的目标配置

LLM 必须同时输出：

- 本次选择的 `decision_unit`；
- 修改后的完整 `target_configuration`。

例如，在当前 KAIROS 内只把 `training.node_hid_dim` 从 128 改为 256：

```xml
<tool_call>
{
  "name": "switch_configuration",
  "arguments": {
    "decision_unit": "train_config.training.node_hid_dim",
    "target_configuration": {
      "pids": "kairos",
      "train_config": {
        "training.node_hid_dim": 256,
        "training.lr": 0.0001,
        "featurization.used_method": "hierarchical_hashing"
      },
      "threshold_config": {
        "method": "validation_quantile",
        "value": 0.95
      }
    }
  }
}
</tool_call>
```

Harness 计算 `current_configuration` 与 `target_configuration` 的实际 diff，并要求：

```text
actual changed fields
    == changed fields of exactly one allowed transition
       declared under the selected decision_unit
```

随后检查完整 target configuration 是否属于合法选择空间。只有通过两项检查后，才进入 artifact resolution。

### 6.4 Registry、validator 与 artifact resolver

Agent-owned registry 保存 LLM-visible 配置语义、compatibility constraints 和执行 artifact 定位信息。它至少记录：

- `checkpoint_id`、版本、路径和 hash；
- environment/schema compatibility；
- PIDS-specific train decision units、threshold value spaces、allowed values 和完整合法 decision configurations；
- transformation、featurization、encoder/decoder 和 scoring semantics；
- 每个 train configuration 到 checkpoint 的映射；
- 每个 threshold configuration 到 validation artifact/resolved threshold 的映射；
- temporal state initialization/restore requirements；
- runtime/resource profile；
- fallback configuration。

执行顺序固定为：

```text
LLM selects decision_unit + target_configuration
    -> Harness computes configuration diff
    -> decision-unit validation
    -> complete-configuration membership/compatibility validation
    -> resolver maps PIDS + train_config to checkpoint
    -> resolver maps checkpoint + threshold_config to threshold artifact
    -> Harness builds resolved execution configuration
```

`checkpoint_id`、checkpoint path/hash 和 `resolved_threshold` 不由 LLM 填入 action，但可作为只读 resolver metadata 出现在 observation/configuration metadata、registry、resolved execution configuration 和 tool response 中。LLM 依据产生 checkpoint 的结构化配置、无标签 validation reference、availability 和 cost 进行选择，不能从 checkpoint 名称猜测隐藏配置。

### 6.5 LLM 如何选择要调整的配置项

LLM 确实需要思考下一步使用哪一个 checkpoint，但不从 checkpoint 名称反推超参数，也不自由猜测要同时修改哪些字段。每个 state 的输入必须明确提供：

- current decision configuration；
- 当前 PIDS 支持的 decision units；
- 每个 decision unit 的字段、耦合关系和 allowed values；
- 从当前配置出发能够形成合法完整配置的 transitions；
- 每套相关 configuration 的 train/validation 无标签 reference metrics；
- 每套 configuration 解析到的 checkpoint availability、只读 artifact identity 和 runtime/resource cost；
- 当前与最近 test states 的 graph、score、alert 和 execution observations；
- Working/Episode Memory 中已经尝试过的 decision unit、值和后续可见结果。

SFT trajectory 必须通过 controlled runs 监督：

```text
visible observation
    -> which decision_unit to change
    -> which allowed value to select
    -> complete target_configuration
```

同一 controlled group 一次只改变一个 decision unit；teacher 可以使用 training-environment hidden labels 和 counterfactual outcomes 确定 target，但 deployable observation/thought 只能引用运行时可见 evidence。Held-out test 中 LLM 只能依据这些无标签 evidence 和 SFT 学到的规律推断，不能声称已经知道某次调整会提高 TP 或降低 FP。

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
6. Harness 构造当前权威 observation，并附上当前合法配置选择空间和上一次 tool response。
7. Harness 调用一次当前实验配置指定的 LLM。
8. LLM 输出一个 XML `agent_response`，其中包含 `thought` 和恰好一个 `tool_call`。
9. Harness 依次执行 XML parsing、tool JSON parsing、schema validation、choice membership 和 compatibility validation。
10. Harness 执行一个 action，生成确定性的 `<tool_response>`；当前 state 不再次调用 LLM。
11. Harness 提交 `G_t` 的正式 node scores 和 alerts。
12. Tool response、最新 committed/pending configuration 和运行状态进入下一 state 的 observation/context。

### 7.3 Action 生效时间

| Tool/action | 对当前 decision-boundary graph | 后续 graph |
|---|---|---|
| `keep_current_configuration` | 提交 provisional outputs | 保持当前完整配置 |
| `switch_configuration` | 提交进入该 state 时已经 committed 的 scores/alerts，不替换当前 graph 输出 | 完整新配置统一从下一张 graph 生效；不存在 threshold-only 或当前 graph re-threshold |
| `fallback_configuration` | 按工具定义提交当前安全输出或失败状态 | 从下一张 graph 使用 fallback |

已经 committed 的历史 graph 不得回写。离线 debugging 可以重跑，但不能替换正式 evaluation outputs。

当新的 decision configuration 被解析到不同 checkpoint 时，stateful PIDS 必须遵循 registry 中固定的 temporal-state policy，例如预热、合法历史 replay 或 state snapshot restore。模型权重冻结不代表 temporal inference state 必须静态；但任何 state update 都必须是该 PIDS 原生 inference 语义的一部分，不能执行梯度更新。

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
| Committed configuration | 当前 PIDS、PIDS-specific train config 和 threshold config |
| Configuration space | 当前 environment/PIDS 下的 decision units、allowed values、完整合法 configurations 和 compatibility constraints |
| Memory | Working Memory window 和 Episode summary |
| Execution | 上一次 tool response、runtime、failure、pending/effective configuration 状态 |

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
  <tool_response>
    {"call_id": "call_0006", "status": "success", "effective_configuration": {}}
  </tool_response>
</agent_context>
```

XML 标签划分语义区块；区块内部动态数据使用 canonical JSON，并分别通过 XML Parser 和 JSON Parser 校验。写入 XML text node 前必须转义 XML 特殊字符，XML Parser 还原 text 后才能交给 JSON Parser。

### 8.3 Tool response 与新 observation 回填

`<tool_call>` 是 LLM 发给 Harness 的执行请求；与之对应的 `<tool_response>` 是 Harness 执行工具后生成的真实结果，不由 LLM 生成，也不属于 `<agent_response>`。

LLM action 执行后，Harness 生成确定性的 tool response：

```xml
<tool_response>
  {
    "call_id": "call_0007",
    "status": "success",
    "decision_unit": "train_config.training.node_hid_dim",
    "applied_configuration": {
      "pids": "kairos",
      "train_config": {
        "training.node_hid_dim": 256,
        "training.lr": 0.0001,
        "featurization.used_method": "hierarchical_hashing"
      },
      "threshold_config": {
        "method": "validation_quantile",
        "value": 0.95
      }
    },
    "resolved_artifacts": {
      "checkpoint_id": "kairos_hd256_lr1e-4",
      "resolved_threshold": 8.42,
      "threshold_option_changed": false,
      "resolved_threshold_changed": true,
      "resolved_threshold_change_reason": "checkpoint_specific_validation_resolution"
    },
    "effective_from_graph": "G_8"
  }
</tool_response>
```

当前 state 不再次调用 LLM。下一 state 到达时，Harness 根据执行后的真实状态重新生成 `<observation>`，并把上一 `<tool_response>` 一起放回 LLM context。这样形成：

```text
observation_t
    -> LLM response_t
    -> parsed tool_call_t
    -> Harness executes the tool
    -> tool_response_t
    -> authoritative observation_t+1 containing the result
```

因此一组完整的交互角色是：

```text
Harness -> <agent_context><observation>...</observation>...</agent_context>
LLM     -> <agent_response>...<tool_call>...</tool_call></agent_response>
Harness -> <tool_response>...</tool_response>
Harness -> 下一 state 的新 <agent_context>，其中包含上一 tool_response 和新 observation
```

上下文只保留固定数量的最近 state transcript。更早内容由 Working Memory/Episode Memory 摘要替代，避免 context 和 token 随 episode 无限增长。

## 9. XML Response 与 Tool Contract

### 9.1 固定输出格式

项目固定：

```python
tool_call_start: str = "<tool_call>"
tool_call_end: str = "</tool_call>"
tool_response_start: str = "<tool_response>"
tool_response_end: str = "</tool_response>"
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
9. 比较 current/target configuration，验证实际 diff 与所选 decision unit 下恰好一个 allowed transition 完全一致；
10. 验证完整配置兼容性、artifact 存在性和 action stage；
11. 只把通过校验的 typed request 交给工具执行层。

SFT 可以教会 LLM 正确输出 XML、选择工具和填写参数，但不能替代 Parser、schema、membership 和 compatibility validation。

### 9.3 第一版工具

| Tool | 作用 | 约束 |
|---|---|---|
| `keep_current_configuration` | 保持当前 committed detector configuration | 默认安全动作 |
| `switch_configuration` | 选择一个 decision unit 和修改后的完整 target configuration；也用于初始化第一套配置 | Test 时间流每次只能改变一个合法 decision unit；Harness 验证 diff 后再映射 checkpoint/threshold artifacts |
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
| Working Memory | 最近 N 张 graphs 的 graph/scores/alerts、当前配置、action、tool response 和运行状态 | 高频滚动；按 scenario 隔离 |
| Episode Memory | 当前 scenario 的 train/validation 无标签画像、长期趋势、已尝试配置、配置变化和失败摘要 | 初始化时写入 train/validation reference；随后从 Working Memory 周期归纳；仅当前 episode 有效 |

Working Memory 和 Episode Memory 的 schema、更新和压缩由 Harness 固定。LLM 可以读取 observation 中提供的 memory 内容，但不直接写数据库或生成任意持久化记录。

Episode Memory 可以保存的 train/validation 无标签信息包括：

- 每套 decision configuration 的 train loss、validation loss 和 selected epoch；
- benign validation node-score distribution、mean、standard deviation 和 quantiles；
- validation-derived threshold method、method value 和 resolved threshold；
- 每个 threshold option 在 benign validation 上的 alert count/rate；
- train/validation graph 数量、node/edge 数量、event rate 和 type distributions；
- 每套 decision configuration 及其 resolved artifacts 的 runtime、resource usage 和 execution failure summary。

这些信息不需要 attack labels，可以作为 Agent 选择初始 configuration 和理解 test-time drift 的 reference。不同 PIDS 的 loss/score 定义可能不同，Episode Memory 必须同时记录 metric definition、PIDS 和 configuration，不能把不可比的原始数值直接排序。

### 10.2 LTM 后续扩展

Long-Term Experience Memory 不进入第一版实现依赖。后续版本可以从 Agent training environments 构造静态、held-out 只读的经验库，存储 environment signature、observable situation、结构化 action、适用条件和部署可见 outcome 摘要。

保留 LTM 的研究问题是：

> 当 LLM 已经在 training environments 上完成 SFT 后，显式检索具体历史经验是否仍能提高 held-out environments 上的长期决策质量？

后续必须通过 `SFT LLM without LTM` 与 `SFT LLM with LTM` 消融回答，不能把 configuration/artifact registry 当成 LTM，也不能把 hidden labels 或 label-derived metrics写入 deployable LTM。

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
- 什么时候保持、调整 configuration 或 fallback；
- 应调整哪个 PIDS-specific decision unit；
- 应从该 decision unit 中选择哪个合法 value；
- 如何输出修改后的完整 target configuration；
- 使用 observation 中真实存在的 evidence；
- 理解 action 的生效时间和成本。

Harness orchestration、XML/JSON parsing、配置 membership、compatibility validation、tool execution、Memory 更新和 hidden evaluator 不由 SFT 学习。

### 11.3 Offline trajectory 构造

只在 Agent training environments 上执行：

1. 按冻结的结构化配置空间实例化多个 PIDS/train/threshold decision configurations，并由 Harness 准备其 checkpoint/threshold artifacts；detector seed 固定为 42。
2. 在 training-environment test streams 上运行不同 configurations 和切换序列。
3. 使用 hidden labels、完整 outcomes 和 controlled counterfactuals 生成 teacher thought/action。
4. 从 observation、thought 和可部署 context 中删除 privileged fields。
5. 每个 controlled group 一次只改变一个 decision unit，并标注该 unit、目标 value 和完整 target configuration。
6. 把所有配置值转换为当时 configuration space 中存在的显式选择。
7. 生成与运行时一致的单状态 XML transcript；每个 target 恰好包含一个 tool call。
8. 按 environment/scenario/run group 划分 SFT train 和 validation。

Offline run table 可以保存 hidden teacher/evaluation fields，但该表不得在 held-out deployment 中被 Agent 查询。

### 11.4 SFT sample

| Part | 内容 |
|---|---|
| System | Agent role、XML grammar、tool definitions、安全边界 |
| Input | 当前 XML observation、有限 configuration space、Working/Episode Memory、previous tool response |
| Target | XML `agent_response`：grounded thought + exactly one tool call |
| Teacher only | attack chain、labels、TP/FP/FN、coverage、MCC、ADP 和 counterfactual outcomes |

### 11.5 SFT 质量指标

- XML parse-valid rate；
- exactly-one-tool-call rate；
- tool JSON/schema-valid rate；
- configuration-space membership rate；
- decision-unit accuracy；
- target-value 和 complete-target-configuration accuracy；
- declared-unit/actual-diff consistency rate；
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

1. 固定 train/validation/test temporal boundaries；任何需要拟合的 transformation/featurization 只使用允许的 train 数据拟合，再确定性应用到 validation/test；
2. 对评估前声明的每个合法 train configuration，使用固定 `seed: 42` 执行一个 Train epoch并更新权重；
3. 每个 Train epoch 后立即在 validation split 上执行无梯度 Validation pass，记录 validation loss 并更新 best-checkpoint selection state；
4. 重复 `Train epoch -> Validation pass`，按冻结的 selection rule 选出该 train configuration 的 final checkpoint；
5. 使用每个 final checkpoint 在 benign validation split 上执行独立 inference，生成 score distribution、benign reference，并为三个合法 method（以及 `validation_quantile` 的每个合法 value）解析 threshold artifact；
6. 记录 train/validation 可见指标、checkpoint manifest、runtime、resource profile 和 failure；
7. 构造该 environment 的有限、条件化 configuration space，以及每套结构化配置到 checkpoint/threshold artifact 的映射；
8. 冻结所有 artifacts、schema 和选择空间，正式 test 期间不再训练、选择 checkpoint 或解析新 threshold；
9. Harness 构造 initialization observation；
10. 由同一 Harness + 当前实验 LLM 调用 `switch_configuration`，使用 `initial_configuration` decision unit 选择完整初始 configuration；
11. Harness 校验该 configuration 后，将其解析到预生成 checkpoint 和 threshold artifact，形成初始 committed execution configuration。

这个流程不由 Agent 训练 PIDS。Agent 只选择结构化 configuration；checkpoint 和 resolved threshold 始终由 Harness resolver 映射。

### 12.2 正式 test deployment

Test graphs 严格按时间顺序处理。正式结果只使用在线 committed outputs。Agent 始终看不到 test labels，不能根据当前检测指标回写或选择 configuration。

### 12.3 主目标

Attack-level coverage 是可行性硬约束：

```text
attack_coverage = detected_attack_campaigns / total_attack_campaigns
```

若 `attack_coverage < 100%`，该 run 对主约束记为 infeasible，但仍报告所有指标。在满足 coverage 的 runs 中，比较 committed node-level precision、recall、MCC 以及规定的 Agent 使用成本。

不使用 held-out labels 扫描 threshold 生成主结果。Oracle threshold curve 只能作为明确标记的 post-hoc diagnostic upper bound。

### 12.4 Label-dependent committed-output metrics

以下指标需要 hidden ground-truth labels，只能由 episode 结束后的独立 evaluator 基于正式 committed outputs 计算：

- TP、FP、FN、TN；
- node-level precision、recall 和 MCC；
- attack-level coverage；

这些指标不能出现在 Agent observation、Working Memory、Episode Memory、LLM context、tool response 或 configuration selection 中。

### 12.5 Train/validation label-free reference metrics

Train/validation split 上可以得到且不依赖 attack labels 的统计，包括 train/validation loss、benign score distributions、quantiles、threshold artifacts、benign alert count/rate、graph/workload profile、runtime 和 resource/failure summary。

这些统计用于初始化 Episode Memory 和构造 Agent observation，帮助 LLM把 test-time 无标签状态与 benign reference 比较。它们不是最终检测性能指标，不能与 TP、FP、FN、TN、precision、recall、MCC 或 attack-level coverage 混写。

### 12.6 每个 environment 的 Agent 报告指标

每个 evaluation environment 只要求汇总报告：

- TP、FP、FN、TN；
- node-level precision、recall 和 MCC；
- attack-level coverage；
- input/output/total tokens；
- tool call count（总数及三个工具分别的调用次数）；
- LLM thinking latency。

`LLM thinking latency` 定义为 Harness 发出 LLM request 到收到完整 LLM response 的时间，不包含 PIDS inference、XML parsing 或 tool execution。除逐调用 trace 外，每个 environment 至少报告 total、mean、p50 和 p95 latency。

### 12.7 Baselines 与消融

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

不得静默切换 provider 或 LLM，也不得绕过 validated `switch_configuration`/fallback 改变 committed configuration 或其 resolved artifacts。Generated data、checkpoints、logs 和 run outputs 不进入 Git。

## 14. 第一版实现顺序

1. 定义 environment、checkpoint manifest、threshold artifact 和条件 configuration-space schemas。
2. 定义 observation、Working Memory、Episode Memory 和 privileged-data sanitization contracts。
3. 定义 XML context/agent-response/tool-response grammar 和安全 Parser。
4. 定义 typed tool requests、configuration membership/compatibility validator 和 deterministic fallback。
5. 迁移 PIDSMaker node-level subset，并记录 upstream provenance 和 material changes。
6. 实现 15 分钟 graph-level inference、node scoring 和 committed output protocol。
7. 实现 checkpoint preparation、validation selection 和 threshold resolution pipeline。
8. 实现 `graphs_per_state` 调度、每状态一次 LLM 调用和上下文回填。
9. 实现 Working Memory 和 Episode Memory；第一版不实现 LTM。
10. 构造 offline run table、XML SFT trajectories 和 leakage/format quality checks。
11. 训练并验证 SFT LLM。
12. 在 held-out evaluation environments 上执行端到端评估、baselines 和消融。

## 15. 实现前仍需冻结的配置

以下属于待配置项，不改变本文架构边界：

- 每个 PIDS 的 train decision units、threshold value spaces、allowed values、coupled fields 和完整合法配置树；
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
