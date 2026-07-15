版本：v0.4（固定 Memory Harness + SFT 读写利用策略实现稿）

状态：已统一 construction-graph step、事件触发双路径、C=100% 硬约束、TP evidence recovery、固定 Memory Harness、SFT 学习 memory 读写与利用策略、受约束 tool API 与 SFT-first 路线。

# 0. 核心结论

本设计将 APT-Detection-Agent 定义为一个 frozen-policy 的 PIDSMaker pipeline controller。第一版先通过监督微调（SFT）学习 observation–diagnosis–action 轨迹；在 held-out evaluation 与部署阶段不在线更新模型权重、不依赖人工反馈，只使用部署可见的无标签信号、当前 PIDSMaker 状态、环境描述和训练阶段构建的可部署 long-term memory 做决策。只有当 SFT 在长期决策、恢复能力或目标优化上暴露明确瓶颈时，才考虑后续 RL。

每个 held-out PIDSMaker dataset 是一个完整 deployment scenario。该 scenario 保留 PIDSMaker 原生 train_dates、val_dates、test_dates 边界：train/val 用于 PIDS 初始化、正常行为参考和阈值校准；test_dates 按时间顺序展开为 construction time-window graphs。每张 construction graph 构成一个 agent observation/detection step。Agent 每步都提交检测输出，但只在事件触发或周期检查时调用完整 LLM 慢路径并执行重配置。

系统目标是在 attack-level coverage=100% 的硬约束下，同时提高 node-level precision、TP/真实攻击证据恢复能力与 MCC，降低 FP、检测延迟和系统成本。Token 使用只作为预算与效率评价指标，不进入第一版训练目标。

| **设计项**             | **v0.3 当前决定**                                                                                                                                                                                  |
|------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Agent step             | 每张 PIDSMaker construction time-window graph 为一个 observation/detection step。                                                                                                                  |
| Reasoning frequency    | Fast path 每图运行；Slow path 仅由无标签事件触发或周期 checkpoint 调用。                                                                                                                           |
| Detection objective    | C=100% 为硬约束；同时提高 P@C=100%、TP/证据恢复和 MCC，降低 FP/FN。                                                                                                                                |
| Memory                 | 按生命周期分 Working / Episode / Long-Term；存储与检索机制由 harness 固定，SFT 学习何时读、如何检索、如何利用以及何时/写入什么。训练可利用攻击链特权信息，部署只暴露蒸馏后的环境与可观察行为经验。 |
| Tools                  | Agent 通过受约束、stage-aware 的 tool API 操作 PIDSMaker，不直接生成任意 CLI。                                                                                                                     |
| multi_dataset_training | 第一版不进入 action space；仅作为固定实验因素、环境元数据和 memory information。                                                                                                                   |
| Training route         | 先做 SFT；通过完整 held-out end-to-end 评估判断是否需要 RL。                                                                                                                                       |
| Token usage            | 完整报告，但不进入第一版 reward/objective。                                                                                                                                                        |

# 1. 背景、任务边界与研究目标

PIDSMaker 是用于构建和比较 provenance-based intrusion detection systems（PIDSs）的统一框架。它将系统 provenance logs 构造成时间图，在 benign train/validation data 上学习正常行为，并在 test period 上输出 anomaly scores 与 thresholded alerts。

本研究不把问题简化为“为一个 dataset 搜索一次最佳配置”，而是研究：如何训练一个 LLM-based agent，在按时间到达的 provenance construction graphs 上，以标签不可见方式持续运行 PIDSMaker，判断何时保持当前配置、何时调整阈值、切换 tuned PIDS、重训或执行资源恢复，并把检测性能、证据恢复、运行成本和 token 使用统一纳入实验评价。

Research problem:

Given a PIDSMaker scenario with native train/validation/test partitions,

train a frozen, label-blind, environment-aware and stage-aware controller that

performs construction-graph-level detection and event-triggered reconfiguration,

subject to complete attack-campaign coverage.

目标采用层级约束，而不是把所有指标粗暴压成同一标量：

1.  硬约束：attack-level coverage=100%，即每个 attack campaign 至少命中一个真实恶意节点。

2.  检测质量：在满足 coverage 的结果中，提高 P@C=100%、TP、node-level recall 和 MCC，降低 FP 与 FN。

3.  证据恢复：更多 TP 不仅意味着发现攻击，还意味着恢复更完整的恶意实体和因果证据。

4.  效率：控制 PIDSMaker stage rerun、runtime、资源失败、LLM calls 和 token usage；token 只评价，不进入第一版训练目标。

# 2. PIDSMaker 边界与数据使用方式

## 2.1 Pipeline 边界

PIDSMaker 包含 construction、transformation、featurization、batching、training、evaluation、triage 七个阶段。第一版排除 triage，只控制前六个 detection-relevant stages。PIDSMaker 基于阶段参数和上游依赖生成 hash 并缓存输出，因此不同动作具有不同的 stage invalidation、cache reuse 和计算成本。

