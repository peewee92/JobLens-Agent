# P0-3B｜Requirement Extractor v1–v30 演进复盘

> 目标：记录 JobLens-Agent 的 Requirement Extraction 从 v1 到 v30 的真实演进，包括每个版本解决的问题、真实 Bad Case、修复方式、为什么采用这种方式、踩过的坑，以及下一阶段应该如何继续。
>
> 证据来源：Git 历史、`docs/roadmap/ROADMAP.md`、Requirement Acceptance Run / Canary Review 持久化记录、Workflow / Adapter 回归测试与当前 working tree。
>
> 时间范围：2026-08-07 ～ 2026-08-18。
>
> 当前状态：`requirement-extractor-v30 / requirement-extraction-v4` 已完成最小真实 Canary，3 个样本中 1 个成功、2 个因非逐字 grounding 失败，已 Stop；v30 代码当前仍在 working tree，尚未作为稳定提交进入主线。

---

## 0. 阅读前术语速查：先把英文翻成“人话”

这份文档保留了不少 LLM / Agent / 后端工程里的标准术语。正文不强行全部改成中文，是因为这些词在代码、日志、面试和技术文档里都会直接出现；但第一次阅读时，可以先把它们理解成下面这些中文意思。

### 0.1 如果只记 12 个词，先记这些

| 术语 | 中文理解 | 在这个项目里具体指什么 |
|---|---|---|
| `Requirement Extractor` | 岗位要求提取器 | 把一整段招聘 JD 拆成结构化岗位要求的模块 |
| `JobRequirement` | 一条岗位要求事实 | 例如“本科及以上”“2 年以上开发经验”“熟悉 Python” |
| `Structured Output` | 结构化输出 | 不让模型自由写一段话，而是按固定字段输出 JSON |
| `Schema / JSON Schema` | 数据格式规则 | 规定字段必须有哪些、是什么类型、哪些值允许出现 |
| `Grounding` | 原文落地 / 证据对齐 | 确认模型提取出的要求，真的能在 JD 原文中找到 |
| `evidenceSpan` | 证据原文片段 | 支撑这条 Requirement 的 JD 原句或连续原文 |
| `must_have` | 硬性要求 | 不满足就可能直接不符合岗位 |
| `preferred` | 优先项 | 有更好，没有通常也不应直接淘汰 |
| `Constraint` | 组合约束 / 条件约束 | 例如“以下 4 项至少满足 2 项”，不能当成单一技能 |
| `Eval` | 评测 | 用真实案例判断模型输出到底对不对 |
| `Canary` | 小流量试跑 / 金丝雀验证 | 新版本先跑 1～3 个真实 JD，发现问题就停止，不直接跑全量 |
| `Trace` | 调用轨迹 / 运行证据 | 记录这次模型调用用了什么版本、耗时、输入输出、错误和修复信息 |

可以先用一句话串起来：

```text
Requirement Extractor
把 JD 变成 JobRequirement；
每条 Requirement 要有 evidenceSpan 做 Grounding；
用 Schema 约束格式，用 Eval 检查质量，
新版本先走 Canary，并通过 Trace 留下完整证据。
```

### 0.2 Requirement 字段相关术语

| 术语 | 中文理解 | 例子 / 说明 |
|---|---|---|
| `type` | 要求类型 | 这条要求属于技能、经验、学历、职责、领域还是组合约束 |
| `skill` | 技能要求 | React、Python、RAG、Electron |
| `experience` | 经验要求 | “2 年以上开发经验”“有车端经验” |
| `education` | 学历 / 专业要求 | “本科及以上”“计算机相关专业” |
| `responsibility` | 岗位职责 | 更偏“入职后要做什么”，不一定是候选人的准入门槛 |
| `domain` | 行业 / 领域要求 | 汽车、医疗、金融等领域知识或经历 |
| `constraint` | 组合条件 | “至少一种”“A 或 B”“以下四项满足两项”等 |
| `originalText` | 这条要求对应的原始表述 | 系统希望保留的 JD 原文 Requirement 文本 |
| `evidenceSpan` | 支撑它的原文证据 | 必须来自 JD 的真实连续片段 |
| `normalizedCapability` | 归一化能力名 | `React.js / ReactJS → React`，便于后续统一匹配 |
| `importance` | 重要程度 | `must_have / preferred / bonus` |
| `bonus` | 加分项 | 明确写“加分”“bonus”“nice to have”的要求 |
| `confidence` | 模型置信度 | 模型对这条抽取结果有多确定；它不是事实正确率 |

### 0.3 Grounding / 证据相关术语

| 术语 | 中文理解 | 为什么重要 |
|---|---|---|
| `exact-grounded` | 已精确对齐原文 | 这段文字可以原封不动在 JD 中找到 |
| `verbatim` | 逐字原文 | 不允许删字、换词、总结或同义改写 |
| `raw JD` | 原始 JD 文本 | 未经模型改写的招聘原文 |
| `raw JD slice` | 从原始 JD 截出来的一段 | 最终保存的 evidence 应尽量来自这里 |
| `source span` | 原文位置区间 | 一段证据在 JD 中从哪里开始、到哪里结束 |
| `whitespace recovery` | 空白字符恢复 | 模型清掉空格/换行时，在唯一可证明的情况下恢复真实原文 |
| `punctuation-width recovery` | 全角/半角标点恢复 | 如 `(LLM)` 与 `（LLM）`，仅做安全可逆的格式修复 |
| `fuzzy matching` | 模糊匹配 | “看起来差不多”就认为是同一句；本项目事实层明确不采用 |
| `semantic rewrite` | 语义改写 | 意思相近但不是原话，例如漏字、换同义词；不能冒充 JD 证据 |
| `Grounding Repair` | 证据修复 | 只对可确定证明的格式漂移恢复真实 raw JD，不猜语义 |

最关键的区别：

```text
“意思差不多” ≠ “这是招聘方原话”
```

所以 Grounding 更接近“证据真实性校验”，而不是普通文本相似度。

### 0.4 Requirement 语义相关术语

| 术语 | 中文理解 | 典型例子 |
|---|---|---|
| `Semantic Guardrail` | 语义护栏 | 模型输出后，用确定性规则防止明显业务语义错误 |
| `Deterministic Repair` | 确定性修复 | 输入相同就一定得到相同修复结果，不再调用另一个模型猜 |
| `cardinality` | 数量约束 | “至少 2 项”“任意一种”“至少一门语言” |
| `alternative` | 备选关系 | “Python 或 Go”“LangChain / Dify 至少一种” |
| `alternative child` | 备选组里的子项 | Python、Go 分别是 “Python 或 Go” 这个组的 child |
| `parent group` | 备选组总约束 | “Python 或 Go 至少一种”本身才是必须满足的总体条件 |
| `waiver` | 豁免 / 放宽条件 | “2 年经验，优秀者可放宽”中的“可放宽” |
| `soft marker` | 软化词 | “优先”“加分”“可选”“preferred”“bonus” |
| `scope` | 作用范围 | 一个“优先”到底只修饰专业，还是连学历也一起修饰 |
| `mixed clause` | 混合条件句 | 一句话里同时出现学历、经验、技能、优先项等不同要求 |
| `hard gate` | 硬门槛 | 影响是否符合岗位的必须条件 |
| `fused gate` | 被模型粘在一起的多个硬要求 | 如“会 Agent 工具 + 有 Agent 产品经验”被错误合成一条 |
| `under-enforcement` | 要求被执行得过松 | 原本要满足 A+B+C，却因为只匹配 A 就被判通过 |
| `over-enforcement` | 要求被执行得过严 | 原本 4 选 2，却被系统要求 4 项全部满足 |

### 0.5 模型输出漂移相关术语

文档里经常出现 `drift`，可以统一理解成“模型输出偏离了我们希望它遵守的语义”。

| 术语 | 中文理解 | 例子 |
|---|---|---|
| `type drift` | 类型漂移 | “有车端经验”本应是 experience，却被标成 skill |
| `importance drift` | 重要程度漂移 | 任职要求中的硬条件被标成 preferred |
| `capability drift` | 能力归一偏移 | “LangChain/LangGraph/Dify 至少一种”被收窄成 LangChain |
| `coverage drift` | 覆盖范围缺失 | 原文要求 A+B，模型只保留 A |
| `Provider duplicate` | 模型重复输出 | 同一 Requirement 在一次返回里重复两遍 |
| `duplicate` | 重复项 | 系统中出现两条实际代表同一要求的 Requirement |
| `dedupe` | 去重 | 把可证明完全等价的重复项收敛成一条 |

### 0.6 Provider / 调用链路术语

| 术语 | 中文理解 | 在项目中的作用 |
|---|---|---|
| `Provider` | 大模型服务提供方 / 网关 | 当前 Requirement Extraction 实际调用的大模型 API 服务 |
| `OpenAI-compatible` | OpenAI 接口兼容格式 | 接口长得像 OpenAI，但具体行为不一定完全一致 |
| `Adapter` | 适配层 | 把不同 Provider 的接口差异统一成项目内部固定调用方式 |
| `Workflow` | 业务流程编排 | 串起调用模型、grounding、semantic repair、validate、trace 等步骤 |
| `Prompt` | 给模型的系统指令 | 告诉模型应该提取什么、输出什么格式、遵守什么规则 |
| `Prompt contract` | Prompt 中约定的行为规则 | 例如“任职要求默认 must-have”“必须逐字引用” |
| `runtime invariant` | 运行时必须成立的不变量 | 不能只相信 Prompt，代码最终还要验证它真的成立 |
| `Responses API` | 一类模型调用协议 | OpenAI 风格的新式响应接口 |
| `Chat Completions` | 对话补全接口 | 很多 OpenAI-compatible 网关实际支持得更稳定 |
| `reasoning` | 模型内部推理预算 | 可能影响延迟、token 和网关超时 |
| `completion` | 模型最终输出 | Requirement JSON 属于最终 completion 的一部分 |
| `upstream` | 上游服务 | 这里通常指 JobLens 调用的模型网关 / Provider |

### 0.7 可靠性 / 错误处理术语

| 术语 | 中文理解 | 这里为什么这么做 |
|---|---|---|
| `fail-fast` | 尽快失败、立即停止扩跑 | 已确认 Provider 503 时，不继续把后面 17 个 Case 都打失败 |
| `fail-closed` | 不确定就拒绝通过 | 找不到真实原文时宁可 Extraction 失败，也不猜一条证据 |
| `retry` | 重试 | 同一请求失败后再次尝试 |
| `bounded retry` | 有明确次数上限的重试 | 比如 504 最多重试 1 次，防止无限消耗成本 |
| `timeout` | 超时 | 请求超过等待时间后失败 |
| `outage` | 服务故障 / 不可用 | 429/503/504 等外部 Provider 问题 |
| `Unavailable` | 暂时不可用 | 表示外部服务问题，不等于模型语义质量差 |
| `deferred` | 暂缓执行 | 因预算或 fail-fast 没有继续调用该 Case |
| `attempt` | 一次真实调用尝试 | 成功或失败都算，因为都发生了真实副作用和成本 |
| `attempt budget` | 调用次数预算 | 限制这一轮最多能实际打多少次 Provider |

### 0.8 Eval / Canary / 治理术语

| 术语 | 中文理解 | 具体含义 |
|---|---|---|
| `Eval` | 模型评测 | 判断 Requirement 输出质量，而不是只看接口是否 200 |
| `Bad Case` | 失败案例 / 反例 | 能暴露模型或规则缺陷的真实 JD 样本 |
| `Regression Test` | 回归测试 | 修完一个 Bad Case 后，确保旧问题不复发、旧能力没被改坏 |
| `Canary` | 小规模真实试跑 | 新版本先跑 1～3 个真实 JD，再决定是否扩大 |
| `Acceptance` | 正式验收 | 用固定数据集和人工 Review 判断该版本能否成为可信基线 |
| `Readiness` | 执行前就绪检查 | 检查版本、数据库、Provider、数据集等是否允许开始真实调用 |
| `Health Gate` | 健康门禁 | Provider 健康条件不满足时禁止 Live Run |
| `plain probe` | 普通最小探针 | 验证基础 Chat Completions 能否正常返回 |
| `json_schema probe` | 结构化输出探针 | 验证 Requirement 真正依赖的 strict JSON schema 路径是否可用 |
| `Human Gate` | 人工门禁 | 系统到关键节点必须由人明确 Continue / Stop |
| `Continue` | 允许继续收集证据 | 不等于版本已通过质量验收 |
| `Stop` | 停止当前 Run | 当前证据已足以说明不能继续扩跑 |
| `Immutable Review` | 不可修改的人工审核记录 | 保留当时谁基于什么证据做了什么决定 |
| `Run` | 一次完整验收运行 | 固定 dataset、版本、Provider、reviewer 的一组执行记录 |
| `Cohort` | 同一版本实验组 | 同一个 extractor/prompt/semantic policy 的结果才可放在一起比较 |
| `Baseline` | 已接受的质量基线 | 后续版本用于对比的正式参考版本 |

### 0.9 Trace / 可观测性术语

| 术语 | 中文理解 | Trace 中通常记录什么 |
|---|---|---|
| `Trace` | 一次调用的完整运行轨迹 | 版本、模型、耗时、token、错误、输出、repair 信息 |
| `traceId / traceRunId` | Trace 唯一编号 | 用来把某个失败 Case 精确定位到那一次模型调用 |
| `latency` | 延迟 | 一次模型调用用了多久 |
| `input tokens` | 输入 token 数 | 发给模型的大致文本量 |
| `output tokens` | 输出 token 数 | 模型生成内容的大致长度 |
| `repair metadata` | 修复审计信息 | 哪一条 Requirement 被什么 deterministic rule 修改过 |
| `observability` | 可观测性 | 出问题后能不能知道“哪里错、为什么错、当时发生了什么” |

### 0.10 下游业务术语

| 术语 | 中文理解 | 为什么 Requirement Extraction 要关心它 |
|---|---|---|
| `Eligibility` | 岗位准入判断 | 先判断候选人有没有明显不满足的硬门槛 |
| `Evaluator` | 某一类要求的判断器 | Skill、Experience、Education、Constraint 可能采用不同判断逻辑 |
| `Skill Evaluator` | 技能匹配判断 | 看候选人是否具备指定技能 |
| `Experience Evaluator` | 经验匹配判断 | 看是否满足年限、项目、领域经历等要求 |
| `downstream` | 下游 | Requirement Extraction 之后的 Eligibility / Match / Gap 等模块 |
| `downstream consequence` | 下游业务后果 | 一个字段错了，最终会不会让用户被错误淘汰或错误推荐 |
| `Match` | 岗位匹配 | 在满足基本 Eligibility 后，比较候选人与岗位的适配程度 |
| `Gap` | 能力差距 | 还缺哪些岗位要求 |
| `False Reject` | 错误淘汰 | 实际符合岗位，却被系统判成不符合 |
| `False Accept` | 错误放过 | 实际不满足硬要求，却被系统判成符合 |

### 0.11 阅读正文时可以这样快速翻译

看到下面这些句子时，可以直接在脑中替换：

```text
“grounding failed”
≈ “模型给出的证据不是 JD 真实连续原文”

“importance drift”
≈ “硬要求 / 优先项分错了”

“type drift”
≈ “这条要求被分到了错误的业务类型，可能走错判断器”

“cardinality / alternative scope 错误”
≈ “至少几个、二选一、四选二这类组合关系被模型理解错了”

“deterministic semantic repair”
≈ “不用再问模型，而是根据明确原文规则做可重复、可审计的修正”

“Canary Stop”
≈ “小规模真实试跑已经发现阻断问题，所以不继续扩大调用”

“Provider outage”
≈ “模型服务挂了，不代表这版抽取逻辑质量差”

“downstream evaluator-sensitive drift”
≈ “表面文字看起来还行，但这个字段会让后面的岗位判断走错逻辑”
```

后文第一次遇到不熟悉的词，可以先回到本节查中文意思；正文仍保留英文术语，方便和代码、Trace、Git commit、面试表达保持一致。

---

## 1. 这 30 个版本到底在解决什么？

Requirement Extractor 不是“帮用户总结 JD”的普通 LLM 功能，而是 JobLens 后续所有职业判断的事实入口：

```text
真实 JD
  ↓
Requirement Extraction
  ↓
JobRequirement[]
  ├─ type
  ├─ originalText
  ├─ evidenceSpan
  ├─ normalizedCapability
  ├─ importance
  └─ confidence
  ↓
Eligibility
  ↓
Profile Evidence Match
  ↓
Ranking / Gap / Action Plan / Resume / Interview
```

如果 Requirement Extraction 错了，后面的结果即使算法完全正确，也会建立在错误事实上。

几个真实例子：

- `至少覆盖以下方向中的两项` 被提取成四项全部 `must_have` → 错误淘汰候选人；
- `本科及以上，相关专业优先` 被整体降为 `preferred` → 错误放宽学历硬门槛；
- `需要有车端经验` 被标成 `skill` → 下游走 Skill evaluator，而不是 Experience evaluator；
- `Prompt 工程 + 结构化 Prompt + 上下文管理` 被压成 `normalizedCapability=Prompt` → 只会 Prompt 也可能错误通过整条硬要求；
- 模型把 JD 的 `至少在以下一个方向` 改成 `至少在一个方向` → 语义近似，但已经不再是招聘方原文证据。

因此 v1–v30 的真实目标是逐步建立四层可靠性：

```text
Provider / Schema Reliability
        ↓
Evidence Grounding Reliability
        ↓
Requirement Semantic Reliability
        ↓
Live Eval / Governance Reliability
```

最终形成的原则是：

> **LLM 负责理解，程序负责证明。模型可以提出 Requirement，但不能自行创造证据。**

---

# 2. 版本总览

| 版本 | 主要问题 | 核心优化 | 关键结果 / 新发现 |
|---|---|---|---|
| v1 | 还没有真实 Requirement LLM Pipeline | Structured Output + Trace + Grounding 基础 | 建立最小事实提取闭环 |
| v2 | OpenAI-compatible Provider 协议差异 | 支持 Chat Completions strict schema | 真实网关可运行 |
| v3 | reasoning / completion 过长，网关不稳定 | 限制推理/输出预算，保留 upstream trace | 首个 `deepseek-v4-flash` Live Canary 成功 |
| v4 | Skill 可能缺 normalizedCapability | Schema 强制 Skill capability | 正式 20-JD Acceptance 暴露稳定 grounding drift |
| v5 | 空格/标点/一侧 quote 漂移 | `grounding-v1`：counterpart、whitespace、punctuation-width deterministic recovery | 20 Case 完成；人工 16 accept / 4 reject，瓶颈转向 importance |
| v6 | Requirement section 默认 importance 错误 | Prompt v2：显式任职要求默认 must-have；soft modifier 局部生效 | 同时暴露 Provider 503，建立 outage 分类 |
| v7 | waiver / example 被错误硬化 | Prompt v3 增加 waiver / example 规则 | Prompt 改善但不能稳定保证 cardinality/waiver |
| v8 | Prompt-only 不可靠 | `requirement-semantics-v1` deterministic guardrail | 开始对 waiver/cardinality 做 exact-grounded 修复 |
| v9 | mixed hard/soft scope；504；duplicate identity | 拆 hard prefix/preferred suffix；单次 504 bounded retry；修 duplicate identity | 扩跑发现 `C++ 或 Python` 被变成双 must-have |
| v10 | 显式 OR siblings 被全部硬化 | 合成 mandatory alternative group，children preferred | 又发现 inline cardinality capability 被收窄为 LangChain |
| v11 | 单条“至少一种”绑定单一 capability | inline cardinality → constraint must-have | 新发现 hard clause 仍混入 trailing preferred |
| v12 | hard + trailing preferred 混合 | 从 hard item 裁掉 soft suffix，复用 soft item | 又出现随机 verbatim 改写；type drift 绕过 cardinality 规则 |
| v13 | cardinality 被标 experience 时规则失效 | cardinality guardrail 泛化到 skill/experience | 新发现 Python 被整句 constraint 吞掉；education 吞经验 |
| v14 | mixed hard gates 被错误合并 | 拆 Skill + alternative、Education + Experience | deterministic repair 自己制造 duplicate |
| v15 | repair duplicate | 只去重 repair 产生的 exact equivalent | 新发现同一 8 年经验因 evidenceSpan 不同重复计数 |
| v16 | parent evidence duplicate | 原子 repair identity 收敛 | 新发现句末标点和全 JD 唯一 scope 过严 |
| v17 | alternative child 全局唯一判断过严 | 改为 group scope 内唯一；窄化标点归一 | 新发现 parent 被标 experience，走错 evaluator |
| v18 | alternative parent type drift | 无经验前缀的 alternative parent → constraint | Provider exact duplicate 随机出现；retry2 证明非稳定 |
| v19 | experience prefix + cardinality；OR importance drift | 拆 Experience + constraint；允许 OR child importance drift | 新发现单条 `Python/Go/Java 至少一门` 和 non-contiguous quote |
| v20 | cardinality 词法/type drift | 支持 `至少一门`；按 exact text 拆 experience/cardinality | 新发现复合 hard skill 被单 capability under-enforce |
| v21 | all-of hard skill 被压成一个 capability | compound hard skill → constraint | 新发现 `工程能力扎实` 被 literal Skill 化 |
| v22 | 抽象评价走 Skill evaluator | 抽象能力 → constraint，小型 allowlist | 新发现 partial-match 和 skill+experience fused gate |
| v23 | fused hard gate | compound evaluative ability + `split_skill_experience` | Provider 503；恢复后真实命中修复；又暴露 duplicate/scope |
| v24 | exact duplicate、non-contiguous cardinality、scope leak | 可观测 exact dedupe、header recovery、编号边界 | 新发现 coverage/type drift |
| v25 | compound hard requirement 截断；responsibility/skill type drift | expand evidence span、扩展 fused split、alternative type normalize | 新发现车端经验/工程习惯/example child evaluator-sensitive drift |
| v26 | Experience / example / habit 类型漂移 | experience type normalize、drop redundant example child、habit → constraint | 新发现 experience + explanatory consequence 被整体 constraint |
| v27 | 显式 experience 被 explanatory suffix 吞掉 | 从窄形态 constraint 恢复 experience prefix | 因同一句在 JD 重复两次，unique span 阻止 repair |
| v28 | semantic split 错用 grounding 唯一性 | semantic split 只要求 item/prefix exact，不要求全 JD 唯一 | 历史高风险点稳定；新发现 requirement section false preferred |
| v29 | Provider 违反 Prompt 的 section default | deterministic `requirement_section_default_must_have`；双健康门禁 | Canary 2/3 成功，1 个真实 verbatim 改写，Stop |
| v30 | 尝试靠 Prompt 再强化 verbatim | Prompt v4 明确逐字符连续 substring | Canary 1/3 成功、2/3 grounding fail，证明 Prompt-only 已到边界 |

---

# 3. Phase A｜v1–v4：先把真实 LLM Pipeline 跑起来

## v1｜建立 grounded structured extraction

v1 的重点不是追求模型质量，而是先定义一个可治理的事实输出协议。

主要能力：

- `JobRequirementExtractionOutput`；
- `type / originalText / evidenceSpan / normalizedCapability / importance / confidence`；
- Workflow Trace；
- 原文 grounding 校验；
- Provider error / invalid output error 区分；
- 后续持久化和 Eval 可以引用固定版本。

### 为什么第一版就做 grounding？

如果最开始只输出自由文本总结：

```text
“这个岗位主要要求 Agent、Python 和沟通能力。”
```

后面很难证明：

- 哪一项真的来自 JD；
- 哪一项是模型总结；
- 哪个 Match 决策引用了哪句话；
- 修改 Prompt 后历史结果为什么变化。

因此 v1 从一开始就把 Requirement 当“事实”而不是“回答”。

---

## v2｜适配真实 OpenAI-compatible Chat Completions

真实 Provider 并不保证完整实现 OpenAI Responses API。

v2 增加：

```text
responses
chat_completions
```

双 API style，并保持 strict JSON schema。

### 踩坑

“OpenAI-compatible”只代表接口形状近似，不代表：

- schema 参数；
- error payload；
- usage；
- trace header；
- thinking 行为；

完全一致。

### 结论

Provider Adapter 必须成为稳定边界，不能把网关差异泄漏到 Workflow。

---

## v3｜限制 reasoning / completion，首个真实 Canary

`deepseek-v4-flash` 类模型如果允许过度 reasoning，会带来：

- latency；
- output token 激增；
- gateway timeout；
- 成本不可预测。

因此 v3 给真实调用增加显式 reasoning / completion 上限，并保留 upstream trace id。

v3 首个 Live Canary 成功后，只能证明：

```text
API 可调用
Schema 可解析
Trace 可记录
```

不能证明：

```text
Requirement 语义可直接进入 Match
```

这是后续 Canary 治理一直坚持的边界。

---

## v4｜Skill schema 强约束 + 正式 Acceptance

v4 把：

```text
type = skill
normalizedCapability = null
```

直接变成 schema/validation error。

原因很简单：后续 Skill evaluator 的核心输入就是 normalized capability。

### 正式 Acceptance 暴露的真实问题

v4 首轮 3 个 Case 技术成功；扩跑 20-JD 后不断出现：

- `originalText` 不在原 JD；
- `evidenceSpan` 不在原 JD；
- 模型轻微删词；
- 异常 whitespace；
- 半角/全角标点变化。

最终 20 Case 中 19 个可用，1 个稳定失败。

### 当时最重要的选择

没有为了“20/20”把 validator 改成 fuzzy matching。

因为：

> 如果模型自己改写的话也能成为 evidence，JobLens 的“可追溯事实”原则会从根上失效。

---

# 4. Phase B｜建立 strict grounding

## v5｜建立 grounding-v1：只修格式漂移，不修语义漂移

v5 是第一个真正的可靠性拐点。

## 4.1 counterpart repair

当：

```text
originalText 不 grounded
evidenceSpan grounded
```

或反过来时，用已经证明真实的一侧回填另一侧。

这不是语义修复，只是从已有真实证据恢复。

## 4.2 whitespace recovery

真实 JD 可能出现：

```text
熟 悉 后 端 系 统
```

模型会自动清掉空格。

v5 只在：

```text
移除 whitespace 后
quote 在 JD 中唯一命中
```

时恢复真实 raw slice。

## 4.3 punctuation width recovery

例如：

```text
JD: (LLM)
模型: （LLM）
```

只归一 ASCII punctuation width，并继续要求唯一命中。

## 4.4 明确不做什么

`grounding-v1` 不允许：

- fuzzy matching；
- 同义词替换；
- 数字改写；
- case rewrite；
- 多位置自动选一个；
- semantic similarity repair。

核心规则：

```text
格式漂移可以确定性恢复
内容漂移必须 fail-closed
```

## 4.5 v5 人工 Review 的真正价值

v5 最终完成 20 Case 人工复核：

```text
16 accepted
4 rejected
```

4 个 Reject 全是 `wrong_importance`。

说明 grounding 的主要工程问题被压住以后，新的瓶颈已经是：

> 模型是否正确理解 Requirement 的“硬/软、组合、作用域”。

---

# 5. Phase C｜v6–v9：从 Prompt 规则走向 Semantic Guardrail

## v6｜修 Requirement section 默认 importance

人工 Review 发现三类关键错误：

### Bad Case A｜4 选 2 被变成 4 个 must-have

```text
JD：至少覆盖以下方向中的两项
- SFT / LoRA
- RAG
- Agent
- Prompt Engineering
```

错误输出：四个 child 全是 must-have。

影响：本来满足任意两项即可，系统会要求四项全部满足。

### Bad Case B｜任职要求全部降 preferred

JD 没有“优先”，但 Provider 把多个 requirement 都标 preferred。

影响：本来不符合硬门槛的候选人也可能进入 Match。

### Bad Case C｜局部“专业优先”污染学历

```text
本科及以上学历，相关专业优先
```

不能把“本科及以上”一起降级。

### v6 解决

Prompt v2：

- requirements / qualifications section 默认 must-have；
- soft marker 只作用于被修饰 clause；
- alternative/cardinality parent 保持 mandatory；
- children 不全部 hard。

### 额外 Provider 坑

v6 首轮 3/3 HTTP 503。

由此补齐：

- 429/503/504 分类为 unavailable；
- 首次 unavailable 后 fail-fast；
- 剩余 Case deferred；
- UI 将 outage 与质量失败分开。

**教训**：服务不可用不能污染模型质量 Eval。

---

## v7｜Prompt v3：waiver 和 example

v6 recovery 的真实输出继续暴露：

```text
2 年以上经验，优秀者可放宽
```

被拆成：

```text
2 年 must_have
可放宽 preferred
```

这样可豁免候选人仍会被 2 年硬门槛淘汰。

另一个问题：

```text
精通 AI 常见场景（如预测、决策、NLP、CV）
```

`如/例如` 后面的例子可能被拆成独立 must-have。

Prompt v3 明确 waiver / example 规则。

### 结果

example 明显改善，但：

- waiver 仍可能错；
- cardinality children 仍可能全部 hard。

这证明：

> Prompt 是概率约束，不是 runtime guarantee。

---

## v8｜第一次加入 deterministic semantic repair

v8 引入 `requirement-semantics-v1`。

核心策略：

```text
waiver_scope
drop_redundant_waiver
alternative_child
```

只基于：

- exact grounded quote；
- 显式 waiver marker；
- 显式 cardinality marker；
- 可证明的局部 scope。

### 为什么不能“语义上觉得像”就修？

Semantic Guardrail 一旦变成另一个模糊 NLP 模型，就只是把一个不可控模型换成另一个不可控规则层。

这里要求每个 repair 都能解释：

> “我修改这条 Requirement 的依据，在 JD 哪个 exact span、哪个 marker？”

### v8 新发现

- 模型已经把完整 waiver 句输出为 must-have 时，旧规则没命中；
- `硬要求 + 尾部优先` 有时整句被降 preferred。

---

## v9｜mixed importance + bounded 504 retry + duplicate identity

v9 解决：

```text
完整 waiver 句 must-have → preferred
硬前缀 + preferred suffix → 拆开
```

并加入反例，避免“其他条件可放宽”错误软化经验门槛。

### 504 根因

真实 Trace 的 504 大约在 60 秒返回，而客户端 timeout 为 180 秒。

结论：

> 504 来自上游 gateway，不是 JobLens local timeout。

策略：

- 429/503：立即 fail-fast；
- 504：本轮预算允许时，同 Case 自动 retry 1 次；
- 每次 retry 都单独计 attempt / Trace；
- 第二次仍失败就停。

### Validator 误伤

不同职责可以共享 section-level evidenceSpan，旧 duplicate identity 太粗。

修为：

```text
(type, normalizedCapability, originalText, evidenceSpan)
```

### v9 扩跑的新 Bad Case

```text
熟悉 C++ 或 Python 编程语言
```

被拆成：

```text
C++ must_have
Python must_have
```

引出 v10。

---

# 6. Phase D｜v10–v20：Alternative / Cardinality / Mixed Clause

## v10｜显式 OR siblings 合成 mandatory group

触发条件严格限定为：

- siblings 共享 exact source；
- 原文含 `或/或者/or`；
- 没有 soft marker；
- 多个 capability 是同一 alternative group children。

输出：

```text
parent constraint must_have
children preferred
```

普通 `A、B、C 等` 枚举不触发。

### 新问题

`LangChain / LangGraph / Dify 至少一种` 可能被压成：

```text
skill must_have
normalizedCapability = LangChain
```

---

## v11｜inline cardinality 不允许绑定单一 capability

对：

```text
至少一种 / 任一 / one of / at least N
```

这类 must-have Skill，转成：

```text
constraint must_have
normalizedCapability = null
```

避免把 LangChain 当唯一硬门槛。

### 新问题

Provider 同时输出：

```text
[硬要求 + 优先后缀] must_have
[优先后缀] preferred
```

hard Requirement 自身仍含 soft 条件。

---

## v12｜裁掉 hard item 中的 trailing preferred

v12：

- 从 hard item 删除 soft suffix；
- 复用已有 preferred item；
- 窄范围忽略句末标点，避免重复 soft item。

### Canary 再次证明 grounding 必须严格

Harness：

```text
JD：但至少要能独立 owner 一个核心方向
模型：至少能独立 owner 一个核心方向
```

这不是 whitespace/punctuation drift，而是删词。

继续 fail-closed，不为通过率放宽 grounding。

### 新问题

同一 cardinality requirement 被 Provider 标成 `experience`，绕过只覆盖 Skill 的 v11 规则。

---

## v13｜cardinality 规则泛化到 experience

将：

```text
must-have skill / experience
+ 显式 cardinality
```

都归一到 `constraint must_have`。

### 新 Bad Case

```text
熟练使用 Python,
具备 LangChain/LangGraph/Dify 至少一种框架经验
```

整句被转 constraint，Python hard skill 丢失。

另一个：

```text
本科 + 2 年经验 + LLM/Agent 项目经验
```

被合成 education；Education evaluator 只检查学历，会放过经验。

---

## v14｜拆 mixed hard gate

v14 两个关键 split：

```text
Skill prefix + cardinality suffix
→ Skill + constraint
```

以及：

```text
Education + Experience + Experience
→ education + experience + experience
```

真实 Case 2 收敛成五条 hard gate：

1. 学历/专业；
2. 2 年开发经验；
3. LLM/Agent 落地经验；
4. Python；
5. 至少一种 Agent 框架 constraint。

### 最大教训

v14 的 deterministic repair 自己制造了 duplicate。

> deterministic code 不是天然正确，repair 后仍必须经过最终 validator 和 regression。

---

## v15｜只去重 repair 自己制造的等价项

多个 Provider capability 经 repair 后变成同一个 cardinality constraint。

v15 只收敛 deterministic repair 的 exact equivalent，不静默清理普通 Provider duplicate。

### 为什么不全局 dedupe？

因为重复项可能存在：

- importance 冲突；
- type 冲突；
- capability 冲突。

静默去重会掩盖模型不确定性。

### 新问题

同一 `8 年以上 AI 产品/解决方案经验`：

- originalText 相同；
- evidenceSpan 一个短、一个父级长；

Eligibility 会把同一 hard gate 重复计数。

---

## v16｜收敛 parent evidence duplicate

repair identity 从依赖 evidenceSpan，收紧到：

```text
type + importance + originalText
```

仅用于可证明的 repair 原子事实。

### 新问题

- 句末标点差异仍重复；
- Harness 方向 child 在后文再次出现，旧规则要求全 JD 唯一，导致无法降为 preferred。

---

## v17｜alternative child 改为 scope 内唯一

v17 不再要求关键词在整份 JD 中只出现一次。

只要求：

> child 在当前明确 alternative group scope 内唯一。

scope 外的说明文字重复不再影响。

这修复了 Harness 中 React/Electron/Python 后文重复导致的误判。

### 新问题

parent：

```text
工程能力扎实，至少在以下一个方向非常熟练
```

