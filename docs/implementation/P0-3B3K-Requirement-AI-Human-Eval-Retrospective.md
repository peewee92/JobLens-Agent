# P0-3B3K：Requirement AI 抽取 + 人工综合评测复盘

日期：2026-09-03

## 1. 这次评测要解决什么问题

JobLens 的 `JobRequirement` 是后续 Eligibility、Match、Ranking、Target Cohort、Skill Gap、Action Plan 和 Job Preparation 的共同事实基础。

因此，Requirement 抽取不能只满足“模型能输出结构化 JSON”，还必须回答一个更关键的问题：

> AI 从真实 JD 中抽出来的岗位要求，是否已经可靠到可以影响用户的投递优先级和学习计划？

本轮采用“AI 先抽取 + 确定性规则治理 + 人工逐岗位验收 + 批次级最终放行”的方式，而不是直接用模型结果进入 Match / Skill Gap。

---

## 2. 评测链路

完整链路如下：

```text
20 个真实岗位 JD
→ Requirement Provider 结构化抽取
→ deterministic validation / semantic policy
→ current JobRequirement Extraction
→ 统一 Provider / Model / Extractor / Prompt Cohort
→ 创建 20-case Requirement Review Batch
→ 人工逐岗位对照完整 JD 和 Requirements
→ 每个 Case Accept / Reject
→ 汇总结构化问题类型
→ 人工提交批次级 accept_for_match / reject_for_match
→ accepted baseline 才允许进入 Match / Skill Gap
```

本轮正式 Cohort 最终统一为：

- Provider：`openai`
- Model：`deepseek-v4-flash`
- Extractor：`requirement-extractor-v42.95`
- Prompt：`requirement-extraction-v7`
- Semantic Policy：`requirement-semantics-v42.95`
- 样本：20 个真实岗位
- Fixture：0
- Stale Case：0

### 为什么先统一 Cohort

过程中曾出现 16 个 `deepseek-v4-flash` + 4 个 `deepseek-v4-pro` 的混合状态。

如果直接把这 20 条混在一起做正式验收，就无法判断质量差异究竟来自模型、Prompt、Extractor、语义规则，还是岗位本身。

因此正式人工证据要求 20 个 Case 的 Provider / Model / Extractor / Prompt 完全一致。4 个旧模型岗位由用户逐次确认真实 Provider 成本后重新分析，最终达到 20/20 同一 Cohort。

---

## 3. 成本和人工边界

本轮刻意把“机器可以自动完成的动作”和“必须由人决定的动作”分开。

### 可以自动完成

- 读取真实岗位 JD；
- 调用 Requirement Provider 生成结构化 Requirements；
- 保存 Extraction / Trace；
- 检查 current / stale；
- 检查 Cohort 是否一致；
- 聚合人工 Review 的问题类型；
- 计算 20/20 Review 进度；
- 根据最终人工结论决定 Match Release Gate 是否可用。

### 必须由用户本人完成

- 每次真实 Provider 成本授权；
- 每个 Case 的 Accept / Reject；
- Reject 时选择质量问题类型；
- 写人工判断依据；
- 最终批次级 `accept_for_match / reject_for_match`。

自动任务不能代替这些人工决策，也不能因为本机已经配置 API Key 就默认获得费用授权。

---

## 4. 人工 Review 方法

每个岗位按固定顺序检查：

1. 阅读完整 JD；
2. 展开抽取后的 Requirements；
3. 检查是否遗漏明确要求；
4. 检查是否凭空生成 JD 中不存在的要求；
5. 检查 Requirement Type 是否合理；
6. 检查 `must_have / preferred / bonus` 是否符合原文语气和章节；
7. 检查 `normalizedCapability` 是否准确表达原文；
8. 检查 `evidenceSpan` 是否能直接回到 JD 原文；
9. 检查是否存在重复、嵌套、递归拆分或碎片化；
10. 给出不可变的人工 Accept / Reject。

核心不是追求“抽得越多越好”，而是确保每条 Requirement 都能作为后续职业决策的可信事实。

---

## 5. 正式 20-case 结果