| **Stage**                | **PIDSMaker 含义**                                  | **第一版 Agent 边界**                                                    |
|--------------------------|-----------------------------------------------------|--------------------------------------------------------------------------|
| 1\. Construction         | 解析 raw provenance，按 time_window_size 构造时间图 | 固定为 scenario 配置；第一版不作为常规在线动作，仅做离线消融或高级恢复。 |
| 2\. Transformation       | 图结构与属性转换                                    | 第一版固定；后续扩展。                                                   |
| 3\. Featurization        | 实体/文本属性表示                                   | 第一版由 validated config 或 tuned PIDS 固定；不允许任意组合。           |
| 4\. Batching             | 组织 temporal graph/model input                     | 仅资源恢复时允许有限调整。                                               |
| 5\. Training             | 训练或重训 PIDS                                     | Slow path 可调用，使用 train/val 边界。                                  |
| 6\. Evaluation/Inference | 生成 anomaly scores 与 thresholded alerts           | 每图执行；阈值调整是第一版核心动作。                                     |
| 7\. Triage               | 攻击追踪与后处理                                    | 第一版排除。                                                             |

## 2.2 两层数据划分

PIDSMaker 文档中的 train/validation/test 是单个 dataset 内供 PIDS 使用的数据划分，不是 agent-level 的训练/测试划分。Agent-level split 是跨 dataset 的：agent-training datasets 用于生成 SFT 数据、offline run table 和 memory；held-out datasets 用于评估 frozen agent 对新环境的泛化。

| **层级**       | **分区**          | **用途**                                             | **Agent 可见性**                                          |
|----------------|-------------------|------------------------------------------------------|-----------------------------------------------------------|
| PIDSMaker 内部 | train_dates       | benign graphs，用于训练 PIDS                         | 可见；无攻击标签指标。                                    |
| PIDSMaker 内部 | val_dates         | benign graphs，用于阈值校准与正常参考                | 可见；无 TP/FP/ADP/MCC。                                  |
| PIDSMaker 内部 | test_dates        | 含 benign 与 attacks 的 deployment/evaluation period | provenance、score、alerts 可见；ground truth 不可见。     |
| Agent-level    | training datasets | 构造 SFT、counterfactual runs、memory                | hidden labels 与完整攻击链可作为 privileged supervision。 |
| Agent-level    | held-out datasets | 评估 frozen agent 泛化                               | labels 只给 post-hoc evaluator。                          |

## 2.3 train/val 上可获得的信号

train_dates 与 val_dates 是 benign data。Agent 可以获得 training/validation loss、benign score distribution、score quantiles、图规模、稳定性、运行时间、OOM 与资源占用，但不能获得 TP、FP、FN、attack coverage、ADP、MCC 或 P@C=100%。这些标签依赖指标只能由 agent-training 环境中的 hidden teacher/evaluator 或 held-out episode 结束后的 post-hoc evaluator 计算。

# 3. Construction-Graph-Level Deployment Protocol

## 3.1 Agent step

每张 PIDSMaker construction time-window graph 直接构成一个 agent observation/detection step。若 construction.time_window_size=15 分钟，则每 15 分钟进入一个新 step。该边界由 PIDSMaker 的自然时间图定义，不依赖 attack_to_time_window 或任何隐藏标签。

At step t:

input: construction graph G_t + historical state + deployable memory

default: KEEP_AND_INFER with the persistent committed configuration

output: committed alerts for G_t

optional: trigger slow-path diagnosis and stage-aware reconfiguration

“每张 graph 是一个 step”不等于“每张 graph 都重新选择模型”。配置跨 step 持续生效，默认行为是沿用当前配置完成 inference。只有无标签 trigger 或固定 checkpoint 到达时，才调用完整 LLM diagnosis 与重配置。

## 3.2 Fast path / Slow path

| **路径**  | **每张 graph 是否执行** | **主要操作**                                              | **LLM 成本**                   |
|-----------|-------------------------|-----------------------------------------------------------|--------------------------------|
| Fast path | 是                      | 更新轻量统计、运行当前 PIDS、提交 alerts、检查 trigger    | 默认不调用主 LLM。             |
| Slow path | 否；事件触发/周期检查   | 检索 LTM、完整诊断、调用受约束工具、更新 committed config | 记录完整 input/output tokens。 |

触发器只使用部署可见信号，例如 score distribution shift、alert volume 异常、连续窗口状态变化、OOM/timeout、degenerate outputs、周期性健康检查或 memory 中的风险条件。触发规则在 held-out evaluation 前固定，不能使用当前 test labels。

## 3.3 Scenario phases

| **阶段**       | **可见输入**                                                        | **行为**                                                  | **禁止事项**                     |
|----------------|---------------------------------------------------------------------|-----------------------------------------------------------|----------------------------------|
| Phase 0 初始化 | train/val、环境描述、training-set LTM                               | 训练/加载初始 PIDS，建立 benign reference，校准 threshold | 查看 test labels。               |
| Phase 1 部署   | 按时间到达的 construction graph、无标签 scores/alerts/runtime/cache | Fast path 每图检测；触发时 Slow path 重配置；每图提交结果 | 用当前 test TP/FP/ADP/MCC 调参。 |
| Phase 2 评价   | 全部 committed outputs + hidden ground truth                        | Evaluator 汇总检测性能、效率、token 和系统指标            | Agent 不参与。                   |

