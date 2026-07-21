# JobLens Agent MVP 产品需求文档

- 状态：Draft v0.1
- 目标版本：MVP
- 产品定位：基于真实岗位市场数据的个人求职与职业转型 Agent

## 1. 背景与问题

现有求职 AI 工具大多停留在三个孤立场景：简历润色、岗位推荐、模拟面试。它们普遍缺少一个关键闭环：**用户的真实能力与真实招聘市场之间没有持续连接**。

用户真正面对的问题不是“帮我生成一份更漂亮的简历”，而是：

- 我现在到底适合什么岗位？
- 我感兴趣的岗位，市场真实要求是什么？
- 我与目标岗位的差距在哪里？
- 哪些差距最值得优先补？
- 学完或完成项目后，如何形成可写进简历的证据？
- 对一个具体岗位，我应该怎么改简历和准备面试？

JobLens 已有的岗位筛选浏览器插件解决了“真实岗位从哪里来”的问题。JobLens Agent 在此基础上解决“这些岗位对我意味着什么、我下一步应该做什么”的问题。

---

## 2. 产品目标

### 2.1 MVP 核心目标

打通以下最短闭环：

```text
用户简历/经历
→ Career Profile
→ 真实岗位池
→ 岗位匹配
→ 目标方向能力差距
→ 个性化行动建议
→ 单岗位简历/面试准备
```

### 2.2 MVP 成功标准

一个用户能够在一次完整流程中：

1. 导入自己的简历或结构化经历；
2. 导入 JobLens Collector 采集的岗位 JSON；
3. 查看适合自己的岗位及可解释匹配理由；
4. 选择一个目标岗位方向；
5. 看到基于真实岗位要求统计出的能力差距；
6. 获得最多 3 个 P0 行动建议；
7. 选择某一岗位生成定制的简历修改建议和面试准备清单。

---

## 3. 目标用户

### Persona A：经验型工程师转 AI

- 有 5–10 年传统软件工程经验；
- 想转 AI 应用、Agent、AI 全栈等岗位；
- 不知道已有经验哪些可迁移；
- 容易陷入“什么都要学”的焦虑。

### Persona B：目标岗位明确的转型者

- 已知道要转 Agent Engineer / AI Application Engineer 等方向；
- 需要用真实岗位反推技能、项目、简历和面试准备。

### Persona C：正在主动求职的人

- 每周收集大量岗位；
- 需要快速判断哪些值得投；
- 希望减少逐条读 JD 和手工定制简历的成本。

---

## 4. 核心价值主张

### 4.1 基于真实岗位，而不是泛泛职业建议

系统的技能建议必须回答：

> 为什么建议我学这个？哪些我真正想投的岗位要求它？

### 4.2 基于证据，而不是模型拍脑袋

“用户会某个技能”应尽量关联到经历、项目和结果证据；“岗位要求某能力”应关联到具体 JD 文本。

### 4.3 从差距到行动，再回到匹配

最终闭环：

```text
发现 Gap
→ 创建 Action
→ 完成学习/项目
→ 添加 Evidence
→ 更新 Profile
→ Re-match
```

MVP 先实现到 Action Plan，保留 Evidence 回写接口和数据模型。

---

## 5. MVP 功能范围

## 5.1 Career Profile｜我的职业画像

### 输入

MVP 支持：

- 简历文本/PDF 解析后的文本；
- 用户手动补充项目和职业偏好；
- 用户明确选择的目标岗位类型。

### 输出

结构化 `UserProfile`：

- 基础工作年限；
- 技能；
- 项目；
- 行业与业务领域；
- 可迁移优势；
- 职业偏好；
- Evidence 列表。

### 关键要求

禁止只保存“React：熟练”这种不可验证标签。技能尽量绑定证据：

```text
React
├── 8 年经验
├── 项目 A
└── 复杂业务结果
```

---

## 5.2 Job Pool｜我的岗位池

### 数据来源

MVP：

```text
JobLens Collector JSON
→ 手动上传/导入
→ JobLens Agent API
```

P1 再改成浏览器插件直接 POST API。

### 能力

- 导入 report JSON；
- 保留原始岗位字段；
- 标准化薪资、城市、远程、技能、JD；
- 基于 URL + 公司 + 标题去重；
- 查询、筛选、收藏、忽略。

---

## 5.3 Job Match｜岗位匹配

每个岗位生成可解释的 `MatchReport`。

### 匹配维度

1. 硬性条件；
2. 核心技能；
3. 相关项目经验；
4. 工作年限/领域；
5. 用户偏好；
6. 转型可迁移能力。

### 输出