批次：`reqreviewbatch_e08cb34fa0444cbba781b50362ddb109`

结果：

- Reviewed：20 / 20
- Accepted：12
- Rejected：8
- Case Accept Rate：60%
- Case Reject Rate：40%
- Stale：0
- Formal Evidence Eligible：true
- Final Decision：`reject_for_match`（用户本人已提交不可变最终结论）
- Match Release Eligible：false

结构化问题统计：

| 问题类型 | 次数 | 含义 |
|---|---:|---|
| `duplicate_requirement` | 6 | 同一原文被重复、嵌套或递归拆成多个 Requirement |
| `wrong_importance` | 4 | 明确的硬要求、优先项或加分项被错误标级 |

同一个 Reject Case 可以同时命中多个问题，因此问题次数可以高于 Reject Case 数。

---

## 6. 20 个岗位逐 Case 复盘

| # | 岗位 | 结果 | 主要结论 |
|---:|---|---|---|
| 1 | AI场景挖掘/AI与智能体应用开发 | Accept | 职责、学历、经验和车端硬条件基本完整，有原文依据 |
| 2 | Harness工程师(Agent外企/薪资好) | Accept | 任职要求覆盖完整，“至少掌握其一”的能力组建模合理 |
| 3 | AI应用开发工程师(Agent方向) | Accept | Python、Agent 框架、MCP 等核心要求覆盖和分档合理 |
| 4 | 泛医疗行业大模型解决方案专家 | Reject | 同一英文能力原句被拆成父项 + 子集，证据完全相同 |
| 5 | 智能体开发工程师 | Reject | 同一句问题分析能力被拆成 3 条近义记录，碎片化严重 |
| 6 | 大模型应用架构师 | Reject | 核心技能整句被拆多条，PyTorch/TensorFlow 明显重复，框架要求存在包含关系 |
| 7 | 大模型应用工程师-双休 | Accept | 主体质量可接受；GitHub ID 投递说明被标必须属于轻微边界问题 |
| 8 | 大模型算法应用工程师 | Accept | 主体质量可接受；同样存在 GitHub ID 投递说明轻微越界 |
| 9 | ai开发工程师 | Accept | 职责、学历、经验、技能覆盖完整，子句拆分基本合理 |
| 10 | 高级ai工程师 | Accept | 4 条职责与任职要求覆盖完整，无明显凭空生成 |
| 11 | 大模型RAG优化工程师 | Accept | 9 条抽取均可回到原文，结构完整 |
| 12 | AI研发工程师 | Reject | Agent/RAG 经验重复；JD 明确“加分项”被标成必须/优先 |
| 13 | 高级开发工程师(AI 平台 / 模型融合方向) | Accept | 30 条覆盖硬性学历、经验、工程、AI 和加分项，层级基本正确 |
| 14 | 大模型应用工程师 | Accept | 与 #7 同源，整体可接受 |
| 15 | AI Agent工程师 | Reject | “扎实后端工程基础”是必须条件，却被标成 preferred |
| 16 | FDE(前沿部署工程师) | Reject | 能力块被递归拆成嵌套子集，同时多项硬要求被降为 preferred |
| 17 | AIAgent 工程师 - AIOS 平台 | Reject | JD 明确【加分项】的完整模块经验、AX 设计被标成 must-have |
| 18 | 交付工程师(FDE) | Accept | 职责、岗位要求和加分项整体分档正确 |
| 19 | 前沿部署工程师(FDE) | Accept | Agent 交付、需求翻译、经验学历等要点基本完整 |
| 20 | AI agent 研发工程师 | Reject | 一句加分项被拆成整句 + MCP + AutoGPT + LlamaIndex 四条，严重碎片化 |

---

## 7. 这次人审真正发现了什么

### 7.1 Grounding（原文可追溯）总体比早期版本稳定

多数 Accept Case 的 Requirement 可以回到真实 JD 原文，说明当前版本已经基本摆脱“凭空编 Requirement”的早期高风险问题。

这也是为什么 12/20 可以接受，而不是整个版本完全不可用。

### 7.2 当前最大问题不是“漏抽”，而是“抽得太碎”