# 4. 检测目标与实验指标

## 4.1 Primary constrained objective

attack_coverage = detected_attack_campaigns / total_attack_campaigns

precision = TP / (TP + FP)

Primary constraint: attack_coverage = 100%

Quality objectives after feasibility: increase P@C=100%, TP, recall and MCC; reduce FP and FN

Held-out evaluation 期间 agent 不知道 coverage、TP 或 FP；这些由隐藏 evaluator 在 episode 结束后计算。若 coverage\<100%，该 episode 对主目标标记为 infeasible，但仍报告全部辅助指标。

## 4.2 检测性能指标

| **指标**               | **角色与解释**                                                                        |
|------------------------|---------------------------------------------------------------------------------------|
| P@C=100%               | 主指标：覆盖全部 attack campaigns 时的 node-level precision。                         |
| TP / FP / FN / TN      | 对所有 committed graph outputs 汇总的 node-level confusion matrix。                   |
| TP / evidence recovery | 衡量恢复的真实恶意实体与证据节点数量；是明确优化目标。                                |
| Precision / Recall     | 分别反映告警质量和恶意节点恢复范围。                                                  |
| Attack coverage        | attack-level 可行性硬约束。                                                           |
| MCC                    | 类别不平衡下的整体二分类质量。                                                        |
| ADP                    | threshold-independent detection/ranking potential；用于分析模型能力与阈值交付的差异。 |
| Per-campaign detection | 逐 campaign 命中、首次命中和检测延迟。                                                |
| Alert volume / FP rate | 安全分析负担与告警洪泛程度。                                                          |
| Stability              | 跨 seed、跨窗口或重复运行的波动。                                                     |

## 4.3 Agent 与系统效率指标

| **类别**              | **指标**                                                                                                         |
|-----------------------|------------------------------------------------------------------------------------------------------------------|
| LLM usage             | Total input/output/total tokens、LLM calls、tokens per graph、tokens per slow decision、maximum context length。 |
| PIDSMaker cost        | 总 runtime、GPU/CPU memory、PIDSMaker calls、各 stage rerun 次数。                                               |
| Control behavior      | Slow-path trigger 次数、重配置次数、model switches、threshold changes、retraining count。                        |
| Cache efficiency      | cache hit/reuse rate、避免的上游重算、stage invalidation cost。                                                  |
| End-to-end efficiency | scenario wall-clock、达到 C=100% 时的 detection–cost–token trade-off。                                           |

Token usage 只作为预算约束和实验评价指标，不进入第一版 SFT objective 或未来 reward。评估前可固定 max LLM calls、max context length 和 total token budget。

# 5. Agent 总体架构与 Observation

Offline training:

agent-training datasets

-\> controlled PIDSMaker runs + privileged attack-chain analysis

-\> offline run table + weak diagnosis labels

-\> privileged-to-deployable experience distillation

-\> SFT trajectories + static task-aware LTM

Held-out deployment:

train/val initialization

-\> construction-graph fast path

-\> event-triggered slow-path tools

-\> persistent committed configuration

-\> per-graph committed alerts

-\> post-hoc evaluator

## 5.1 Observation schema

| **Observation block**       | **内容**                                                                                                                                          |
|-----------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------|
| Environment profile         | dataset/scenario、OS/platform、provenance schema、node/edge types、graph规模/密度、event rate、normal-workload statistics、resource constraints。 |
| Current graph               | node/edge counts、entity/relation distributions、time span、structural statistics。                                                               |
| Pipeline state              | current PIDS/config/threshold、checkpoint、stage cache、last training/inference status。                                                          |
| Unlabeled detection signals | score distribution、tail mass、alert volume、trend/shift/degeneracy/instability proxies。                                                         |
| Memory retrieval            | 环境兼容的历史经验、可观察行为模式、PIDS capability、诊断、适用与失败条件。                                                                       |
| Efficiency state            | remaining budget、runtime、cache opportunities、token usage so far。                                                                              |

当前攻击身份、攻击时间、恶意节点、attack_to_time_window、当前 TP/FP/ADP/MCC 不进入 held-out observation。

# 6. Memory 架构：生命周期、环境感知与特权知识蒸馏

## 6.1 为什么不按 success/failure/environment/config 四种语义类型拆分

简单按内容语义拆 memory 不能决定生命周期、更新频率、索引方式、冲突处理或是否可进化；同一条经验通常同时包含环境、配置、诊断、动作和结果。因此 v0.4 延续删除旧版的 Negative Memory、Configuration Memory 等并列类型，改为按生命周期与抽象层级组织。success/failure、PIDS、diagnosis、outcome 等作为 record fields 和检索过滤条件。

## 6.2 三层生命周期