被标成 `experience must_have`。

Experience evaluator 会按经历证据做 literal 判断，造成 false missing。

---

## v18｜alternative parent type drift

对：

- must-have；
- 有显式 alternative group；
- 没有真实年限/experience prefix；

的 `experience` type drift 转为 `constraint`。

### Provider duplicate 的正确处理

v18 首轮出现一次完全相同的 Provider 原生 duplicate。

没有立即改代码，而是同版本新 Run retry2。

retry2 未复现。

这说明它更像 Provider 随机波动，而不是稳定版本缺陷。

**教训**：不要看到每个随机坏样本就 bump 版本。

### retry2 新问题

- experience prefix + cardinality parent fused；
- OR group 的 child importance 不一致。

---

## v19｜Experience prefix + cardinality 拆分

v19 将：

```text
真实 Experience hard prefix
+
后续 cardinality group
```

拆为：

```text
experience must_have
constraint must_have
```

同时 explicit OR grouping 允许 Provider 的 child importance 出现 must/preferred 漂移，只要 source 能证明它们属于同一 mandatory OR group。

### Canary budget 门禁发挥作用

一次请求 4 个初始新 Extraction，被 Application gate 在：

```text
0 Provider call
0 DB write
```

时直接阻止。

### 新问题

Case 4 模型把 cardinality header 和后续多个 bullet 非连续拼接为一条 quote，被 grounding 正确拒绝。

同时：

```text
Python 或 Go 或 Java 至少一门
```

可能作为单条 Skill + 组合 normalizedCapability 输出。

---

## v20｜单条组合 cardinality + type drift

v20：

- 增加 `至少一门` cardinality 词法；
- 单条组合语言要求转 constraint；
- Experience/cardinality split 更多依赖 exact text，而不是 Provider type。

### 新问题：under-enforcement

Provider 把：

```text
Prompt 工程
结构化 Prompt
上下文管理
复杂意图拆解
```

合成一条 must-have skill，但 normalizedCapability 只有 `Prompt`。

只匹配 Prompt 可能错误通过整条。

同类问题：

```text
RAG + 向量数据库 + Function Calling
```

---

# 7. Phase E｜v21–v29：Downstream Evaluator-aware Quality

从 v21 开始，判断一条 Requirement 对不对时，不再只看文本，而是明确问：

> **这个 type / importance / capability 交给 Eligibility evaluator 后，会产生什么结果？**

这是后期质量显著提升的关键。

---

## v21｜compound hard skill → constraint

对 exact-grounded、无 soft/alternative 的复合 all-of 硬技能：

```text
Prompt + structured prompt + context management
RAG + vector DB + Function Calling
```

统一转：

```text
constraint must_have
normalizedCapability = null
```

避免单一 capability 虚假通过。

### 防误伤

`如 LangChain、AutoGPT 等` 是 example，不触发 all-of。

### 新问题

`工程能力扎实` 被标成 Skill，会要求 Profile 中出现字面 `engineering ability`。

---

## v22｜抽象评价能力 → constraint

只对小型 allowlist：

- 工程能力；
- 综合能力；
- 学习能力；
- 沟通、协作、表达、分析、抗压能力；

做 deterministic normalize。

具体技术能力如：

```text
企业级 AI 系统架构设计能力
```

继续保持 Skill。

### 新问题

Case 0：复合沟通/业务理解/方案设计被压成一个 capability，出现 partial match。

Harness：AI Agent 工具真实开发 + Agent 产品高强度使用经验被融合成 Experience。

---

## v23｜处理 compound evaluative ability 与 fused skill+experience

新增：

```text
split_skill_experience
```

只对 exact-grounded、两段式、边界明确的 hard clause 拆分。

例如：

```text
熟练使用 AI Agent 工具进行真实软件开发
→ constraint must_have

对 Agent 产品有高强度使用经验
→ experience must_have
```

### Provider outage

v23 Harness 连续 HTTP 503。

人工 Continue 只表示：

> 允许在 Provider 恢复后做受控 probe。

不表示 v23 已质量通过。

Provider 双健康恢复后，真实输出验证 `split_skill_experience` 生效。

继续扩跑又发现：

- Provider exact duplicate；
- non-contiguous cardinality quote；
- alternative scope 穿透后续编号条目。

---

## v24｜exact duplicate + header recovery + numbered scope

v24 三个重点：

1. importance 一致、最终语义完全相同的 exact duplicate 可以可观测去重；
2. non-contiguous cardinality aggregate 只有在同一编号 scope 的 children 能完整证明时，恢复真实 header；
3. alternative scope 增加相邻 numbered item 边界。

importance 冲突 duplicate 仍 fail-closed。

### 新问题

3/3 技术成功，但：

- compound hard requirement 只提取前半句；
- fused Skill + Experience 被 Provider 标 Skill，绕过旧 split；
- alternative parent 出现 responsibility type drift。

---

## v25｜coverage / type drift

新增：

```text
expand_compound_hard_evidence_span
```

只有在：

- original/evidence 都 exact-grounded；
- evidence 中缺失 suffix 是明确 hard clause；
- 没有 soft/cardinality marker；

时，才从 raw JD slice 恢复完整 hard requirement。

同时：

- skill-type fused gate 也可进入 `split_skill_experience`；
- responsibility alternative parent → constraint。

### 新的 Evaluator-sensitive Bad Case

```text
需要有车端经验
```

被标成 Skill。

```text
如预测、决策、NLP、CV等
```

被独立标 domain must-have。

```text
有良好的工程习惯
```

被标 Skill。

这些文本“看起来都没乱说”，但 type 会改变 evaluator 行为。

---

## v26｜Experience type drift + example child + engineering habit

v26：

- `需要有/有/具备…经验` 的 Skill drift → Experience；
- 工程习惯/工程实践/工程素养等抽象评价 → constraint；
- example child 只有在已有同 evidenceSpan hard parent 时才删除。

### 为什么不能看到 `如/例如` 就全部删？

如果模型没有保留 umbrella parent，example-shaped item 可能是唯一剩余信息。

确定性修复必须避免 information loss。

### 新问题

```text
需要有车端经验,
非车端经验的无法到副总师层级
```

被整体标 constraint。

Experience 缺失通常应 blocked，而 constraint 缺失可能只 conditional，因此必须继续修 type。

---

## v27｜恢复显式 Experience prefix

只处理窄形态：

```text
显式 Experience hard fact
+
否定性后果解释
```

保留第一段为 `experience must_have`。

如果第二段本身是另一个独立 hard requirement，不拆。

### 新坑：规则逻辑正确，但 unique span 阻止命中

该车端句子在 JD 原样出现两次。

旧 `_unique_exact_span` 因多位置返回 None。

问题不是语义，而是：

> 把 grounding recovery 的“唯一 raw location”要求错误套到了 semantic split 上。

---

## v28｜区分 grounding 唯一性与 semantic split 安全性

这是一个重要边界澄清。

### Grounding recovery

如果 normalized quote 在 JD 有多个位置：

```text
不能自动选 raw slice
```

必须继续 fail-closed。

### Semantic split

如果 Provider item 本身已经 exact-grounded，并且只从 item 内截取一个 exact prefix：

```text
不需要整个 JD 中唯一
```

因为不会选择另一份不同文本。

v28 只在 `normalize_experience_type_drift` 的 split 中放宽这条限制，`grounding-v1` 完全不变。

### 结果

v28 首轮 3/3 历史高风险点稳定。

受控扩跑 Case 3 又发现：

> 任职要求中没有任何 soft marker 的硬条件，被 Provider 标 preferred。

---

## v29｜把 Prompt importance contract 下沉为 deterministic rule

Prompt v3 早已写明：

```text
requirements / qualifications section 默认 must-have
```

但 Provider 仍会违反。

因此 v29 新增：

```text
requirement_section_default_must_have
```

只有同时满足以下窄条件才提升：

- `originalText == evidenceSpan`；
- exact-grounded；
- 以明确 requirement predicate 开头；
- 无 soft marker；
- 最近 section heading 是岗位要求/任职要求/任职资格/requirements/qualifications；
- responsibility/description section 不处理。

### 为什么不能简单“任职要求区全部 must-have”？

因为任职要求里也可能真实出现：

```text
有 XX 经验者优先
相关专业优先
```

必须保留真正 soft item。

### Provider 双健康门禁

v28→v29 多次出现：

```text
plain probe = 200
json_schema probe = 503
```

Requirement Extractor 实际依赖 structured path，只测 plain 会误判恢复。

因此正式门禁变为：

```text
plain HTTP 200
AND
json_schema HTTP 200
→ readyForRequirementLiveRun = true
```

### v29 Canary

```text
3 attempts
2 extracted
1 failed
17 deferred
Stop
```

失败 Harness：

```text
JD：至少在以下一个方向非常熟练
模型：至少在一个方向非常熟练
```

漏“以下”二字。

这是内容改写，不属于允许的格式 recovery。

---

# 8. Phase F｜验证 Prompt-only grounding 的上限

## v30｜Prompt v4：强化逐字引用并验证 Prompt-only 边界

v30 没有立刻设计复杂新机制，而是先验证一个假设：

> 如果 Prompt 更明确地要求逐字符连续引用，能不能把 v29 grounding failure 压下去？

Prompt v4 明确要求：

```text
originalText 和 evidenceSpan
必须逐字符复制输入中的连续 substring
不得删词
不得改写
不得总结
不得拼接非连续片段
```

因为 Prompt 行为已经变化，所以 cohort 明确升级：

```text
requirement-extractor-v30
requirement-extraction-v4
```

相关 Workflow 回归：

```text
65 / 65 passed
```

但真实 Canary：

```text
3 attempts
1 extracted
2 failed
17 deferred
Stop
```

两次失败仍然是：

```text
originalText / evidenceSpan
不是 raw JD 连续原文
```

## v30 得到的结论

Prompt 可以降低概率，但不能承担最终 grounding guarantee。

继续做：

```text
v31 再强调一次 Prompt
v32 再换一种措辞
v33 再加几个例子
```

收益预计已经很低。

下一阶段应该从：

```text
“让模型自由生成 evidence text”
```

转向：

```text
“让模型选择 / 指向 raw JD 中的 evidence span”
```

---

# 9. 最重要的 10 个坑与工程结论

## 9.1 Structured Output 只保证格式，不保证事实

JSON Schema 能保证：

```text
字段存在
枚举合法
类型正确
```

但不能保证：

```text
importance 正确
type 正确
证据真实
scope 正确
```

因此 Schema 是起点，不是 Eval。

---

## 9.2 语义相同，不代表可以当证据

```text
至少在以下一个方向
```

和：

```text
至少在一个方向
```

人类理解接近，但第二句不是招聘方原话。

如果 JobLens 展示“JD 明确要求……”就必须能指回 raw JD。

---

## 9.3 Prompt contract 不是 runtime invariant

v6–v30 反复证明：

- Prompt 写了 must-have scope；
- Prompt 写了 waiver；
- Prompt 写了 alternative；
- Prompt 写了 verbatim；

Provider 仍会违反。

关键业务不变量最终必须由：

```text
validator
semantic guardrail
human gate
```

保证。

---

## 9.4 Type 是业务路由，不是 UI 标签

```text
需要有车端经验
```

标成 Skill 与 Experience，会走完全不同 evaluator。

因此质量审核要看 downstream consequence，而不是只看文本是否“差不多对”。

---

## 9.5 Importance 是 Eligibility 硬开关

Importance 错误会同时造成：

```text
False Reject
False Accept
```

这也是 v5 正式人工 Review 4 个 Reject 都必须阻止 baseline 的原因。

---

## 9.6 Deterministic repair 自己也会制造 bug

v14 repair 产生 duplicate 是典型案例。

所以 Pipeline 必须是：

```text
LLM output
→ deterministic grounding repair
→ deterministic semantic repair
→ final validator
→ Trace
```

deterministic 不等于无 bug。

---

## 9.7 去重必须非常保守

静默全局 dedupe 会隐藏：

- importance 冲突；
- type 冲突；
- Provider 不确定性。

因此只对可证明等价的 repair output 做收敛；无法证明时继续 fail-closed。

---

## 9.8 Scope 比关键词匹配难得多

真实 JD 会：

- 在后文重复 React/Python；
- 用编号分隔新的 hard gate；
- 把 cardinality header 与 bullet 分开；
- 在一个句子混合 education / experience / skill。

所以 scope 不能依赖“这个词全 JD 是否唯一”，必须引入 section / numbered-item / local clause boundary。

---

## 9.9 Provider outage 和模型质量必须分开

真实遇到过：

- 429；
- 502；
- 503；
- 504；
- plain 200 / json_schema 503。

正确做法：

- unavailable 单独分类；
- fail-fast；
- bounded retry；
- 每次 attempt 独立 Trace；
- structured path 双健康门禁；
- outage 不算语义质量反证。

---

## 9.10 Canary 的价值经常是“及时 Stop”

大量版本是：

```text
3/3 HTTP 成功
但人工 Stop
```

因为：

```text
HTTP 200
Schema valid
Trace complete
```

只代表技术链路成功。

质量 Canary 的真正职责是：

> 用最小真实成本尽快发现 blocking Bad Case，阻止坏版本扩散到 20 Case 或下游 Match。

---

# 10. 为什么一直版本化，而不是直接覆盖？

当前至少维护：

```text
extractorVersion
promptVersion
semanticPolicyVersion
```

它们分别回答：

```text
整套 Extraction 行为是哪一代？
模型看到哪个 Prompt？
后处理用了哪版确定性语义策略？
```

版本化保证：

- Trace 可解释；
- Regression 可重放；
- Acceptance cohort 不串证据；
- old Run 不冒充 new version 质量证明；
- Bad Case 能定位到具体行为版本；
- baseline 可以真正冻结。

例如 v29 和 v30 即使只改了 Prompt，也必须是不同 cohort。

---

# 11. 为什么坚持 Fail-Closed？

很多地方都可以为了“跑通率”做宽松处理：

- grounding fuzzy match；
- duplicate 全部自动删；
- type 错但文本接近就忽略；
- importance 不确定统一 preferred；
- 503/504 无限 retry；
- 旧版本 Extraction 混入新版本 Acceptance。

短期数字会更好看，但会破坏 JobLens 的核心承诺：

> 重要职业判断必须追溯到真实 Profile Evidence、SearchIntent 或真实 JD Requirement。

因此当前安全偏好是：

```text
不确定
→ fail / stop / review
```

而不是：

```text
不确定
→ 猜一个最可能答案继续
```

---

# 12. Canary / Human Gate / Attempt Budget 为什么必要？

真实 Provider 有成本和副作用，因此当前流程是：

```text
Regression
→ Readiness
→ Provider Health
→ 1~3 Case Canary
→ Human Review
→ Continue / Stop
→ Bounded Resume
→ 20-case Manual Review
→ Final Release Decision
```

几个治理规则：

### 失败 attempt 也计数

即使 503/504 没有 Extraction，也已经消耗：

- 请求；
- 时间；
- Trace；
- 可能的 Token；
- 排查成本。

### Continue 不等于质量通过

Continue 只代表：

> 当前证据允许继续收集更多真实样本。

不代表：

- 20 Case 完成；
- baseline accepted；
- 可以进入 Match。

### Review 不可修改

因为它是审计事实：

```text
谁
基于哪些 Case / Extraction / Trace
为什么
在当时决定 Continue / Stop
```

如果判断需要纠正，创建新 Run，不改写历史。

---

# 13. v1–v30 的架构认知升级

## 阶段 1｜相信 Structured Output

```text
LLM
→ JSON Schema
→ Validate
```

发现：格式合法不代表业务正确。

## 阶段 2｜加入 Evidence Grounding

```text
LLM
→ Schema
→ Exact JD Evidence
→ Validate
```

发现：证据真实不代表 importance/type/scope 正确。

## 阶段 3｜加入 Deterministic Semantic Guardrail

```text
LLM
→ Grounding Repair
→ Semantic Repair
→ Final Validation
```

发现：repair 本身也会产生 duplicate / scope bug，需要 Trace 和反例测试。

## 阶段 4｜从 Extraction 视角转向 Evaluator 视角

不再只问：

> “这条输出看起来像不像正确答案？”

而是问：

> “这个 type / importance / capability 进入 Eligibility 后，会不会造成 false reject / false accept？”

这是 v20–v29 最重要的成熟标志。

## 阶段 5｜确认 Prompt-only Grounding 上限

v29/v30 明确说明：

> “让模型逐字复制”不是可靠协议。

Evidence anchoring 应该成为结构化接口，而不是自然语言要求。

---

# 14. 下一阶段：v31 不应只是 Prompt v5

当前最值得做的是 **structural exact-span grounding**。

目标：

```text
LLM：理解这是什么 Requirement
程序：证明它对应 raw JD 中哪一个连续 span
```

可评估的实现方向：

## 方案 A｜模型返回 source offsets

```json
{
  "start": 120,
  "end": 168,
  "type": "experience",
  "importance": "must_have"
}
```

Backend 按 offset 切 raw JD，再严格验证。

风险：LLM 对字符 offset 本身可能不稳定。

## 方案 B｜短 anchor + deterministic exact location

模型返回稳定的前后 anchor，Backend 在 raw JD 中唯一定位 span。

如果无法唯一定位，fail-closed。

## 方案 C｜先生成 clause candidates，模型只能选择

```text
Raw JD
→ deterministic sentence/clause splitter
→ candidate spans
→ LLM 选择 candidate ID + semantic fields
→ persistence 使用 candidate raw text
```

这会显著减少模型“自由生成 evidence text”的空间。

## 不变的原则

无论采用哪种方案：

```text
最终持久化的 originalText / evidenceSpan
必须来自 raw JD slice
```

不把 fuzzy semantic similarity 重新引入事实层。

---

# 15. 这段经历可以沉淀出的 LLM / Agent Engineering 能力

这 30 个版本最有价值的部分，不是“写了 30 版 Prompt”，而是形成了完整的质量工程闭环：

```text
真实 Bad Case
→ 判断 downstream impact
→ 冻结 Run / Trace
→ 写 failure regression
→ 最小 deterministic 修复
→ 版本升级
→ 回归测试
→ 新 Canary
→ Human Continue / Stop
```

对应能力包括：

- Structured Output；
- Grounding / Citation Reliability；
- deterministic guardrail；
- Eval / Bad Case 回流；
- Trace / observability；
- Provider reliability；
- timeout / retry / attempt budget；
- Canary；
- Human-in-the-loop governance；
- versioned cohort / immutable evidence；
- downstream evaluator-aware LLM quality engineering。

---

## 15.1 2026-08-21 补充：v42.8 → v42.9 的组合语义收敛

v42.8 的 3 Case Canary 在技术链路上 3/3 成功，但人工审核发现一个新的 evaluator-sensitive Bad Case：同一条显式任职资格被 Provider 拆成多个互相重叠的 `must_have`，以及一个带 `或 + 者优先` 的整行软条件被拆成多个独立 `preferred`。这些碎片文本单独看都来自原文，但进入 Match / Eligibility 后会产生重复硬门槛、重复加权或丢失替代关系，因此 v42.8 被 Stop，没有扩大到 20 Case。

v42.9 的修复原则不是继续逐个词打补丁，而是恢复“原始任职资格行”这个更接近业务语义的评估单元：

- 仅在显式 requirements/qualifications section 内触发；
- 原始整行必须能唯一 exact-grounded；
- 至少存在两个同线碎片，才允许 collapse；
- 无 soft marker、无 education/experience/threshold、无 cardinality alternative、无 inline example 的复合硬资格，收敛成一个 `constraint must_have`；
- 整行存在 `或/or` 且以明确优先标记结束时，多个 soft fragments 收敛成一个 `constraint preferred`，保留原始替代关系；
- 含 `(如...)` / inline example 的行明确排除，避免把“核心技能 + 示例列表”误合并，继续交给既有 example-child 规则处理；
- 不跨行、不 fuzzy merge、不重新调用模型猜语义。

这轮最重要的经验是：**Requirement 的最小可评估单元不一定等于模型最小拆分单元。** 当 JD 原文表达的是一个组合资格或替代组时，过度原子化本身就是语义错误。Deterministic repair 的目标不是“尽可能多保留碎片”，而是恢复对 downstream evaluator 最安全、最接近招聘方原始条件结构的事实单元。

验证顺序同样保持 fail-closed：先用真实 Bad Case 建红灯回归，再修规则；宽回归曾抓到 example-child 被误合并的副作用，因此进一步收窄 grammar；收窄后 workflow + adapter 宽回归恢复全绿。完整 Requirement 回归最终达到 365/365 通过，Provider plain + json_schema 双健康均返回 200，readiness 允许执行后，v42.9 才启动唯一一次 3 Case Canary。

v42.9 Canary 的结果是 2 个成功、1 个失败。失败的是金山办公目标 Case，但 Trace 仅记录 `OpenAI Requirement extractor failed: ValidationError`，没有 `semanticPolicyVersion`、`semanticRepairs` 或 Requirement output，说明失败发生在 Provider structured-output 校验阶段，尚未进入 `requirement-semantics-v40`。因此这次失败既不能证明 same-line collapse 规则有问题，也不能作为该规则通过真实 Case 的证据。按同版本一次 Canary 与 fail-closed 门禁，本轮正式 Stop，不重试、不扩大 20 Case。

下一轮最小安全增量不是继续修改组合规则，而是先增强 Provider structured-output `ValidationError` 的诊断可观测性：在不泄漏敏感 JD/Provider 原始内容的前提下，Trace 至少应能区分 schema parse、字段 validation、response shape 等失败阶段，并保留足够的结构化错误摘要。只有能证明失败属于 Provider 随机格式漂移还是 adapter/schema 契约问题后，才决定是否需要 v42.10 的代码 patch，再重新进入新的最多 3 Case Canary。

## 15.2 2026-08-21 补充：v42.10 → v42.12 的 Provider 可观测性、方向子项恢复与预算内重试

v42.10 先把此前被压扁成 `ValidationError` 的 Provider structured-output 故障分层：Trace/Error 在不记录原始 Provider 文本的前提下，能够区分 `structured_output_json`、`structured_output_validation`、`provider_response_shape`、refusal 与 transport 等阶段，并对 Pydantic validation 仅记录字段路径和错误类型摘要。专项与完整 Requirement 回归通过后，v42.10 Canary 技术上 3/3 extracted，但人工审核发现 Harness Case 的四个显式方向子项（前端、桌面、后端、工程化）全部被 Provider 漏掉，只留下“至少一个方向”的父约束。这个输出不会错误制造四个 hard gate，却会让下游失去可选集合，因此 v42.10 Stop。

v42.11 保持 Prompt v7 和既有 grounding 不变，只增加 `requirement-semantics-v41` 的窄范围 deterministic child recovery：父项必须已经是显式 requirements section 内 exact-grounded 的 hard cardinality constraint，原始父行必须明确“以下/下列/如下”等 following-list 关系并以冒号结束；到下一个顶层编号 sibling 之前的全部非空行都必须是明确方向/选项标签或 bullet，任何叙述文本、soft/hard child marker、歧义 grounding 都会让整组恢复 fail-closed。恢复出的 child 使用原始 JD slice，统一为 non-blocking `preferred`；仅在 child 首 token 是单一明确 capability 时写入 React/Electron/Python/Git 一类 capability。红灯测试、mixed narrative 防误伤、workflow/adapter 宽回归和完整 Requirement 回归均通过。

v42.11 live Canary 随后是 2 extracted / 1 failed。Harness 在进入 semantics 前就失败，新诊断明确给出 `ValidationError(failureStage=structured_output_json, issues=root:json_invalid)`，因此这次没有机会验证 child recovery 的真实命中。v42.11 按同版本一次 Canary 原则 Stop，不重试、不扩 20 Case。

v42.12 不再修改语义策略，而是在现有 Requirement Acceptance attempt budget 内增加一个极窄恢复：只有 `RequirementExtractorFailedError.failure_stage == structured_output_json` 才允许同 Case 最多重试一次；重试像既有 504 recovery 一样消耗 `max_new_extractions`，字段 validation、response shape、grounding 或 deterministic validator 错误均不重试。专项验证确认一次 malformed JSON 后可恢复、连续 malformed JSON 只重试一次；完整 Requirement 回归达到 371/371。

v42.12 双健康再次 plain/json_schema 双 200，readiness 授权后启动唯一一次 3-attempt Canary `reqacceptrun_875fae732cc749fabe8e0107085ea9e0`。Case 0 成功；Harness 第一次返回 invalid structured JSON 后触发预算内 recovery，但第二次仍是同一 `structured_output_json / root:json_invalid`，因此 Harness `attemptDelta=2` 且失败，剩余预算为 0，Case 2 正确 deferred。这个 live 结果证明重试门禁和预算记账按设计工作，同时也证明当前 blocker 已从“错误分类不清”收敛为“Provider 对 Harness 输入持续返回非法 structured JSON”。本轮正式 Stop，不继续给 v42.12 增加重试次数，也不扩大到 20 Case。

下一轮最优先事项不是继续堆 deterministic semantics，也不是放宽 JSON/grounding，而是针对 Provider 结构化输出稳定性做离线/低成本诊断：确认 Harness 是否存在稳定触发 provider malformed JSON 的输入形态、输出 token 截断或 Provider json_schema 实现缺陷；在有证据前不应增加第二次以上 retry。若 Provider 后续健康且问题无法稳定复现，再通过新 patch 版本做一次最多 3 Case Canary 验证 `requirement-semantics-v41` 的真实 Harness child recovery。

## 15.3 2026-08-21 补充：v42.13 → v42.14 的 malformed JSON 诊断与 capability scope 修复

v42.13 不改 Prompt、grounding、coverage 或 retry 次数，只补 Provider malformed structured-output 的安全诊断。Adapter 在 Pydantic JSON validation 失败时记录 `finishReason`、input/output token usage、输出字符数以及请求的 completion-token cap，并把失败 token usage 带进 Trace；不记录 Provider 原始输出。专项回归 142/142、完整 Requirement 回归 372/372 通过，随后 Provider plain/json_schema 双健康均为 200。

v42.13 唯一一次 3-attempt Canary 为 `reqacceptrun_e40109e3e0f64cf88c64c2a2eed4c13a`。Case 0 一次成功；Harness 第一次 malformed JSON 后触发既有的一次预算内 recovery，第二次成功，因此 Harness `attemptDelta=2`，总预算耗尽后 Case 2 正确 deferred。人工审核 Harness 成功输出时，父 cardinality 与四个 child 的 `preferred` importance 均正确，但四个方向子项的 `normalizedCapability` 被 Provider 写成了 `前端 / 桌面端 / 后端 / 工程化`，而不是行内具体技术能力 `React / Electron / Python / Git`。这不会制造 false hard gate，但会削弱下游技术栈匹配，因此 v42.13 以 `reqacceptcanary_177b259c746a493b94f861354594d9dd` 正式 Stop，不扩 20 Case。

v42.14 在 `requirement-semantics-v42` 中做窄范围 deterministic capability-scope repair。仅当 child 已是 `skill preferred`、位于唯一 bounded alternative-group scope、evidence 使用明确方向/选项 label、当前 capability 确实来自该 generic label，且 child body 首 token 是单一明确英文 capability 时，才将 capability 改为 body 首 token。例如 `【前端方向】:React...` 且 Provider 返回 `前端` 时修为 `React`。如果 Provider 已返回具体 capability（例如 `TypeScript`），保持不变。该修复不改变 importance、原文 evidence、cardinality、grounding、Prompt 或 retry policy，并配有真实 Harness 形态红灯和“具体 capability 不覆盖”的防误伤回归。

v42.14 专项与防误伤回归 2/2 通过，workflow + adapter 宽回归 144/144，完整 Requirement 回归 374/374；Provider plain/json_schema 双健康均为 200，readiness 确认为全新 0-attempt Run 后，执行唯一一次 3-attempt Canary `reqacceptrun_bf0c86d8da49467982b2009791fbbc84`。结果为 1 extracted / 2 failed：Case 0 因 Provider 返回不存在的 `sourceCandidateId=S00011` 被 fail-closed；Case 2 因 `structured_output_json` 失败，但 v42.13 新诊断明确记录 `finishReason=stop`、`outputTokens=693`、`requestedMaxCompletionTokens=8192`、`outputChars=2324`，因此可以排除 completion token 截断，问题更接近 Provider 在正常 stop 下仍返回非法 JSON。

唯一成功的 Harness Case 也没有通过人工语义门禁。Provider 本次把四个方向行全部输出为 `responsibility must_have`，且 capability 仍是 `前端方向 / 桌面端方向 / 后端方向 / 工程化/代码控制方向`。由于 v42.14 的修复边界只覆盖 `skill preferred` child，它没有触发；更严重的是四个 alternative child 再次变成四个独立 hard gate。说明真正稳定的系统边界不能只修 capability label，还必须先从 exact cardinality parent + bounded child scope 恢复 child 的 canonical type/importance，再做 capability normalization。v42.14 以不可变 Stop `reqacceptcanary_4eff7c4580d14c3ebb3c7ebf8308b76f` 收口，不重试、不扩大到 20 Case。

v42.15 将 Harness 的真实 v42.14 shape 固化为红灯，并继续留在 v42 主线。根因是 Provider 把 hard cardinality parent 的 `originalText` 截成 `工程能力扎实`，但 exact `evidenceSpan` 仍保留完整 `至少在以下一个方向...:`，导致原先只从 `originalText` 建立的 group scope 丢失。`requirement-semantics-v42.15` 现在仅允许 hard constraint parent 在 explicit requirements section 内、exact evidence 同时满足既有 alternative-cardinality + following-list grammar 且以冒号结尾时，用该 evidence 建立 bounded scope。只有位于唯一 scope 且使用明确 `【方向/选项】:` label 的 child，才允许把 `responsibility must_have` 或 hard `skill` 漂移归一为 `skill preferred`；capability 只在为空或来自 generic label 时取 child body 的首个明确英文技术 token。已有 `skill preferred` 仍交给 v42.14 capability-only repair，Provider 已选中的具体 capability（例如 TypeScript）不覆盖。真实红灯及两个防回归用例已通过 3/3。

v42.15 宽回归 174/174、完整 Requirement 回归 375/375 通过，Provider 再次 plain/json_schema 双 200，readiness 确认为全新 0-attempt Run。唯一一次 3-attempt Canary 为 `reqacceptrun_c7257ca88135455989b0cf58c7c14ef8`：Case 0 首次失败后预算内恢复并 extracted，Harness 直接 `structured_output_json` 失败，诊断为 `finishReason=stop / outputTokens=468 / requestedMaxCompletionTokens=8192 / outputChars=1631`，因此仍可排除 completion token 截断；Case 2 因总预算耗尽 deferred。目标 Harness repair 本轮没有获得 live 验证。

人工审核唯一成功 Case 0 时发现新的 evaluator 风险：原文 `熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)` 是 umbrella requirement + examples，但 Provider 将 `normalizedCapability` 绑定为示例 `LangChain`。Requirement 文本与 must-have scope 本身正确，可下游若按 normalized capability 匹配，会把“熟悉 Agent 技术栈”错误收窄成“必须 LangChain”，与既有 example-child 非 hard-gate 原则冲突。v42.15 因此以不可变 Stop `reqacceptcanary_fc1d911396a7445aa6e89431079a98fe` 收口，不扩 20 Case。

`sourceCandidateId` hallucination 与 `finishReason=stop` 的 malformed JSON 继续按 Provider reliability 证据处理，不放宽 source ID 或 JSON validation。

v42.16 将 v42.15 的 example-capability leakage 固化为新的窄修：仅当 Requirement 是 `skill must_have`、`originalText` 在 JD 中 exact-grounded、正文包含明确 `如/例如/比如/such as/e.g.` inline example list、Provider 当前 `normalizedCapability` 只出现在 example suffix 且不在 umbrella prefix 中，同时 umbrella prefix 本身仍满足既有 hard-skill grammar 时，才把 capability 恢复为去掉 hard-skill 动词后的 umbrella 文本。该修复不改 `originalText / evidenceSpan / type / importance`，Provider 已返回正确 umbrella capability 时不触发，preferred 示例与普通具体技能也不触发。真实红灯与既有 example 防误伤专项 3/3，workflow + adapter 宽回归 146/146，完整 Requirement 回归 376/376 通过。

Provider plain/json_schema 再次双 200，v42.16 readiness 为全新 0-attempt 后执行唯一一次 3-attempt Canary `reqacceptrun_dfe9fcca84714f63ad5eb96ce311b656`。Case 0 一次 extracted；Harness 第一次 malformed JSON 后由既有单次 recovery 成功，因此总 attempt 恰好 3，Case 2 deferred。人工语义审核确认：Case 0 的 umbrella hard skill 保持为 `智能体技术栈`，没有再次收窄为 `LangChain`；Harness 的 hard cardinality parent 保留，四个方向全部为 `skill preferred` 且 capability 分别为 `React / Electron / Python / Git`，`不要求四项全会、至少 owner 一个方向` 仍是独立 hard constraint，Agent 工具、Agent 产品使用经验和工程习惯均无 duplicate/hard-gate leakage。`理解 LLM / Agent 的基本机制...` 本次为 `domain must_have`，在当前 Eligibility 中与其他非 skill/experience/education 类型一样仅在直接证据不足时产生 conditional，不会制造 false missing，因此不视为 blocking regression。

本轮提交不可变 Continue `reqacceptcanary_6bba34714866428b9baf7c98eeadbcf0`。Continue 只表示该 2-case 小 Canary 通过语义门禁，不代表自动批准 20 Case；本轮不扩跑。下一步应先从现有 Run 状态确认 acceptance 是否允许 bounded resume，再决定是否扩至 Case 2-4；若扩展，仍先双健康，并继续重点观察 Provider malformed JSON 与 sourceCandidateId adherence，而不是放宽 validation。

2026-08-21 后续 bounded resume 前 readiness 确认原 v42.16 Run 仍为 `partial + Continue`、`attemptedCallsBefore=3` 且允许 resume；Provider plain/json_schema 恢复双 200 后执行最多 3-attempt resume。Case 2 一次成功，Case 3 首次 malformed JSON 后由既有单次 recovery 成功，总 attemptedCalls 到 6，Case 4 因预算耗尽正确 deferred，未自动扩大。Case 2 的职责、学历/经验、Python、至少一种 Agent 框架、Prompt/RAG 复合 hard constraint 与 preferred 工具链保持合理。Case 3 暴露新的 evaluator-sensitive type drift：原文 `具有较强的沟通、表达、总结及文档制作能力,具有高度的责任心,并具有较高的抗压能力。` 中，Provider 将第一组抽象评价能力作为 `skill must_have / normalizedCapability=沟通、表达、总结及文档制作能力`，而同一行责任心/抗压能力已是 constraint；这会让当前 literal skill evaluator 把抽象软技能标签当成同名技术 Skill hard gate。由于这是实质 false-missing 风险，停止继续 v42.16 resume，不执行 Case 4 或更大扩跑。