6 个 Case 出现 `duplicate_requirement`，典型形式包括：

- 父句 + 子句同时保留；
- 一句话被递归拆成多个嵌套要求；
- 同一个 evidenceSpan 支撑多个高度重叠 Requirement；
- 一个“掌握 A/B/C”能力组同时保留整句和 A、B、C 子项。

这会直接污染 Match、Ranking、Skill Gap 和 Action Plan，所以不是展示问题，而是核心事实层 P0 质量问题。

### 7.3 Importance 错分会直接把“加分项”变成“淘汰条件”

4 个 Case 出现 `wrong_importance`，典型问题包括：

- JD 明确写“加分项”，模型却标成 `must_have`；
- 任职资格中的硬条件被降成 `preferred`；
- 同一句中的两个并列硬要求得到不同 importance。

这比普通文本分类错误更危险，因为 Eligibility 会把 `must_have` 当硬条件。错误 importance 可能导致用户其实可以投的岗位被 JobLens 错误判成 blocked。

---

## 8. 当前版本是否应该进入 Match / Skill Gap

从当前人工证据看：

- 20 个 Case 中 8 个被人工 Reject；
- Reject Rate = 40%；
- 问题集中在两个会直接影响下游决策的系统性缺陷；
- 不是少数措辞不漂亮，而是重复事实和硬/软条件标级错误。

因此本次复盘的工程建议是：

> **当前 `requirement-extractor-v42.95 / requirement-semantics-v42.95` 已由用户本人最终 `reject_for_match`，不能作为新的 human-accepted Match baseline。下一阶段正式进入基于 8 个 Reject Case 的确定性质量修复。**

该最终结论已经由用户本人提交，系统和自动任务没有代签；Match Release 继续保持关闭，直到未来新 Batch 获得人工 `accept_for_match`。

---

## 9. 下一轮 Requirement 修复优先级

### P0-1：重复 / 递归拆分治理

优先把以下真实 Reject Case 固化成 deterministic regression：

- 泛医疗行业大模型解决方案专家；
- 智能体开发工程师；
- 大模型应用架构师；
- AI研发工程师；
- FDE(前沿部署工程师)；
- AI agent 研发工程师。

修复目标：

- 同一 evidenceSpan 下高度包含的父/子 Requirement 不重复计数；
- 能力组不同时保留“整句总项 + 每个子项”，除非原文明确表达独立硬条件；
- 不使用模糊语义相似度直接删数据，优先使用可解释的 exact span / containment / grouping 规则；
- 每个修复都必须先有真实失败回归，再改规则。

### P0-2：显式 Importance 语义优先

真实 Reject Case：

- AI研发工程师；
- AI Agent工程师；
- FDE(前沿部署工程师)；
- AIAgent 工程师 - AIOS 平台。

修复目标：

- 【加分项】、优先、preferred、bonus 等明确章节/措辞必须高于模型自由判断；
- 任职资格中的明确硬条件不能被无依据降级；
- 同一并列条件组 importance 应保持一致，除非原文明确区分；
- 规则必须保留 evidenceSpan 和版本信息，可回放验证。

### 版本策略

此前 v42.95 被声明为 MVP frozen，只有真实用户可见、可复现的 P0 缺陷才允许解冻。

本次 20-case 人审已经提供了解冻证据：8/20 Reject、6 个重复 Requirement Case、4 个 importance 错分 Case，而且两类问题都会直接改变 Eligibility / Match / Skill Gap。

因此可以合理开启下一版本，但必须保持小步、可回放。本轮已先将 semantic policy 小步推进到 `requirement-semantics-v42.96`，Extractor 仍保持 `requirement-extractor-v42.95`；只有真正修改 Provider 抽取边界时才再决定是否 bump Extractor，不直接跳 v43。