| **层级**                    | **生命周期与内容**                                                       | **更新/索引**                                      | **第一版实现**                                                                  |
|-----------------------------|--------------------------------------------------------------------------|----------------------------------------------------|---------------------------------------------------------------------------------|
| Working Memory              | 最近 N 张 construction graphs、当前 config、scores/alerts、trigger、预算 | 高频滚动；scenario_id + timestamp                  | 实现。                                                                          |
| Episode Memory              | 当前 scenario 的环境画像、趋势、已尝试动作、配置与失败摘要               | 从 Working Memory 周期归纳；可修正                 | 实现轻量摘要。                                                                  |
| Long-Term Experience Memory | 跨 training scenarios 的环境—行为—PIDS 适配经验、适用条件、置信度        | 结构化过滤 + 数值相似 + 语义重排；可合并/降权/淘汰 | 第一版静态：固定 schema、索引、检索与 top-k；SFT 仅学习使用策略；演化后续实现。 |

## 6.3 Memory 学习的核心不是“攻击类型 → PIDS”

训练阶段可以看到完整攻击链和标签，但应学习三方适配关系：

PIDS suitability = f(Environment characteristics, Attack/behavior manifestation, PIDS capability)

Deployment action = f(Environment, Observable behavior, PIDS capability, Historical experience)

不同数据集可能环境相似，也可能在 OS、provenance schema、图规模/密度、事件速率、normal workload、feature vocabulary、资源约束上显著不同。即使攻击链相似，历史 PIDS 结论也不能无条件复用。Agent 应先判断环境兼容性，再判断当前可观察行为是否需要某种 PIDS 能力。

| **信息块**              | **训练阶段可用信息**                                                           | **部署阶段可用形式**                                                         |
|-------------------------|--------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| Environment profile     | 真实 dataset/scenario 属性与统计                                               | 直接可见，作为首要过滤与索引。                                               |
| Attack/behavior profile | 完整攻击链、phase、恶意节点、causal span、cross-window span、entity dispersion | 只保留由当前无标签 graph/score 可推断的 observable behavior representation。 |
| PIDS capability/outcome | 各 PIDS/config 的 TP/FP/coverage/ADP/MCC、延迟、成本、稳定性                   | capability tags、适用/失败条件、部署可见 outcome summary。                   |

## 6.4 Privileged-to-Deployable Experience Distillation

在 agent-training datasets 上，memory constructor 可以利用完整攻击链、攻击标签和不同 PIDS/config 的 counterfactual outcomes，发现“某种环境 + 某种攻击表现形态 + 某种 PIDS 能力”的适配规律。但原始 attack identity、malicious nodes、attack times 和 label-derived metrics 属于 privileged fields，只用于 teacher、pseudo-label 和 offline analysis。进入 agent prompt 的 deployable memory 必须经过 sanitization。

Privileged record (training only):

attack chain + labels + per-PIDS TP/FP/coverage/ADP/MCC

-\> derive environment/behavior/capability compatibility

Deployable memory (agent-visible):

environment signature + observable pattern + diagnosis + recommended action

\+ applicability/failure conditions + confidence

## 6.5 LTM record 与检索

| **字段组**          | **主要字段**                                                                                                                           |
|---------------------|----------------------------------------------------------------------------------------------------------------------------------------|
| Environment         | OS/platform、schema、graph scale/density、event rate、node/edge distributions、normal-workload statistics、resource profile。          |
| Observable behavior | temporal persistence、cross-window change、entity dispersion、score clustering/tail、graph structural shift。                          |
| PIDS capability     | temporal/local structural modeling、evidence granularity、scalability、feature dependence、threshold sensitivity、latency。            |
| Experience          | visible symptom、diagnosis、action、stage invalidation、deployable outcome、applicability/avoid conditions、confidence/support count。 |

5.  环境兼容性门控：先按 OS/schema/PIDS support/resource constraints 过滤或强降权。

6.  数值/结构相似：比较 graph scale、density、event rate、entity distributions、score trends。

7.  行为与能力匹配：比较当前 observable pattern 需要的能力与 PIDS capability。

8.  经验置信度重排：综合 support count、success/failure、stability、cost 和 last verified。

第一版实现 Working Memory + 轻量 Episode Summary + 静态 LTM。Memory 的存储结构、索引、检索、过滤、top-k、去重、容量控制、sanitization 与持久化均由 harness 固定实现；SFT 只学习何时读、如何构造 query、如何利用结果、何时写以及写入什么。自动学习 retriever、在线修改检索权重、冲突解析、置信度进化、遗忘与降权保留为后续扩展。

## 6.6 固定 Memory Harness 与 SFT 学习策略的实现边界

第一版将 memory 明确实现为 agent harness 的外部固定模块，而不是可端到端训练的神经记忆。系统由“固定存储/检索机制”和“SFT 学习的 memory 使用策略”两部分组成：

Fixed memory mechanism + SFT-learned memory read/write/use policy

| 组件                   | 第一版实现方式                                                        | 是否由 SFT 学习     |
|------------------------|-----------------------------------------------------------------------|---------------------|
| Memory schema          | 固定字段、类型约束、privileged/deployable 字段隔离                    | 否                  |
| Storage backend        | 固定数据库/文件布局、scenario namespace、持久化规则                   | 否                  |
| Retrieval pipeline     | metadata gate → numeric similarity → semantic reranking → fixed top-k | 否                  |
| Index/embedding        | 固定 embedding model、numeric normalization、索引更新方式             | 否                  |
| Capacity/cleanup       | 固定窗口长度、去重、容量上限、TTL/归档策略                            | 否                  |
| Read policy            | 是否读取、检索目标、query 字段和过滤条件                              | 是                  |
| Use policy             | 是否采纳、降权或忽略 retrieved memories，并据此形成 diagnosis/action  | 是                  |
| Write policy           | 是否写入、目标层级、写入字段、置信度与适用条件                        | 是                  |
| Actual write execution | schema 校验、sanitization、去重、namespace 检查、持久化               | 否，由 harness 执行 |