v42.17 继续留在 v42 主线，只做窄范围 deterministic repair：对 exact-grounded `skill must_have`，仅当无 soft/alternative marker、原文是多段 compound qualification、首段满足 `具有较强/优秀/良好/...能力|素养|意识` 评价形态，且 Provider capability 确实来自该首段时，复用既有 `abstract_evaluative_skill_constraint` 将其归一为 `constraint must_have / normalizedCapability=null`。真实 Case 3 形态红灯已补充；普通工程习惯防回归仍通过。专项 2/2、workflow+adapter 147/147、完整 Requirement 回归 388 passed。该修复不改变 grounding、Prompt、coverage、retry、importance 或真实技术 skill 的类型。

v42.17 在代码回归后再次通过 Provider plain/json_schema 双 200 与全新 0-attempt readiness，执行唯一一次 3-attempt Canary `reqacceptrun_f46393526f224a86a1460305277570d4`。Case 0 与 Harness 各一次成功；Case 2 返回 `structured_output_json`，诊断为 `finishReason=stop / outputTokens=561 / requestedMaxCompletionTokens=8192 / outputChars=1877`，继续排除 completion-token 截断。人工审核确认 Case 0 的 umbrella `智能体技术栈` 仍未泄漏为 LangChain hard gate；但 Harness 出现新的组合语义 Bad Case：每个“至少一个方向” child line 被 Provider 展开成多个共享同一 original/evidence 的 independent `skill preferred`（前端 5、桌面 5、后端 5、工程化 8）。虽然没有 false hard gate，但会把一个方向的内部能力拆成大量独立加分项，破坏 direction-level cardinality/group weighting，并允许跨方向 partial match 被过度奖励。因此以不可变 Stop `reqacceptcanary_c031acca2d5941c792ae349b56ea157a` 收口，不重试 Case 2、不扩 20 Case。下一轮最小安全增量应只在唯一 bounded alternative-group scope 内，对同一 child evidence/original 的多 capability preferred siblings 做可观测 collapse，恢复一个 direction-level non-blocking child；不得跨 scope 合并，也不得改 hard/soft、grounding 或 Provider JSON 校验。

v42.18 继续沿 v42 主线处理上述 direction fan-out，不引入新的 Prompt 或 Provider 行为。仅当同一 exact child line 位于唯一 bounded alternative scope、至少两个 `skill preferred` sibling 共享完全相同的 `originalText/evidenceSpan` 且 capability 不同，才把这些 sibling canonicalize 到该行首个明确 capability，再复用现有 exact duplicate 去重，最终恢复为一个 direction-level non-blocking child。单个具体 capability（例如独立的 `TypeScript`）继续保留，不跨 line/scope 合并，也不改 importance、grounding、cardinality、retry 或 JSON validation。新增首版 fan-out 红灯与单 capability 防误伤回归；专项/宽回归 148/148、完整 Requirement 回归 389 passed。

v42.18 随后通过 Provider 双 200 与全新 0-attempt readiness，唯一一次 3-attempt Canary `reqacceptrun_2ddae1ad012a42aa8512b92758b92a1d` 三个 Case 均技术成功，但 Harness 仍有 31 条 Requirement：前端、桌面、后端、工程化方向继续被拆成大量 independent `skill preferred`。只读输出证明真实 Provider 形态不是 `originalText == evidenceSpan`，而是 `originalText=React/TypeScript/...` 等原子片段、`evidenceSpan` 才是完整方向行，所以 v42.18 条件未触发。该轮以不可变 Stop `reqacceptcanary_8fe9317f980d4866bf19275c4b8f0c99` 收口，不 resume、不扩 20 Case。

v42.19 只修正这一条错误假设：同一唯一 bounded alternative scope 内，若至少两个 `skill preferred` sibling 共享完全相同的 exact direction `evidenceSpan`，具有不同 capability 与不同原子 `originalText`，且每个原子文本都逐字出现在该 direction body 内，则统一恢复为完整 direction `originalText/evidenceSpan` 并使用该行首个明确 capability，再交给已有 exact duplicate 去重。单个具体 capability 仍不动，也不跨 line/scope 合并；importance、grounding、cardinality、Prompt、JSON validation 与 retry 全部不变。将测试改成真实 live 形态后先暴露首项 React 未提升导致 2 条残留，再修正为 sibling group 一旦成立首项也必须提升；最终宽回归 148/148、完整 Requirement 回归 389 passed。

v42.19 通过双健康与 0-attempt readiness 后执行唯一一次 3-attempt Canary `reqacceptrun_72f3d4d42c3f47f09507d370d693516f`，3/3 技术成功，但 Harness 仍有 29 条 Requirement。只读审核发现 skill siblings 部分收敛，而其余原子项被 Provider 漂成 `domain preferred`，例如同一前端 direction evidence 下仍残留 `复杂交互`、`桌面端 UI 工程` 等 domain preferred；桌面、后端、工程化同样存在。说明真正 invariant 是“同一 direction evidence 下多个 non-blocking 技术 sibling”，不是 skill type 本身。该轮以不可变 Stop `reqacceptcanary_d31c511a41644dccbf07b5e92c72440d` 收口，不 resume、不扩 20 Case。

v42.20 继续做最小 deterministic repair：仅在既有唯一 bounded alternative scope、同一 exact direction evidence、至少两个不同原子 `originalText` 且均逐字出现在 direction body 的前提下，允许 sibling type 为 `skill preferred` 或 `domain preferred`；一旦 group 被证明，统一恢复为一个完整 direction 行的 `skill preferred`，capability 仍取该行首个明确技术 token。must-have、其他 type、跨 line/scope、单 concrete child 全部不变。真实混合 skill/domain fan-out 红灯已补，宽回归 148/148；当前仓库完整 Requirement/Eligibility/Target Cohort 回归口径 387 passed。

v42.20 随后通过 Provider plain/json_schema 双 200 与全新 0-attempt readiness，执行唯一一次 3-attempt Canary `reqacceptrun_0eea07b66f4b441381cec5234ce62dad`。Case 0 与 Harness 成功，Case 2 为 `structured_output_json`，诊断 `finishReason=stop / outputTokens=1119 / requestedMaxCompletionTokens=8192 / outputChars=3609`，仍不是 completion-token 截断。人工审核 Harness 发现仍有 27 条 Requirement：前端方向已 collapse，但桌面、后端、工程化 direction evidence 下的 `domain preferred` 原子项继续残留。只读输出证明这些 domain 项真实为 `normalizedCapability=null`；v42.20 helper 仍要求 sibling 必须有 normalized capability，因此只在同一方向至少两个有 capability 的 sibling 时触发。以不可变 Stop `reqacceptcanary_a13aa37de43d400f9bdc71154f2093af` 收口，不重试、不扩 20 Case。

v42.21 只修这个实现假设，不扩大语义边界：仍要求唯一 bounded alternative scope、共享同一 exact direction evidence、type 仅 `skill/domain preferred`，但 sibling proof 改为依赖非空且逐字存在于 direction body 的原子 `originalText`，至少两个不同原子文本即可，不再要求 domain 原子必须有 `normalizedCapability`。canonical direction capability 仍只取 exact direction 行首个明确技术 token；单 concrete child、must-have、跨 line/scope、grounding、Prompt、JSON validation、retry 均保持不变。真实 `1 skill + 多个 domain preferred + normalizedCapability=null` 红灯先失败后通过，专项/防误伤 2/2、宽回归 148/148、完整 Requirement/Eligibility/Target Cohort 回归 387 passed。

v42.21 通过双健康与 0-attempt readiness 后启动唯一 Canary `reqacceptrun_a1660095d5a94f148dcb3f2a9ee25850`。首次 Case 0 成功、Harness HTTP 503 后 fail-fast；Provider 恢复双 200 后只在同一 Run 内消耗剩余 1 attempt，Harness 成功，总 attempt=3，Case 2 未再启动。Harness 从 v42.20 的 27 条收敛到 12 条，四个方向均恢复为单个 `skill preferred` child，证明 capability-null-safe fan-out collapse 在真实输出生效；但 Provider 将四个 capability 写成 `Frontend / Desktop / Backend / Engineering/Code Control`，属于方向 label 的英文翻译而不是具体技术能力，仍会削弱 React/Electron/Python/Git 下游匹配。因此以不可变 Stop `reqacceptcanary_feed0fd140c440d9ae16a45e4cdfbb3e` 收口，不扩 20 Case。

v42.22 继续做最小 bounded repair：在既有 exact direction-child grammar 和唯一 alternative scope 内，只增加四个 live direction label 的显式英文别名表（含紧邻拼写变体），把 `Frontend / Desktop / Backend / Engineering/Code Control` 识别为 generic direction capability，再恢复为 exact direction 行首个具体 token `React / Electron / Python / Git`。不做任意语义翻译，不覆盖具体 Provider capability（如 `TypeScript`），也不改 importance、scope、grounding、Prompt、JSON validation 或 retry。专项/防误伤 3/3、宽回归 149/149、完整 Requirement/Eligibility/Target Cohort 回归 388 passed。

v42.22 唯一一次 Canary 为 `reqacceptrun_e71eac112bf5483d88e230687dcd8bd6`，3 attempts 后 2 extracted / 1 failed。Case 2 继续是 malformed structured JSON，`finishReason=stop / outputTokens=577 / requestedMaxCompletionTokens=8192 / outputChars=1894`，仍可排除 completion-token 截断。更关键的是 Harness 回归到 30 条 Requirement：Provider 这次完全漏掉 `3.工程能力扎实,至少在以下一个方向非常熟练...:` 父 cardinality，只保留四个 direction body 并把大量原子技术输出为 `skill must_have`；因为系统没有 parent，就没有 bounded alternative scope，v42.22 的 child normalization 与 sibling collapse 都无法触发。该轮已以不可变 Stop `reqacceptcanary_4ed219d513174f629196cfddd7ea6124` 收口，不 retry、不扩 20 Case。

v42.23 只修这条缺失父 scope 的前置条件。系统仅扫描 recognized requirements section 中唯一 exact 行：必须命中既有 alternative/cardinality grammar、显式 `以下/下列/如下`、以冒号结尾、无 soft marker，并且在下一条 top-level 编号前只包含 2–8 个明确 direction-label child；同时每个 child 行都必须已经被 Provider 的 exact `evidenceSpan` 覆盖，才恢复一个 `constraint must_have` 父节点。这样只恢复 Provider 漏掉的显式结构，不从语义猜 parent；若 child evidence 不完整、scope 混入 narrative、存在 child hard/soft marker、跨 section 或 grounding 不唯一则不修。父 scope 恢复后继续复用已有 alternative-child 降级、direction fan-out collapse 与 capability normalization。真实缺父 hard-fanout 红灯先暴露 bracketed section detection 假设，再改为复用 `_is_requirement_section_span`；随后又暴露 sibling proof 读取 pre-normalization `must_have` 快照的问题，仅允许“已在 alternative scope 且无显式 hard marker”的 must-have 原子参与既有 sibling proof。最终宽回归 151/151，Requirement/Acceptance/Target Cohort/Eligibility 完整回归 390/390 passed。

随后 `deepseek-v4-flash` 恢复 plain/json_schema 双 200，v42.23 通过全新 0-attempt readiness 并启动唯一 Canary `reqacceptrun_fc317ecfb83a4c12944847f18014a16b`。3 attempts 得到 2 extracted / 1 failed：Case 2 再次 malformed structured JSON，`finishReason=stop / outputTokens=835 / requestedMaxCompletionTokens=8192 / outputChars=2572`，继续排除 completion-token 截断。Harness 已成功恢复缺失 parent cardinality，但 Provider 把四个 direction line 拆成 23 个独立 `skill bonus` 原子项；现有 sibling collapse 仅接受 preferred/must-have，因此没有收敛，仍破坏 direction-level cardinality 并过度奖励跨方向 partial match。该轮以不可变 Stop `reqacceptcanary_d7d804230817498ea02c88813f2e3914` 收口，不 retry、不扩 20 Case。

v42.24 做最小 importance-drift 修复：仅在既有唯一 bounded alternative scope、同一 exact direction evidence、至少两个 distinct atomic sibling 的 sibling-collapse proof 已成立时，允许 `bonus` 与既有 `preferred/must_have` 一样参与 fan-out 证明，并统一归一为一个 `skill preferred` direction node。单个 bonus、跨 direction/cross-scope 项、显式 hard child、非 direction evidence 均保持不变；不修改 parent cardinality、grounding、Prompt、Provider JSON validation 或 retry。新增真实 bonus fan-out 红灯后专项 3/3、workflow+adapter 152/152、Requirement/Acceptance/Eligibility/Target Cohort 完整回归 425/425 passed。下一步只允许在重新通过双健康和全新 0-attempt readiness 后启动 v42.24 唯一一次最多 3-attempt Canary。

2026-08-21：Provider plain/json_schema 双 200 后，v42.24 通过全新 0-attempt readiness，并启动唯一 Canary `reqacceptrun_feccaabfb0af47169025eb1dcf16e84f`。3/3 Provider 调用技术成功、0 failure、17 deferred。Harness 目标修复在 live 中稳定：父 cardinality 存在，四个方向分别收敛为一个 `skill preferred`，capability 为 React/Electron/Python/Git；Case 0 的车端 hard experience、Agent 技术栈 umbrella 与软经验也保持正确。但 Case 2 暴露新的 blocking example drift：职责 `基于LangChain、LangGraph、Dify等框架,构建面向研发场景的Agent应用(代码助手、运维助手、文档问答等)` 被额外拆出 `(代码助手、运维助手、文档问答等)` 作为独立 `domain must_have`，会把括号内示例误成 hard gate；同一职责行 `探索MCP协议...` 还被 Provider 漂为 preferred，但本轮不扩大修复范围。v42.24 已以不可变 Stop `reqacceptcanary_cc7216081043476aa056472bc3642024` 收口，不扩 20 Case。

v42.25 只修证据最强的 standalone parenthetical example child。复用既有 `drop_example_child` exact-evidence proof，仅新增“整个 child 是一个括号内列表、以 `等`/`etc` 收尾”的 example 识别；仍要求同一 exact evidence 上存在更早的 non-example `must_have` parent，才删除该 child。没有共享 hard parent、跨 evidence、非 example parenthetical、soft requirement 均保持不变；不修改职责 importance、grounding、Prompt、Provider JSON validation 或 retry。真实 Case 2 形态专项 3/3、workflow+adapter 153/153、Requirement/Acceptance/Eligibility/Target Cohort 完整回归 426/426 passed。Provider 双健康与全新 0-attempt readiness 通过后，v42.25 唯一 Canary `reqacceptrun_bfdacd5349834b4fa79f4f5380af083d` 3/3 技术成功。目标修复在 live 中生效：Case 2 的括号 example hard gate 消失，Harness 继续稳定为父 cardinality + React/Electron/Python/Git 四个 `skill preferred`。但 Case 0 将 `需要有车端经验,非车端经验的无法到副总师的层级` 作为一条 Provider-native `experience must_have` 原样保留，重新把否定性后果说明带入 literal experience evaluator。v42.25 已以不可变 Stop `reqacceptcanary_df1372246fdf457fbd52f84a1d0e9886` 收口，不扩 20 Case。

v42.26 只恢复这条已有 experience+explanation 安全边界。`_normalize_explicit_experience_type_drift` 现在也检查 Provider 原生 `experience must_have`：若 exact 文本严格是两个逗号段，第一段完整命中显式经验事实 grammar，第二段完整命中既有否定性 explanation grammar，则只保留第一段并清空 normalized capability；普通单句 experience 不记录无意义 repair，后缀若本身是另一个 hard requirement 则保持原样。专项 2/2、workflow+adapter 154/154、Requirement/Acceptance/Eligibility/Target Cohort 完整回归 427/427 passed。下一步重新过双健康与全新 0-attempt readiness 后，v42.26 才允许唯一一次最多 3-attempt Canary。

2026-08-21：v42.26 实际已完成唯一一次 3-attempt Canary `reqacceptrun_4c494ec878e54059a44dc3476aabab53`，3/3 技术成功。目标 experience 修复在 Case 0 生效，Case 2 的 parenthetical example 修复保持稳定；但 Harness 再次出现 direction-level fan-out：四个明确 alternative direction 被 Provider 输出成 23 个 `skill preferred`，这次每组 sibling 的 `originalText` 与 `evidenceSpan` 都重复整条 direction line，只通过不同 `normalizedCapability` 区分，因此 v42.24 的 sibling proof（要求至少两个不同 atomic `originalText`）没有触发。该 Run 已以不可变 Stop `reqacceptcanary_02cfa4f274174a3cb14fc18729b5f1e5` 收口，不允许重试或扩 20 Case。Case 0 还存在 education+experience 行的 overlapping `domain must_have`，但本轮不扩大修复范围。

v42.27 只修上述 full-line sibling proof 缺口。仍要求同一 unique bounded alternative scope、同一 exact direction evidence、允许的 skill/domain 与 importance 形态；若 sibling 的 `originalText` 全都等于整条 direction line，则必须至少存在两个不同且非空的 `normalizedCapability` 才证明为 Provider fan-out，并统一复用既有 canonical first-capability collapse。单个 full-line child、相同 capability duplicate、跨 direction/cross-scope、显式 hard child 和 unrelated evidence 均不触发。专项真实形态与 bonus/single-child 防误伤 3/3、workflow+adapter 155/155、Requirement/Acceptance/Eligibility/Target Cohort 完整回归 428/428 passed；Provider plain/json_schema 双 200 后进入 live gate。

2026-08-21：v42.27 唯一一次 3-attempt Canary 实际已经在前一轮连接中断前完成，Run 为 `reqacceptrun_647fbba696a1413685e574ec6ea33fae`。恢复连接后的 zero-call readiness 正确识别该 Run 已 `attemptedCalls=3 / nextAction=review_canary`，因此没有产生重复 Provider 调用。结果为 2 extracted / 1 failed / 17 deferred：Case 0 成功且车端 hard experience 等既有关键语义保持稳定；Harness 目标修复 live-proven，父 `至少一个方向` 为 `constraint must_have`，四个 direction 各自收敛为唯一 `skill preferred`，capability 分别为 React/Electron/Python/Git，Trace 明确记录多次 `collapse_alternative_group_child_siblings`。Case 2 仍因 `structured_output_json` 失败，诊断为 `finishReason=stop / inputTokens=1481 / outputTokens=1261 / outputChars=3887 / requestedMaxCompletionTokens=8192`，再次排除 completion-token 截断。按一版本一次 Canary 与任一失败即 Stop 的 fail-closed 门禁，本轮提交不可变 Stop `reqacceptcanary_8ef17c97197645d4ba15b441ebe47097`，不 retry、不扩 20 Case。下一步不应继续修改已经 live-proven 的 direction fan-out 语义，而应把 Provider 正常 stop 仍返回 malformed JSON 作为独立 reliability 问题处理。

v42.28 只验证一个 reliability 假设，不改 `requirement-semantics-v42.27`：Provider-facing JSON Schema 从 discriminated `oneOf + discriminator + $defs` union 简化为单一扁平 Requirement object；Provider 返回 JSON 后，backend 立即再通过原 `_RequirementsOutput` discriminated union 做严格二次校验，因此 `skill + normalizedCapability=null`、非法 type、extra field、sourceCandidateId/grounding 错误仍 fail-closed。Provider schema/strict-validation 专项 4/4、workflow+adapter 155/155、Requirement/Acceptance/Eligibility/Target Cohort 完整相关回归 423/423 passed；Provider plain/json_schema 双 200，zero-call readiness 为全新 `attemptedCallsBefore=0` 且 `providerExecutionAllowed=true`。

v42.28 唯一一次 3-attempt Canary 为 `reqacceptrun_32d17b7f89b044fda295a31a172e419f`，结果 1 extracted / 2 failed / 17 deferred。Case 0 成功；Harness 返回了可解析 JSON，但其中两条 `skill` 的 `normalizedCapability=null`，因此 backend 严格二次校验以 `structured_output_validation` 拒绝，证明 flat Provider schema 没有放宽 skill 合同。Case 2 仍为 `structured_output_json`，诊断是 `finishReason=stop / inputTokens=1481 / outputTokens=786 / outputChars=2472 / requestedMaxCompletionTokens=8192`，再次排除 completion-token 截断，也直接否定“复杂 `oneOf/discriminator` 是该 malformed JSON 主要根因”的假设。按一版本一次 Canary 与任一失败即 Stop 的 fail-closed 门禁，本轮已提交不可变 Stop `reqacceptcanary_f3423ab3c4904264b50c01bc2d29a84c`，不 retry、不扩 20 Case。下一 patch 不应继续围绕 schema 复杂度，也不应修补 malformed JSON 文本；应把 Provider 在正常 stop 下仍偶发非法 JSON 视为外部 reliability 问题，优先评估可观测的 provider/model/API-style 隔离或切换策略。

v42.29 将 Provider-facing schema 恢复为 v42.27 的严格 discriminated union，继续使用 `requirement-semantics-v42.27`，只把 live model 作为隔离变量。`responses` API style 在当前网关 plain probe 即 HTTP 400，因此被排除；`deepseek-v4-pro + chat_completions` 的 plain/json_schema 双探针均为 200。代码回归为 workflow+adapter 155/155、Requirement/Acceptance/Eligibility/Target Cohort 423/423。全新 zero-call readiness 确认 `model=deepseek-v4-pro / attemptedCallsBefore=0 / providerExecutionAllowed=true` 后执行唯一 3-attempt Canary `reqacceptrun_35e93782875b427cb897cb3fb5faa909`，3 个 Case 全部一次 extracted，无 malformed JSON、无 retry、无缺失 Trace，说明 pro 在这组样本上的 structured-output reliability 明显优于 flash。

但人工语义审核未通过。Harness 的 cardinality/type/importance 基本正确，四个 direction 仍各自为单个 `skill preferred`，但 normalized capability 漂成 `frontend engineering / desktop application development / backend engineering / engineering infrastructure`，没有恢复成 React/Electron/Python/Git，削弱下游技术栈匹配。Case 2 还把同一条 `基于LangChain、LangGraph、Dify等框架...构建Agent应用` 职责重复持久化为 3 条 `responsibility must_have`，仅 normalized capability 分别是 LangChain/Dify/LangGraph，形成 example-driven duplicate weighting。该 Run 已提交不可变 Stop `reqacceptcanary_4f8d4909a87d4119968a145072e211ad`，不 resume、不扩 20 Case。下一轮最小安全增量应同时固化这两个 live shape：一是 bounded direction child 的 generic semantic label 归一化边界，二是同 exact responsibility evidence/original 下仅 capability 不同的 example fan-out collapse；仍不得放宽 grounding、importance、cardinality 或 Provider validation。

v42.30 将上述两个 v42.29 live Bad Case 固化为窄范围 deterministic repair，并继续使用 v42 主线。第一处仅扩展既有 direction-label alias 表，新增 `frontend engineering / desktop application development / backend engineering / engineering infrastructure` 四个已经在 live 出现的 generic label；它仍要求 child 位于唯一 bounded alternative scope、evidence 使用明确 direction label，并只恢复到 exact child body 首个 concrete capability，因此 React/Electron/Python/Git 之外不做开放式语义推断。第二处仅在 `responsibility` sibling 具有完全相同的 exact `originalText + evidenceSpan + importance`、且至少出现两个不同 non-empty normalized capability 时收敛为一个职责事实，并清空 capability，防止同一职责因 LangChain/Dify/LangGraph 等注解被重复计权；单个 capability annotation、跨 evidence/type/importance 均保持不变。专项 3/3、workflow+adapter 158/158、Requirement/Acceptance/Eligibility/Target Cohort 完整相关回归 431/431 passed。下一步只允许在 Provider 双健康与全新 0-attempt readiness 后进入 v42.30 唯一一次最多 3 Case Canary。

v42.30 live gate 显式使用 v42.29 已隔离验证的 `deepseek-v4-pro`；默认 runtime 当时已回到 flash，因此仅对 health/readiness/Canary 命令做进程级 model override，不修改或提交环境配置。pro plain/json_schema 双 200，zero-call readiness 确认 `attemptedCallsBefore=0 / providerExecutionAllowed=true` 后，唯一 3-Case Canary `reqacceptrun_c145cb4714cb4ea89fc503e9010a1255` 3/3 均一次 extracted、0 failure、17 deferred。人工审核确认 Harness 的 hard cardinality parent 与四个 `skill preferred` direction child 均正确，最终 capability 为 React/Electron/Python/Git；Trace 在 `requirement-semantics-v42.30` 下真实记录 `normalize_alternative_group_child_capability`，证明 generic direction repair 至少命中一个 live child。Case 2 本次 Provider 自身只输出一条 LangChain/Dify/LangGraph Agent 应用职责，因此 responsibility sibling collapse 未 live 触发，但没有 duplicate weighting；对应分支由新增红灯和完整回归覆盖。Case 0 的 hard 车端经验、学历/8 年经验、Agent umbrella skill、preferred 落地经验/车企路径均保持合理。3 Case 未发现 blocking missing/duplicate/cardinality/importance/type regression，已提交不可变 Continue `reqacceptcanary_be1a8e80a54944659679fe7060ecaf5d`；Continue 仅代表小 Canary 通过，不自动扩 20 Case。随后 zero-call post-readiness 显示 Run 为 `partial / attemptedCalls=3 / canaryDecision=continue / nextAction=resume_run`，证明 acceptance 流程允许后续 bounded resume；初始 Canary operator 因 `next_action_is_not_run_canary` 正确阻断，没有产生重复 Provider 调用。