首个 v42.96 slice 已用人工 Reject Case #4 锁定“同一来源行父 constraint + 严格子句重复”：只有同类型、同 importance、无独立 normalized capability、唯一 grounded 来源、且子项从父项明确逗号/分号边界开始时，才删除冗余子项。另有反例确保同一来源行里的两个独立 sibling 不会被误删。第二个 v42.96 slice 继续用人工 Reject Case #5 锁定“同一复合能力句被 3+ normalizedCapability fan-out 后重复计数”：仅当同一 grounded 来源、hard skill、完整原句存在评价性能力/经验结构并带后续“能够/能”动作子句、且至少出现 3 个不同 capability 时，才收敛为一条 hard constraint；明确的三项技术能力并列反例继续保留。第三个 slice 开始处理 Case #6：`熟练使用 PyTorch/TensorFlow。` 在同一原文、同一 evidence 下被分别归一为 PyTorch 与 TensorFlow 两条 hard skill，现在只有括号外 `/` 或 `／` 明确替代关系才会收敛成单一 hard constraint；括号内 `GPT / Llama` capability list 以及普通 `、` 并列技术能力保持不变。第四个 slice 继续关闭同一 Case #6 的 LangChain/LlamaIndex 包含重复：当 `精通 LangChain` 与 `精通 LangChain、LlamaIndex 等大模型应用开发框架` 同属 must-have skill、同一 evidence，且短子项是 umbrella 父项的严格开头成员、父项明确使用 `、…等…框架/工具/技术栈/平台/数据库/模型/语言` 结构时，只保留父项并收敛为 constraint，避免同一框架要求重复计数；普通 `LangChain 和 LlamaIndex` 并列不触发。至此 Case #6 人工指出的两类 duplicate 均有 deterministic regression。随后继续固定 Case #12「AI研发工程师」的真实重复：冻结结果把同一 `有 Agent / 多模态 / RAG 系统实际开发经验` 同时保存为 `experience/must_have` 与 `domain/preferred`。将真实【加分项】章节一起放入离线 replay 后，现有 v42.96 规则组合已经能够正确收敛：显式 bonus section 先把该事实统一为 `bonus`，随后 exact same-source cross-type 去重仅保留 canonical `experience`。因此这一 Case 不再新增第五条业务规则，而是新增正式回归来锁住既有治理组合，避免未来重新出现跨类型重复。随后 Case #16「FDE(前沿部署工程师)」继续提供第六条 duplicate regression：人工 Reject 记录显示同一硬核工程能力块被递归拆成 3 层嵌套子集。v42.96 只在三条记录均为 exact-grounded must-have skill、共享同一唯一 evidence、originalText 构成严格前缀链，且最长父项至少包含两段明确能力连接时收敛成单一 hard constraint；普通三项技术能力并列、只有两层父子关系的结构都不触发。Case #20「AI agent 研发工程师」提供第七条 duplicate regression：正式冻结结果把 `5、加分项:熟悉 MCP 协议、LangChain、AutoGPT、LlamaIndex 等 Agent 开发框架。` 同时保留为整句与 MCP / AutoGPT / LlamaIndex 子 capability。v42.96 仅在同一 evidence、全部为 bonus skill、至少 3 个不同 capability、父项 exact-grounded，且原文明确使用 `等…框架/工具/技术栈/平台/数据库/模型/语言/协议` umbrella 时，收敛为一个 bonus constraint；如果只是普通多项加分技能、没有 umbrella，总体仍保持独立事实。至此已有七条 duplicate regression；全部为零 Provider 调用。duplicate Reject Case 全部获得回归后，P0-2 explicit importance 开始以同样方式逐 Case 固化。首个正式 Case #15「AI Agent工程师」锁定 `扎实后端工程基础`：它位于明确“任职要求”章节且没有任何 `优先/加分/preferred/bonus` 软化措辞，v42.95 冻结输出却为 `preferred`。v42.96 不新增第二套 importance 策略，而是扩展现有 requirement-section 默认硬条件识别，使该唯一 exact-grounded 的 requirement-shaped 条目恢复为 `must_have`；同时用 `扎实的软件工程基础者优先` 反例确保显式软化条件继续保持 `preferred`。第二个 importance slice 固化正式 Case #16「FDE(前沿部署工程师)」：冻结 Extraction 把 `具备在受限网络环境下的独立部署与系统监控能力`、`能与客户业务人员顺畅沟通,也能与内部研发团队无缝对接`、`具备Owner心态`、`具备从“定制化项目”中抽象“标准化产品”的能力` 四项明确位于“任职要求”的无软化资格条件全部标成 `preferred`。零 Provider replay 证明现有 v42.96 `requirement_section_default_must_have` 已能把四项恢复为 `must_have`，并且 `熟悉Dify、Coze等低代码/无代码AI平台,能快速搭建业务原型者优先` 仍保持 `preferred`；因此该 Case 只新增正式 deterministic regression，不增加新的 importance 规则。第三个 importance slice 固化正式 Case #17「AIAgent 工程师 - AIOS 平台」：真实 JD 的 `【加分项】` 下，`有独立负责完整产品模块或独立开发AI产品的经验` 与 `熟悉AX（Agent体验）设计，能设计Agent易理解、易操作的接口与交互流程` 被 Provider 输出为 `must_have`。新增零 Provider 回归后真实失败，根因不是模型自由判断本身，而是 deterministic bonus-section detector 只识别裸 `加分项`，漏掉中文方括号 `【加分项】`；本轮仅补全该显式标题形式，并把后续任意 `【...】` 新章节视为 bonus scope 终点，避免 `【职位亮点】` 等内容错误继承 bonus。修复后两条真实加分项恢复为 `bonus`，任职硬条件和后续章节保持原 importance。以上修复和回归仍为零 Provider 调用，Extractor 继续保持 `requirement-extractor-v42.95`，Semantic Policy 保持 `requirement-semantics-v42.96`。在进入正式 v42.96 live revalidation 前，又补了一条必须的 cohort 复用保护：旧 acceptance 只按 input + provider/model/extractor/prompt 判断现有 Extraction 是否可复用，因此 semantic policy 单独从 v42.95 升到 v42.96 时会错误复用旧结果。新的 deterministic regression 先稳定复现了“新 v42.96 revalidation 仍 0 新抽取、20 条全部复用旧 semantic 结果”；修复后 JobRequirement query 会从不可变 Trace 输出读取 `semanticPolicyVersion`，acceptance 只有在该版本也与当前 target semantic policy 一致时才允许复用。semantic policy 变化因此会生成新的 Extraction，而相同 semantic policy 的重复执行仍保持幂等。该 slice 本身不调用 Provider，也不改变人工 Reject baseline；它只是确保下一次经用户实时授权的 20-case re-extraction 能真正生成 v42.96 新证据，而不是把 v42.95 旧证据换标题后重新送审。随后正式 Review 证据边界也补齐同一语义版本：candidate / Batch Case / Batch summary 会从不可变 Trace 暴露 `semanticPolicyVersion`，Batch 创建禁止混合 semantic policy，Final Decision evidence fingerprint 冻结该版本，accepted baseline 与 current Extraction 的 semantic policy 不一致时 Requirement Release 保持 fail-closed。这样未来人工通过的是完整的 v42.96 cohort，而不是只冻结 extractor/prompt 名称。进一步检查 Acceptance Run 后又发现同一 title/reviewer identity 仍可能命中已经产生 v42.95 Extraction 的旧 Run；旧实现会先生成新的 v42.96 Extraction，最后才因 Run 已绑定旧 Batch 报错，造成不必要副作用。现在 Run 在任何新的 import / Provider / DB 写入前，会先逐个验证已绑定成功 Extraction 的 `semanticPolicyVersion`；只要与当前 target 不一致或旧成功证据无法证明版本，就直接 fail-closed 并要求创建新的 Run identity。相同 semantic policy 的既有 Run 仍可正常幂等续跑，未引入 migration，也没有放宽 Canary / Human Review 门禁。随后进度判定也补齐 semantic cohort：历史 v42.95 Reject Batch 在当前 semantic v42.96 下不再被解释为“继续修规则”，`check_mvp_progress` 会明确返回 `revalidate_requirement_quality`；只有 Reject Batch 与当前 semantic policy 一致时才返回 `remediate_requirement_quality`。在新的 v42.96 Formal Revalidation Run 完成 3/20 Canary 且用户本人提交 `continue` 后，又发现“新 Review Batch 尚未创建”会让进度检查器把 Requirement gate 误判为无数据并退回 UserFeedback。现在进度模型会读取进行中的 Acceptance Run，并用成功 Extraction 的 Trace 证明 semantic cohort；Run `reqacceptrun_bc81e867629a45469969b5f265151abe` 因而保持 `next_priority=resume_requirement_revalidation`，不会绕回 Match/Feedback。随后经用户单独实时授权，Run 推进到 19/20 completed、20 attempted；最后 Case「交付工程师（FDE）」的 Provider Trace 实际包含 7 条完整 responsibility，但 `requirement-coverage-v4` 使用 raw string 比较，JD 中全角中文逗号与 Provider/grounding 后的半角逗号造成 `coveredDutyCount=0` false negative。新增真实结构回归后稳定复现 7 candidates / 0 covered；修复仅复用既有 `_normalize_grounding_text` 做格式等价比较，不放宽语义匹配，回归恢复为 7 candidates / 6 covered（第 7 条受既有 soft-marker 候选规则影响），已高于 minimum=2，因此能关闭该 deterministic blocker。由于最后一次 Provider attempt 已实际发生且失败被持久化，本修复不自动重试；最后 Case 的 live retry 仍需新的实时成本授权，之后才可形成新的 20-case Review Batch。