### 运行时读取流程

1\. LLM 根据当前 observation 输出 memory_read_request，包括 need_read、query intent、environment filters、observable symptom、current PIDS 和 requested top-k。

2\. Harness 校验请求，只保留白名单字段，并执行固定环境兼容性门控、数值相似度和语义重排。

3\. Harness 返回带 provenance_id、confidence、applicability_conditions 和 failure_conditions 的 top-k deployable memories。

4\. LLM 输出 memory_use_decision，逐条标记 use / downweight / ignore，并给出仅基于部署可见证据的理由。

5\. 最终 diagnosis/action 必须引用被采纳的 memory IDs；检索结果不能直接等价于最终动作。

### 运行时写入流程

1\. LLM 输出 memory_write_candidate，指定 target_layer（working/episode/ltm_candidate）、write_reason、record、confidence 和 applicability_conditions。

2\. Harness 删除攻击身份、恶意节点、攻击时间、TP/FP/coverage/ADP/MCC 等部署不可见字段。

3\. Harness 执行 schema 校验、长度限制、重复检测、scenario namespace 检查和低置信度拒绝。

4\. Working/Episode Memory 可在当前 scenario 内写入；永久 LTM 只在 agent-training/validation 阶段离线 consolidation 后更新。

5\. Held-out scenario 的 episode memory 默认隔离，episode 结束后归档或删除，不污染后续独立 scenario。

### SFT 输出 schema（第一版）

{

"path_decision": "FAST_PATH \| SLOW_PATH",

"memory_read_request": {"needed": true, "query": {...}, "filters": {...}, "top_k": 5},

"memory_use_decision": \[{"memory_id": "...", "decision": "use\|downweight\|ignore", "reason": "..."}\],

"diagnosis": "...",

"action": {"tool": "...", "arguments": {...}},

"memory_write_candidate": {"should_write": true, "target_layer": "episode", "record": {...}},

"confidence": 0.0,

"fallback": "..."

}

该设计意味着第一版不训练 learned retriever、memory embedding、similarity weights、top-k、schema、淘汰规则或在线 memory evolution。若 SFT 结果证明 memory 检索质量是主要瓶颈，再把 retriever learning 或 memory adaptation 作为后续独立研究问题。

# 7. 受约束的 PIDSMaker Tool API

Agent 不直接生成任意 PIDSMaker CLI 或任意参数组合，而是调用具备 schema 校验、候选集合、stage invalidation 和 cache reuse 信息的结构化工具。Tool 不是每个 CLI 参数一个函数，而是按观察、memory、执行和受控重配置组织。

## 7.1 Observation tools

| **Tool**                  | **作用**                                                     | **返回边界**             |
|---------------------------|--------------------------------------------------------------|--------------------------|
| get_environment_profile   | 读取 scenario 静态环境画像                                   | 不返回攻击标签/时间。    |
| get_current_graph_summary | 当前 construction graph 的节点、边、类型、密度、事件速率等   | 无标签结构统计。         |
| get_recent_trend          | 计算最近 N 图的 graph/score/alert shifts                     | 用于 fast-path trigger。 |
| get_active_pids_state     | 当前 PIDS、config、threshold、checkpoint、stage hashes/cache | 部署可见状态。           |
| get_training_summary      | train/val loss、stability、runtime、resource                 | 不返回 test metrics。    |
| get_score_summary         | 当前/近期 score quantiles、tail mass、alert count/ratio      | 不返回 TP/FP。           |

## 7.2 Memory tools

| **Tool**                     | **作用**                                        | **第一版策略**                                                                                      |
|------------------------------|-------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| retrieve_similar_experiences | 按环境门控、行为相似和 PIDS capability 检索经验 | 启用；固定 metadata gate、numeric similarity、semantic reranking 与 top-k。LLM 只生成受约束 query。 |
| write_episode_memory         | 记录当前 scenario 的部署可见状态与动作          | 启用；LLM 生成候选 record，harness 做 schema 校验、字段清洗、去重和实际写入。                       |
| summarize_episode_memory     | 把滚动状态压缩为 episode summary                | 启用；SFT 学习摘要内容选择，harness 固定触发时机、长度上限和存储位置。                              |
| consolidate_to_ltm           | 把 episode experience 写入永久 LTM              | 第一版仅 agent-training/validation 离线执行并审核；held-out episode 不写永久 LTM。                  |

## 7.3 Execution and reconfiguration tools