- 综合匹配分；
- 推荐等级；
- 已匹配能力；
- 部分匹配；
- 明显差距；
- 用户证据；
- JD 证据；
- 推荐动作。

### 原则

分数必须可解释。禁止只输出一个 `87%`。

---

## 5.4 Job Target & Market Gap｜目标方向与能力差距

用户可以：

- 选择一个预设方向；
- 由 Agent 根据岗位池建议方向；
- 选择若干收藏岗位组成自定义目标岗位集。

系统从目标岗位集统计：

- 技能出现频率；
- 关键技术组合；
- 经验要求；
- 学历要求；
- 薪资区间；
- 高频职责关键词。

结合 UserProfile 生成 Skill Gap：

```text
能力
市场需求强度
当前覆盖程度
证据充分度
优先级
建议行动
```

### MVP 行动建议限制

只生成：

- 最多 3 个 P0；
- 最多 5 个 P1。

避免生成“大而全 50 项学习清单”。

---

## 5.5 Job Preparation｜单岗位求职准备

针对某个具体岗位生成最小 Job Pack：

### MVP 只包含

1. 简历调整建议；
2. 项目经历排序与讲法；
3. 面试准备清单。

### 不在 MVP

- 自动改完整简历 PDF；
- 自动投递；
- 自动和招聘者聊天；
- 语音模拟面试。

---

## 6. 核心用户流程

### Flow A：从“我是谁”到“哪些岗位适合我”

```text
导入简历
→ Profile Extraction
→ 用户确认/修正画像
→ 导入岗位
→ 批量 Match
→ 按推荐等级查看岗位
```

### Flow B：从目标岗位反推学习路线

```text
选择岗位方向或收藏岗位集
→ Market Requirement Aggregation
→ Profile Comparison
→ Skill Gap
→ P0/P1 Action Plan
```

### Flow C：准备一个具体岗位

```text
打开岗位
→ 查看 Match Report
→ 点击“为这个岗位准备”
→ Resume Advice
→ Project Story
→ Interview Checklist
```

---

## 7. Agent 设计

MVP 使用 **单 Career Agent + Tools**，不使用 Multi-Agent。

### Tools

- `get_user_profile`
- `list_jobs`
- `get_job`
- `get_job_target`
- `analyze_job_requirements`
- `match_job`
- `aggregate_market_requirements`
- `analyze_skill_gap`
- `generate_resume_advice`
- `generate_interview_pack`

### Agent 不负责

- 直接写数据库；
- 修改原始采集数据；
- 自动申请岗位；
- 绕过确定性业务规则。

---

## 8. 核心数据模型

MVP 以五个模型为主：

```text
UserProfile
Job
JobTarget
MatchReport
SkillGap
```

并辅以：

```text
Evidence
ActionItem
JobPreparationPack
```

JSON Schema 位于：`packages/contracts/schemas/`。

---

## 9. 非功能需求

### 可解释

所有关键职业判断必须尽量带 `evidence`。

### 可追踪

记录：

- 模型版本；
- Prompt/Agent 版本；
- 输入 Profile 版本；
- Job 数据版本；
- 输出 Artifact。

### 可评估

至少建立：

- 10 条 Profile Extraction 测试；
- 20 条 Job Match 测试；
- 10 条 Skill Gap 测试。

### 隐私

简历和个人经历默认本地存储；未经用户操作，不对外分享。

---

## 10. 明确不做

MVP 不做：

- 自动投递；
- 自动 Boss 打招呼；
- 多平台爬虫；
- Multi-Agent；
- 长期自治求职；
- Offer 决策；
- 社交关系拓展；
- 复杂课程平台；
- 云原生基础设施。

---

## 11. MVP 验收清单

### Profile

- [ ] 用户可导入一份简历文本并得到结构化画像
- [ ] 用户可以修改错误的技能和经历
- [ ] 核心技能至少关联一个 Evidence 或明确标记“缺少证据”

### Jobs

- [ ] 可导入 Collector v1.3.1 report JSON
- [ ] 可查看最终岗位与候选岗位
- [ ] 重复导入不会产生大量重复岗位

### Match

- [ ] 可批量匹配至少 50 个岗位
- [ ] 每个匹配报告都有理由和证据
- [ ] 可按匹配等级排序

### Gap

- [ ] 可基于目标岗位集聚合技能需求
- [ ] 可生成 P0/P1 差距
- [ ] 每项 P0 可以追溯到对应岗位需求

### Prepare

- [ ] 可针对具体岗位生成简历调整建议
- [ ] 可生成项目讲述重点
- [ ] 可生成岗位相关面试准备清单