---

## 10. 下一阶段主线

当前批次已经由用户提交 `reject_for_match`，因此下一阶段实际执行链路是：

```text
20-case 人工证据
→ 8 个 Reject Case 固化为 regression
→ 修 duplicate requirement
→ 修 explicit importance
→ v42.96 offline replay
→ 必要时 bounded Provider re-extraction
→ 新 20-case human review
→ accept_for_match
→ 重新生成 current MatchReport
→ 用户真实 Feedback
→ interested / maybe Target Cohort
→ Skill Gap
→ P0/P1 Action Plan
```

如果用户最终选择 `accept_for_match`，系统会立即放行 current baseline，但基于本轮 40% Reject 的人工证据，不推荐这样做。

---

## 11. 自动推进应该如何工作

JobLens 的自动任务应该自动推进“工程能力”，但不能自动推进“用户判断”。

自动任务每小时应该：

1. 读取 AGENTS.md / README / ROADMAP；
2. 检查 branch、git status、最近提交；
3. 运行 `scripts.check_mvp_progress --json`；
4. 读取 Requirement Review 当前人工门禁；
5. 如果等待人工 Case Review / Final Decision，则明确 HUMAN_GATE，不代签；
6. 同时扫描是否存在可安全推进的 A/B 工程项；
7. 若 Final Decision 为 `reject_for_match` 且该 Review 与当前 semantic policy 相同，优先把人工 Reject Case 固化为 deterministic regression 并修复系统性质量缺陷；若 Review 属于旧 semantic policy、当前代码已进入新版本，则停止继续调规则，进入 `revalidate_requirement_quality` HUMAN_GATE；
8. 若新版本 Final Decision 为 `accept_for_match`，停止 Requirement 调优，回到 MatchReport → UserFeedback → Target Cohort → Skill Gap 主线；
9. 不自动调用真实 Provider，不自动构造 `confirmLiveCost=true`；
10. 每轮只完成一个最小可验证纵向切片，测试通过后本地 commit，不自动 push。

---

## 12. 本轮最大的产品与工程收获

这次评测证明，JobLens 真正需要的不是“更强的模型”，而是一个可信的决策流水线：

> 模型负责高召回地提出结构化候选事实；确定性规则负责守住可解释边界；人工只审真正会影响职业决策的高风险质量；最终 accepted baseline 才进入下游。

人工 Review 的价值也不是给模型打一个抽象分数，而是把失败转成可执行工程信号：

- 6 次 duplicate → 下一轮 dedup / grouping regression；
- 4 次 wrong importance → 下一轮 explicit importance regression；
- 12 个 Accept → 保留已有 grounding / coverage，不进行无目的大改。

这比继续随机调 Prompt 更接近可持续的 Agent / AI 产品工程：**每一次人工判断都应该变成下一轮可回归、可定位、可验证的改进证据。**