| **Tool**               | **作用**                                                              | **成本/边界**                        |
|------------------------|-----------------------------------------------------------------------|--------------------------------------|
| run_current_pids       | 使用 persistent committed config 对当前 graph inference 并提交 alerts | 每图 fast path。                     |
| adjust_threshold       | 从 validated threshold candidates 中选择/校准                         | 低成本；evaluation/inference stage。 |
| load_tuned_config      | 加载 PIDSMaker 已验证 tuned PIDS/config                               | 低至中成本；按模型影响 stage。       |
| switch_pids            | 切换到另一 validated PIDS/checkpoint                                  | 中成本；禁止自由神经架构搜索。       |
| retrain_current_pids   | 在 train/val 边界上重训当前 PIDS                                      | 高成本 slow path。                   |
| run_repeated_training  | 多 seed 运行以诊断 instability                                        | 高成本；训练/离线优先。              |
| adjust_resource_config | 有限调整 batching、hidden dim 等资源参数                              | 仅 OOM/资源失败恢复；离散候选。      |

## 7.4 第一版暂不开放

- 任意 construction/time_window_size 在线搜索；任意 transformation 修改；任意 encoder/objective 组合。

- multi_dataset_training 的动态开启、数据集组合或训练源搜索。

- triage、attack tracing、test-label-based evaluation tool。

- 任意数值参数生成；所有数值动作必须从预验证离散候选中选择。

## 7.5 第一版决策动作

| **Action**             | **映射工具**               | **说明**                                 |
|------------------------|----------------------------|------------------------------------------|
| KEEP_AND_INFER         | run_current_pids           | 默认动作。                               |
| INVOKE_SLOW_DIAGNOSIS  | observation + memory tools | 触发完整诊断，但不必立即重配置。         |
| ADJUST_THRESHOLD       | adjust_threshold           | 优先处理阈值交付问题。                   |
| LOAD_TUNED_CONFIG      | load_tuned_config          | 复用验证过的配置。                       |
| SWITCH_PIDS            | switch_pids                | 模型能力/环境不匹配时切换。              |
| RETRAIN_CURRENT_PIDS   | retrain_current_pids       | 现有 checkpoint 不适用或稳定性不足。     |
| ADJUST_RESOURCE_CONFIG | adjust_resource_config     | OOM、超时或 batching/resource mismatch。 |
| FALLBACK_OR_STOP       | 回退到稳定 config          | 预算耗尽或工具失败时保证协议可终止。     |

每个 action 统一输出 diagnosis、visible evidence、tool arguments、stage_to_rerun_from、expected_cache_reuse、confidence 和 commit/fallback policy。

# 8. Diagnosis Taxonomy、Offline Run Table 与训练数据

## 8.1 Diagnosis taxonomy

| **粗粒度**              | **细粒度示例**                                            | **证据来源**                                      |
|-------------------------|-----------------------------------------------------------|---------------------------------------------------|
| Viable                  | viable_configuration                                      | 满足 hidden feasibility 且部署信号稳定。          |
| Threshold failure       | threshold_too_tight / threshold_too_loose_or_flood        | controlled threshold counterfactual。             |
| Detection failure       | no_score_separation / model_mismatch / parameter_mismatch | ADP、score overlap、model/config counterfactual。 |
| Representation/resource | featurization_or_batching_mismatch / OOM                  | representation/resource controlled runs 与日志。  |
| Instability             | unstable_scores / undertrained                            | 跨 seed 方差、loss/score 异常。                   |
| Engineering             | timeout / invalid_config / pipeline_failure               | 运行日志。                                        |
| Ambiguous               | ambiguous_failure                                         | 反事实证据不足或多原因同时成立。                  |

标注采用 weak supervision：规则与 controlled counterfactual runs 生成 pseudo-label，必要时由 LLM 生成 rationale，经过一致性检查与小规模人工抽样审核。人工不逐条标注全部数据；不确定样本保留 ambiguous。

## 8.2 Offline run table

Offline run table 是我们在 agent-training/validation datasets 上建立的实验结果数据库，不是 PIDSMaker 官方现成表。它保存 dataset/environment、PIDS/config/seed、visible observations、hidden evaluation、cost、diagnosis 和 counterfactual group，用于生成 SFT 数据、初始化静态 LTM 和快速验证 action。

| **构造环节**                     | **作用**                                                                        |
|----------------------------------|---------------------------------------------------------------------------------|
| Representative runs              | 覆盖主要 PIDS、tuned configs、threshold candidates、少量训练/资源候选和 seeds。 |
| Controlled counterfactual groups | 一次只改变 threshold、PIDS、training 或 resource factor，以支持归因。           |
| Privileged analysis              | 使用完整攻击链和 hidden metrics 分析环境—行为—PIDS 适配。                       |
| Deployable distillation          | 移除 attack identity/labels，生成 agent 可见的环境与行为经验。                  |
| SFT trajectory generation        | 生成 fast/slow trigger、diagnosis、tool/action demonstrations。                 |

Held-out datasets 不能预先建立包含全部 config 和 hidden metrics 的 oracle table 供 agent 查询；正式评估应真实调用 PIDSMaker，或只使用部署本来可用的 cache。

# 9. 第一阶段训练路线：SFT-First