2026-08-22：对同一 v42.30 Run 做第二个 bounded resume 前，默认 runtime 已回到 flash；使用上一轮相同的进程级 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro` override 后，pro plain/json_schema 再次双 200，readiness 精确识别原 Run 为 `partial / attemptedCalls=3 / canaryDecision=continue / nextAction=resume_run`。本次只追加 3 次调用：Case 3 extracted；Case 4 以 `Requirement extractor returned more than 50 requirements` fail-closed，Trace 中 deterministic repair 后为 52 条；Case 5 以 `responsibility coverage too low: covered 0 of 4 explicit duty candidates` fail-closed。Case 5 的 Trace 实际已经包含大量 `responsibility must_have`，原 JD 结构是 `1. 核心AI引擎设计与实现` 这类短编号分组标题，后面再跟 `混合知识引擎构建: 设计并实现...` 等具体职责，说明 coverage-v2 把分组标题误当 duty candidate，形成确定性的 false failure。Case 4 的 52 条则来自复杂 compound/alternative JD，当前证据不足以安全提升上限或截断，因此不与本轮混修；v42.30 停止 further resume，剩余 14 Case 不继续烧成本。

v42.31 只修上述 coverage false failure，不改 `requirement-semantics-v42.30`。`requirement-coverage-v3` 仅在显式职责 section 内识别一种有结构证据的 group heading：短编号行后紧跟 `标签: 设计/构建/集成/开发/优化/...` 形式的具体职责时，编号行不计入 coverage，而标签化具体职责本身作为 candidate。既有普通编号职责（包括 `基于/持续跟踪/与...协作`）保持 v2 规则；教育/经验/阈值/soft marker 排除和 `>=4 candidates / <2 covered` 的 fail-closed 门槛均不变。真实缩减形态红灯及 coverage 防回归 4/4、workflow+adapter 159/159、Requirement/Acceptance/Eligibility/Target Cohort 完整相关回归 427/427 passed。Case 4 的 post-repair >50 继续作为独立 blocker 记录，不在 v42.31 放宽上限。

v42.31 通过 `deepseek-v4-pro` plain/json_schema 双 200 与全新 zero-call readiness 后，唯一 3-Case Canary `reqacceptrun_de796108cf764d448bae418566d8df94` 3/3 均一次 extracted。人工审核发现 blocking regression：Harness 的 hard cardinality parent 仍正确，但桌面、后端、工程化 direction 被重新拆成多个 `preferred` sibling；这次 Provider 把许多原子项漂成 `experience preferred`（如 `本地文件系统`、`跨平台桌面应用`、`异步/进程模型`、`diff/patch`），而既有 sibling collapse 只接受 skill/domain，因此无法收敛，重新造成同一方向内部多项加权。Case 0 基本稳定；Case 2 仍存在若干同职责子句重复，但不是本轮最强 blocker。v42.31 已提交不可变 Stop `reqacceptcanary_0094b098d4d2427d8b437a94b0d61e0f`，不 resume、不扩跑。

v42.32 只修上述 bounded alternative direction 的 experience-type drift，同时保留 `requirement-coverage-v3`。只有位于同一唯一 direction scope、importance 为 preferred/bonus、原文逐字位于该 direction body 且自身不含任何 experience/年限语义的 `experience` atom，才允许参与已有 sibling-collapse proof，并统一恢复成一个 `skill preferred` direction node；`experience must_have`、`3年以上桌面端开发经验` 一类显式经验事实、跨 direction/cross-scope 项均保持不变。真实 Harness 缩减红灯与显式经验防误伤通过，workflow+adapter 161/161；本轮重新按当前完整 Requirement/Acceptance/Eligibility/Target Cohort 口径复验为 434/434 passed。

2026-08-22：v42.32 实际已有 `deepseek-v4-pro` Run `reqacceptrun_442f4b92d5004c1fb08df6282adfc08b`。初始 3-Case Canary 3/3 均一次 extracted，人工审核确认 Harness 的 hard cardinality parent 保持正确，四个 direction 分别收敛为唯一 `skill preferred`，capability 为 React/Electron/Python/Git，v42.31 的 `experience preferred` fan-out 在 live 中消失；Case 0 与 Case 2 未发现新的 blocking hard-gate/duplicate/cardinality regression，因此提交不可变 Continue `reqacceptcanary_eb591a94be254fde9786e5eb2af5be52`。随后同一 Run 已完成第一段 bounded resume 至 Cases 3–5，总 attemptedCalls=6：三项均一次 extracted；复审确认 Case 4 的 `Python/Go/Java 至少一门`、四方向至少两项、`PyTorch/TensorFlow` 都保持 hard parent + non-blocking child，Case 5 的 grouped responsibility coverage 在 `requirement-coverage-v3` 下正常，不再出现 v42.30 的 false 0/4 failure。

本轮再次确认 `deepseek-v4-pro` plain/json_schema 双 200 后，只对同一 Continue Run 追加第二段最多 3 Case bounded resume，没有新建 Run。Cases 6–8 仍 3/3 一次 extracted，使该 Run 到 `attemptedCalls=9`。人工审核：Case 6 的学历/2 年经验/微调与部署 hard requirement、计算机视觉 preferred 和三条职责层级合理；Case 7 的 RAG/Agent/Python 为 hard，LangChain/LlamaIndex/AutoGen/MetaGPT 仅作为 preferred example children，客户交互经验保持 preferred；Case 8（东风汽车）历史 importance 错分未复发，搜索/推荐经验、MCP+智能体框架、至少一种编程语言、系统分析能力均为 must-have，只有车载应用开发经验和系统性能优化经验为 preferred。9 个已跑真实 Case 未出现新的 malformed JSON、coverage false failure、direction fan-out 或 blocking importance/cardinality/duplicate regression。

下一段 bounded resume 实际由同一 identity 的并发执行者完成至 Cases 9–11；当前 Run `reqacceptrun_442f4b92d5004c1fb08df6282adfc08b` 为 12 extracted / 0 failed / 8 deferred，累计 `attemptedCalls=12`。人工审核发现 Case 9「大模型应用工程师」存在 blocking importance drift：JD 明确进入 standalone `加分项:` section 后，`MCP协议深度实践` 下的 `熟悉MCP协议的设计理念和实现细节`、`有实际的协议实现或集成经验`，以及 `论文与技术博客` 下的技术论文/博客经验被 Provider 输出为 `must_have`。这些文本本身没有逐条重复“优先/加分”字样，但 section heading 已明确给出 soft scope；继续按 hard gate 持久化会造成 Eligibility false reject。Case 10 的 mixed education/experience 行与 Case 11 的职责父子重复仍值得后续观察，但本轮最强 blocker 已足够停止 v42.32 继续 resume，因此不执行 Cases 12–19。

v42.33 只修上述显式 bonus-section importance inheritance，不改 `requirement-coverage-v3`、type、capability、grounding、cardinality 或 Provider contract。系统仅在 requirement 的 exact evidence 位于 standalone `加分项/加分条件`（或显式英文 bonus heading）之后、且尚未进入下一个 recognized section heading 时，把 Provider `must_have/preferred` importance 归一为 `bonus`；一旦进入后续 `岗位职责/任职要求/...` section 即停止继承。真实 Case 9 形态红灯同时覆盖三个 must-have 漂移与跨 section 防泄漏；专项 2/2、workflow+adapter 162/162、当前完整 Requirement/Acceptance/Eligibility/Target Cohort 回归口径 430/430 passed。

v42.33 通过 `deepseek-v4-pro` plain/json_schema 双 200 与全新 zero-call readiness 后，同 identity 已有并发执行者先完成两次 Provider 调用；安全门因此阻止继续烧剩余第 3 次。只读审核 Run `reqacceptrun_d936e250ac68406c87b0dab04475eb32` 发现 Case 0 稳定，但 Harness 出现新的 direction-level fan-out：hard parent `至少一个方向` 保留，四个 direction 内大量原子项被 Provider 漂成 `constraint preferred`（例如状态管理、复杂交互、桌面端 UI 工程、本地文件系统、异步/进程模型、diff/patch 等），而 v42.32 sibling proof 只接受 skill/domain/experience，因此没有收敛。该轮已提交不可变 Stop `reqacceptcanary_9440180ab66f493488cf1d1396059cea`，不补第 3 次、不扩跑。v42.33 的 bonus-section 本地修复保留，但尚未通过 live Case 9 复验。

v42.34 只扩展这一条 bounded sibling proof：`constraint preferred/bonus` 仅在同一 unique alternative direction scope、共享同一 exact direction evidence 且 fan-out proof 至少有两个 sibling 时才允许参与 collapse；`constraint must_have` 明确排除，真实 hard child 不会被降级或吞并。参与后统一恢复为一个完整 direction 行的 `skill preferred`，capability 仍取该 exact line 首个具体技术 token。真实 Harness constraint-fanout 红灯、hard-constraint 防误伤与 v42.33 bonus-section 回归 3/3；workflow+adapter 164/164，当前完整 Requirement/Acceptance/Eligibility/Target Cohort 回归 432/432 passed。

v42.34 通过 Pro 双 200 与全新 zero-call readiness 后，同 identity 再次已有并发执行者先推进 live Run `reqacceptrun_41c7c947955a46989ef235a430d6797a`。安全门阻止本调用继续烧预算；只读审核现有 Case 0/1 证据时，Case 0 基本稳定，但 Harness 的 direction fan-out 再次出现。此次不是 `constraint preferred`，而是多条 `skill preferred` sibling：每个 sibling 的 `originalText` 都重复完整 direction line、但比 exact `evidenceSpan` 少末尾句号，且通过不同 `normalizedCapability` 区分。v42.27 full-line proof 要求 `originalText == evidenceSpan` 精确相等，因此未触发。该轮已提交不可变 Stop `reqacceptcanary_c8c4b82af8394c939df846c6adb25af4`，不补 pending Case 2。v42.34 的 constraint-drift 修复保留为本地已回归能力。

v42.35 只修上述 presentation-only full-line gap：full-line sibling proof 现在仅允许 `originalText` 与 exact direction `evidenceSpan` 在去掉末尾 `，,。.;；` 与首尾空白后完全一致；仍必须位于同一 unique bounded alternative scope，并至少有两个 distinct non-empty capability 才成立。内部标点、措辞、label、大小写、scope 或 evidence 任何其他差异都不会归一；单个 presentation-drift child 保持原样。一旦 proof 成立，持久化恢复 exact evidence 全行并取首个具体 capability。真实 v42.34 形态、单 child 防误伤、v42.34 constraint drift、hard constraint 与 v42.33 bonus-section 专项 5/5；workflow+adapter 166/166，完整 Requirement/Acceptance/Eligibility/Target Cohort 回归 434/434 passed。下一步重新过 Pro 双健康与全新 v42.35 zero-call readiness 后，才允许唯一一次最多 3-Case Canary。

v42.35 live Run 为 `reqacceptrun_62693ffea140440da6877d8f030b2538`。初始 Canary 3/3 均一次 extracted，人工审核确认 Harness 的 hard `至少一个方向` parent 保留，四个 direction 精确收敛为 React/Electron/Python/Git 四个 `skill preferred`，Case 0/2 也没有新的 blocking hard/soft、duplicate 或 cardinality regression，因此提交不可变 Continue `reqacceptcanary_a266bacca9b34683bfa80ee18de3e844`。后续 bounded resume 期间，同 identity 的并发执行者多次先于本调用获取 execution lease；本轮始终复用已有 evidence，没有重复烧 Provider。Run 最终继续推进到 Cases 0–8 全部 extracted、累计 `attemptedCalls=9`。Case 3「泛医疗行业大模型解决方案专家」重新暴露历史 evaluator-sensitive type drift：JD 原文第 7 条是 `具有较强的沟通、表达、总结及文档制作能力,具有高度的责任心,并具有较高的抗压能力`，Provider 将第一段单独切出为 `skill must_have / normalizedCapability=沟通表达`，同一 exact evidence 的责任心和抗压能力则为 constraint；这会让 literal skill evaluator 把抽象评价能力当技术 Skill hard gate。Case 8「智能体开发工程师」又暴露独立 cardinality drift：原文 `熟练掌握C/C++/Go/Python等一种以上编程语言` 明确只要求至少一种，但 Provider 同时持久化 `C/C++`、`Go`、`Python` 为多个独立 `skill must_have`，会把 one-of 错成 all-of。两者均属于 blocking false-reject 风险，因此不执行 Case 9；Case 3 先进入 v42.36，Case 8 cardinality 明确保留给后续独立 patch，避免把两个假设混在同一版本。

v42.36 只补上述 Case 3 split-compound gap，不改 coverage-v3、importance、grounding、cardinality 或 Provider contract。仅当 `skill must_have` 的 exact `originalText` 恰好等于同一 exact `evidenceSpan` 去编号后的第一个逗号段、该段完整命中既有 `具有较强/优秀/良好/...能力|素养|意识` 抽象评价 grammar、且 evidence 至少还有一个后续 clause 时，才归一为 `constraint must_have / normalizedCapability=null`。standalone 技术 skill、soft/alternative 项、跨 evidence 项和非评价能力文本均保持不变。聚焦专项 2/2、workflow+adapter 167/167、完整 Requirement/Acceptance/Eligibility/Target Cohort 回归 435/435 passed。`deepseek-v4-pro` 再次 plain/json_schema 双 200，zero-call readiness 为 attemptedCalls=0；但同 identity 并发执行者先取得 Canary lease。本轮在安全门阻止继续调用后审核已有 Case 0，发现新的 responsibility parent/child duplicate：同一 duty line 同时保留完整职责与其子句（如完整“主导企业级AI应用…构建AI中台”又单独保留“构建可复用的AI能力中台”，类似重复还出现在规模化推广、CI、智能体平台）。这会造成职责重复计权，已足以 Stop；提交不可变 Stop `reqacceptcanary_581f9301c3b848959c093b68bebb06a4`，不主动补烧剩余 Canary。Stop 落库前并发执行已继续产生 Case 1/2，因此 review 记录最终覆盖 3 个 extraction，但决策依据无需扩大：Case 0 duplicate 已是 blocking。v42.36 的 Case 3 修复目前只有本地回归证据，尚未 live-proven。下一轮最优先修复应是同 exact duty evidence 下的 responsibility parent/subclause duplicate；Case 8 的 inline one-of language cardinality 仍作为随后独立 blocker，不应遗忘或混入同一 patch。

v42.37 收口 responsibility parent/subclause duplicate。只有当同一 exact `evidenceSpan` 上已经存在 `originalText == evidenceSpan` 的完整 `responsibility` parent，且 sibling 与 parent importance 相同、`originalText` 是 parent 内的严格子串时，才删除该 sibling，并记录 `drop_redundant_responsibility_subclause`。如果没有完整 parent，则多个职责子句继续各自保留；不同 importance、不同 evidence、跨职责行均不合并。这个边界只消除重复计权，不改变职责内容、hard/soft、coverage 或 grounding。

v42.38 处理 evaluator-sensitive 的技术 hard skill type drift。Provider 若把 exact-grounded 的 `熟悉/熟练/掌握/精通/使用 + 技术对象` 错标成 `experience must_have`，且文本不包含经验/年限、soft marker、alternative/cardinality，也不存在同证据的正确 skill sibling，则归一为 `skill must_have`。若文本带 `如/例如/e.g.` 示例，capability 只从 umbrella prefix 推导，避免 LangChain/AutoGPT 等例子被提升为 hard capability；真实“有…项目经验”仍保持 experience。

v42.39 补齐 umbrella skill 的另一种 live drift：Provider 有时把整个 `智能体(Agent)技术栈(如LangChain、AutoGPT等)` 作为 normalized capability，而不是只返回某个示例。现有 example-capability repair 现在同时识别“capability 只来自 example suffix”和“capability 等于包含 example 的完整 hard-skill phrase”两种形态；两者都只在 exact hard-skill umbrella grammar 成立时收敛为 `智能体(Agent)技术栈`。这一轮本地专项 4/4、workflow+adapter 172/172、Requirement/Acceptance/Eligibility/Target Cohort 完整相关回归 445/445 passed。随后只读审核已存在 v42.39 Run `reqacceptrun_3d6672ba35ad413a8ce7db1a72d5df24` 的 6 个 Case，确认 Case 0 的 responsibility duplicate 与 Agent umbrella capability 已稳定、Harness 方向收敛也正常；但 Case 3 仍把 `具有高度的责任心,并具有较高的抗压能力` 持久化为 `skill must_have / 抗压能力`，形成新的 literal-skill false-reject 风险，因此不继续 resume。

v42.40 只扩展既有 abstract-evaluative skill repair 到这一种 compound trait 后半段漂移。新增 grammar 仅接受由多个 `具有/并具有 + 高度/较高/较强/... + 责任心|抗压能力` segment 组成的 exact hard skill，且 normalized capability 必须出现在整条文本中；命中后仍统一归一为 `constraint must_have / normalizedCapability=null`。具体技术复合能力如 `Python性能优化 + 分布式系统设计` 明确保持 skill。专项 2/2、workflow+adapter 174/174、完整 Requirement/Acceptance/Eligibility/Target Cohort 回归 447/447 passed。Case 8 的 inline one-of cardinality 继续留给独立后续 patch。

v42.40 随后通过 `deepseek-v4-pro` plain/json_schema 双 200 与全新 zero-call readiness，唯一 3-Case Canary `reqacceptrun_bbc9b60fa6a947b98b79ef67590e3acc` 3/3 均一次 extracted、0 failed、0 retry。人工审核时 Harness 的 hard cardinality parent 与 React/Electron/Python/Git 四个 direction child 保持稳定，Case 2 也未出现新的 blocking duplicate/cardinality 问题；但 Case 0 暴露两个 blocking regression：`需要有车端经验` 被完全重复持久化为两条 `experience must_have`，形成 hard duplicate weighting；同时 Agent umbrella skill 的 normalized capability 漂成带全角标点/空格的完整 `智能体（Agent）技术栈（如 LangChain、AutoGPT）`，再次把 example phrase 留在 hard capability。说明 exact duplicate 与 umbrella-capability presentation equivalence 仍有缺口，且 v42.40 目标 Case 3 尚未 live-proven。按 fail-closed 门禁提交不可变 Stop `reqacceptcanary_88003ea7f69c41cb906bba8dee7324bd`，不 resume、不扩 20 Case。下一轮应优先处理 Case 0 的 exact hard duplicate 与 umbrella capability 标点/空格等价，不同时混入 Case 8 one-of cardinality。

v42.41 只修这两个 Case 0 缺口。exact duplicate identity 最初尝试对全部 non-skill 忽略 `normalizedCapability`，宽回归立即抓到 `domain` 多 capability sibling 被误合并，因此规则进一步收窄为仅 `experience`：同 type/importance、同 presentation-equivalent original/source 的 experience 即使 Provider capability 不同也视为同一事实；skill/domain/responsibility/constraint 等继续保留既有 capability identity。umbrella full-phrase 判断则复用 grounding 已有的 whitespace removal + ASCII/full-width punctuation normalization，仅用于比较当前 capability 是否只是同一句 hard-skill phrase 的 presentation 变体，再 canonicalize 到 exact umbrella prefix；不做语义别名或 fuzzy match。真实两个红灯与相邻防误伤专项 4/4、workflow+adapter 176/176、当前完整 Requirement/Acceptance/Eligibility/Target Cohort 口径 443/443 passed。

v42.41 随后使用 `deepseek-v4-pro` 通过 plain/json_schema 双 200 与全新 zero-call readiness，唯一 3-Case Canary 为 `reqacceptrun_930195d16621415a977066a7bcdf4aea`，3/3 均一次 extracted、0 failed、0 retry。人工审核确认 Case 0 只保留一条 `需要有车端经验` hard experience，Agent umbrella capability 收敛为 `智能体(Agent)技术栈`；Harness 继续保持 hard `至少一个方向` parent + React/Electron/Python/Git 四个 `skill preferred` child；Case 2 的职责、2 年经验、Python、至少一种 Agent 框架 cardinality、Prompt/RAG hard constraint 与 preferred AI 工具链均无 blocking missing/duplicate/importance 回归。因此提交不可变 Continue `reqacceptcanary_076b19a1d5f84a06b998fc45acd2912b`。本轮不 resume、不扩 20 Case。下一轮优先事项回到此前独立保留的 Case 8 inline one-of cardinality (`C/C++/Go/Python 等一种以上`)；仍应先固化红灯并做窄 deterministic repair，不把 v42.41 已 live-proven 的 duplicate/umbrella 逻辑继续扩大。

v42.42 只扩展既有 `_ALTERNATIVE_GROUP_PATTERN` 到中文后置 one-of 形态：仅接受 `等/中 + 最多 8 字 + 一门/一个/一项/一种 + 以上`，例如东风汽车 Case 8 的 `熟练掌握C/C++/Go/Python等一种以上编程语言`。真实红灯最初证明现有 pipeline 会把该形态直接收敛成一个 `constraint must_have`，而不是保留四个 preferred child；这与既有 inline-cardinality contract 一致，因此不额外扩大设计。专项 6/6、workflow+adapter 177/177、完整 Requirement/Acceptance/Eval/Eligibility/Target Cohort 当前口径 450/450 passed。Pro 双健康与 zero-call readiness 通过后，唯一 3-Case Canary `reqacceptrun_ec8e28a9ad70428c982a8b5ee6432b54` 3/3 extracted，但人工审核发现 Case 0 的 `需要有车端经验` 再次出现两条 hard experience。两条最终 original/type/importance/capability 完全相同，只因 evidence span 一条较窄、一条覆盖更宽上下文而逃过 v42.41 duplicate key。该轮以不可变 Stop `reqacceptcanary_3c73e37eb3f541309d6fb9f5d4de7c38` 收口，不 resume、不扩跑。

v42.43 只修这个 live duplicate identity 缺口，并保留 v42.42 的 postfix cardinality grammar。根因是同一句 `需要有车端经验` 在 Case 0 JD 中实际出现两次，导致 `_unique_presentation_span` 无法返回唯一位置；v42.41 随后退回 evidence identity，而 Provider 两次给了不同宽度的 evidence。v42.43 因此只对 `experience` 将 duplicate `source_identity` 固定为空：仍要求 type、importance 和 presentation-equivalent original 完全一致；skill/domain/responsibility/constraint 等继续使用 source identity。真实 widened-evidence 红灯与既有 capability-drift duplicate 防回归通过；workflow+adapter 178/178、完整相关回归 451/451 passed。

v42.43 重新锁定 `deepseek-v4-pro` 后 plain/json_schema 双 200，zero-call readiness 为全新 0-attempt。唯一 3-Case Canary `reqacceptrun_63ec0707ac344eb288295a940ce311e7` 3/3 一次 extracted；人工审核确认 Case 0 只剩一条 `需要有车端经验` hard experience，Harness 与 Case 2 也无 blocking missing/duplicate/importance/cardinality 回归，因此提交不可变 Continue `reqacceptcanary_2405a000c8f64869a5c17ae1ef6f5667`。Readiness 随后明确允许 bounded resume，所以只追加 Cases 3–5。该段结果为 Case 3 extracted、Case 4 failed、Case 5 extracted；Case 4 `高级开发工程师（AI 平台 / 模型融合方向）` 报 `InvalidRequirementExtractorOutputError: Requirement extractor returned more than 50 requirements`。Trace 显示 Provider/repair 产生大量 responsibility/skill fan-out，并在 semantic repair 后仍超过系统 50 条硬上限。按 fail-closed 规则立即停止，不再推进 Cases 6–8，因此本轮目标 Case 8 的 postfix one-of 只获得 deterministic regression 证明，尚未 live-proven。下一轮优先事项应先把 Case 4 `>50 requirements` 膨胀固化为红灯并判断是 Provider fan-out 还是 repair 后上限管理缺口；在该 blocker 解除前不要继续 v42.43 resume。

v42.44 将 Case 4 Trace 重新拆解后确认：Provider 原始输出仍在 50 条 contract 内（repair index 最高为 43），最终越界不是单纯 Provider 超量，而是原始输出已经高密度 fan-out，随后 cardinality/alternative deterministic repair 合法增加父约束后把总数推过 50。最明显且本身有重复计权风险的冗余是职责 continuation `包括但不限于模型路由、负载均衡、推理调度、协议转换等关键子系统` 被拆成四条独立 responsibility。v42.44 因此不做截断、排序丢弃或提高 50 条上限，而只新增一个 exact-grounded collapse：仅当至少两个 responsibility sibling 共享同一 evidence、evidence 明含 `包括但不限于`、且每个 original 都是该 evidence 的真实子串时，将它们收敛成一条完整 enumeration responsibility，capability 置空并取最低 confidence。普通 conjunctive responsibility sibling 没有该 marker 时保持不变。专项 4/4、workflow+adapter 180/180、完整 Requirement/Acceptance/Eval/Eligibility/Target Cohort 相关回归 453/453 passed。随后 `deepseek-v4-pro` plain/json_schema 双 200，zero-call readiness 为全新 0-attempt；唯一 3-Case Canary `reqacceptrun_66c08d9e1bca4f1d80847eff1991207f` 3/3 一次 extracted、0 failed、0 retry。只读审核 Cases 0–2 未发现 blocking missing/duplicate/importance/cardinality/grounding regression；Case 0 仍只有一条 `需要有车端经验`，Harness 保持 hard cardinality parent + React/Electron/Python/Git preferred children，Case 2 核心 hard gates 稳定。随后通过正式 review endpoint 提交不可变 Continue `reqacceptcanary_fa59f2b3f2f141a88b91ceb69c52ba08`，并只追加 Cases 3–5。该段 3/3 extracted，Run 累计 attemptedCalls=6；历史 Case 4 成功持久化 42 条 requirements，Trace 真实命中一次 `collapse_responsibility_enumeration_siblings`，证明 >50 blocker 已解除。人工语义审核仍发现两个新 blocker：Case 4 的 `二、任职要求` 中 Docker/Kubernetes、分布式/微服务经验及部分后端组件被 Provider 降为 `preferred`，原文无任何 soft marker；Case 3 的 standalone `具有较高的抗压能力` 再次被提成 `skill must_have`。因此不再继续 Cases 6–8。

v42.45 只修上述两个 live blocker。第一，section heading 识别允许一个 bounded 的中文或阿拉伯序号前缀，例如 `二、任职要求`、`2. 任职要求`，从而让既有 requirement-section default-must-have 规则覆盖真实 JD 的编号章节；任何显式 `优先/加分/optional/preferred/bonus` 仍阻止 promotion，不改变 alternative/cardinality 的后续降级规则。第二，既有 abstract-evaluative hard-skill normalization 增加 standalone exact trait 形态，`具有较高的抗压能力` 这类已在受限 trait grammar 内的文本归一为 `constraint must_have`；具体技术能力不受影响。两个 live-shape regression 均通过，workflow+adapter 182/182，当前 Requirement/Acceptance/Eval/Eligibility/Target Cohort 相关回归 424/424 passed。随后 `deepseek-v4-pro` 双健康与全新 zero-call readiness 通过，唯一 3-Case Canary `reqacceptrun_5abb7ac78c594ba6b552cf296904b1e0` 3/3 一次 extracted。人工审核发现 Case 0 原文 `熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)` 被 Provider 直接输出为 `constraint must_have`，没有任何 semantic repair；这会绕过 literal skill evaluator，形成 false-accept 风险，因此提交不可变 Stop `reqacceptcanary_a9ea301cd4aa46f6949cbfb9ef8742f7`，不 resume。

v42.46 只修上述 hard technical-stack constraint type drift。仅当 item 是 `constraint must_have`、位于显式任职要求 section、无 soft marker、原文 exact-grounded、匹配 hard-skill verb、包含 inline example list，且 example 前的 umbrella 明确以 `技术栈` 结尾时，才恢复为 `skill must_have`；capability 直接从原文 umbrella 去掉限定动词后取得，例如恢复为 `智能体(Agent)技术栈`。不做 generic constraint→skill，也不处理 conceptual mechanism、抽象能力或普通 constraint。目标红灯与 v42.45 两个相邻红灯 3/3，通过后 workflow+adapter 183/183，当前完整相关回归 425/425 passed。Pro 双健康与全新 zero-call readiness 通过后，唯一初始 Canary `reqacceptrun_ea792e10f1c245d49818f37266707f45` 3/3 extracted；Case 0 本次 Provider 已直接返回正确 `skill must_have / 智能体(Agent)技术栈`，因此新增 constraint-drift repair 未在该次 live 触发，但结果通过人工门禁，提交 Continue `reqacceptcanary_5a38c26da8ff46598a46f3564b52288d`。随后 Cases 3–5 仍 3/3 extracted：Case 3 `具有较高的抗压能力` 已为 `constraint must_have`；Case 4 Docker/Kubernetes、分布式/微服务经验、MySQL/PostgreSQL、Redis、Kafka/RabbitMQ/RocketMQ 均恢复为 must-have，`至少覆盖以下方向中的两项` 仍是 hard constraint + 四个 preferred child，最终 48 条 requirements，历史 `>50` 未复发。后续又仅追加 Cases 6–8，三者仍一次 extracted，使 Run 累计 attemptedCalls=9。Case 8 的历史 postfix one-of 已首次获得 live 证明：`掌握EINO/DIFY等一种以上智能体框架` 与 `熟练掌握C/C++/Go/Python等一种以上编程语言` 均保持为单条 `constraint must_have`，没有拆成多个独立 hard skill；其余 must/preferred 也未复发。Case 7 则暴露新的 false hard gate：原文 `对RAG和agent框架有基本了解,包括但不限于 langChain、llama index、autoGen、metaGPT等` 除 umbrella hard requirement 外，又持久化四条 framework `constraint must_have` example fragment。另一个仍待独立处理的 Case 6 风险是 `熟悉大语言模型核心技术,如 Transformer 架构、微调(如 LoRA、PEFT)、AI智能体等` 被 fan-out 出 LoRA/PEFT/AI智能体 hard children，并且 umbrella capability 漂到示例 Transformer；这不是 v42.47 的 `包括但不限于` grammar 范围。

v42.47 只修 Case 7 的 `包括但不限于` continuation example fan-out。已有 `drop_example_child` 原先只识别 child 自身显式以 `如/例如` 开头或整体为 parenthetical example；新规则仍要求 hard umbrella parent 与 child 共享同一 exact evidence，且 parent 位于 explicit `包括但不限于` marker 之前，只有 marker 起点及之后的 fragment 才视为 redundant example 并丢弃。没有 umbrella、不同 evidence、marker 前 child 均不触发。真实 live-shape 红灯与相邻 example regression 3/3、workflow+adapter 184/184、当前完整 Requirement/Acceptance/Eval/Eligibility/Target Cohort 相关回归 419/419 passed。Pro plain/json_schema 双 200，zero-call readiness 为全新 attemptedCalls=0；唯一 3-Case Canary `reqacceptrun_47a25d5561a7442eabfcfed466e8d05e` 3/3 extracted、0 failed、0 retry。初始人工审核将 Case 0 的 `高价值AI场景挖掘` / `企业级AI与智能体应用开发` 短编号 scope summary 判为职责 duplicate，因此提交不可变 Stop `reqacceptcanary_c9b50d320ea548b5a68453caa1b2dbb8`，没有 resume。随后复核既有 contract/test 后确认该判断过于保守：项目已有 `short_scope_summary_responsibility` 明确将这种有多个后续 action duty 佐证的短编号 scope summary 作为合法 responsibility，而不是应删除的 heading。由于 Stop 已不可变且同版本不得重复 Canary，v42.47 不再重跑；也不据此制造删除 scope summary 的 v42.48。下一轮应优先固化 Case 6 的 `如 ...` nested example fan-out / umbrella capability leakage，这才是尚未处理的明确 live blocker。

v42.48 只修上述 Case 6 的 non-parenthetical illustrative example 漂移，不扩大到普通逗号枚举。新增 marker 只接受 `,如/例如/比如`（含中英文逗号），且 example child 仍必须与 hard umbrella sibling 共享同一 exact evidence、位于 marker 之后；无 parent 或不同 evidence 均保留。与此同时既有 umbrella capability repair 也识别该 marker，因此 `熟悉大语言模型核心技术,如 Transformer 架构、微调(如 LoRA、PEFT)、AI智能体等` 会保留一个 hard skill，并把 capability 从示例 `Transformer` 恢复成 `大语言模型核心技术`，LoRA/PEFT/AI智能体不再成为额外 hard gates。新增真实 shape 与 no-parent 边界测试后专项 3/3、workflow+adapter 186/186、当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 回归 464/464 passed。随后按既有实验口径用进程级 `deepseek-v4-pro` override 通过 plain/json_schema 双 200 与全新 zero-call readiness，唯一 3-Case Canary `reqacceptrun_7f8e4b41fe5f459087f00f477b6b911d` 3/3 一次 extracted。人工审核 Case 0/1 未见新的 hard/soft、duplicate/cardinality blocker，但 Case 2 原文 `理解RAG、向量数据库、Function Calling等核心技术,能独立完成原型验证与方案评估` 被 Provider 漂成 `experience must_have`，会让 Eligibility 走错误 evaluator；因此提交不可变 Stop `reqacceptcanary_8d489c6f26984ab49eda73e192416a58`，没有 resume。

v42.49 只修上述 Case 2 的复合技术资格 experience type drift。复用既有 `non_experience_qualification_constraint` 路径，不新增 generic experience→constraint：当 hard experience 无任何经验/年限/soft marker，且首段精确命中既有 `理解/熟悉/掌握/精通/了解 + 多项 + 等核心技术` grammar，后续逗号段均仍是已允许的 hard-skill/ability qualification segment 时，才归一为 `constraint must_have / normalizedCapability=null`。这样 `理解RAG、向量数据库、Function Calling等核心技术,能独立完成原型验证与方案评估` 被恢复为单一 hard constraint，同时真实经验句和普通 experience 不受影响。目标红灯与相邻规则专项 3/3、workflow+adapter 187/187、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 回归 465/465 passed。随后 Pro 双健康和全新 readiness 通过，唯一 3-Case Canary `reqacceptrun_bd9d52b120584e8f9183ea3978f278f5` 3/3 extracted；Case 2 的 RAG type drift 已修复，但同一软条件 `有MCP协议实践、研发效能/DevOps工具链经验,或熟练使用Cursor、Claude Code等AI工具链者优先` 被按 MCP/DevOps/Cursor/Claude Code 四种 capability 重复持久化为四条 `skill preferred`，形成 preferred duplicate weighting，因此提交 Stop，不 resume。

v42.50 只修上述显式 soft preferred capability fan-out。初始实现曾把所有非 hard 同源 capability 都忽略 capability 做 duplicate identity，目标专项虽通过，但完整 Eval/Review 回归出现 10 个失败：fixture 的普通 `熟悉 Agent 和 RAG 相关技术` 本来应保留两个 preferred capability，却被错误合并。这证明 `preferred` 本身不是 fan-out 证据。最终规则收窄为：仅 `importance=preferred` 且 original/evidence 内存在显式 `优先/preferred/bonus` soft marker、同时不属于已有 hard-cardinality alternative child 时，exact duplicate identity 才忽略 capability；hard、bonus、无显式 soft marker 的 preferred 仍保持 capability-sensitive。新增 live-shape、hard sibling、unsoftened preferred sibling 和 alternative 边界后专项 4/4、workflow+adapter 189/189、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 回归 417/417 passed。提交 `3c5545f` 后 Pro plain/json_schema 双 200，zero-call readiness 为全新 0-attempt；唯一 3-Case Canary `reqacceptrun_2bdab0b16df2486cbdff81a290f4b0f7` 3/3 extracted。人工审核确认 Case 2 的 RAG 资格保持单条 `constraint must_have`，原先 MCP/DevOps/Cursor/Claude Code 四条 preferred duplicate 收敛为一条，Case 0/1 也无新的 blocking hard/soft、type、missing、duplicate 或 cardinality 回归，因此提交 Continue `reqacceptcanary_03398fbb08644354880368fbcdc284a9`。随后仅追加 Cases 3–5，仍 3/3 extracted，Run 累计 attemptedCalls=6。Case 3 的责任心/抗压保持 constraint，Case 4 总量 47、Docker/Kubernetes 和分布式/后端组件 hard requirement 稳定，但同一个 cardinality child `模型微调(SFT / LoRA / QLoRA)` 被按 `模型微调`、`LoRA`、`QLoRA` 三种 capability 重复持久化为三条 `skill preferred`，会让“至少两项”中的一个方向被重复计权，因此停止 further resume，不运行 Cases 6+。

v42.51 只修上述 cardinality child capability fan-out。新规则仍复用 exact duplicate pass：仅当 `preferred` item 位于 exactly one 已识别的 bounded cardinality/alternative group scope 内，且至少还有一个同 type、同 presentation-equivalent original/evidence、但 capability 不同的 preferred sibling 时，duplicate identity 才忽略 capability；这会把 `模型微调(SFT / LoRA / QLoRA)` 的三个 Provider capability 装饰收敛为一个 child，同时不会影响 group 外 `熟悉 Agent 和 RAG` 这类合法 preferred 多 capability、hard sibling、不同 evidence 或不同 child。新增真实 live-shape 与相邻边界后专项 4/4、workflow+adapter 191/191、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 回归 418/418 passed，并提交 `728ee11`。随后 Pro plain/json_schema 双 200，zero-call readiness 为全新 0-attempt；唯一 3-Case Canary `reqacceptrun_47aa67228afb4a05baadb12b474824c6` 3/3 extracted。人工审核 Cases 0–2 未见新的 blocking hard/soft、type、missing、duplicate/cardinality 回归，Case 2 仍保持单条 RAG hard constraint 与单条 MCP/DevOps/Cursor/Claude Code preferred，因此提交 Continue `reqacceptcanary_c18926c5ffca41b98515f49bff92c096`。后续运行重新确认 `deepseek-v4-pro` plain/json_schema 双 200，readiness 精确命中同一 Run 为 `partial / attemptedCalls=3 / canaryDecision=continue / nextAction=resume_run / blockers=[]`，因此只追加 Cases 3–5 三次 live extraction，3/3 extracted，Run 累计 attemptedCalls=6。Case 4 的目标修复已 live-proven：`模型微调(SFT / LoRA / QLoRA)` 只保留一条 `skill preferred`，RAG/Agent/Prompt 三个 sibling 也各一条，hard `至少覆盖以下方向中的两项` parent 保持正确，没有重复计权。但同一只读审核发现更严重的新 false-reject：JD 的 `三、加分项(满足越多越优先)` 未被现有 bonus heading grammar 识别，导致 AI 网关、多模型编排、vLLM/TGI/Triton、CUDA 等明确加分项被持久化为 `must_have`。因此立即停止 further resume，不运行 Cases 6+，并将该真实 live shape 作为 v42.52 红灯。

v42.52 只扩展既有 explicit bonus-section heading grammar：允许一个 bounded 中文/阿拉伯序号前缀，并允许 bonus heading 后带最多 40 字的单层括号说明，例如 `三、加分项(满足越多越优先)`。命中后仍复用既有 `explicit_bonus_section` inheritance；遇到下一个标准 section heading 时仍停止，不改变普通任职要求、inline soft marker、type 或 cardinality 逻辑。新增 live-shape regression 与既有 plain bonus-section 边界后专项 2/2、workflow+adapter 192/192、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 431/431 passed。提交后重新进入全新 Pro 双健康 + zero-call readiness，二者通过后启动唯一 3-Case Canary `reqacceptrun_b8c8930660724608b4e3bdd2ee88b534`，3/3 extracted。人工审核发现 Case 0 的 hard skill `熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)` 被 Provider 持久化为 capability `智能体(Agent)技术栈(如LangChain、AutoGPT等),有落地项目经验`，把后续 soft experience 污染进 hard skill capability，形成 literal hard-skill false-reject 风险，因此提交不可变 Stop `reqacceptcanary_77013c1eaeda4161ad21ec566d33fabf`，不 resume。

v42.53 只修上述 trailing-soft capability leak，不做 generic capability truncation。既有 umbrella repair 继续要求 hard skill exact-grounded 且存在 inline example list；新增分支仅在 Provider capability 以去除限定动词后的完整 hard phrase 开头时生效，并要求多出来的 trailing fragment 能在该 original 紧邻的 JD source window 中找到，同时该 source window 存在显式 soft marker。满足这些强证据后才把 capability 收回 example 前的 hard umbrella；如果 trailing fragment 没有 soft-source 证据，则保持原 capability 不变。新增真实 live-shape 与防误伤边界后专项 4/4、workflow+adapter 194/194、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 467/467 passed，并提交 `1052d0e`。随后 `deepseek-v4-pro` plain/json_schema 再次双 200，zero-call readiness 为全新 0-attempt；唯一 3-Case Canary `reqacceptrun_079a7e1ede8c4b2b8c06cb923dacbe74` 3/3 extracted。人工审核确认 Case 0 的 hard Agent technology-stack capability 已收敛为 `智能体技术栈`，不再夹带 trailing preferred experience；Harness 与 Case 2 也未见新的 blocking hard/soft、type、missing、duplicate 或 cardinality 回归，因此提交 Continue `reqacceptcanary_9c9c35992b4047ce9373d6aa5d454ba9`。后续自动推进先发现项目 `.env` 已切到 `deepseek-v4-flash`；为避免把已有 `deepseek-v4-pro` Run 混入不同模型证据，本轮没有修改 `.env`，只对健康检查、readiness 与 resume 命令临时覆盖 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro`。Pro plain/json_schema 重新双 200 后，readiness 精确返回同一 Run 为 `partial / attemptedCalls=3 / canaryDecision=continue / nextAction=resume_run / blockers=[]`，因此只执行 bounded Cases 3–5。实际结果：Case 3 一次 extracted；Case 4 在该 bounded budget 内两次 Provider 调用后以 `HTTP 504` 失败；Case 5 因 provider unavailable fail-fast 未尝试。Run 现为 `attemptedCalls=6`，没有超预算，也没有继续 Cases 6+。这属于 Provider transient blocker，不能据此做 semantic patch，也不能用 flash 替代继续同一 Pro Run。解除条件：保持 `deepseek-v4-pro` identity，重新获得 plain + json_schema 双 200，并由 readiness 仍精确返回同一 Run 的 `resume_run`；之后最多只重试未完成的 Case 4/5 bounded 段，完成后立即人工审核 Case 4 的 bonus inheritance、cardinality child 去重与 requirement 总量。后续双健康恢复为 200/200，readiness 仍精确命中同一 v42.53 Run；Case 4/5 随后均完成 extracted，Run 累计 attemptedCalls=8，因此停止继续 Cases 6+ 并只读审核。Case 4 的 v42.52/v42.51 目标修复均 live-proven：`三、加分项(满足越多越优先)` 下 7 条全部为 bonus，`模型微调(SFT / LoRA / QLoRA)` 仅保留一条 preferred child，hard `至少覆盖以下方向中的两项` parent 保持。与此同时发现新的 blocking false-accept：`二、任职要求 → 3. 编程与工程能力` 下 `熟悉后端系统开发常用组件`、`具备分布式系统或微服务架构的设计与实战经验`、`熟练使用 Docker、Kubernetes` 三条无 soft marker 的独立硬要求被降为 preferred。Trace 显示其被 `alternative_child` 误处理；复现确认 `精通 Python 或 Go 或 Java 至少一门语言...` 的 one-of scope 因 `_next_top_level_numbered_item_start` 无法从包含 group text 前的 source-line prefix 正确取得 bare ordinal，错误延伸到后续 2/3/4 sibling。