第一版不预设必须使用 RL。首先验证一个任务化 SFT agent 是否能在固定 memory storage/retrieval harness 下，学会 memory read/write/use policy、slow-path trigger、diagnosis 和 tool/action selection。

## 9.1 SFT sample

| **部分**            | **内容**                                                                                                                                          |
|---------------------|---------------------------------------------------------------------------------------------------------------------------------------------------|
| Input               | environment profile、current graph/score trends、current PIDS state、working/episode summary、retrieved deployable memories、budget/cache state。 |
| Target              | path decision、diagnosis、visible evidence、structured tool/action、stage/cache expectation、confidence/fallback。                                |
| Hidden teacher only | attack chain、TP/FP/FN、coverage、ADP/MCC、counterfactual best action；不得直接复制到 input/rationale。                                           |

### 9.1.1 Memory-policy supervision targets

- Read decision：是否需要检索；不需要时避免无效 LLM/memory 调用。

- Query construction：从当前环境、图趋势、PIDS 状态和诊断症状中选择检索字段。

- Retrieval use：对返回经验执行 applicability 判断、冲突处理和证据引用。

- Write decision：只记录未来可复用、部署可见且非冗余的经验。

- Write content：生成符合固定 schema 的 environment–observable behavior–PIDS–action record。

- Safety boundary：拒绝写入 privileged labels、当前 held-out attack identity 或 hidden metrics。

训练样本可采用两阶段 tool-use transcript：模型先生成 memory_read_request，harness 返回固定检索结果；模型再生成 memory_use_decision、diagnosis、action 与可选 write candidate。这样 SFT 学习的是读写和利用策略，而不是模仿一个不存在的可训练 memory 内部状态。

## 9.2 SFT evaluation

| **层级**             | **指标**                                                                                                                                                     |
|----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Schema/tool validity | JSON/schema valid rate、tool argument validity、forbidden-tool rate。                                                                                        |
| Trigger              | slow-path precision/recall、unnecessary LLM-call rate。                                                                                                      |
| Diagnosis            | coarse accuracy、fine macro-F1、ambiguous calibration。                                                                                                      |
| Action               | top-1/top-k action accuracy、stage-aware correctness、cache-aware correctness。                                                                              |
| Memory               | retrieval query validity、relevant retrieval rate、environment compatibility、memory-use correctness、write precision/duplication rate、no-memory ablation。 |
| End-to-end           | P@C=100%、TP/FP/FN/TN、precision/recall/MCC/ADP、delay、tokens、calls、runtime、cache reuse。                                                                |

## 9.3 何时再考虑 RL

- SFT 单步 accuracy 较高，但长期 end-to-end coverage/TP/FP 明显不理想。

- 多个局部合理动作之间需要优化长期 trade-off，SFT 无法稳定选择。

- 分布外状态下错误累积且缺乏恢复能力。

- Memory 已检索正确经验，但 action 利用不稳定。

- 需要显式优化延迟或 stage cost，而模仿数据不足以提供信号。

只有出现上述可验证瓶颈，才进入 RFT/DPO/GRPO/GDPO 等后续路线比较；v0.4 不把任何 RL 方法写成既定方案。

# 10. 预期技术创新点

| **Innovation**                                 | **具体内容**                                                                           | **任务特异性**                                        |
|------------------------------------------------|----------------------------------------------------------------------------------------|-------------------------------------------------------|
| Constrained evidence-oriented objective        | C=100% 硬约束下联合关注 P@C、TP/evidence recovery、FP/FN 与 MCC                        | 避免只命中每个 campaign 一个节点却忽视攻击链证据。    |
| Environment–Behavior–PIDS Compatibility Memory | 利用训练攻击链和多 PIDS outcomes 学习三方适配，并蒸馏为部署可见经验                    | 解决不同 dataset 环境差异导致的经验误复用。           |
| Privileged-to-Deployable Distillation          | 完整攻击链仅用于 teacher/memory construction；部署 memory 移除攻击身份和 label metrics | 保留攻击监督价值同时避免 held-out 泄漏。              |
| Stage-Aware Tool Control                       | 工具绑定 pipeline stage、cache reuse、validated candidates 和成本                      | 直接利用 PIDSMaker staged pipeline。                  |
| Event-Triggered Hierarchical Reasoning         | 每图 fast path，只有变化/检查触发 slow-path LLM                                        | 解决高频 provenance graph 与 token/context 成本矛盾。 |
| Weak Diagnosis Supervision                     | controlled runs + pseudo-label + 少量人工审核                                          | 把失败归因转为可训练任务。                            |

# 11. 实验设计与 Baselines