v42.54 只修上述 cardinality scope bleed。`_next_top_level_numbered_item_start` 现在只从 containing source line 的行首解析 ordinal，不再要求 group 起点前的 prefix 在 ordinal 后立即结束；因此 `1 精通 Python 或 Go 或 Java 至少一门语言...` 可正确以 `2 ...` 作为下一 sibling 边界，而 `3 具备 LLM 应用工程实战经验,至少覆盖以下方向中的两项:` 这类 group phrase 位于编号行后半段的既有场景仍能以 `4 ...` 结束 scope。新增 live-shape 回归并保留 noncontiguous cardinality parent 边界；专项 2/2、workflow+adapter 195/195、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 424/424 passed，并提交 `34909ba`。随后 `deepseek-v4-pro` plain/json_schema 双 200，zero-call readiness 为全新 0-attempt；唯一初始 Canary `reqacceptrun_3f29104f09554ef9a3fd48fad23cf773` 3/3 extracted。人工审核 Cases 0–2 未见 blocking missing/duplicate/importance/type/cardinality 回归，因此提交 Continue `reqacceptcanary_08cf96feb4f04d5a9dc96319f04481e0`，并只追加 Cases 3–5。该段 3/3 extracted，Run 累计 attemptedCalls=6；Case 4 的目标修复 live-proven：后端组件、分布式/微服务、Docker/Kubernetes 都恢复为 must-have，`模型微调(SFT / LoRA / QLoRA)` 仍只一条 preferred child。但同一只读审核发现更严重的新 coverage blocker：Case 4 最终只有 45 条 requirements，原文 `5 有向量数据库...实际使用经验` 与 `三、加分项(满足越多越优先)` 下 7 条编号 bonus 全部缺失，且 `LangChain / LlamaIndex / Dify 等至少一种` 未独立保留。该缺失不是 50 条上限导致；Trace 的 `coverageAudit` 仍只审职责，因此把资格/bonus 大段漏提取当成技术成功。由于 Canary Continue 已不可变，运营上立即停止 further resume，不运行 Cases 6+。

v42.55 只新增 explicit numbered bonus-section 的 severe-omission fail-closed gate，不做 capability 猜补，也不改变 `requirement-semantics-v42.54`。只有 recognized bonus heading 下至少 4 条明确编号 candidate 时才启用；若最终连 2 条都未被任何 grounded requirement 表示，则 extraction 直接失败。小于 4 条的 bonus section 不启用，部分漏项但已覆盖至少 2 条也不会失败。该规则专门避免 Case 4 这种整段 bonus 被 Provider 吞掉却进入后续匹配的 false-success；它不会修复单条向量库或第二个 one-of 本身，后续仍需依赖 Provider 重试/新 live evidence。新增 live-shape 与 small-section 边界后专项 4/4、workflow+adapter 197/197、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 464/464 passed，并提交 `94edb26`。后续 live gate 一度被配置误判阻塞：项目实际模型键是 `REQUIREMENT_EXTRACTOR_MODEL`，而不是 `OPENAI_MODEL`，`.env` 当前为 `deepseek-v4-flash`；不修改 `.env`，仅对 live 命令临时覆盖 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro` 后，health/readiness 均明确报告 Pro，plain/json_schema 双 200 且 zero-call readiness 为全新 0-attempt。唯一 3-Case Canary `reqacceptrun_2216668c03164b8da8ef0ab04a85d689` 3/3 extracted，但人工审核 Harness Case 1 发现同一原文 `有良好的工程习惯,重视可维护性、测试、可观测性、安全边界和长期演进成本` 被拆成 `重视可维护性 / 测试 / 可观测性 / 安全边界 / 长期演进成本` 五条共享同一 evidence 的 hard row，形成重复计权和过度硬化，因此提交不可变 Stop `reqacceptcanary_6bad25df1d144bd78102a82e94c141bd`，不 resume。

v42.56 只修上述 Harness engineering-practice same-evidence fan-out。规则不做通用同源 hard dedupe，而只接受 exact numbered `有良好的工程习惯,重视...` clause，且 quality list 至少包含 3 个受限词项（`可维护性 / 测试 / 可观测性 / 安全边界 / 长期演进成本`）；当 Provider 至少把其中 3 个词项拆成共享该 exact evidence 的独立 hard row 时，统一收敛为一条 full-clause `constraint must_have / normalizedCapability=null`，confidence 取成员最低值。相同 evidence 的 Python/Docker/Kubernetes 等技术 hard sibling 明确保留。真实红灯与防误伤专项 3/3、workflow+adapter 199/199、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 426/426 passed，并提交 `26aabb6`。随后继续仅以临时 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro` 覆盖 live 命令，Pro plain/json_schema 双 200，zero-call readiness 为全新 0-attempt；唯一 3-Case Canary `reqacceptrun_592a119858604ab58dd1cd9377df9d17` 3/3 extracted。Harness Case 1 已 live-proven：工程习惯质量项只保留一条完整 `constraint must_have`，不再产生 5 个 hard gate；Cases 0/2 无新的 blocking hard/soft、type、duplicate、missing 或 cardinality 回归，因此提交 Continue `reqacceptcanary_05ee8bb4166f40a78ed0ed557dc59160`。随后只追加 Cases 3–5，仍 3/3 extracted，Run 累计 attemptedCalls=6。Case 4 最终 49 条 requirements：后端组件、分布式/微服务、Docker/Kubernetes 继续保持 must-have，`至少覆盖以下方向中的两项` 与单一模型微调 preferred child 稳定；explicit bonus section 本次覆盖 4 条，达到 coverage-v4 最低 2 条表示阈值，因此正确放行，没有再出现整段 bonus severe omission 的 false-success。下一轮重新确认 Pro 双健康 200/200 且 readiness 精确命中同一 Run 为 `partial / attemptedCalls=6 / continue / resume_run` 后，仅追加 Cases 6–8。外层 DevSpace 调用虽然返回 504，但只读 readiness 证明确有执行，attemptedCalls 增至 10；数据库确认 Cases 6/7/8 均 `extracted` 且各自 case attempt_count=1，因此没有重放。人工审核确认 Case 8 postfix one-of 仍稳定为单一 `constraint must_have`，Case 7 的 `包括但不限于` example children 也未再 fan-out；但同一 hard umbrella `对RAG和agent框架有基本了解` 被 Provider 以 `RAG` 与 `Agent Frameworks` 两个 capability 重复输出，形成同原文/同 evidence 的 hard duplicate weighting，成为 v42.57 红灯。

2026-08-22 后续再次用 `deepseek-v4-pro` 做 plain/json_schema 双健康，二者均 200；readiness 精确识别同一 v42.46 Run 为 `partial / attemptedCalls=6 / canaryDecision=continue / nextAction=resume_run`，因此只追加 Cases 6–8 三次调用，不新建 Run。三例均一次 extracted，Run 累计 attemptedCalls=9。人工审核确认 Case 6 的本科/2 年经验/大模型微调和部署 hard requirement、计算机视觉 preferred 与三条职责基本稳定；Case 8（东风汽车）的历史 importance/cardinality blocker 已 live-proven：搜索/推荐经验、MCP、`掌握EINO/DIFY等一种以上智能体框架`、`熟练掌握C/C++/Go/Python等一种以上编程语言`、系统问题分析均保持 must-have，只有车载应用与系统性能经验为 preferred，其中 postfix one-of 编程语言已正确收敛为一个 `constraint must_have`。但 Case 7 暴露新的 blocking false-reject：原文 `对RAG和agent框架有基本了解,包括但不限于 langChain、llama index、autoGen、metaGPT等` 除正确 hard umbrella 外，又把四个示例 fan-out 成独立 `constraint must_have`，会错误要求候选人四个框架都满足。由于该 Run 的 Canary Continue 已 immutable，不能补第二个 Stop review，因此运营上立即停止 further resume，不运行 Cases 9+，并将该 live shape 固化为下一 patch 红灯。

v42.47 只修上述 same-evidence `包括但不限于` example fan-out。规则要求 child 为 hard、original/evidence 均 exact-grounded；同一 exact evidence 中必须存在明确 `包括但不限于` marker，并且还必须存在另一个 hard umbrella sibling，其 original 位于 marker 之前。只有位于 marker 及其后的 fragment 才作为 redundant example 使用既有 `drop_example_child` 丢弃；无 parent、不同 evidence、marker 前真实 requirement 均保持不变。这样 Case 7 收敛为单一 hard umbrella，不会把 LangChain/LlamaIndex/AutoGen/MetaGPT 变成四个独立硬门槛。新增 live-shape 红灯及相邻 no-parent 保留测试后专项 3/3，workflow+adapter 184/184，完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 423/423 passed。下一步应先提交本 patch，再进入 v42.47 全新 Pro 双健康 + zero-call readiness；不要复用或继续 v42.46 的 Cases 9+。

v42.57 只修 Case 7 上述 hard umbrella capability fan-out，不做通用 hard capability 去重。新规则仅在 `must_have skill`、presentation-equivalent original/evidence 完全相同、evidence 明确包含 `包括但不限于`，且该 original 位于 marker 之前时，才在 exact-duplicate identity 中忽略 capability；因此 `RAG` / `Agent Frameworks` 两条同源 umbrella 只保留第一条。普通无 example marker 的 `熟悉 Agent 和 RAG 相关技术` 仍允许两个独立 capability，不会被误折叠。新增 live-shape 与防误伤回归后专项通过，workflow+adapter 201/201，完整 Requirement 相关回归 498 passed，并提交 `7c9e79e`。随后 v42.57 Pro live gate 启动唯一 Canary `reqacceptrun_2e52a85b52a343988c833bb6611a8063`；Cases 0–2 均已 extracted，但人工门禁发现 Harness Case 1 的既有概念机制 umbrella `理解 LLM / Agent 的基本机制,包括 ...` 被 Provider 直接输出为 `domain must_have`，绕过之前只处理 skill 的 conceptual-mechanism repair，会让下游走错误 evaluator type。因此提交不可变 Stop `reqacceptcanary_ff7fbca67c0044f99248fdbd7223b1e1`，不 resume。

v42.58 只修上述 conceptual-mechanism domain type drift，不做通用 domain→constraint。复用既有 exact-grounded umbrella mechanism grammar：只有 hard、无 soft marker、带 normalized capability、且完整匹配 `理解/了解 ... 基本机制 + 包括 ...` 概念清单形态的 `domain` 才归一为 `constraint must_have / normalizedCapability=null`；具体 domain knowledge 不受影响，并用独立 Trace strategy `conceptual_mechanism_type_constraint` 区分 Provider 原始类型。目标与相邻专项 3/3、workflow+adapter 202/202，当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 475/475 passed，并提交 `259f3ef`。随后 `deepseek-v4-pro` plain/json_schema 双 200，zero-call readiness 为全新 0-attempt；唯一 3-Case Canary `reqacceptrun_e61a68493f25408e9172f8b51fd3d78b` 3/3 extracted，且 conceptual mechanism 已 live-proven 恢复为 `constraint must_have`。但人工审核 Harness Case 1 发现独立原文 `2.知名高校本科及以上学历。` 被 Provider 输出为 `education preferred`，该行无任何 soft marker 或 waiver，形成 hard gate 被错误降级的 blocking false-accept，因此提交不可变 Stop `reqacceptcanary_dbe3c3c1a04c45d0aaa8f2f2e354ac33`，不 resume。

v42.59 只修上述显式任职要求 section 内的 education importance drift，不做通用 preferred→must-have。根因是既有 `requirement_section_default_must_have` 只接受以 `本科/硕士/必须/需要/熟悉...` 等显式 requirement 前缀开头的文本，`知名高校本科及以上学历` 虽是 uniquely grounded `education` 且位于 `【任职要求】` 下，却因修饰词开头而漏过。新规则仅对 `education` 放宽这一前缀条件：文本仍必须唯一 grounded、nearest section 必须是 requirements/qualifications、original/evidence 均无 soft marker，且文本中存在学历/学位/本科/硕士/博士/大专/专科/专业教育信号；`知名高校本科及以上学历者优先` 仍保持 preferred，非 requirement section 的教育事实不受影响。真实红灯与防误伤专项 3/3、workflow+adapter 204/204、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 472/472 passed，并提交 `40ca280`。随后 v42.59 唯一 Canary `reqacceptrun_ddbf3fbce2c1436dbac3573c395b08a8` 初始 3/3 extracted，Harness Case 1 live-proven 学历恢复为 `education must_have`，提交 Continue `reqacceptcanary_fc27de31843543789037d642f61b42e0` 后只追加 Cases 3–5。Case 3 暴露新的 duplicate-weighting：单一原文 `计算机科学、人工智能等相关专业本科及以上学历` 被 Provider 以 `计算机科学` / `人工智能` 两个 capability 重复输出为两条 `education must_have`；Case 4 则被既有 coverage-v4 正确 fail-closed（7 条编号 bonus 覆盖 0 条，低于至少 2 条阈值），因此不应为 Case 4 放宽门禁。

v42.60 只修上述 Case 3 education same-source capability fan-out，不做通用教育事实合并。exact duplicate identity 对 `education` 与既有 `experience` 一样忽略 capability，但仍要求 presentation-equivalent original、相同 importance、相同 source evidence；因此同一学历事实仅保留一条，而 `本科及以上学历` 与 `计算机相关专业` 这类不同 source fact 继续独立保留。新增真实 live-shape 与防误伤测试后专项 2/2、workflow+adapter 206/206、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 481/481 passed，并提交 `63bd6c5`。随后临时覆盖 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro`，plain/json_schema 双 200，zero-call readiness 为全新 0-attempt；唯一 3-Case Canary `reqacceptrun_735278e8bca945bb85aac6d67271a535` 3/3 extracted。但人工审核 Harness Case 1 再次发现 conceptual mechanism 原文 `理解 LLM / Agent 的基本机制,包括 ...` 被输出为 `domain must_have`。这次 Provider 没有返回 normalized capability，导致 v42.58 的 domain 修复因为 capability 必填而未触发；因此提交不可变 Stop `reqacceptcanary_b14ae8aabc8749ad82838a94384f1b02`，不 resume。

v42.61 只修上述 capability-null conceptual-mechanism domain drift，不做通用 domain→constraint。沿用 v42.58 已验证的 exact umbrella grammar；唯一变化是 `domain` 分支不再要求 Provider 提供 normalizedCapability，因为最终本就归一为 capability-less `constraint must_have`。`skill` 分支仍维持 capability 必填，具体 domain knowledge、soft/alternative clause、带 action 的机制描述都不会被放宽；当 `domain` capability 缺失时也禁止从更宽 evidenceSpan 反推 umbrella，只接受 originalText 自身完整命中 grammar。新增真实 live-shape 与防误伤回归后专项 3/3、workflow+adapter 208/208、当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 471/471 passed，并提交 `513f9b8`。随后 `deepseek-v4-pro` plain/json_schema 双 200，zero-call readiness 为全新 0-attempt；唯一 3-Case Canary `reqacceptrun_4c57e737432445089a9ae8feb744788e` 3/3 extracted，conceptual mechanism 已 live-proven 为 `constraint must_have`，学历与工程习惯历史修复也稳定。人工门禁最初把工程化方向理解为“完整 labeled child + 同源 body child”重复计权，并提交不可变 Stop `reqacceptcanary_856b453663b24ef799f1d70d1586de0d`。随后复核最终持久化 rows 纠正该判断：实际只有一条工程化方向 requirement；问题是 Provider 仅保留了 body `Git、branch/worktree...` 作为 originalText，而 evidenceSpan 仍是完整 `【工程化/代码控制方向】:...`。因此 Stop 保持历史不可变，但下一 patch 不做 dedupe，而只修 source identity 一致性。

v42.62 只修上述 alternative-direction body-only source identity，不改变 importance/type/capability/cardinality。仅当 item 已是 `preferred skill`、位于唯一 bounded alternative scope、evidenceSpan 完整匹配受支持的 `【...方向】:body` 标签语法、Provider capability 正好等于 body 首个 concrete capability，且 originalText 恰好等于该 body 时，才把 originalText 恢复为完整 evidenceSpan；普通 preferred skill、无 direction label 的 evidence、capability 不一致或 scope 不唯一时均不触发。真实 live-shape 红灯先在 v42.61 下确认失败；修复后专项与相邻防误伤通过，workflow+adapter 209/209、当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 472/472 passed，并提交 `efcc46d`。随后 `deepseek-v4-pro` plain/json_schema 双 200；v42.62 Run `reqacceptrun_21b6c15ff8894fc3bf3b5031e6b47605` 已处于 `awaiting_canary_review / attemptedCalls=3`，因此未重复调用 Provider。只读人工审核发现目标修复并未 live 生效：Harness Case 1 的四个方向 child 仍持久化为 body-only `originalText`（React/Electron/Python/Git），而 `evidenceSpan` 保留完整 `【...方向】:body。`；Trace 中没有 `normalize_alternative_group_child_source_identity`。根因是 v42.62 单测让 body 自带终止句号，但真实 Provider 会去掉终止 `。`，严格 `original == body` 因此漏过。已提交不可变 Stop `reqacceptcanary_2bb008f4929d49c6a152f0010c3ba44e`，不 resume。

v42.63 只修上述 terminal-punctuation comparison gap。仍复用 v42.62 的全部 bounded 条件，唯一变化是 body-only 判断由严格字符串相等改为既有 presentation identity（仅忽略展示编号/终止标点）比较；因此 `Git...流水线` 与 source body `Git...流水线。` 可被识别为同一 body，并恢复为完整 labeled `originalText`，但 importance/type/capability/cardinality 不变。真实无句号 live-shape 测试先在 v42.62 下确认失败，修复后专项 2/2、workflow+adapter 209/209、当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 471/471 passed，并提交 `96fb2bd`。随后 v42.63 唯一初始 Canary `reqacceptrun_51467cb83c964deab9a171caaf735090` 3/3 extracted，Harness Case 1 四个方向 child 已 live-proven 恢复完整 labeled originalText，因此提交 Continue；继续 bounded segment 时 Cases 3/4 extracted，Case 4 因一次额外 Provider attempt 已耗尽本段预算，Case 5 保持 deferred。只读人工审核 Case 4 发现新的 blocking duplicate-weighting：原文整体 hard requirement `熟悉主流大模型(GPT 系列 / DeepSeek / Llama / Qwen 等)的技术特性和使用场景` 被拆成 GPT/DeepSeek/Llama/Qwen 四条同 original/evidence 的 `must_have skill`。由于该 Run 已存在 immutable Continue，不追加第二个 review，也不再 resume v42.63，直接固化下一 patch 红灯。

v42.64 只修上述 parenthetical enumeration example fan-out，不做通用 slash-list dedupe。沿用既有 `collapse_example_skill_siblings` 的 exact same-source / must-have skill / multi-capability 条件，只额外把括号内包含 `/` 或 `、` 且以 `等`/`etc.` 明确收尾的枚举识别为 example list；因此 GPT/DeepSeek/Llama/Qwen 四条收敛为一个完整 `constraint must_have`。没有 `等`/`etc.` 的普通括号 capability 列表保持 capability-sensitive。新增真实 live-shape 与防误伤测试后专项 3/3、workflow+adapter 211/211、当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 464/464 passed，并提交 `c123727`。随后临时覆盖 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro`，plain/json_schema 双 200，zero-call readiness 为全新 0-attempt；唯一初始 Canary `reqacceptrun_297b3d64fc9d48de88b2eea8df780601` 3/3 extracted。人工审核 Cases 0–2 未见 blocking hard/soft、type、missing、duplicate 或 cardinality 回归，Harness 的学历 hard、四个方向 preferred、conceptual mechanism、engineering habit 均稳定，因此提交 Continue `reqacceptcanary_af75ae00d92547f396e127398ed8e93b`，并只追加 Cases 3–5。该段 3/3 extracted，Run 累计 attemptedCalls=6；Case 4 目标已 live-proven：`熟悉主流大模型(GPT 系列 / DeepSeek / Llama / Qwen 等)的技术特性和使用场景` 最终仅保留一条 `constraint must_have`，不再出现四 capability hard fan-out。分布式/微服务、Docker/Kubernetes 继续保持 must-have，`至少覆盖以下方向中的两项` parent 与模型微调 preferred child 稳定，7 条 bonus 均有覆盖。下一轮重新检查后 Pro plain/json_schema 仍双 200，readiness 精确命中同一 Run 为 `partial / attemptedCalls=6 / continue / resume_run`，因此只追加 Cases 6–8；该段 3/3 extracted，Run 累计 attemptedCalls=9，未继续 Cases 9+。只读审核确认 Case 7 的 `包括但不限于` example children 已降为 preferred、Case 8 的 EINO/DIFY 与 C/C++/Go/Python two one-of 仍分别保持单一 `constraint must_have`，但 Case 6 暴露新的 blocking duplicate-weighting：完整 hard clause `有实际大模型微调经验,能基于开源基座大模型完成模型的二次训练(...)` 同时持久化为 `experience must_have`、`constraint must_have`，并额外派生两个同 original/evidence 的 `preferred skill`。由于当前 Run 已存在 immutable Continue，不再追加 review 或继续 resume，直接把该 live shape 固化为 v42.65 红灯。

v42.65 只修上述 exact-source `有/具备 ... 经验, 能/能够 ...` fan-out，不做通用跨 type/importance 合并。只有原文唯一 grounding、位于明确任职要求 section、source 无 soft marker，且已经存在同 original/同 evidence 的 `experience must_have` canonical sibling 时，才丢弃同完整 source fact 的 `constraint must_have` 与 `preferred skill` copies；不同 original 的 experience/skill 子事实保持独立，显式 soft source 也不触发。真实红灯与两条防误伤边界专项 4/4、workflow+adapter 214/214、当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 481/481 passed，并提交 `4183e47`。随后 v42.65 全新 Pro Canary `reqacceptrun_35cd412653694e98bf8c6c61f7e094f2` 初始 3/3 extracted，但 Harness Case 1 暴露新的 source-shape blocker：编号第 3 条 `工程能力扎实,至少在以下一个方向非常熟练...:` 被拆成两个 hard constraint，使后续四个 labeled direction 失去稳定的 bounded group source identity，分别 fan-out 成 23 条 atomic preferred skill；编号第 4 条组合约束也被拆为两个 constraint + 一个 responsibility，改变 one-of/owner 组合语义。因此提交不可变 Stop `reqacceptcanary_682fdd45c9a74eab82286bfe5849e9df`，不 resume。

v42.66 只修上述 numbered cardinality group-header source-shape，不做通用列表合并。新规则仅接受明确任职要求 section 内、带编号、包含 `至少...一个/一项/一种` 与 `以下/下列/如下`、并以 `:`/`：` 结尾的 group header；只有该同一 source line 被 Provider 拆成至少两个 hard `constraint/responsibility` fragment、且无 soft/education/experience marker 时，才恢复为完整 exact-source `constraint must_have`。恢复发生在既有 alternative child canonicalization 之前，因此 `【前端方向】:React、TypeScript...` 等 atomic preferred fan-out 会重新进入原有 sibling collapse 并收敛为单条完整 direction node。第 4 条非 following-list cardinality 组合句继续走旧有 `recover_uncovered_cardinality_requirement`，避免改变已验证 trace contract。真实 v42.65 shape 回归通过，workflow+adapter 215/215、当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 493/493 passed，并提交 `4970b98`。随后 v42.66 全新 Pro Canary `reqacceptrun_7e290f6d8a1b44a2b0cb722bd649a7ba` 初始 3/3 extracted；zero-call readiness 明确为 `awaiting_canary_review / attemptedCalls=3 / providerCalls=0`，因此未重复做 Provider probe。人工审核 Case 0 发现新的 blocking over-hardening：原文 `熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)` 已正确保留 umbrella hard skill，但 Provider 又把括号内示例 `LangChain`、`AutoGPT` 作为两条独立 `must_have skill` 持久化，形成示例硬化与重复计权。Trace 显示既有 `normalize_umbrella_skill_example_capability` 已命中 umbrella，但 `drop_example_child` 没有识别 `(如...)` 内部的 atomic child。于是提交不可变 Stop `reqacceptcanary_7ee64399cc80426eaa2c28dc5b398abc`，不 resume。

v42.67 只修上述 inline-parenthetical example child 漏删，不做通用括号内容过滤。实现继续复用 `_is_redundant_example_child`，仅新增对既有 `_INLINE_EXAMPLE_LIST_PATTERN` 的 bounded 范围判断：child 必须与一个更早的同 evidence hard parent 共存，且自身 `originalText` 起止位置完全落在 `(如/例如/比如/such as/e.g. ... )` 括号范围内，才使用既有 `drop_example_child` 丢弃；括号后的独立 hard sibling 明确保留，没有同 evidence parent 时括号内 atomic child 也保留。真实 v42.66 `LangChain/AutoGPT` shape + no-parent + 括号后 hard sibling 防误伤专项 4/4，workflow+adapter 217/217，当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 490/490 passed，并提交 `e8f2fdf`。随后临时覆盖 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro`，plain/json_schema 双 200，zero-call readiness 为全新 0-attempt；唯一初始 Canary `reqacceptrun_0673490a37b64ecc92fee1692001ee94` 3/3 extracted。Case 0 目标 live-proven：`LangChain` / `AutoGPT` atomic hard child 已消失，只保留完整 umbrella hard skill。但 Harness Case 1 的编号第 4 条 `不要求 React / Electron / Python / 工程化四个方向都精通,但至少要能独立 owner 一个核心方向,并能读懂、协作另一个方向` 仍被 Provider 拆为 `至少要能独立 owner 一个核心方向` constraint + `并能读懂、协作另一个方向` hard skill，丢掉前半句“不要求四个方向都精通”的限定，改变单句组合 cardinality 语义，因此提交不可变 Stop `reqacceptcanary_96307943a6634471b9c8fecbf941dd5b`，不 resume。

v42.68 只修上述 bracketed requirement-section cardinality recovery 漏口，不新增新的句法推断。既有 `recover_uncovered_cardinality_requirement` 本来已经严格限定为：明确任职要求 section、原句以 `不要求...都...，但...至少...` 形式表达、无 soft marker、exact grounded；本轮只让它的 section scanner 同时识别 `【任职要求】` 这类已被全局 section grammar 接受的括号标题。恢复 full exact-source parent 后，`drop_redundant_recovered_cardinality_child` 也扩展到同 evidence 的 `skill must_have` strict subfragment，因此 live 中 `至少要能独立 owner...` 与 `并能读懂、协作...` 都被 full parent 吸收；不同 evidence 或非 parent substring 不受影响。真实 v42.67 partial-fragment shape 与既有 unbracketed recovery 专项 2/2，workflow+adapter 218/218，当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 491/491 passed，并提交 `2f09a51`。随后已以 `deepseek-v4-pro` 启动全新 v42.68 Run `reqacceptrun_ebd399d69e86473b89f72fa192ca640b`，唯一初始 Canary 3/3 extracted；人工审核确认 Harness Case 1 已恢复完整第 4 条组合 cardinality 为单一 `constraint must_have`，四个方向仍为 preferred，hard education、conceptual mechanism 与 engineering-habit 约束稳定，Cases 0/2 也未见 blocking hard/soft、type、missing、duplicate 或 cardinality 回归，因此提交 Continue `reqacceptcanary_222c576f046e4208bd334d6b211d2ea3`，且只授权 bounded Cases 3–5。后续已重新以临时 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro` 完成 plain + json_schema 双 200，readiness 精确命中同一 v42.68 Run 为 `partial / attemptedCalls=3 / continue / resume_run`，因此只追加 bounded Cases 3–5。该段实际 Case 3/5 extracted，Case 4 被 `requirement-coverage-v4` 正确 fail-closed：Provider 本次虽然返回大量 hard requirements，但 explicit bonus section 的 7 条编号 bonus 全部未被表示，错误为 `covered 0 of 7 numbered bonus candidates; at least 2 must be represented`；Run 累计 attemptedCalls=6，未继续 Cases 6+。只读 Trace 未发现 deterministic repair 把 bonus 错删的证据，因此不做无依据 semantic patch。随后再次完成 Pro 双健康 200/200 且 readiness 仍精确返回同一 Run `resume_run` 后，只对失败的 Case 4 做 1 次最小重试；该次调用直接遇到 Provider HTTP 504，Run 累计 attemptedCalls=7，进一步确认当前 blocker 属于 Provider 输出/可用性而非已证明的 deterministic 规则回归。此处停止所有 live 动作，不新建 v42.69，也不继续 Cases 6+。本地基线复核 workflow+adapter 218/218、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 491/491 passed。解除条件：`deepseek-v4-pro` 再次稳定 plain + json_schema 双 200，readiness 仍精确命中该 v42.68 Run；届时优先只重试未完成 Case 4，成功后先人工审核其 bonus inheritance、hard/soft、duplicate/cardinality，再决定是否允许后续 bounded resume。2026-08-22 后续自动推进时已再次满足前两项：Pro plain/json_schema 双健康均 200，readiness 精确返回同一 Run `partial / attemptedCalls=7 / continue / resume_run / blockers=[]`。按最小安全增量计划仅准备重试 Case 4 一次，但正式 resume 命令在发起 Provider 调用前被当前执行环境安全检查拦截，因此没有新增 Provider call、没有数据库写入，也没有触碰 Cases 6+；不将该环境阻塞误判为 Provider 或语义代码失败。本轮重新验证 workflow+adapter 218/218、当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 480/480 passed。下一步仍保持 v42.68：只有执行环境允许正式 resume 且 Pro 双健康/readiness 继续满足时，才对 Case 4 做单次 bounded retry；否则继续 fail closed。2026-08-22 23:57 后续自动推进再次完成 Pro plain/json_schema 双 200，readiness 精确命中同一 Run `partial / attemptedCalls=7 / continue / resume_run / blockers=[]`，因此仅执行 `max-new-extractions=1` 的 Case 4 retry。该唯一 Provider 调用再次返回 `HTTP 504`，Run 累计 attemptedCalls=8；Cases 6+ 继续保持未调用。由于本次仍没有产生可人工审核的 Case 4 extraction，也没有任何证据表明 deterministic repair 导致失败，因此不创建 v42.69、不修改语义规则，并继续把 blocker 分类为 Provider transient availability。解除条件保持不变：Pro 双健康恢复且 readiness 精确允许同一 Run resume 后，最多再对 Case 4 做一次 bounded retry；若成功，必须先审核 bonus inheritance、hard/soft、type、duplicate、missing 与 cardinality，再决定任何后续动作。2026-08-23 00:55 后续自动推进再次完成 Pro plain/json_schema 双 200，readiness 仍精确命中同一 v42.68 Run `partial / attemptedCalls=8 / continue / resume_run / blockers=[]`。按最小安全增量仍只准备 `max-new-extractions=1` 重试 Case 4，但正式 resume 在 Provider 调用前再次被当前执行环境安全检查拦截，因此 attemptedCalls 仍为 8、无新增 Provider call、无数据库写入、Cases 6+ 未触碰。本轮不把环境拦截误判为语义缺陷，不创建 v42.69。解除条件：执行环境允许正式 resume，同时 Pro 双健康/readiness 继续满足；届时仍只重试 Case 4 一次，成功后先人工审核再决定任何后续 bounded resume。2026-08-23 01:56 后续自动推进再次先完成 Pro plain/json_schema 双 200，readiness 精确命中同一 v42.68 Run `partial / attemptedCalls=8 / continue / resume_run / blockers=[]`；随后正式执行唯一 `max-new-extractions=1` Case 4 retry。该调用不再是 transport 504，而是再次被 `requirement-coverage-v4` deterministic fail-closed：explicit bonus section 仍为 `covered 0 of 7 numbered bonus candidates; at least 2 must be represented`，Run 累计 attemptedCalls=9，Cases 6+ 仍未调用。这条新证据说明 Provider 可用性已恢复，但内容 coverage 仍持续缺失；现有 guardrail 正确阻止 false-success，且没有证据证明 deterministic repair 错删 bonus，因此不创建无依据的 v42.69 semantic patch。本轮复核 workflow+adapter 218/218、当前 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 250/250 passed。下一步仍保持 v42.68：停止继续 live 调用，先把 Case 4 的重复 0/7 omission 视为 Provider content-quality blocker；只有后续出现可审核 extraction 或明确 trace 证明本地 repair 丢失 bonus 时，才进入新的窄修复。

v42.69 基于同一 Case 4 Trace 获得了新的本地根因证据，因此不再把 0/7 omission 仅归因于 Provider 内容随机性：失败 Trace 的原始 structured output 恰好打满 50 条（requirementIndex 0–49），而后部 7 条 bonus 完全未进入 raw output；与此同时前部存在大量随后会被 deterministic repair 折叠的 capability/example fan-out。现有 workflow 顺序是 Provider raw output → grounding repair → semantic repair → final validation → coverage，因此原始 50 条 schema 上限会在 repair 之前截断后部事实。v42.69 不放宽最终业务 contract，也不猜补 bonus，只把 OpenAI-compatible Provider 的 raw `requirements` 容量从 50 提到 64，给已有 repair 一个 14 条缓冲；最终 `validate_job_requirement_output` 仍严格限制最多 50 条，`requirement-semantics-v42.68` 与 `requirement-coverage-v4` 均不变。新增 adapter 回归证明 51 条 raw output 可进入 repair pipeline，新增最终验证回归证明 >50 条最终结果仍 fail-closed；专项 2/2、workflow+adapter 220/220、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 482/482 passed，并提交 `f680207`。随后 `deepseek-v4-pro` plain/json_schema 双 200，zero-call readiness 为全新 0-attempt；唯一初始 Canary `reqacceptrun_d66d3fd976aa4516bcb77044a7398a13` 3/3 extracted。人工审核 Cases 0–2 未见 blocking hard/soft、type、missing、duplicate 或 cardinality 回归，因此提交 Continue `reqacceptcanary_4324acf6dc8b4a2b9ca8fae2a31910fb`，只授权 bounded Cases 3–5。该段 Case 3 一次 extracted；Case 4 在同一 3-call budget 内两次 Provider 调用后以 `HTTP 504` 失败；Case 5 因 provider unavailable fail-fast 未尝试，Run 累计 attemptedCalls=6，Cases 6+ 未触碰。当前 blocker 属于 Provider transient availability，尚未获得 Case 4 对 raw-buffer 修复的 live 证明，也没有新证据支持修改 semantic/coverage 规则。2026-08-23 后续自动推进重新取得 `deepseek-v4-pro` plain + json_schema 双 200，zero-call readiness 精确命中同一 v42.69 Run 为 `partial / attemptedCalls=6 / continue / resume_run / blockers=[]`，因此只执行 bounded `max-new-extractions=2` 以补 Case 4/5。实际 Case 4 在本段预算内再次连续两次 Provider 调用后以 `HTTP 504` 失败，Case 5 因 provider unavailable fail-fast 仍未尝试，Run 累计 attemptedCalls=8，Cases 6+ 未触碰。由于没有产出可人工审核的 Case 4 extraction，也没有 Trace 证据证明 v42.69 raw-buffer 或既有 deterministic repair 导致失败，本轮不创建 v42.70、不修改 semantic/coverage；workflow+adapter 220/220、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 487/487 passed。解除条件仍是：重新获得 Pro plain + json_schema 双 200 且 readiness 精确命中同一 Run；之后优先只重试 Case 4，成功后必须先审核 bonus coverage、hard/soft、type、duplicate、missing 与 cardinality，再决定是否补 Case 5 或继续任何后续 bounded segment。2026-08-23 后续自动推进再次取得 Pro plain/json_schema 双 200，readiness 仍精确命中同一 v42.69 Run 为 `partial / attemptedCalls=8 / continue / resume_run / blockers=[]`。按最小安全增量只对 Case 4 执行一次 `max-new-extractions=1` retry；该唯一调用再次返回 `HTTP 504`，Run 累计 attemptedCalls=9，Case 5 及 Cases 6+ 均未触碰。本次仍没有产生可人工审核的 Case 4 extraction，也没有新的 Trace 证据指向 raw-buffer、semantic repair 或 coverage gate 缺陷，因此继续把 blocker 分类为 Provider transient availability，不创建 v42.70、不修改业务代码。重新验证 workflow+adapter 220/220、当前 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 493/493 passed。下一步继续保持 v42.69：先重新做 Pro 双健康与同 Run readiness；只有仍明确允许 resume 时才考虑单次 Case 4 retry，若成功必须先人工审核后再决定任何后续动作。2026-08-23 后续自动推进再次完成 Pro plain/json_schema 双 200，readiness 精确命中同一 v42.69 Run `partial / attemptedCalls=9 / continue / resume_run / blockers=[]`，因此只执行一次 `max-new-extractions=1` 的 Case 4 retry。该次成功 extracted，Run 累计 attemptedCalls=10，Case 5 与 Cases 6+ 均未执行。人工审核确认 v42.69 raw 64 buffer 已 live-proven：Case 4 最终 32 条 requirements，7 条 explicit bonus 全部出现并继承 bonus，最终没有触及 50 条业务上限；但同时暴露新的 blocking false-accept：`二、任职要求 → 4. AI 技术能力 → 5 有向量数据库(...等)的实际使用经验` 无任何 soft marker，却最终为 `experience preferred`。Trace 证明该行先被 `requirement_section_default_must_have` 恢复为 hard，随后又被 `alternative_child` 降为 preferred；根因是第二个 cardinality parent `4 熟练使用 PyTorch 或 TensorFlow,熟悉 LangChain / LlamaIndex / Dify 等至少一种` 本身从行首以裸编号开头，现有 `_next_top_level_numbered_item_start` 只从 group 前缀读取裸 ordinal，导致没有识别下一行 `5 有向量数据库...` 为新 sibling，scope 泄漏。由于 v42.69 已有 immutable Continue review，本轮运营上立即停止 further resume，不执行 Case 5/6+。

v42.70 只修上述 line-start bare-numbered cardinality scope leak，不做通用编号语义重写。`_next_top_level_numbered_item_start` 在既有“从 group 前 source-line prefix 解析 ordinal”失败且 group 自身恰好从行首开始时，额外只从 exact group text 的 leading bare ordinal 解析 parent number，再继续沿用原有“下一连续 ordinal sibling”边界。这样 `4 ...至少一种` 能在 `5 有向量数据库...` 前结束 scope，后者先由 requirement-section 默认 hard 规则恢复为 must-have 后不会再被 `alternative_child` 降级；既有 noncontiguous cardinality parent 与 dotted-number fallback 均保持。新增真实 live-shape 回归后专项 2/2，workflow+adapter 221/221，完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 494/494 passed，并提交 `20958a4`。随后 `deepseek-v4-pro` plain/json_schema 双 200，zero-call readiness 为全新 0-attempt；唯一初始 Canary `reqacceptrun_d6544a46e1114e9486ab55e141b6ad0e` 3/3 extracted。人工审核 Cases 0–2 未见 blocking hard/soft、type、missing、duplicate 或 cardinality 回归，提交 Continue `reqacceptcanary_6e63a30bc4de4ad8909b4d1921a04b76`，只追加 Cases 3–5。该段 3/3 extracted，Run 累计 attemptedCalls=6；Case 4 目标修复 live-proven：`5 有向量数据库(...等)的实际使用经验` 恢复为 `experience must_have`，7 条 bonus 全部正确保留，`至少两项` parent 与四个 preferred child 稳定。但同一人工审核发现新 blocking duplicate：第 4 条完整 `constraint must_have` 与其同 evidence 的 leading `skill must_have` `熟练使用 PyTorch 或 TensorFlow` 同时存在，造成重复计权。Trace 确认二者共享 exact evidence 且 full parent 已完整覆盖 child；由于 v42.70 已有 immutable Continue review，运营上立即停止 further resume，不执行 Cases 6+。

v42.71 只修上述 same-evidence leading cardinality subclause duplicate，不做通用 substring dedupe。新 helper 仅接受：child 为 `skill must_have`、parent 为同 evidence 的 `constraint must_have`、parent 含现有 cardinality grammar、parent 本身 uniquely exact-grounded，且 child 恰好等于去除 presentation bare ordinal 后 parent 的完整逗号前首段；不同 evidence、不同首段或普通 atomic substring 均保留。新增 live-shape 红灯与 different-evidence 防误伤后专项 3/3，workflow+adapter 223/223，完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 496/496 passed，并提交 `8a8717a`。随后 `deepseek-v4-pro` plain/json_schema 双 200，zero-call readiness 为全新 0-attempt；唯一初始 Canary `reqacceptrun_61a1be8b373e499a8bac6fceb0cb4437` 3/3 extracted。人工审核 Cases 0–2 未见 blocking hard/soft、type、missing、duplicate 或 cardinality 回归，因此提交 Continue `reqacceptcanary_c14e62fe5ee243cbb4c9c2536f6784f7`，只授权 bounded Cases 3–5。readiness 精确命中同一 Run `partial / attemptedCalls=3 / continue / resume_run / blockers=[]` 后执行该 bounded 段；Case 3 一次 extracted，Case 4 在该 3-call 预算内使用两次尝试后 extracted，Case 5 因预算耗尽未执行，Run 累计 attemptedCalls=6，Cases 6+ 未触碰。Case 4 人工审核确认 v42.71 目标 live-proven：此前同 evidence 的独立 hard `熟练使用 PyTorch 或 TensorFlow` 已消失，只保留完整 `4 熟练使用 PyTorch 或 TensorFlow,熟悉 LangChain / LlamaIndex / Dify 等至少一种` hard cardinality parent；`5 有向量数据库(...等)的实际使用经验` 继续保持 must-have，7 条 explicit bonus 全部正确继承 bonus，前一个 `至少覆盖以下方向中的两项` parent 与四个 preferred child 稳定，未见新的 blocking hard/soft、type、missing、duplicate 或 cardinality 回归。本轮后续重新取得 Pro plain/json_schema 双 200，readiness 精确命中同一 Run `partial / attemptedCalls=6 / continue / resume_run / blockers=[]`，因此严格只补 Case 5 一个真实调用；Case 5 一次 extracted，Run 累计 attemptedCalls=7，Cases 6+ 未触碰。只读审核确认 10 条任职要求均保持 must-have、15 条职责全部被 coverage 表示，未见 cardinality/duplicate/missing 回归，但发现新的 blocking false-accept：原文末尾 `投递简历请附带 GitHub ID(或其他开源网站/邮件列表的个人页面地址)` 无任何 soft marker，却被 Provider 原生输出为 `constraint bonus`，Trace 无 semantic repair 参与。该句是明确投递材料祈使要求，而非“有则加分”；由于 v42.71 已有 immutable Continue review，运营上立即停止 further resume，不执行 Cases 6+，并把该 shape 固化为 v42.72 红灯。

v42.72 只修上述 explicit application-material importance drift，不做通用 GitHub/portfolio hardening。新规则仅接受 uniquely exact-grounded `constraint`，当前 importance 为 preferred/bonus、source 无任何 soft marker，并且文本同时满足明确申请动作（`投递/申请/应聘`）、提交动作（`附带/附上/提供/提交`）和具体材料（GitHub/作品集/portfolio/个人页/开源页）三类证据，才提升为 `must_have`；普通 GitHub 技能、开源经历和显式 `优先/加分` 文案保持 soft。真实 Case 5 红灯与非祈使 GitHub bonus 防误伤专项 2/2，workflow+adapter 225/225，完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 498/498 passed，并提交 `6b7c47f`。随后 Pro plain/json_schema 双 200、zero-call readiness 为全新 0-attempt；启动唯一初始 Canary 时发现同版本 Run `reqacceptrun_d76b190829e94ae68fbf4b10d881f3a7` 已并发产生调用，门禁先阻止了重复第三次调用，随后只读状态确认 Cases 0–2 均已 extracted，因此不再烧 Provider。人工审核 Harness Case 1 与 Case 2 基本稳定，但 Case 0 出现新的 blocking same-evidence hard duplicate-weighting：`主导...构建可复用AI能力中台` 与 strict child `构建可复用的AI能力中台` 同时 hard，`制定AI工程标准...推动敏捷交付与持续集成` 与 strict child `推动敏捷交付与持续集成` 同时 hard；同一教育 source 也同时保留完整 `本科及以上学历,计算机/人工智能/汽车工程相关专业` 与 major-only education child。三个 child 均与 full parent 共享 exact evidence。Trace 证明既有责任子句去重只接受 `original == evidence` full parent，带编号/终止标点的 source 形态未命中；qualification 子句去重则只覆盖 DOMAIN-under-CONSTRAINT，未覆盖 EDUCATION-under-EDUCATION。提交不可变 Stop `reqacceptcanary_8ac5c70a0c9546ebb2c914026712d0a3`，不 resume。

v42.73 只补上述两个既有去重 guard 的 source/presentation 漏口，不做通用 substring dedupe。Responsibility parent 仍必须 uniquely exact-grounded，只是 full-parent 识别允许 `original` 与 `evidence` 在去除展示编号与终止标点后等价；child 仍必须同 evidence、同 importance、strict substring。Qualification subclause guard 仍要求明确 requirement section、same evidence、strict substring 和 must-have，只把可处理的 child 扩到 EDUCATION，并允许 canonical parent 为 EDUCATION；不同 evidence、非 strict substring 或独立教育事实均保留。真实 v42.72 responsibility/education 红灯专项 2/2，workflow+adapter 227/227，完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 500/500 passed。随后全新 v42.73 Run `reqacceptrun_e5e0715b76084316a7e84a406d0ff963` 进入初始 Canary；Case 0 已 live-proven responsibility/education subclause dedupe，但同一行 `精通AI常见场景(如预测、决策、NLP、CV等),具备企业级AI系统架构设计能力` 又同时持久化 full hard constraint 与 strict child `具备企业级AI系统架构设计能力`，后者被 Provider 错标为 `experience must_have`。二者 same evidence、strict substring，造成重复 hard weighting 且 child 进入错误 evaluator，因此提交不可变 Stop `reqacceptcanary_91904fd3a6454c81877f4305df7be458`，不继续 Cases 1–2。

v42.74 只扩展既有 qualification-subclause dedupe 到上述非经验语义的 `experience` type drift，不做通用 experience 删除。规则仍要求 requirement section、same evidence、strict substring、must-have，并且仅当 child 自身不包含真实经验信号（如 `X年以上...经验` 或 `有/具备...经验`）时，才允许把误标成 experience 的 strict child 视为 full hard constraint 的冗余子句；真正经验事实即使 same-source 也明确保留。新增真实 v42.73 红灯和 true-experience 防误伤回归；专项通过，workflow+adapter 229/229，当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 497/497 passed，并提交 `23088d6`。随后临时覆盖 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro`，plain/json_schema 双 200，zero-call readiness 为全新 0-attempt；唯一初始 Canary `reqacceptrun_e38047af35544465904c61853d920de3` 3/3 extracted。人工审核确认 Case 0 目标 live-proven：完整 `精通AI常见场景(...),具备企业级AI系统架构设计能力` hard constraint 唯一保留，误标的同源 `experience must_have` strict child 已消失，而真实 `8年以上AI产品/解决方案经验` 仍保留；Cases 1–2 未见 blocking hard/soft、type、missing、duplicate 或 cardinality 回归，因此提交 Continue `reqacceptcanary_0c37d6e0c779426da2448cdff7370858`，只授权 bounded Cases 3–5。再次 Pro 双健康 200/200 且 readiness 精确命中同一 Run `partial / attemptedCalls=3 / continue / resume_run / blockers=[]` 后执行该 bounded 段；Case 3 一次 extracted，Case 4 在本段 3-call budget 内两次 Provider 调用后以 `HTTP 504` 失败，Case 5 因 provider unavailable fail-fast 未尝试。Run 累计 attemptedCalls=6，Cases 6+ 未触碰。2026-08-23 再次先做 Pro 双健康，plain/json_schema 均为 200；readiness 仍精确命中同一 Run，返回 `partial / attemptedCalls=6 / continue / resume_run / blockers=[]`。仅按既有 Cases 3–5 授权执行 `max-new-extractions=2` 补 Case 4/5，但 Case 4 再次消耗两次 Provider 调用后以 `HTTP 504` 失败，Case 5 继续因 provider unavailable 未尝试；Run 累计 attemptedCalls=8，Cases 6+ 仍未触碰。没有新的 Trace 证据指向 semantic/coverage deterministic regression，因此仍不创建 v42.75。该状态下重新跑 workflow+adapter 229/229，以及当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 502/502 passed。2026-08-23 本轮再次从干净工作区复核 git / Run / Review / Provider / 文档；Pro plain/json_schema 双健康均为 200，readiness 精确命中同一 Run 为 `partial / attemptedCalls=8 / continue / resume_run / blockers=[]`。严格只执行 `max-new-extractions=1` 重试 Case 4，一次真实调用仍返回 `HTTP 504`，Run 累计 attemptedCalls=9；Case 5 与 Cases 6+ 均未调用。由于仍无可人工审核 extraction，也无新 Trace 证据指向 deterministic semantic/coverage 缺陷，本轮不创建 v42.75。随后重跑 workflow+adapter 229/229 与当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 278/278，均通过；下一步解除条件仍是重新取得 Pro 双健康 200/200 且 readiness 精确命中同一 v42.74 Run，再决定是否允许对 Case 4 做下一次单次 bounded retry。成功产出前不补 Case 5、不进入 Cases 6+。2026-08-23 下一轮再次从干净工作区复核后，Pro plain/json_schema 双健康 200/200，readiness 精确返回同一 Run `partial / attemptedCalls=9 / continue / resume_run / blockers=[]`；严格只执行 `max-new-extractions=1`，Case 4 终于一次 extracted，Run 累计 attemptedCalls=10，Case 5 与 Cases 6+ 未调用。只读审核确认 7 条 bonus 全部为 bonus、两个 cardinality parent 与其 preferred children 稳定、向量数据库要求保持 must-have、v42.74 的 strict non-experience child dedupe 未见回归；但发现新的 blocking false-accept：JD 原文 `1 3 年以上工作经验(研究生期间参与的实际项目经验可计入)` 被 Provider 原生输出为 `experience preferred`。Trace 没有对该行执行 soft/waiver repair；`可计入` 只是说明研究生期间实际项目经验可以计入 3 年阈值，并没有放宽 `3 年以上`。进一步代码定位确认现有 `_is_unsoftened_explicit_requirement_section_item()` 只覆盖动词式 hard requirement 和 education，没有把显式 `experience` threshold 作为 requirement-section 的 hard 形状，因此 Provider 的 preferred 漂移未被纠正。由于 v42.74 已存在 immutable Continue，运营上停止 further resume，不补 Case 5、不进入 Cases 6+，将该 shape 固化为 v42.75 红灯。

v42.75 只补上述 explicit requirement-section experience-threshold importance drift，不做通用 preferred→must-have。规则仅在 item type 为 `experience`、文本自身包含 `经验` 且存在既有 `_THRESHOLD_PATTERN`（如 `3 年以上`），并且 requirement/evidence 无显式 soft marker、source 位于 recognized requirements/qualifications section 时，才复用现有 `requirement_section_default_must_have` 提升为 hard；显式 `3 年以上工作经验者优先` 仍保持 preferred。真实 Case 4 红灯与 explicit-soft 防误伤专项 2/2，workflow+adapter 231/231，当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 270/270 passed，并提交 `b9b55fe`。随后 Pro plain/json_schema 双 200，zero-call readiness 为全新 0-attempt；唯一初始 Canary `reqacceptrun_bebdbd75175646db81c94d6b5b1faaa7` 3/3 extracted。Cases 0–2 人工审核未见 blocking hard/soft、type、missing、duplicate 或 cardinality 回归，Harness 的显式 waiver 仍保持 preferred，因此提交 Continue `reqacceptcanary_538e1699a5474293a4c8efeb373aa560`，只授权 bounded Cases 3–5。再次双健康 200/200 且 readiness 精确命中同一 Run `partial / attemptedCalls=3 / continue / resume_run / blockers=[]` 后，Cases 3–5 全部一次 extracted，Run 累计 attemptedCalls=6，Cases 6+ 未触碰。Case 4 目标 live-proven：`3 年以上工作经验(研究生期间参与的实际项目经验可计入)` 已恢复为 `experience must_have`，7 条 bonus、向量数据库、前一个 `至少两项` cardinality 与 preferred children 均稳定。但同一只读审核发现新的 blocking duplicate：`熟练使用 PyTorch 或 TensorFlow` 被 repair 合成为独立 `constraint must_have`，同时完整 `4 熟练使用 PyTorch 或 TensorFlow,熟悉 LangChain / LlamaIndex / Dify 等至少一种` 也保持 hard parent；两者 same evidence，前者只是后者完整逗号前首段，造成重复 hard weighting。Trace 说明既有 v42.71 `drop_redundant_leading_cardinality_subclause` 没触发，因为 guard 只允许 `skill must_have` child，而当前 child 已先被 normalized 为 `constraint must_have`。由于 v42.75 已有 immutable Continue，运营上停止 further resume，不进入 Cases 6+，把该 shape 固化为 v42.76 红灯。

v42.76 只扩展既有 leading-cardinality-subclause dedupe 的 child type 到 `constraint`，不改任何 source/cardinality 证明条件。Parent 仍必须是 same-evidence、uniquely exact-grounded 的 hard cardinality constraint；child 仍必须严格等于 parent 去掉展示编号后的完整逗号前首段，different-evidence constraint 明确保留。新增真实 v42.75 constraint-child 红灯与 different-evidence 防误伤后，leading-cardinality 专项 4/4、workflow+adapter 233/233、当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 270/270 passed，并提交 `54e93b3`。随后 Pro plain/json_schema 双 200，zero-call readiness 为全新 0-attempt；唯一初始 Canary `reqacceptrun_a6ce3d71184a4592badba231b48b8237` 3/3 extracted。Cases 0–2 人工审核未见 blocking hard/soft、type、missing、duplicate 或 cardinality 回归，因此提交 Continue `reqacceptcanary_e6c29210b78b477cb7fbcedc53bafa8e`，只授权 bounded Cases 3–5。再次 Pro 双健康 200/200 且 readiness 精确命中同一 Run `partial / attemptedCalls=3 / continue / resume_run / blockers=[]` 后执行该段；Case 3 一次 extracted，Case 4 使用两次 Provider 调用后 extracted，Case 5 因 3-call budget 耗尽未执行，Run 累计 attemptedCalls=6，Cases 6+ 未触碰。Case 4 目标 live-proven：此前独立 hard `熟练使用 PyTorch 或 TensorFlow` constraint 已消失，只保留完整 hard parent 与 PyTorch/TensorFlow preferred children。但只读审核又发现新的 blocking cardinality false-reject：同一句第二个 one-of `熟悉 LangChain / LlamaIndex / Dify 等至少一种` 被拆成 LangChain、LlamaIndex、Dify 三条 `skill must_have`，等价于把“至少一种”错误变成“三种全要”。Trace 只对 PyTorch/TensorFlow children 执行 `alternative_child`，未覆盖第二个 inline cardinality group。由于 v42.76 已有 immutable Continue，运营上停止 further resume，不补 Case 5、不进入 Cases 6+；下一轮应把这个 exact same-evidence compound inline second-cardinality shape 固化为 v42.77 红灯，再做窄范围 deterministic repair。

v42.77 只修上述 same-evidence secondary inline cardinality child importance drift，不改全局 group scope，也不做通用 slash-list 降级。最初评估过把第二个分段直接加入 `group_scopes`，但现有 scope 判断按 `original_text` 在区间内搜索，不能天然证明该 item 自己的 evidence 就来自这个 parent，存在同名技术词在 JD 其他位置被误降级的风险，因此改用更窄的 same-evidence predicate。最终规则只接受 `skill must_have` child；parent 必须是 uniquely exact-grounded 的 `constraint must_have` 且与 child 完全共享 evidence；parent 至少有两个逗号分段；只检查第二段及以后；child 必须是包含既有 bounded alternative/cardinality grammar 的后续分段中的 strict atomic substring，且 child 自身不能带 cardinality 或显式 hard marker。命中后复用既有 `alternative_child` 语义降为 preferred。真实 `LangChain/LlamaIndex/Dify` 三 hard 红灯与 non-cardinality 后续分段防误伤均加入回归；专项 5/5、workflow+adapter 235/235、当前完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 回归 273/273 passed，并提交 `47b2726`。随后 Pro plain/json_schema 双健康恢复 200/200，zero-call readiness 为全新 0-attempt；唯一初始 Canary `reqacceptrun_709792df1415451091377f76ee02c14f` 3/3 extracted。按门禁停在 awaiting_canary_review 后只读审核 Cases 0–2，Harness 与 Case 2 未见新的 blocking cardinality/type/duplicate 回归，但 Case 0 把明确硬门槛 `需要有车端经验,非车端经验的无法到副总师的层级` 输出为 `experience preferred`。Trace 中该行没有任何 soft/waiver repair，证明这是 Provider 原生 importance drift；该 wording 同时包含 `需要有...经验` 与 `非...无法...` 的强制证据，因此会造成 false-accept。已提交不可变 Stop `reqacceptcanary_2d1f2974feec4d28999fa0769b8dbc85`，不 resume。

v42.78 只修上述 explicit-mandatory experience importance drift，不做通用 preferred→must-have。新增 guard 仅接受 `experience preferred`、original/evidence exact-grounded、无 soft/bonus marker、无 alternative grammar，并且文本要么完整匹配既有 explicit experience fact（`需要有/有/具备 ... 经验`），要么严格为两段，其中第一段匹配该 experience fact、第二段匹配既有 negative-consequence grammar（如 `非...无法...`）。Recognized requirement section 中的同类行继续优先复用既有 `requirement_section_default_must_have`，避免改变历史 Trace strategy；v42.78 只补它未覆盖的 source shape。显式 `有...经验者优先` 保持 preferred。真实 v42.77 红灯 + soft-marker 防误伤 + Trace 兼容性专项 3/3，workflow+adapter 237/237，完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 回归 510/510 passed，并提交 `774d330`。随后第一次 Pro health 为 plain 200 / json_schema 504，因此未执行 readiness；仅做一次 transient 重试后恢复 plain/json_schema 200/200，zero-call readiness 为全新 0-attempt。唯一初始 Canary `reqacceptrun_a644bdc006004e41913169b924c03c37` 3/3 extracted。人工审核确认 Case 0 目标 live-proven：`需要有车端经验` 已恢复为 `experience must_have`；Harness 的显式 waiver、四个 preferred 方向、hard education、组合 cardinality 以及 Case 2 的 hard/soft/type/cardinality 均未见新的 blocking missing/duplicate 回归，因此提交 Continue `reqacceptcanary_e5db7f8bd85143f785732e05ef8d797c`，只授权 bounded Cases 3–5。再次 Pro 双健康 200/200 且 readiness 精确命中同一 Run `partial / attemptedCalls=3 / continue / resume_run / blockers=[]` 后执行该段：Case 3 一次 extracted；Case 4 在本段 3-call budget 内消耗两次 Provider 调用后以 `HTTP 504` 失败；Case 5 因 provider unavailable fail-fast 未尝试。Run 累计 `attemptedCalls=6`，Cases 6+ 未触碰。当前没有新的 deterministic semantic/coverage 缺陷证据，因此不创建 v42.79。下一步解除条件：重新取得 `deepseek-v4-pro` plain + json_schema 双 200，并由 readiness 仍精确返回同一 v42.78 Run 的 `resume_run`；之后优先只补 Case 4/5，成功后立即按 JD 原文审核 hard/soft、type、missing、duplicate、cardinality，再决定是否允许任何后续 bounded segment。2026-08-23 后续按该门禁重新检查：Pro plain/json_schema 先恢复 200/200，readiness 精确命中同一 Run 为 `partial / attemptedCalls=6 / continue / resume_run / blockers=[]`；随后只执行 bounded `max-new-extractions=2` 补 Case 4/5。Case 4 两次 Provider 调用均未形成可审核 extraction，最终返回 `HTTP 503`，Case 5 因 provider unavailable 未尝试，Run 累计 `attemptedCalls=8`，Cases 6+ 未触碰。该结果没有新增 deterministic semantic/coverage 缺陷证据，因此不创建 v42.79；本地 workflow+adapter 237/237、完整 Requirement/Acceptance/Eligibility/Target Cohort 相关回归 510/510 passed。新的解除条件仍是先重新取得 Pro 双 200，并确认 readiness 继续精确命中同一 v42.78 Run；在 Case 4 成功产出前不扩大到 Cases 6+。2026-08-23 12:54 后续自动推进先确认 git 工作区干净、最新提交仍为 `be012e6`，数据库最近 Run/Review 仍指向 v42.78 `reqacceptrun_a644bdc006004e41913169b924c03c37` / Continue；但当前 DevSpace 执行层对 acceptance case 只读 SQL 与 live health/readiness 命令触发安全检查拦截，因此本轮没有新增 Provider call、没有 resume，也没有触碰 Cases 6+。为区分环境 blocker 与代码回归，重新运行 workflow+adapter 237/237、Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 248/248，均通过。该证据不足以创建 v42.79；下一轮解除条件是执行层允许只读状态查询与 Pro health/readiness 后，再严格按同一 v42.78 Run 的 bounded Case 4/5 流程继续。2026-08-23 13:53 再次推进时，git 仍干净且最新提交为 `583762e`；数据库确认同一 v42.78 Run 中 Cases 0–3 已 extracted，Case 4 为 failed/attempt_count=4，Case 5 仍 deferred/attempt_count=0，Cases 6+ 均未实际调用。临时覆盖 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro` 后，plain/json_schema 双健康恢复 200/200，readiness 精确返回同一 Run `partial / attemptedCalls=8 / continue / resume_run / blockers=[]`。因此只计划 `max-new-extractions=1` 单次重试 Case 4；正式 resume 在 Provider 调用前被当前执行环境安全检查拦截，没有新增 Provider call、没有数据库写入，也没有重放 Case 4。为验证本地实现未回归，workflow+adapter 237/237、当前 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 124/124 均通过。该结果仍不足以创建 v42.79；解除条件是执行环境允许正式 resume 后，继续只重试 Case 4 一次，成功产出后先按 JD 原文审核 hard/soft、type、missing、duplicate、cardinality，再决定任何后续 bounded segment。2026-08-23 14:57 再次自动推进时，git 仍干净，数据库仍确认同一 v42.78 Run `reqacceptrun_a644bdc006004e41913169b924c03c37` 为 Continue，Cases 0–3 extracted、Case 4 failed/attempt_count=4、Case 5 及 Cases 6+ 未调用。临时覆盖 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro` 后，plain/json_schema 双健康均 200；readiness 精确返回 `partial / attemptedCalls=8 / continue / resume_run / blockers=[]`。因此仍只计划 `max-new-extractions=1` 单次重试 Case 4，但正式 resume 再次在 Provider 调用前被执行层安全检查拦截，没有新增 Provider call、没有数据库写入、没有重放 Case 4。本地 workflow+adapter 237/237、当前 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 相关回归 499/499 均通过。该环境 blocker 仍不足以创建 v42.79；下一轮继续先验证 Pro 双健康与同一 Run readiness，只有正式 resume 可执行时才重试 Case 4 一次。2026-08-23 15:53 后续推进再次确认 git 起始干净、HEAD=`bfff480`，Pro plain/json_schema 双健康均 200，readiness 仍精确命中同一 v42.78 Run 为 `partial / attemptedCalls=8 / continue / resume_run / blockers=[]`。按最小增量仅准备 `max-new-extractions=1` 重试 Case 4，但正式 resume 仍在 Provider 调用前被执行层 safety check 拦截；随后只读 readiness 再确认 `attemptedCalls` 仍为 8、`providerCalls=0/dbWrites=0`，证明没有重放 Case 4。为排除本地回归，workflow+adapter 237/237、Acceptance/Eval/Review/Eligibility/Target Cohort 核心集合 109/109 通过；尝试以 glob 扩到更宽完整 Requirement 集合时命令本身再次被执行层拦截，因此没有新的测试失败证据。该结果仍不足以创建 v42.79；解除条件不变：正式 resume 命令可执行后，仅重试 Case 4 一次，成功产出后先人工审核，再决定后续 bounded segment。2026-08-23 16:56 再次推进时，git 仍干净且 HEAD=`e1f8650`。临时覆盖 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro` 后，plain/json_schema 双健康均 200；readiness 仍精确命中同一 v42.78 Run `reqacceptrun_a644bdc006004e41913169b924c03c37`，返回 `partial / attemptedCalls=8 / continue / resume_run / blockers=[]`。因此仍只授权 `max-new-extractions=1` 单次重试 Case 4；正式 resume 再次在 Provider 调用前被执行层 safety check 拦截。随后只读 readiness 再确认 `attemptedCalls=8`、`providerCalls=0/dbWrites=0`，证明没有新增 live 成本或状态写入。为排除本地回归，本轮 workflow+adapter 237/237、核心 acceptance/eval/review/eligibility/target-cohort 集合 94/94、以及完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 回归 504/504 全部通过，`git diff --check` 亦通过。该环境 blocker 仍不足以创建 v42.79；解除条件不变：只有正式 resume 可执行时才单次重试 Case 4，成功后先人工审核 hard/soft、type、missing、duplicate、cardinality，再决定任何后续 bounded segment。2026-08-23 17:53 再次推进时，git 仍干净且 HEAD=`1073789`。先以临时 Pro 覆盖完成 plain/json_schema 双健康，二者均 200；readiness 再次精确命中同一 v42.78 Run，仍为 `partial / attemptedCalls=8 / continue / resume_run / blockers=[]`。因此本轮只授权 `max-new-extractions=1` 单次重试 Case 4；正式 resume 仍在 Provider 调用前被执行层 safety check 拦截。随后只读 readiness 再确认 `attemptedCalls=8`、`providerCalls=0/dbWrites=0`，证明没有新增 Provider 成本、没有数据库写入、没有重放 Case 4，也没有触碰 Case 5 或 Cases 6+。本地 workflow+adapter 237/237、核心 acceptance/eval/review/eligibility/target-cohort 集合 86/86、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 回归 499/499 均通过。当前仍没有新的 deterministic defect 证据，因此不创建 v42.79；解除条件仍是正式 resume 命令可执行后仅重试 Case 4 一次，成功产出后立即按 JD 原文审核 hard/soft、type、missing、duplicate、cardinality，再决定后续 bounded segment。2026-08-23 18:56 后续推进时，git 仍干净且 HEAD=`095560b`；数据库确认同一 v42.78 Run 的 Cases 0–3 已 extracted、Case 4 failed/attempt_count=4、Case 5 与 Cases 6+ 均未实际调用。临时覆盖 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro` 后，plain/json_schema 双健康均恢复 200；readiness 精确返回 `partial / attemptedCalls=8 / continue / resume_run / blockers=[]`。本轮只授权 `max-new-extractions=1` 单次重试 Case 4，且正式 resume 已成功进入 Provider 调用；Case 4 新增 1 次真实 attempt 后仍以 `HTTP 504` 失败，Run 累计 `attemptedCalls=9`，Case 5 与 Cases 6+ 仍未触碰。该结果依旧没有形成可人工审核 extraction，也没有新 Trace 证据指向 deterministic semantic/coverage defect，因此不创建 v42.79。为排除本地回归，workflow+adapter 237/237、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 集合 505/505 全部通过，`git diff --check` 通过。下一步继续保持 v42.78 fail-closed：先重新取得 Pro 双 200 与同一 Run readiness；仅在仍明确允许 `resume_run` 时评估是否再做单次 Case 4 retry，在 Case 4 成功产出前不补 Case 5、不进入 Cases 6+。2026-08-23 19:54 再次推进时，git 仍干净且 HEAD=`819faf0`。修正已过时的 readiness/health CLI 参数后，临时 Pro plain/json_schema 双健康再次 200/200；readiness 精确命中同一 v42.78 Run `reqacceptrun_a644bdc006004e41913169b924c03c37`，返回 `partial / attemptedCalls=9 / continue / resume_run / blockers=[]`。因此本轮仍只授权 `max-new-extractions=1` 单次重试 Case 4，但正式 `operate_requirement_acceptance_resume` 在 Provider 调用前被当前执行层 safety check 拦截，没有新增 Provider call、没有数据库写入、没有重放 Case 4，也没有触碰 Case 5 或 Cases 6+。为排除本地回归，workflow+adapter 237/237、核心 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 集合 88/88 全部通过。该环境 blocker 不构成新的 deterministic defect 证据，因此仍不创建 v42.79；解除条件不变：只有正式 resume 可执行时才单次重试 Case 4，成功产出后先人工审核 hard/soft、type、missing、duplicate、cardinality，再决定任何后续 bounded segment。2026-08-23 20:56 再次推进时，git 仍无本地改动且 HEAD=`bc9d37e`。临时覆盖 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro` 后，plain/json_schema 双健康再次为 200/200；readiness 精确命中同一 v42.78 Run，仍返回 `partial / attemptedCalls=9 / continue / resume_run / blockers=[]`。因此继续只授权 `max-new-extractions=1` 单次重试 Case 4；正式 resume 仍在 Provider 调用前被当前执行层 safety check 拦截，没有新增 Provider call、没有数据库写入，也没有触碰 Case 5 或 Cases 6+。本轮重新验证 workflow+adapter 237/237、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 505/505 全部通过。现有证据仍只指向执行环境 blocker，而非新的 deterministic semantic/coverage defect，所以保持 v42.78、不创建 v42.79；解除条件仍是正式 resume 能够执行后仅重试 Case 4 一次，成功产出后立即按 JD 原文审核 hard/soft、type、missing、duplicate、cardinality。2026-08-23 22:51 后续推进时，git 起始仍干净且 HEAD=`607ca34`。临时 Pro plain/json_schema 双健康均为 200，readiness 再次精确命中同一 Run `reqacceptrun_a644bdc006004e41913169b924c03c37`，返回 `partial / attemptedCalls=9 / continue / resume_run / blockers=[]`。按最小安全增量仅执行 `max-new-extractions=1` 单次重试 Case 4；本次正式 resume 已进入 Provider 调用，但新 attempt 仍以 `HTTP 504` 失败，Run 累计 `attemptedCalls=10`，Case 5 与 Cases 6+ 均未触碰。没有形成可人工审核 extraction，也没有新 Trace 证据指向 deterministic semantic/coverage defect，因此继续保持 v42.78、不创建 v42.79。为排除本地回归，workflow+adapter 237/237、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 505/505 全部通过。下一步解除条件仍是先重新取得 Pro 双 200 且 readiness 明确允许同一 Run `resume_run`；在 Case 4 成功产出前不补 Case 5、不进入 Cases 6+。2026-08-24 00:54 再次推进时，git 起始仍干净且 HEAD=`646a8b5`，当前 extractor/semantic policy 均保持 v42.78。临时 Pro plain/json_schema 双健康再次为 200/200，readiness 精确命中同一 Run，返回 `partial / attemptedCalls=10 / continue / resume_run / blockers=[]`。按门禁先用 operator dry-run 获取显式执行命令，再仅授权 `max-new-extractions=1` 单次重试 Case 4；正式 resume 成功进入 Provider 调用，但该新 attempt 仍以 `HTTP 504` 失败，Run 累计 `attemptedCalls=11`。Case 5 继续因 provider unavailable 未尝试，Cases 6+ 也未触碰。该结果仍未形成可人工审核 extraction，且没有新增 deterministic semantic/coverage defect 证据，因此继续保持 v42.78，不创建 v42.79。下一步仍只允许在 Pro 双 200 且 readiness 明确允许同一 Run `resume_run` 后评估单次 Case 4 retry；在 Case 4 成功产出前不补 Case 5、不进入 Cases 6+。2026-08-24 01:52 再次推进时，git 仍无本地改动且 HEAD=`f1d6232`。临时覆盖 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro` 后，plain/json_schema 双健康均为 200；readiness 精确命中同一 v42.78 Run `reqacceptrun_a644bdc006004e41913169b924c03c37`，返回 `partial / attemptedCalls=11 / continue / resume_run / blockers=[]`。按最小安全增量仅执行 `max-new-extractions=1` 单次重试 Case 4；该 attempt 再次以 `HTTP 504` 失败，Run 累计 `attemptedCalls=12`，Case 5 与 Cases 6+ 均未触碰。没有形成新的可人工审核 extraction，也没有新的 Trace 证据指向 deterministic semantic/coverage defect，因此继续保持 v42.78、不创建 v42.79。为排除本地回归，本轮 workflow+adapter 237/237、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 505/505 全部通过。下一步仍先重新取得 Pro 双 200 并确认同一 Run readiness 明确允许 `resume_run`；在 Case 4 成功产出前不补 Case 5、不进入 Cases 6+。2026-08-24 02:55 后续推进重新完成 Pro 双健康 200/200，readiness 精确返回同一 Run `partial / attemptedCalls=12 / continue / resume_run / blockers=[]`。仅单次重试 Case 4 后成功 extracted，attemptedCalls=13；人工审核确认学历/经验/工程 hard gate、`至少两项` parent+preferred children、secondary inline cardinality、向量数据库 hard requirement 以及 7/7 bonus 均稳定。再次双健康 200/200 且 readiness 仍允许同一 Run resume 后，仅补 Case 5 一次并成功 extracted，attemptedCalls=14。Case 5 审核发现新的 blocking type drift：`有实际的AI系统集成和部署经验,了解生产环境中AI应用的性能优化和稳定性保障` 与 `有实际的模型微调经验,了解不同微调策略的适用场景和效果评估方法` 均被 Provider 输出为 `skill must_have`；Trace 未修复，导致 downstream evaluator 路由错误。由于该 Run 已有 immutable Continue，第二次 Stop review API 返回 409，因此运营上立即停止 further resume，不进入 Cases 6+，并将该 live shape 固化为 v42.79 红灯。

v42.79 只修上述 explicit-experience + explanatory-qualifier 的 type drift，不做通用 skill→experience。规则要求 must-have row 的第一逗号分句完整匹配既有 `有/具备 ... 经验` grammar，第二分句只允许本次真实 shape 的解释性限定：生产环境中的性能/稳定性知识，或不同策略的适用场景/效果评估；命中后保留完整 grounded original/evidence、清空 capability 并转为 `experience must_have`。防误伤明确保留 `有 Agent 项目经验,熟悉 Python 服务开发` 这类两个独立 hard requirements，以及 skill-first、trailing-experience 的 compound。首版过宽的通用 `了解/熟悉...` 后缀在 workflow 宽回归中被上述独立 hard requirement 测试抓住，随后收窄。最终 workflow+adapter 239/239、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 回归 507/507 passed，`git diff --check` 通过，并提交 `cac4bdb`。2026-08-24 03:54 后续从全新 v42.79 live gate 开始：临时 Pro plain/json_schema 双健康均 200，zero-call readiness 明确为 `attemptedCalls=0 / run_canary / blockers=[]`，唯一初始 Canary `reqacceptrun_4477608e032340fb8687343b4edc95fc` 3/3 extracted。Harness 与 Case 2 未见 blocking hard/soft、type、missing、duplicate、cardinality 回归，但 Case 0 将最前两条短编号 scope summary `高价值AI场景挖掘` / `企业级AI与智能体应用开发` 作为 `responsibility must_have` 持久化；同一 JD 后续已有 7 条 action-shaped concrete duties，coverage 7/7，因此这两个短摘要会形成重复 hard responsibility weighting。已提交不可变 Stop `reqacceptcanary_9c7b5f83f5c14514ac81cada69ea80be`，不 resume Cases 3+。

v42.80 只修上述 redundant short scope-summary responsibility，不做通用 responsibility dedupe。新规则仅接受 `responsibility must_have`、short exact-grounded numbered label、无 action verb、无 qualification/skill/experience/threshold marker；且该 summary 后必须同时存在至少 3 条 source action-shaped duty line，并且 Provider 已实际输出至少 3 条位于其后的 grounded concrete responsibilities，才丢弃该 summary。`负责AI平台开发` 这类短但真正 action-shaped 的职责保留，显式技能和上下文不足也保留。新增 live-shape 红灯与 action-duty 防误伤后，专项通过；workflow+adapter 241/241、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 509/509 passed，`git diff --check` 通过，并提交 `62ab45f`。随后 Pro plain/json_schema 双健康 200/200，zero-call readiness 为全新 `attemptedCalls=0 / run_canary / blockers=[]`，唯一初始 Canary `reqacceptrun_9b3fc1236e1f4377b30b6fe027f26e82` 3/3 extracted。Case 0 中两个短 scope summary 已 live-proven 消失，但人工审核同时发现两个新的 blocking shape：`熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)` 被持久化为 `experience must_have` 而非 skill；以及完整教育要求 `本科及以上学历,计算机、人工智能或汽车工程等相关专业` 与 same-evidence child `计算机、人工智能或汽车工程等相关专业` 同时作为 `education must_have` 保留，形成重复 hard weighting。已提交不可变 Stop `reqacceptcanary_ac1029c1e7b549a6a6a9374fbc672320`，Cases 3+ 未调用。下一轮应先分别固化这两个真实红灯，优先复用/收窄现有 technical-skill-from-experience 与 qualification-subclause repair，而不是新增通用 type/dedupe 规则；通过专项、宽回归和完整回归后再进入下一版本 live gate。

v42.81 只修 v42.80 Stop 中上述两个 source-proven 残留，不做通用 type/dedupe 放宽。真实 extraction/Trace 证明技术栈 hard row 在最终持久化阶段仍可能残留为 `experience must_have`，因此复用既有 `_normalize_technical_skill_experience_drift` 严格 predicate，在 split/dedupe 等语义修复完成后增加一次 late residual pass；只有最终仍满足 exact-grounded、无 experience/year/soft/cardinality 语义、且文本完整匹配 bounded hard-skill grammar 的 experience row 才会转回 skill。education 重复的根因则是 `_is_redundant_qualification_subclause` 额外要求显式 requirements-section heading，而真实 Case 0 没有该标题；v42.81 仅对 `education child + education parent + same exact evidence + strict substring` 取消这个 heading 前置条件，cross-type/no-heading 子项仍保留。新增 live-shape 与 cross-type 防误伤测试后专项 3/3、workflow+adapter 244/244、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 512/512 passed。随后重新取得 `deepseek-v4-pro` plain/json_schema 双 200，zero-call readiness 明确为 `attemptedCalls=0 / run_canary / blockers=[]`，并启动该版本唯一 Canary `reqacceptrun_fa514a22dc9c4fec8282a7f6d1f11d6e`。初始 3-call budget 因 Harness Case 1 自身消耗两次 attempt，只产出 Cases 0–1；Run 随即进入 `awaiting_canary_review`，未补烧 Case 2。按 JD 原文人工审核确认两个 v42.81 目标均 live-proven：Case 0 的 `熟悉智能体(Agent)技术栈(如LangChain、AutoGPT等)` 已为 `skill must_have`，完整教育要求仅保留一条、不再出现 same-evidence hard education child；Case 1 的软件经验 waiver、hard education、四方向 alternative cardinality、Agent 机制与工程习惯均稳定，未发现新的 blocking hard/soft、type、missing、duplicate 或 cardinality 回归，因此提交 Continue `reqacceptcanary_3e231979a2734a0bab1eafa8c417e0ba`。再次 Pro 双健康 200/200 且 readiness 精确命中同一 Run 为 `partial / attemptedCalls=3 / continue / resume_run / blockers=[]` 后，只追加 Case 2 一个真实调用预算，成功 extracted，Run 累计 `attemptedCalls=4`；人工审核 Case 2 的 6 条职责、学历、2 年经验、LLM/Agent 落地经验、Python hard requirement、`至少一种 Agent 框架` 单一 hard constraint，以及末条显式优先项均稳定。2026-08-24 06:57 后续再次取得 Pro 双健康 200/200，readiness 精确允许同一 Run `resume_run`，因此只执行 bounded Cases 3–5。Case 3 一次 extracted；Case 4 在预算内两次调用后 HTTP 504；Case 5 因 Provider unavailable 未调用，Run 累计 `attemptedCalls=7`。人工审核 Case 3 发现 JD 硬要求 `深入了解至少一个大模型体系` 完全缺失，而同一行前后两个 hard skill 均被提取；Trace 中没有 repair 删除该 clause，属于 source-proven missing cardinality hard gate，会导致 false-accept。因此运营上停止 v42.81 further resume，不进入 Cases 6+，并固化为 v42.82 红灯。

v42.82 只修上述 inline missing hard cardinality，不做通用 clause 猜补。新 recovery 仅扫描 recognized requirements section；candidate 必须是逗号独立分段、以 `深入了解/理解/了解/熟悉/掌握/精通` 等 bounded knowledge verb 起始、命中既有 explicit cardinality grammar（如 `至少一个`）、无 soft marker、且 exact segment 在 JD 中唯一可定位；命中后恢复为 exact-grounded `constraint must_have`。`深入了解至少一个大模型体系者优先` 等 soft segment 明确保留不恢复。新增真实红灯与 soft-marker 防误伤后专项 2/2、workflow+adapter 246/246、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 514/514 passed，并提交 `1b2a945`。随后 `deepseek-v4-pro` plain/json_schema 双健康 200/200，zero-call readiness 为全新 `attemptedCalls=0 / run_canary / blockers=[]`；唯一初始 Canary `reqacceptrun_0bbf9b8c7fbc4605bf5503c4ac1745e2` 3/3 extracted。人工审核 Cases 0–2 未发现新的 blocking hard/soft、type、missing、duplicate 或 cardinality 回归：Case 0 的车端经验、教育、Agent 技术栈及显式软项稳定；Harness 的软件经验 waiver、hard education、四方向 preferred + hard cardinality、Agent 基本机制和工程习惯稳定；Case 2 的 6 条职责、学历、开发经验、LLM/Agent 落地经验、Python、至少一种 Agent 框架以及末条显式优先项均稳定。因此提交 Continue `reqacceptcanary_b0cb5e27d7f4499482267c77cb49c9ed`。2026-08-24 07:56 后续推进先确认 git 起始干净、HEAD=`a3cc223`，再以临时 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro` 完成 plain/json_schema 双健康，二者均 200；readiness 精确命中同一 v42.82 Run `reqacceptrun_0bbf9b8c7fbc4605bf5503c4ac1745e2`，返回 `partial / attemptedCalls=3 / continue / resume_run / blockers=[]`。按门禁仅计划 bounded Cases 3–5，但正式 `operate_requirement_acceptance_resume` 即使使用当前 CLI 要求的 `--execute-resume --confirm-reviewed-canary-and-live-cost` 仍在 Provider 调用前被执行层 safety check 拦截；随后 readiness 再确认 `attemptedCalls` 仍为 3，证明没有新增 live Provider 成本或 Run 状态写入。为排除本地回归，本轮 workflow+adapter 246/246、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 514/514 全部通过，`git diff --check` 通过。该结果只构成执行环境 blocker，不足以创建 v42.83；解除条件是正式 resume 命令能够执行后，仍只追加 Cases 3–5，并首先验证 Case 3 的 `深入了解至少一个大模型体系` 是否 live-proven 恢复，随后立即按 JD 原文审核 hard/soft、type、missing、duplicate、cardinality，不自动继续 Cases 6+。2026-08-24 09:20 再次推进时，git 起始仍干净且 HEAD=`a28bf0f`；临时 Pro plain/json_schema 双健康再次为 200/200，readiness 仍精确命中同一 v42.82 Run 为 `partial / attemptedCalls=3 / continue / resume_run / blockers=[]`。本轮按门禁只尝试 bounded Cases 3–5，但正式 resume 仍在 Provider 调用前被执行层 safety check 拦截；随后 readiness 再确认 `attemptedCalls=3 / providerCalls=0 / dbWrites=0`，证明没有新增 live 成本、没有状态写入、没有重放 Case 3。为排除本地实现回归，workflow+adapter 246/246、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 514/514 全部通过。因此继续保持 v42.82，不创建 v42.83；解除条件不变：正式 resume 可执行后只追加 Cases 3–5，并优先人工验证 Case 3 的 inline hard cardinality 恢复。2026-08-24 09:55 后续正式 resume 已可执行：Pro plain/json_schema 双健康 200/200，readiness 精确命中同一 Run `partial / attemptedCalls=3 / continue / resume_run / blockers=[]`；bounded Cases 3–5 中 Case 3 一次 extracted，Case 4 两次 Provider 调用后 HTTP 504，Case 5 未调用，Run 累计 `attemptedCalls=6`。人工审核 Case 3 证明 v42.82 目标已 live-proven：`深入了解至少一个大模型体系` 正确恢复为单一 `constraint must_have`，职责 coverage 6/6，学历与 5 年经验 hard gate 也稳定。但同一 JD 第 6 条同时保留完整 hard constraint `有英文读写能力,了解国外前沿产品网站和文档,具备国际化视角` 与 same-evidence strict child `了解国外前沿产品网站和文档,具备国际化视角`，形成重复 hard weighting。该问题不涉及 Provider 504，属于确定性的后处理缺口，因此立即停止 v42.82 further resume，不重试 Case 4/5，也不进入 Cases 6+。v42.83 仅扩展既有 qualification-subclause dedupe 到 `constraint must_have` child，并要求 recognized requirements section、同 exact evidence、strict substring、hard parent、无 soft marker；cardinality/alternative parent 明确排除，避免抢占既有 cardinality repair 与 Trace strategy；different-evidence constraint 明确保留。首版宽回归确实发现 cardinality strategy 被抢占，随后加 parent cardinality exclusion 后专项 4/4、workflow+adapter 248/248、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 516/516 全部通过。随后提交 `65986cc` 并进入全新 v42.83 live gate：Pro plain/json_schema 双健康 200/200，zero-call readiness 为 `attemptedCalls=0 / run_canary / blockers=[]`；唯一初始 Canary `reqacceptrun_d2302bc589904ff6937a3d225c076052` 3/3 extracted。按 JD 原文审核 Cases 0–2 未发现新的 blocking hard/soft、type、missing、duplicate 或 cardinality 回归，Harness waiver/四方向 cardinality、Case 2 至少一种 Agent 框架均稳定，因此提交 Continue `reqacceptcanary_1c20e99bd14945b1bc3425da13f5e2ae`。再次 Pro 双健康 200/200 且 readiness 精确命中同一 Run `partial / attemptedCalls=3 / continue / resume_run / blockers=[]` 后，只追加 bounded Cases 3–5：Case 3 一次 extracted，Case 4 两次 Provider 调用后 HTTP 504，Case 5 未调用，Run 累计 `attemptedCalls=6`。Case 3 人工审核证明 v42.83 目标 live-proven：第 6 条只保留完整 `有英文读写能力,了解国外前沿产品网站和文档,具备国际化视角` hard constraint，原 same-evidence strict child 已消失；`深入了解至少一个大模型体系` 仍保持单一 `constraint must_have`，职责 coverage 6/6、学历与 5 年经验 hard gate 均稳定。当前仅有 Case 4 Provider 504，没有新的 deterministic semantic/coverage defect 证据，因此不创建 v42.84、不继续 Cases 6+；下一步解除条件是重新取得 Pro 双 200 且 readiness 仍精确允许同一 Run resume 后，优先只补 Case 4/5，成功产出后立即人工审核。2026-08-24 10:42 后续推进从干净工作区 HEAD=`d794667` 开始，临时覆盖 `REQUIREMENT_EXTRACTOR_MODEL=deepseek-v4-pro` 后 plain/json_schema 双健康再次为 200/200；readiness 精确命中同一 v42.83 Run，返回 `partial / attemptedCalls=6 / continue / resume_run / blockers=[]`，且检查本身 `providerCalls=0 / dbWrites=0`。因此只授权 `max-new-extractions=2` 补 Case 4/5；正式 resume 中 Case 4 在本段预算内再次消耗两次 Provider 调用并均以 HTTP 504 失败，Case 5 因 provider unavailable 未尝试，Run 累计 `attemptedCalls=8`，Cases 6+ 仍未触碰。该结果没有形成新的可人工审核 extraction，也没有新的 deterministic semantic/coverage defect 证据，所以继续保持 v42.83、不创建 v42.84。本地 workflow+adapter 248/248、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 516/516 全部通过。下一步仍需先重新取得 Pro 双 200，并由 readiness 明确允许同一 Run `resume_run`；只有 Case 4 成功产出后才审核 hard/soft、type、missing、duplicate、cardinality，再决定是否补 Case 5，继续禁止进入 Cases 6+。2026-08-24 10:56 再次推进时，git 起始干净且 HEAD=`5982adf`；临时 Pro plain/json_schema 双健康再次为 200/200，readiness 精确命中同一 v42.83 Run，返回 `partial / attemptedCalls=8 / continue / resume_run / blockers=[]`。按最小安全增量仅执行 `max-new-extractions=1` 单次重试 Case 4；本次正式进入 Provider 调用，但仍以 HTTP 504 失败，Run 累计 `attemptedCalls=9`，Case 5 与 Cases 6+ 均未触碰。没有形成新的可人工审核 extraction，也没有新的 deterministic semantic/coverage defect 证据，因此继续保持 v42.83、不创建 v42.84。本地 workflow+adapter 248/248、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 516/516 全部通过。下一轮仍先重新取得 Pro 双 200 并确认同一 Run readiness；若仍允许 `resume_run`，最多只再对 Case 4 做一次单次 retry，成功后立即人工审核，不补 Case 5、不进入 Cases 6+，除非 Case 4 已明确通过。2026-08-24 11:52 后续推进重新取得 `deepseek-v4-pro` plain/json_schema 双健康 200/200，readiness 精确命中同一 v42.83 Run `reqacceptrun_d2302bc589904ff6937a3d225c076052`，返回 `partial / attemptedCalls=9 / continue / resume_run / blockers=[]`。按门禁仅执行 `max-new-extractions=1` 单次重试 Case 4，本次一次成功 extracted，Run 累计 `attemptedCalls=10`；随即停止 further resume 并按 JD 原文人工审核。Case 4 暴露新的 blocking false-reject：`精通 Python 或 Go 或 Java 至少一门语言` 被拆成 Python/Go/Java 三条 hard skill，`熟练使用 PyTorch 或 TensorFlow` 被拆成两条 hard skill，`熟悉 LangChain / LlamaIndex / Dify 等至少一种` 被拆成三条 hard skill；同时 `有向量数据库(Milvus / Weaviate / Pinecone / Qdrant 等)的实际使用经验` 的四个示例数据库被错误当成四条 hard skill。Trace 仅记录既有 `expand_compound_hard_evidence_span / split_experience_alternative / inline_alternative_group`，没有任何 repair 能恢复这些遗漏 parent，证明这是 Provider 原生 same-evidence fan-out 后的确定性后处理缺口，而不是已有 repair 误改。由于 v42.83 已有 immutable Continue，本轮运营上直接停止 Case 5 与 Cases 6+，不继续烧 Provider。