| **实验维度**            | **当前方案**                                                                                                                             |
|-------------------------|------------------------------------------------------------------------------------------------------------------------------------------|
| Agent-level split       | 跨 PIDSMaker datasets 划分 training/validation/held-out scenarios。                                                                      |
| Scenario initialization | 使用该 dataset 的 train/val 训练或加载 PIDS、校准 threshold、建立 benign reference。                                                     |
| Deployment step         | 每张 construction time-window graph 一个 step。                                                                                          |
| Decision policy         | Fast path 每图运行；Slow path 由固定无标签 trigger 或周期 checkpoint 调用。                                                              |
| multi_dataset_training  | 第一版为预先固定实验因素和 environment/memory field；不进入 action space。                                                               |
| Primary result          | Coverage=100% feasibility + P@C=100%；同时强调 TP/evidence recovery。                                                                    |
| Detection metrics       | TP/FP/FN/TN、precision、recall、coverage、MCC、ADP、per-campaign detection、delay、alert volume、stability。                             |
| Agent/system metrics    | tokens、LLM calls、context length、PIDSMaker runtime/calls、reconfiguration、cache reuse、wall-clock。                                   |
| Baselines               | static tuned PIDS、validation-selected config、rule-only controller、SFT no-memory、SFT no-diagnosis、always-slow-path、full SFT agent。 |

关键消融包括：无 environment gate、只按 semantic similarity 检索、无 privileged attack-chain distillation、无 PIDS capability profile、无 Episode Memory、无 trigger（always-slow）和静态 PIDS。

# 12. 已确认边界、尚待实现决策与一致性审计

## 12.1 已确认

- 每张 construction graph 是一个 observation/detection step；配置 persistent。

- 每图提交 alerts；默认 KEEP_AND_INFER，Slow path 只由无标签 trigger/checkpoint 调用。

- C=100% 是硬约束；目标显式包含提高 TP/true-positive evidence recovery。

- 完整报告检测性能、PIDSMaker 成本、LLM token/context 和控制行为。Token 不进入第一版 objective。

- Memory 按 Working/Episode/LTM 生命周期组织；存储、索引与检索机制由 harness 固定，SFT 学习 read/query/use/write policy。

- 训练可使用完整攻击链和 label-derived outcomes；部署 prompt 只使用环境、可观察行为和蒸馏经验。

- 经验复用以环境兼容性为门控，并结合 observable behavior 与 PIDS capability。

- 第一版使用受约束 tool API；multi_dataset_training 不进入 action space；triage 排除。

- 训练路线为 SFT-first；是否加 RL 由 SFT 的可验证瓶颈决定。

## 12.2 尚待实现前确定

- 第一版支持的具体 PIDS/tuned configs、threshold candidates 和 resource adjustment 候选集合。

- Fast-path trigger 的无标签统计、窗口长度、阈值与周期 checkpoint。

- Offline run table 的 PIDS/config/seed 覆盖范围与计算预算。

- Environment profile、observable behavior profile 和 PIDS capability profile 的最终字段与归一化。

- SFT base model、数据规模、train/validation/held-out dataset split 与生成质量控制。

- 固定 memory backend、embedding/index、top-k、去重/容量参数与 held-out namespace 隔离策略；held-out episode 默认不写永久 LTM。

## 12.3 全文逻辑审计结果

| **审计项**        | **v0.3 处理结果**                                                                                                                 |
|-------------------|-----------------------------------------------------------------------------------------------------------------------------------|
| 数据泄漏          | PIDSMaker test labels、attack identity 和 label metrics 不进入 held-out agent observation 或 deployable memory。                  |
| Step 冲突         | 删除 test_date、固定 group 和 attack-relevant group；统一为 construction graph step。                                             |
| Memory 冲突       | 删除四种语义 memory type；统一三层生命周期、privileged/deployable 双视图，并明确 fixed harness 与 SFT-learned use policy 的边界。 |
| Action/tool 冲突  | 删除任意 featurization/encoder/window 在线搜索；第一版限定 validated tools/actions。                                              |
| Training 路线冲突 | 删除默认“后训练/RL 已确定”表述；统一 SFT-first、按瓶颈升级。                                                                      |
| 目标遗漏          | 补入 TP、FN、recall 和 true-positive evidence recovery。                                                                          |
| 成本边界          | Token 仅评估；stage rerun、runtime、cache 和 calls 完整报告。                                                                     |
| 环境泛化          | 经验检索加入 environment compatibility gate，避免只按攻击或文本相似复用。                                                         |
| Memory 训练边界   | 明确第一版不训练 storage/retriever；SFT 仅学习 read/query/use/write policy，实际检索与写入由固定 harness 执行。                   |

# References and Source Notes

PIDSMaker Documentation, Home: https://ubc-provenance.github.io/PIDSMaker/

PIDSMaker Documentation, Pipeline: https://ubc-provenance.github.io/PIDSMaker/pipeline/

PIDSMaker Documentation, Datasets: https://ubc-provenance.github.io/PIDSMaker/datasets/

PIDSMaker Documentation, Tasks and Arguments: https://ubc-provenance.github.io/PIDSMaker/config/tasks/

PIDSMaker Documentation, Batching & Sampling: https://ubc-provenance.github.io/PIDSMaker/features/batching/

PIDSMaker Documentation, Instability: https://ubc-provenance.github.io/PIDSMaker/features/instability/

PIDSMaker Documentation, Tuned PIDSs: https://ubc-provenance.github.io/PIDSMaker/tuned_systems/

Bilot et al., Sometimes Simpler is Better: A Comprehensive Analysis of State-of-the-Art Provenance-Based Intrusion Detection Systems, USENIX Security 2025.

Project design-review conversations through v0.4.