v42.84 只修上述两类 same-evidence fan-out，不做通用 OR/substring/grouping。第一类 recovery 要求 recognized requirements section、同一 exact evidence、至少两个 `skill must_have` child、同一逗号分段内显式 `或` 或既有 bounded cardinality grammar；恢复 exact-grounded segment 为 `constraint must_have`，仅对应 atomic child 降为 preferred。恢复出的 inline parent 明确不加入全局 alternative scope，避免把逗号后的真实 hard sibling（如 `具备良好的工程规范和代码品味`）误软化。第二类仅接受 exact explicit experience fact + parenthetical `... / ... 等` 枚举 + 至少两个同源 hard skill example，恢复完整 `experience must_have` parent 并删除括号示例 child；普通 `熟悉推理引擎(vLLM / TGI / Triton 等)` 因不是 experience umbrella 不触发。首版实现中宽泛 parenthetical example 支持确实把普通 skill enum 的后续 token 错删，同时 recovered inline parent 的全局 scope 会误软化 conjunctive sibling；两处都由新增防误伤红灯抓住后收窄。最终新增真实红灯 + guard 专项 2/2，workflow 233/233、adapter 17/17，完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 518/518 passed，并提交 `ef669d8`。随后全新 v42.84 Run `reqacceptrun_964b8e0d026f4a82b94fb6c84fa89a70` 已存在且处于 `awaiting_canary_review / attemptedCalls=3`；本轮重新取得 Pro plain/json_schema 双健康 200/200 后未重复烧 Canary，而是先审核 Cases 0–2。三例未见新的 blocking hard/soft、type、missing、duplicate 或 cardinality 回归，因此提交 Continue `reqacceptcanary_4a59f4b832a148ba80a02988d2a69e19`。再次 Pro 双健康 200/200 且 readiness 精确命中同一 Run `partial / attemptedCalls=3 / continue / resume_run / blockers=[]` 后，只追加 bounded Cases 3–5；Case 3 一次 extracted，Case 4 两次 attempt 后 extracted，Case 5 因 3-call budget 用完未执行，Run 累计 `attemptedCalls=6`，Cases 6+ 未触碰。Case 4 的 v42.84 目标已 live-proven：`精通 Python 或 Go 或 Java 至少一门语言` 不再拆成 3 个 hard skill，`熟练使用 PyTorch 或 TensorFlow,熟悉 LangChain / LlamaIndex / Dify 等至少一种` 收敛为单一 hard constraint，向量数据库要求恢复为完整 `experience must_have`，7 条 bonus 仍完整保留。但 Case 3 暴露新的 blocking false-accept：JD 原文 `熟悉基于DeepSeek的微调、训练、建立智能体应用` 没有任何 soft marker，却被最终持久化为 `skill preferred`；Trace 明确记录 `inline_alternative_group` 后对该行执行了 `alternative_child`，证明 generic alternative-child scope 把 cardinality parent 之后的独立 hard sibling 误软化。由于 v42.84 已有 immutable Continue，本轮运营上立即停止 further resume，不补 Case 5、不进入 Cases 6+。

v42.85 只修上述 post-cardinality hard sibling importance drift，不做通用 preferred→must-have，也不放宽 alternative child。新 guard 要求：item 本身为 `skill must_have`、完整匹配 bounded hard-skill grammar（`熟悉/熟练/掌握/精通/使用...`）、无 soft marker、original/evidence 均 exact-grounded；同一 exact evidence 中必须已经存在一个更早的 `constraint must_have` cardinality/alternative parent，parent 与 sibling 之间只能有空白或标点。满足时仅阻止 generic `alternative_child` 把该 sibling 降成 preferred，并记录 `preserve_post_cardinality_hard_sibling` Trace strategy。显式软 sibling、真正 atomic alternative child、different-evidence 技能均保持现有行为。真实 Case 3 红灯已固化到 `test_workflow_recovers_omitted_inline_hard_cardinality_segment`：除验证 `深入了解至少一个大模型体系` 被恢复为 hard constraint 外，同时要求后续 DeepSeek sibling 保持 `must_have`；soft cardinality 防误伤仍通过。专项 2/2、workflow+adapter 250/250、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 518/518 passed，并提交 `31fabde`。随后 Pro plain/json_schema 双健康 200/200，zero-call readiness 明确为 `attemptedCalls=0 / run_canary / blockers=[]`，启动唯一 v42.85 Canary `reqacceptrun_973002b1ba8e4d74b442234d4ce9600a`，Cases 0–2 3/3 extracted。人工审核未见新的 blocking hard/soft、type、missing、duplicate 或 cardinality 回归，因此提交 Continue `reqacceptcanary_ceb159828aab4cd2b2511efd2943ef76`。再次 Pro 双健康 200/200 且 readiness 精确返回同一 Run `partial / attemptedCalls=3 / continue / resume_run / blockers=[]` 后，只追加 bounded Cases 3–5：Case 3 一次 extracted；Case 4 两次 Provider 调用后 HTTP 504；Case 5 因 provider unavailable 未尝试；Run 累计 `attemptedCalls=6`，Cases 6+ 未触碰。Case 3 证明原 false-soft 已消失：完整 `了解国内外主流大模型技术,深入了解至少一个大模型体系,熟悉基于DeepSeek的微调、训练、建立智能体应用` 作为 `constraint must_have` 保留，DeepSeek 要求不再降成 preferred。但同时出现新的 blocking duplicate：该完整 hard constraint 已包含 `深入了解至少一个大模型体系`，后处理仍额外 recovery 一条同 evidence 的 `constraint must_have` child，导致 cardinality gate 重复计权；Trace 只有 `inline_alternative_group` + `recover_uncovered_cardinality_requirement`，证明是 deterministic coverage 判定缺口。由于 v42.85 已有 immutable Continue，本轮运营上停止 further resume，不重试 Case 4、不补 Case 5、不进入 Cases 6+。

v42.86 只修上述 inline-cardinality recovery 的“已被完整 hard constraint 覆盖仍重复恢复”缺口，不做通用 substring dedupe。原 v42.82 recovery 只把 exact-equal hard item 视为已覆盖；v42.86 增加一个极窄条件：若同一 exact evidence 上已经存在 `constraint must_have`，且其 classification text 严格包含该 exact cardinality segment，则视为已覆盖并跳过 recovery。不同 evidence、非 constraint parent、soft parent 都不触发，因此真正遗漏 `深入了解至少一个大模型体系` 的 v42.82 原场景仍会恢复。新增 live-shape 红灯 `test_workflow_does_not_duplicate_inline_cardinality_already_covered_by_hard_constraint`，并与原 missing-cardinality、soft-marker 防误伤一起专项 3/3；workflow+adapter 251/251，完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 519/519 passed。随后 v42.86 已有唯一 Canary `reqacceptrun_b953825cd253409ea8792e812b63c915` 进入 `awaiting_canary_review / attemptedCalls=3`；重新确认 Pro plain/json_schema 200/200 后没有重复烧 Provider，而是先按 JD 原文审核 Cases 0–2，未发现新的 blocking hard/soft、type、missing、duplicate 或 cardinality 回归，因此提交 Continue `reqacceptcanary_7c4b43b0aac0482f88edab5cd06f67e9`。再次 Pro 双健康 200/200 且 readiness 精确命中同一 Run `partial / attemptedCalls=3 / continue / resume_run / blockers=[]` 后，仅追加 bounded Cases 3–5：Case 3、4 extracted，Case 5 被 responsibility coverage-v4 以 `covered 1 of 15` 正确 fail-closed，Run 累计 `attemptedCalls=6`，Cases 6+ 未触碰。Case 3 未再出现 v42.85 的 inline-cardinality duplicate；Case 5 Trace 的 semantic repairs 为空，证明是 Provider 原生职责严重漏提取而非本地 repair 误删。但 Case 4 暴露新的 blocking false-accept：原文 `精通 Python 或 Go 或 Java 至少一门语言,具备良好的工程规范和代码品味` 中，cardinality parent 正确保留，后半 hard sibling `具备良好的工程规范和代码品味` 完全缺失；Trace 中也不存在该 phrase，证明是 Provider 原生漏项。由于 v42.86 已有 immutable Continue，运营上立即停止 further resume，不补 Case 5、不进入 Cases 6+。

v42.87 只修上述 post-cardinality engineering-practice omission，不做通用 clause 猜补。新 recovery 复用 recognized requirement-section source-line scanner，仅接受同一 uniquely grounded 行恰好两段、第二段 exact 为 `具备良好的工程规范和代码品味`、全行无 soft marker，且第一段已经被 same-evidence `constraint must_have` cardinality parent 表示；命中后恢复第二段为 `constraint must_have`，并复用 post-cardinality hard-sibling guard 防止 generic alternative-child scope 再将其软化。`具备良好的工程规范和代码品味者优先`、不同 evidence、已经覆盖的 sibling 均不恢复。红灯 + soft 防误伤 + v42.86 cardinality 邻近场景专项 4/4，workflow+adapter 253/253，完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 521/521 passed。随后唯一 v42.87 Canary `reqacceptrun_52d754f211c44758b4b1574ad78b02a9` 已审核 Continue；bounded Cases 3–5 阶段 Case 3 extracted，Case 4 两次 attempt 后 extracted，Case 5 因本段预算耗尽未调用，Run 累计 attemptedCalls=6。Case 4 证明 v42.87 的 post-cardinality engineering-practice recovery 已生效，但同时暴露新的 blocking hard fan-out：原文 `熟悉后端系统开发常用组件: MySQL/PostgreSQL、Redis、消息队列` + 下一行 `(Kafka/RabbitMQ/RocketMQ)` 被 Provider 拆成 MySQL、PostgreSQL、Redis、Kafka、RabbitMQ、RocketMQ 六个 `skill must_have`，会把一个组合能力要求放大成六个独立 hard gate。Trace 没有本地 repair 合并该 shape，说明是 Provider 原生 capability fan-out；由于该 Run 已有 immutable Continue，运营上立即停止 further resume，不补 Case 5、不进入 Cases 6+，并将该 live shape 固化为 v42.88 红灯。

v42.88 只修上述 backend-component capability fan-out，不做通用 slash-list 或 same-line skill dedupe。新 repair 仅接受 recognized requirements section 中 uniquely grounded 的 live shape：主行明确包含 `熟悉后端系统开发常用组件`、`MySQL/PostgreSQL`、`Redis`、`消息队列`，下一非空行 exact 为 `(Kafka/RabbitMQ/RocketMQ)`，且 Provider 至少已经从这两个 slash group 中 fan-out 出两个 `skill must_have` sibling。命中时删除 MySQL/PostgreSQL、Redis 和 Kafka/RabbitMQ/RocketMQ 对应 hard child，恢复主行本身为单一 `constraint must_have / normalizedCapability=null`；单独的 Redis hard skill、没有该 exact source shape、soft marker、不同 evidence 都不触发。真实红灯 + 单技能防误伤已补；workflow+adapter 255/255 passed，完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 523/523 passed，`git diff --check` 通过，并提交 `cff8d46`。随后 Pro plain/json_schema 双健康 200/200，zero-call readiness 为全新 `attemptedCalls=0 / run_canary / blockers=[]`，唯一 v42.88 Canary `reqacceptrun_e3cc2070f8e64516bc1ad4581dbb5e68` Cases 0–2 3/3 extracted；人工审核未见 blocking hard/soft、type、missing、duplicate 或 cardinality 回归，提交 Continue `reqacceptcanary_8326e7231d614433a96653712ebabbd0`。再次 Pro 双健康 200/200 且 readiness 精确允许同一 Run `resume_run` 后，只追加 bounded Cases 3–5，三例均一次 extracted，Run 累计 attemptedCalls=6，Cases 6+ 未触碰。Case 4 目标未 live-proven：Provider 本次把 6 个 backend component fan-out 都输出为 same-evidence/full-line original，仅 `normalizedCapability` 分别为 MySQL/PostgreSQL/Redis/Kafka/RabbitMQ/RocketMQ；v42.88 只识别 atomic child original，因此 repair 未触发，六个 hard gate 仍全部保留。Trace 明确没有 `recover_backend_component_umbrella`/`drop_backend_component_fanout`，证明是 predicate shape 缺口。由于 Run 已有 immutable Continue，运营上停止 further resume，不进入 Cases 6+，并固化该新 live shape为 v42.89 红灯。

v42.89 只扩展 v42.88 已有 exact backend-component repair 的 child identity，不做任何新的通用 grouping。仍要求同一 uniquely grounded backend-component source shape；除 atomic `MySQL/PostgreSQL` / `Redis` / queue-line child 外，额外接受 `original_text` 等于完整主行或去编号主行、`evidence_span` 为该主行、且 capability 仅属于 `{MySQL, PostgreSQL, Redis, Kafka, RabbitMQ, RocketMQ}` 的 hard fan-out。命中后仍统一删除这些 hard child并恢复单一 `constraint must_have`。新增 v42.88 full-line live 红灯后，workflow+adapter 256/256 passed，完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 524/524 passed，`git diff --check` 通过，并提交 `93cd4ca`。随后 Pro plain/json_schema 双健康 200/200，zero-call readiness 为全新 `attemptedCalls=0 / run_canary / blockers=[]`，唯一 v42.89 Canary `reqacceptrun_e877d2d97bb64df7bad7b06d680fbf71` 在 3-call budget 内因 Case 0 消耗两次 attempt，只产出 Cases 0–1；按门禁未补烧 Provider，先人工审核两例，Case 0 的车端/8 年/教育/Agent 技术栈 hard gate 与显式软项稳定，Harness 的 waiver、hard education、四方向 preferred + hard cardinality、Agent 机制和工程习惯稳定，因此提交 Continue `reqacceptcanary_1cd7cbb1198d460aa1bac0f6b43db55c`，且只授权补齐初始 Canary 的 Case 2。再次 Pro 双健康 200/200 且 readiness 精确返回同一 Run `partial / attemptedCalls=3 / continue / resume_run / blockers=[]` 后，仅执行 `max-new-extractions=1`，Case 2 一次 extracted，Run 累计 attemptedCalls=4；人工审核确认 6 条职责、学历、2 年经验、LLM/Agent 落地经验、Python、`至少一种 Agent 框架` hard cardinality及末条显式 preferred 均稳定。Cases 3+ 本轮未调用。下一轮重新检查 git/Run/Provider/readiness；只有仍明确允许同一 v42.89 Run `resume_run` 时，才考虑 bounded Cases 3–5，并优先验证 Case 4 backend-component fan-out 是否 live-proven 收敛。2026-08-24 13:54 后续推进重新确认 git 起始干净且 HEAD=`bec2f41`，Pro plain/json_schema 双健康均 200，readiness 精确命中同一 v42.89 Run 为 `partial / attemptedCalls=4 / continue / resume_run / blockers=[]`。因此只执行 bounded Cases 3–5：Case 3 一次 extracted；Case 4 在本段 3-call budget 内消耗两次 Provider 调用后以 `HTTP 504` 失败；Case 5 因 provider unavailable 未尝试，Run 累计 `attemptedCalls=7`，Cases 6+ 未触碰。由于 Case 4 没有形成可人工审核 extraction，也没有新 Trace 证据指向 deterministic semantic/coverage defect，本轮不创建 v42.90、不修改业务代码；workflow+adapter 256/256、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 524/524 全部通过。下一轮解除条件是重新取得 Pro 双 200 且 readiness 仍精确允许同一 v42.89 Run `resume_run`；之后优先只补 Case 4/5，Case 4 一旦成功产出就先审核 backend-component fan-out、hard/soft、type、missing、duplicate、cardinality，再决定是否允许任何后续 bounded segment。2026-08-24 15:17 后续推进再次确认 git 起始干净且 HEAD=`33a0993`，数据库中同一 v42.89 Run 仍为 Continue，Cases 0–3 extracted、Case 4 failed/attempt_count=2、Case 5 及 Cases 6+ 未实际调用。临时 Pro plain/json_schema 双健康重新为 200/200，readiness 精确返回 `partial / attemptedCalls=7 / continue / resume_run / blockers=[]`，因此只执行 bounded `max-new-extractions=2` 补 Case 4/5。本次 Case 4 再次消耗两次真实 Provider 调用后以 HTTP 503 失败，Run 累计 `attemptedCalls=9`；Case 5 因 provider unavailable 未尝试，Cases 6+ 仍未触碰。没有形成可人工审核 extraction，也没有新 Trace 证据指向 deterministic semantic/coverage defect，因此继续保持 v42.89、不创建 v42.90。为排除本地回归，workflow+adapter 256/256、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 524/524 全部通过。下一轮仍先重新取得 Pro 双 200 并确认 readiness 精确命中同一 Run；只有 Case 4 成功产出后才审核 v42.89 backend-component fan-out 是否 live-proven，再决定 Case 5 或任何后续 bounded resume。2026-08-24 16:01 后续推进再次确认 git 起始干净且 HEAD=`874b7b1`；临时 Pro plain/json_schema 双健康均为 200/200，readiness 精确返回同一 v42.89 Run `partial / attemptedCalls=9 / continue / resume_run / blockers=[]`。本轮按最小增量只尝试单次 Case 4 retry，但正式 resume 因同一 cohort 的 execution lease 已被另一执行者持有而在 Provider 调用前拒绝，当前 invocation `liveExtractionAttemptsObserved=0`。5 秒后只读 readiness 显示 attemptedCalls 已由 9 增至 10，证明另一个执行者确实推进了同一 Run；数据库随后确认 Case 4 变为 failed/attempt_count=5、`RequirementExtractorUnavailableError`，Case 5 仍 deferred/attempt_count=0，因此本轮没有并发重试、没有触碰 Cases 6+。本地 workflow+adapter 256/256、eligibility+target-cohort 41/41 通过；更宽 Requirement glob 两次均因 DevSpace 上游 504 在结果返回前超时，未形成测试失败证据。该结果仍只指向 Provider/并发执行环境 blocker，不足以创建 v42.90；解除条件仍是 Case 4 成功形成可审核 extraction 后，先人工验证 backend-component fan-out、hard/soft、type、missing、duplicate、cardinality，再决定 Case 5 或任何后续 bounded resume。2026-08-24 16:07 后续再次取得 Pro plain/json_schema 双 200，readiness 精确命中同一 v42.89 Run，Case 4 只授权单次 retry，并在 1 次 Provider 调用后成功 extracted，Run attemptedCalls=11，Case 5 与 Cases 6+ 未触碰。人工审核终于得到新的 deterministic evidence：v42.89 的六组件 full-line fan-out 已消失，但 Provider 改为保留两个独立 hard skill——完整 backend-component 主行被归一成 capability `熟悉后端系统开发常用组件`，紧随其后的 `(Kafka/RabbitMQ/RocketMQ)` 行被归一成 capability `消息队列`；Trace 未命中 backend-component umbrella repair。该形态仍把同一个组合要求拆成额外 hard gate，并让主行落入 generic skill evaluator，因此固化为 v42.90 红灯。

v42.90 只扩展既有 exact backend-component repair 到上述 umbrella + queue-category pair，不做通用跨行 skill merge。仍要求 recognized requirements section 中 uniquely grounded 的同一主行、下一非空行 exact 为 `(Kafka/RabbitMQ/RocketMQ)`；只有一个 full-line `skill must_have / normalizedCapability=熟悉后端系统开发常用组件` 与一个 queue-line `skill must_have / normalizedCapability=消息队列` 同时存在时，才将两者删除并恢复单一 exact-grounded `constraint must_have`。任一 child 单独存在、不同 evidence、soft wording 或 unrelated backend skill 均不触发。真实 live 红灯加入后 backend-component 专项 4/4、workflow+adapter 257/257、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 525/525 passed。后续发现该版本唯一 Canary `reqacceptrun_6c00a5d2d550478ba484cdf221453bf0` 已在 3/3 extracted 后提交 Stop `reqacceptcanary_97a3b36a1ede4fd09379308d4f209c18`：Harness 前端 alternative direction 持久化为 canonical React preferred child 加一个 same-evidence TypeScript preferred child，造成方向内重复计权；Case 4 未到达，因此 backend umbrella+queue 修复尚未 live-proven。为避免基于旧 live output 重复修复，已把该 exact mixed full-line/body shape固化为 deterministic regression；当前 HEAD 会正确收敛为单一 React preferred direction child，workflow+adapter 258/258、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 回归 526/526 passed，说明现有 production repair 对该静态 shape 已具备保护。当前证据不足以安全创建 v42.91 逻辑 patch；下一步应优先对比 Stop Trace/raw Provider item ordering 与 deterministic replay 的差异，只有找到当前 HEAD 可复现的 predicate 缺口后再做新的窄修复。2026-08-24 17:55 后续只读排查补齐了该差异证据：v42.90 Harness Stop Trace 中 React full-line child 命中了 `normalize_alternative_group_child_source_identity`，但同 evidence 的 TypeScript body child 没有命中 source-identity normalization，也没有出现后续 `collapse_alternative_group_child_siblings`，最终因此残留两条 preferred skill；而当前 HEAD 的 exact mixed full-line/body regression 会正常触发 sibling canonicalization 并只保留单一 React preferred child。该 live Run 创建期间存在并发执行/工作树变动历史，因此旧 Trace 与当前已提交 HEAD 的 deterministic replay 不一致，现阶段不能证明当前 production predicate 仍有缺口。重新确认 `deepseek-v4-pro` plain/json_schema 双健康 200/200；v42.90 readiness 明确为 `stopped / attemptedCalls=3 / canaryDecision=stop / nextAction=stopped`，不存在合法 resume 路径。当前 HEAD 专项 regression 1/1、workflow+adapter 258/258、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 526/526 全部通过，`git diff --check` 通过。因此本轮不创建 v42.91、不启动新 live Run；下一轮优先确认是否有新的、基于当前 HEAD 生成的可复现 live evidence，再决定是否继续新的 v42 小 patch。2026-08-24 18:54 再次从干净 HEAD=`501833d` 复核当前状态：数据库最新 Run 仍是 v42.90 `reqacceptrun_6c00a5d2d550478ba484cdf221453bf0` 且 Canary decision=Stop，没有新的 acceptance evidence；临时 `deepseek-v4-pro` plain/json_schema 双健康再次 200/200。精确 mixed full-line/body Harness regression 1/1、workflow+adapter 258/258、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 526/526 再次通过。由于当前 HEAD 仍无法 deterministic replay 旧 Stop 缺口，且 Stop Run 不存在合法 resume，本轮继续不创建 v42.91、不启动新的 Canary；解除条件保持为：只有出现基于当前已提交 HEAD 生成的新 live evidence，并且该 Bad Case 能在 deterministic regression 中稳定复现，才允许进入下一 v42 小 patch。2026-08-24 19:54 自动推进再次从干净 HEAD=`64e54c7` 复核：`deepseek-v4-pro` plain/json_schema 双健康仍为 200/200，readiness 精确返回同一 v42.90 Run `stopped / attemptedCalls=3 / canaryDecision=stop / nextAction=stopped`，不存在合法 resume 或第二个同版本 Canary 路径。当前 HEAD 的 exact Harness mixed full-line/body replay 1/1、workflow+adapter 258/258、完整相关回归 526/526 再次全部通过，且没有新的 acceptance/live evidence。因此继续不创建 v42.91；下一步仍必须等待基于当前已提交 HEAD 新生成、且可 deterministic replay 的实质 Bad Case 证据。2026-08-24 21:00 再次从干净 HEAD=`02bed83` 完成同一门禁复核：Pro plain/json_schema 仍为 200/200，readiness 仍精确返回 v42.90 Run `reqacceptrun_6c00a5d2d550478ba484cdf221453bf0` 为 `stopped / attemptedCalls=3 / canaryDecision=stop / nextAction=stopped`，因此没有合法 resume、也没有启动第二个同版本 Canary。当前 HEAD 的 exact Harness mixed full-line/body replay 1/1、workflow+adapter 258/258、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 526/526 全部通过，`git diff --check` 通过。没有新的 acceptance/live evidence，也没有当前 HEAD 可复现的 predicate 缺口，因此本轮继续不创建 v42.91、不修改 production semantic/coverage 逻辑；解除条件仍是出现基于当前已提交 HEAD 新生成且可 deterministic replay 的实质 Bad Case。2026-08-24 21:58 再次从干净 HEAD=`8b2e78c` 复核同一 replay gate：当前 health CLI 先因旧参数 `--execute-live` 在 Provider 调用前退出，改用仓库现行 `--execute-health-probe --confirm-live-cost` 后 Pro plain/json_schema 均明确为 200/200；readiness 仍精确命中同一 v42.90 Run `reqacceptrun_6c00a5d2d550478ba484cdf221453bf0`，状态保持 `stopped / attemptedCalls=3 / canaryDecision=stop / nextAction=stopped`，不存在合法 resume 或第二个同版本 Canary。当前 HEAD 的 exact Harness mixed full-line/body replay 1/1、workflow+adapter 258/258、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 526/526 再次全部通过。由于没有新的 acceptance/live evidence，且旧 Stop 仍不能在当前 HEAD deterministic replay，本轮继续不创建 v42.91、不修改 production semantic/coverage；下一步门槛仍是基于当前已提交 HEAD 新生成并可稳定 replay 的实质 Bad Case。2026-08-24 23:58 从干净 HEAD=`937a1dd` 再次复核时，数据库仍无新 Run，v42.90 仍为 `stopped / attemptedCalls=3 / canaryDecision=stop / nextAction=stopped`；本次 Pro plain probe 为 200，但 json_schema probe 返回 `503 / SERVICE_BUSY`，因此 live health gate 当前不满足。零成本 readiness 仍精确命中同一 stopped Run，且没有合法 resume。当前 HEAD 的 exact Harness replay 1/1、workflow+adapter 258/258、完整相关回归 526/526 再次全绿，说明没有新的 deterministic production 缺陷证据。因此保持 v42.90、不创建 v42.91、不启动新 Canary；解除条件是 Provider plain/json_schema 双健康重新明确 200/200，并且出现基于当前已提交 HEAD 新生成、可稳定 deterministic replay 的实质 Bad Case。2026-08-25 00:52 再次从干净 HEAD=`30a8d2f` 复核：Pro plain/json_schema 已恢复为 200/200，但 readiness 仍精确命中同一 v42.90 Run `reqacceptrun_6c00a5d2d550478ba484cdf221453bf0`，状态保持 `stopped / attemptedCalls=3 / canaryDecision=stop / nextAction=stopped`，因此不存在合法 resume，也不能启动第二个同版本 Canary。当前 HEAD 的 exact Harness mixed full-line/body replay 1/1、workflow+adapter 258/258、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 526/526 全部通过，`git diff --check` 通过。Provider gate 已恢复，但 replay/evidence gate 仍未解除；在出现基于当前已提交 HEAD 新生成、且可稳定 deterministic replay 的实质 Bad Case 前，继续保持 v42.90 Stop，不创建 v42.91、不修改 production semantic/coverage。2026-08-25 03:56 再次从干净 HEAD=`c691bbd` 复核：数据库仍无新 Requirement acceptance Run/Review，v42.90 仍为 `stopped / attemptedCalls=3 / canaryDecision=stop / nextAction=stopped`；Pro plain/json_schema 双健康再次明确为 200/200。当前 HEAD 的 exact Harness mixed full-line/body replay 1/1、workflow+adapter 258/258、完整相关回归 526/526 再次全部通过。旧 Stop 中的 React + TypeScript duplicate 仍无法在当前已提交 HEAD deterministic replay，且没有基于当前 HEAD 新生成的 live evidence，因此继续保持 v42.90 Stop，不创建 v42.91、不启动新的 Canary；下一步仍只接受“当前 HEAD 新证据 + 可稳定 replay”作为进入下一 v42 小 patch 的解除条件。

2026-08-25 新一轮将该解除条件改为可执行的 evidence-rebuild cohort，而不是继续无限等待历史 Run 自己产生新证据。`requirement-extractor-v42.91` 仅推进 extractor cohort，明确继续使用 `requirement-semantics-v42.90`、Prompt v7、`grounding-v1`、`requirement-coverage-v4` 与现有 retry policy，不新增任何 production semantic repair。目的仅是让新的 immutable Canary Run 与当前稳定提交一一对应，从而重新验证旧 v42.90 Stop 的 Harness duplicate 是否还能在当前代码上真实出现，并在不改语义的前提下争取覆盖 Case 4 backend umbrella+queue 修复。切版前 exact Harness replay 1/1、workflow+adapter 258/258、完整相关回归 531/531 全部通过。只有 Pro plain/json_schema 双 200 且 v42.91 zero-call readiness 明确为全新 `attemptedCalls=0 / run_canary / blockers=[]` 时，才允许该 cohort 唯一一次最多 3-attempt Canary。

v42.91 已从 immutable HEAD `191f84b` 进入全新 Canary `reqacceptrun_0a9bec8a94a0455ba2dcd0eda7ed7b2d`。初始 Cases 0–2 3/3 extracted；Harness 旧 v42.90 Stop 的 React + TypeScript same-evidence duplicate 未再出现，稳定为一个 hard parent + React/Electron/Python/Git 四个 preferred direction child，因此提交 Continue `reqacceptcanary_2412314a37094388832cbadade0725ab`，只授权 bounded Cases 3–5。再次 Pro 双健康 200/200 且 readiness 精确命中同一 Run `partial / attemptedCalls=3 / continue / resume_run / blockers=[]` 后，Cases 3–5 3/3 extracted，Run 累计 attemptedCalls=6。Case 4 证明 v42.90 backend umbrella+queue repair 已 live-proven：Trace 同时命中 `recover_backend_component_umbrella` 与 6 次 `drop_backend_component_fanout`，最终只保留一个 backend-component `constraint must_have`。但人工 duplicate/weighting 审核发现新的 source-proven blocker：原 JD 加分区只有 7 个编号 bullet，Provider 却把第 4 条 `熟悉 vLLM / TGI / Triton Inference Server 等推理引擎` 拆成 3 个同 full-line/same-evidence bonus skill，并把第 5 条 `有 CUDA 编程或模型推理优化经验` 拆成 2 个同 full-line/same-evidence bonus skill，导致 7 个 bonus bullet 持久化成 10 条 bonus Requirements。该重复计权不影响 hard eligibility，但会污染 Match/Gap/bonus ranking，因此运营上停止 v42.91 further resume，不进入 Cases 6+，并固化为 v42.92 红灯。

v42.92 只修上述 explicit bonus-section full-line capability fan-out，不做通用 bonus merge。最终 exact-dedupe 仅在 recognized bonus section 中启用 capability-insensitive identity，并且要求同 type、`bonus` importance、presentation-equivalent full-line `originalText`、同 presentation-equivalent `evidenceSpan`、不同且非空 normalized capability；命中后复用既有 `drop_exact_duplicate_requirement`，保留第一个 canonical child。atomic 不同 original、不同 evidence、不同 type、非 bonus section 均保持原样。真实红灯先失败、防误伤测试先通过；实现后专项 4/4、workflow+adapter 260/260、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 回归 533/533 全部通过。随后唯一 v42.92 Canary `reqacceptrun_d73be8454657412483461d6633174a89` 初始 3/3 extracted，并提交 Stop `reqacceptcanary_c358a19604ce4ac2af5d0bf2d9ffa0a1`：Case 2 的独立 `...者优先` 条目被 Provider 持久化为 `skill bonus`，但现行 v33 business vocabulary 已定义这类 standalone explicit preferred wording 应为 `preferred`；继续保留 bonus 会污染下游 preferred/bonus weighting。Harness 与 Case 0 稳定，Cases 3+ 未执行，因此 v42.92 bonus fan-out 修复本轮未获得 live coverage。

v42.93 只修上述 Provider-native false-bonus importance drift，不做通用 `bonus→preferred`。新规则要求 exact-grounded standalone clause 位于非 explicit bonus section、无 `加分/bonus/nice-to-have` wording、以 `优先/者优先/preferred` 明确收尾，并命中既有 bounded preferred-suffix 或 preferred-alternative grammar；才把 `bonus` 归一为 `preferred`，复用 `explicit_soft_marker_preferred` Trace strategy。显式 bonus section 与同一行 `加分项:` label 仍保持 bonus。宽回归首先抓到全局 bonus-section helper 扩张会误把既有 inline preferred alternative 提升成 bonus，因此最终将 inline label 识别局限在 v42.93 自身的 false-bonus guard，不改变历史 bonus inheritance 路径。另发现 immutable `requirement-extraction-v1.jsonl` 仍把两个 standalone `者优先` case 冻结为 bonus，与 v33 之后 contract 冲突；为保留历史可复现性，不改写 v1，而新增 `requirement-extraction-v2.jsonl`，只把这两条期望更新为 preferred，并让当前 Requirement Eval runner/相关测试使用 v2。专项 preferred/bonus 边界 4/4、workflow+adapter 262/262、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 回归 530/530 全部通过，`git diff --check` 通过，并提交 immutable HEAD `7a015ed`。随后 `deepseek-v4-pro` plain/json_schema 双健康 200/200，zero-call readiness 明确为 `attemptedCalls=0 / run_canary / blockers=[]`；唯一初始 Canary `reqacceptrun_74a90873284e43d8a0051914ef85f67e` 3/3 extracted。按 JD snapshot 做只读审核确认目标 live-proven：Case 2 的 `有MCP协议实践、研发效能/DevOps工具链经验,或熟练使用Cursor、Claude Code等AI工具链者优先` 已持久化为 `preferred` 而非 `bonus`，Case 0 两条 `者优先` 亦保持 preferred；Harness 的软件经验 waiver、hard education、四方向 preferred + hard cardinality 以及 Cases 0–2 的 type/missing/duplicate/cardinality 均未发现新的 blocking 回归。因此提交 Continue `reqacceptcanary_f888a5c54e0945fd8f770c52394fc6de`。2026-08-25 后续重新取得 Pro 双健康 200/200，readiness 精确命中同一 Run `partial / attemptedCalls=3 / continue / resume_run / blockers=[]`，因此只执行 bounded Cases 3–5。Case 3 一次 extracted；Case 4 在剩余预算内两次调用后 HTTP 504；Case 5 因 Provider unavailable 未调用，Run 累计 attemptedCalls=6，Cases 6+ 未触碰。人工审核 Case 3 发现新的 blocking type drift：`具有高度的责任心,并具有较高的抗压能力` 被持久化为 `skill must_have`，而同一 Trace 已把前一抽象能力分句修为 constraint；现有 compound evaluative-trait predicate 因 Provider 给出英文 normalized capability `Responsibility and Stress Management`，要求 capability 必须字面出现在中文原文而失效。这会把抽象人格/抗压约束路由到 skill evaluator，属于当前 HEAD 可 deterministic replay 的真实缺口，因此停止 v42.93 further resume，不进入 Cases 6+。

v42.94 只修上述 compound evaluative-trait 的 capability-literal 偶然依赖，不扩展 trait grammar。`evaluative_trait_compound` 仍要求至少两个 comma segment，且每个 segment 必须完整匹配既有严格 `_ABSTRACT_EVALUATIVE_TRAIT_PATTERN`；唯一变化是取消 `normalizedCapability` 必须字面出现在 source text 的前置条件。真实 live shape（英文 capability + 中文责任心/抗压原文 + full-line evidence）先红灯失败，修复后与既有中文 capability case 一起 2/2 通过；workflow+adapter 263/263、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 回归 531/531 全部通过，`git diff --check` 通过。随后 `deepseek-v4-pro` plain/json_schema 双健康 200/200，zero-call readiness 为全新 `attemptedCalls=0 / run_canary / blockers=[]`，启动唯一初始 Canary `reqacceptrun_b680bf77f4674964b310f4879e3000b0`，Cases 0–2 3/3 extracted。按 JD snapshot 只读审核未发现新的 blocking hard/soft、type、grouping、missing、duplicate 或 cardinality 回归，因此提交 Continue `reqacceptcanary_c21a2811534843bba58222b70bce1b20`。再次取得 Pro 双健康 200/200 且 readiness 精确返回同一 Run `partial / attemptedCalls=3 / continue / resume_run / blockers=[]` 后，只执行 bounded Cases 3–5：Case 3 一次 extracted；Case 4 在剩余预算内两次 Provider 调用后 HTTP 504；Case 5 因 Provider unavailable 未调用，Run 累计 `attemptedCalls=6`，Cases 6+ 未触碰。Case 3 人工审核确认 v42.94 目标 live-proven：`具有高度的责任心` 与 `具有较高的抗压能力` 均持久化为 `constraint must_have`，不再错误路由到 skill evaluator；同一行的沟通/表达/总结/文档制作能力保持独立 constraint，没有同文本 duplicate，`深入了解至少一个大模型体系`、职责、学历与 5 年经验 hard gate 也稳定。当前唯一 blocker 是 Case 4 Provider 504，没有新的 deterministic semantic/coverage defect 证据，因此不创建 v42.95。复验 workflow+adapter 263/263、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 531/531 全部通过。2026-08-25 后续再次推进时，git 起始干净且 HEAD=`b657e10`；重新取得 `deepseek-v4-pro` plain/json_schema 双 200，readiness 精确命中同一 v42.94 Run 为 `partial / attemptedCalls=6 / continue / resume_run / blockers=[]`。按最小安全增量仅计划补 Case 4/5，但正式 resume 在执行前遇到 `RequirementAcceptanceExecutionLeaseUnavailableError`，本执行者没有进入 Provider。随后只读状态显示 attemptedCalls 已由其他执行者推进到 7，Case 4 仍为 `failed / attempt_count=3 / RequirementExtractorUnavailableError`，Case 5 与 Cases 6+ 均未调用，说明当前仅存在并发 execution lease + Provider unavailable blocker，没有新的可审核 extraction 或 deterministic defect 证据。为排除本地回归，本轮 workflow+adapter 263/263、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 531/531 再次通过，`git diff --check` 通过。因此继续保持 v42.94，不创建 v42.95；下一轮解除条件是先确认 execution lease 已释放、Pro 双健康仍 200/200 且 readiness 继续精确允许同一 Run `resume_run`，之后仍只补 Case 4/5，成功产出后立即人工审核，不进入 Cases 6+。2026-08-25 后续再次推进时，git 起始干净且 HEAD=`68d102f`；execution lease 已释放，`deepseek-v4-pro` plain/json_schema 双健康恢复 200/200，readiness 精确命中同一 v42.94 Run 为 `partial / attemptedCalls=8 / continue / resume_run / blockers=[]`。只读状态确认 Case 4 为 failed/attempt_count=4，Case 5 与 Cases 6+ 均未调用，因此按最小安全增量仅授权 `max-new-extractions=2` 补 Case 4/5。正式 resume 成功进入 Provider，但 Case 4 在该预算内新增 2 次真实调用后仍以 HTTP 504 失败，Run 累计 `attemptedCalls=10`；Case 5 因 provider unavailable 未尝试，Cases 6+ 仍未触碰。没有形成可人工审核 extraction，也没有新的 Trace 证据指向 deterministic semantic/coverage defect，因此继续保持 v42.94，不创建 v42.95。为排除本地回归，workflow+adapter 263/263、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 531/531 全部通过。下一轮继续先重新取得 Pro 双 200 并确认 readiness 仍精确允许同一 Run `resume_run`；在 Case 4 成功产出前不补 Case 5、不进入 Cases 6+。2026-08-25 本轮再次从干净 HEAD=`df9b071` 检查最新状态，确认当前仍为 v42.94、Run `reqacceptrun_b680bf77f4674964b310f4879e3000b0` 且 Canary Continue。临时 `deepseek-v4-pro` plain/json_schema 双健康均 200，readiness 精确返回 `partial / attemptedCalls=10 / continue / resume_run / blockers=[]`；因此只授权 `max-new-extractions=1` 单次重试 Case 4，不补 Case 5、不进入 Cases 6+。正式 resume 成功进入 Provider，但该次调用仍以 HTTP 504 失败，Run 累计 `attemptedCalls=11`，Case 5 与 Cases 6+ 均未触碰；没有形成新的可人工审核 extraction，也没有 Trace 证据指向 deterministic semantic/coverage defect，所以继续保持 v42.94，不创建 v42.95。为排除本地回归，本轮 workflow+adapter 263/263、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 531/531 全部通过。下一轮仍先重新取得 Pro 双 200 并确认同一 Run readiness；只有 Case 4 成功产出后才进入只读质量审核，否则继续 fail-closed。2026-08-25 本轮从干净 HEAD=`b4f8bd3` 再次检查，确认版本仍为 v42.94、Run `reqacceptrun_b680bf77f4674964b310f4879e3000b0`、Canary Continue。临时 `deepseek-v4-pro` plain/json_schema 双健康重新达到 200/200，readiness 精确返回 `partial / attemptedCalls=11 / continue / resume_run / blockers=[]`；因此严格只执行 `max-new-extractions=1` 单次重试 Case 4，不补 Case 5、不进入 Cases 6+。本次正式 Provider 调用返回 HTTP 503，Run 累计 `attemptedCalls=12`，Case 4 仍无可审核 extraction；没有新的 Trace 证据指向 deterministic semantic/coverage defect，因此继续保持 v42.94，不创建 v42.95。为排除本地回归，本轮 workflow+adapter 263/263、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 531/531 全部通过，`git diff --check` 通过。下一轮继续先重新取得 Pro 双 200 并确认同一 Run readiness；在 Case 4 成功产出前继续不补 Case 5、不进入 Cases 6+。2026-08-25 本轮从干净 HEAD=`0ef9904` 再次核对运行时最新状态，确认主线仍为 v42.94，Run=`reqacceptrun_b680bf77f4674964b310f4879e3000b0`、Canary Continue；Case 4 已 failed/attempt_count=8，Case 5 与 Cases 6+ 仍未实际调用。临时 `deepseek-v4-pro` plain/json_schema 双健康重新达到 200/200，readiness 精确返回 `partial / attemptedCalls=12 / continue / resume_run / blockers=[]`，因此只授权 `max-new-extractions=1` 单次重试 Case 4。正式 resume 成功进入 Provider，但该次调用仍以 HTTP 504 失败，Run 累计 `attemptedCalls=13`；Case 5 与 Cases 6+ 继续未触碰。没有形成新的可人工审核 extraction，也没有新的 Trace 证据指向 deterministic semantic/coverage defect，因此继续保持 v42.94，不创建 v42.95。为排除本地回归，本轮 workflow+adapter 263/263、完整 `test_job_requirement_* / test_requirement_* / test_eligibility_* / test_target_cohort_*` 回归 531/531 全部通过，`git diff --check` 通过。下一轮解除条件不变：先重新取得 Pro 双 200 并确认同一 Run readiness 仍允许 `resume_run`；只有 Case 4 成功产出后才进入只读质量审核，否则继续 fail-closed。

v42.95 只修 v42.94 Case 4 最终成功产出后暴露的 mixed-importance backend-component residual fan-out，不做通用 preferred dedupe。真实 extraction 已正确恢复完整 `熟 悉 后 端 系 统 开 发 常 用 组 件 : MySQL/PostgreSQL 、 Redis 、 消 息 队 列` 为 `constraint must_have`，但同源 PostgreSQL、RabbitMQ、RocketMQ 仍以 `skill preferred` 残留，造成额外软权重；Trace 同时证明 hard siblings 已触发既有 `recover_backend_component_umbrella` / `drop_backend_component_fanout`。根因是 `_is_backend_component_fanout_child` 只允许删除 `must_have` child，而部分 sibling 在更早的 alternative normalization 后已被软化成 preferred。v42.95 保持 v42.88-v42.90 exact source shape、hard fan-out proof 与 umbrella recovery 条件完全不变，只在 umbrella 已成功恢复后，把同一 bounded capability set（MySQL/PostgreSQL/Redis/Kafka/RabbitMQ/RocketMQ）的 preferred sibling 也视为 redundant fan-out 删除；如果没有 exact umbrella recovery，preferred component skill 完全不受影响。新增 mixed hard/preferred live-shape regression 后 backend-component 专项 5/5、workflow+adapter 264/264、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 回归 532/532 全部通过。随后从 immutable v42.95 HEAD 重新取得 `deepseek-v4-pro` plain/json_schema 双健康 200/200，zero-call readiness 明确为 `attemptedCalls=0 / run_canary / blockers=[]`，启动该版本唯一初始 Canary `reqacceptrun_f03d91a93fc14267acee91ab1f92034e`，Cases 0–2 3/3 extracted。按 JD snapshot 做只读审核未发现新的 blocking hard/soft、type、grouping、missing、duplicate 或 cardinality 回归，因此提交 Continue `reqacceptcanary_929c4cc0867b4f9dab1625b8061f4b70`。再次取得 Pro 双健康 200/200 且 readiness 精确命中同一 Run `partial / attemptedCalls=3 / continue / resume_run / blockers=[]` 后，只执行 bounded Cases 3–5；Case 3 首次真实调用即返回 HTTP 503，Run 累计 `attemptedCalls=4`，Case 4/5 因 provider unavailable 未尝试，Cases 6+ 未触碰。当前没有新的可人工审核 extraction，也没有 Trace 证据指向 deterministic semantic/coverage defect，因此继续保持 v42.95，不创建 v42.96。复验 workflow+adapter 264/264、完整 Requirement/Acceptance/Eval/Review/Eligibility/Target Cohort 532/532 全部通过。下一轮解除条件：重新取得 Pro plain/json_schema 双 200，并确认 readiness 仍精确允许同一 v42.95 Run `resume_run`；之后优先从 Case 3 恢复，不自动扩大到 Cases 6+。

---

# 16. 面试时如何用 3 分钟解释

可以按下面的结构讲：

> 我在 JobLens 里实现过一个 JD Requirement Extraction pipeline。最开始是比较标准的 structured output，让模型提取 type、importance、capability 和 evidence，但真实跑 20 个招聘 JD 后发现，JSON 正确远远不等于业务正确。
>
> 第一类问题是 grounding。模型经常语义不变地改写原文，比如删除一个字、清理异常空格、把半角标点改成全角。我们最后只允许 whitespace 和 ASCII punctuation width 这类可逆、唯一定位的格式恢复，最终持久化仍然写 raw JD slice，任何语义改写继续 fail-closed。
>
> 第二类问题是 Requirement semantics。例如“至少四项中的两项”被拆成四个 must-have，“2 年经验、优秀者可放宽”仍保留 2 年硬门槛，“专业优先”污染学历条件。单靠 Prompt 不稳定，所以后来增加 deterministic semantic guardrail，对 waiver、cardinality、alternative、mixed hard/soft clause 做窄范围、exact-grounded 的修复，并把每次 repair 写入 Trace。
>
> 第三类问题来自下游 evaluator。例如“需要有车端经验”如果标成 Skill，文本看起来没错，但 Eligibility 会走错误 evaluator。所以后期 Eval 不再只看文本，而是看 type/importance 会不会导致 false reject 或 false accept。
>
> Live 侧用了 1～3 个真实 JD Canary、不可变 Continue/Stop、attempt budget、Provider 双健康门禁和 Trace 控制副作用。到 v30 我们又验证了一个边界：Prompt 再强调逐字引用仍不能稳定解决 grounding，所以后续准备把 evidence selection 改成 source-span/候选选择式结构，让 LLM 负责理解、程序负责证明。

---

# 17. 最终总结

从 v1 到 v30，真正的演进可以压缩成一句话：

```text
从“让模型生成结构化答案”
进化成
“让模型提出候选事实，再用程序、Trace、Eval 和人工门禁证明这些事实能安全进入系统”。
```

三个最重要的认知升级：

1. **模型语义正确，不能替代证据正确。**
2. **Prompt 规则，不能替代 deterministic business invariant。**
3. **LLM 输出质量必须按 downstream consequence 判断，而不是只看文本像不像。**

v30 之后，不应该继续以“版本号变大”为目标，而应该减少模型对 evidence text 的自由生成，把 Grounding 从 Prompt contract 升级为结构化 source anchoring contract。

这会让 Requirement Extraction 从一个高质量 LLM Pipeline，进一步变成一个真正可维护、可审计的事实系统。

---

## 18. 关键代码与证据入口

### Workflow

```text
services/backend/app/workflows/job_requirement_extraction.py
```

### Provider Adapter / Prompt

```text
services/backend/app/llm/job_requirement_extractors.py
```

### Grounding / Semantic Guardrail

```text
services/backend/app/application/job_requirements/validation.py
```

### Regression

```text
services/backend/tests/test_job_requirement_workflow.py
services/backend/tests/test_job_requirement_adapters.py
```

### Contract

```text
docs/integration/JOB-REQUIREMENT-EXTRACTION-API-CONTRACT.md
```

### 真实演进时间线

```text
docs/roadmap/ROADMAP.md
```

### 私有 Acceptance / Canary 证据

```text
data/private/requirement-acceptance/session-manifests/
services/backend/data/joblens.db
```

私有 dataset、manifest、SQLite 中的运行事实只作为本地审计证据，不应把敏感数据直接复制到公开文档。
