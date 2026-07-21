# JobLens Agent 路线图

## 总目标

用最小工程成本打通：

```text
Collector → Profile → Match → Gap → Prepare → Eval
```

路线图强调先形成可验证闭环，再增加自动化和平台规模。

---

# Phase 0｜基线与契约（已建立）

目标：让项目有清晰边界和可直接开发的契约。

### 交付

- [x] 新建 JobLens-Agent 仓库
- [x] 集成现有 Collector 插件源码
- [x] MVP PRD
- [x] 系统架构
- [x] Collector 导入契约
- [x] 五个核心领域模型 Schema
- [x] 本地 Git 初始化

### 完成标准

Codex/开发者进入仓库后，可以直接回答：

- 系统解决什么问题；
- MVP 不做什么；
- Collector 与 Agent 如何分工；
- 第一批 API 和数据模型是什么。

---

# Phase 1｜岗位数据接入（P0）

建议周期：2–3 天

目标：不依赖手工 CSV 分析，把已有 Collector 的 JSON 正式导入系统。

### 任务

1. FastAPI 基础服务；
2. SQLite 数据库；
3. `POST /api/v1/job-imports`；
4. 解析 Collector report：
   - `jobs`
   - `candidates`
   - `statistics`
   - `config`
5. Job 标准化与去重；
6. Job Pool 查询接口；
7. 保存 `source_raw`，避免数据不可追溯。

### 验收

- 同一 JSON 重复导入两次，Job 数量基本不增加；
- 可以按城市、薪资、关键词查看岗位；
- 可以打开原始 BOSS URL。

---

# Phase 2｜Career Profile（P0）

建议周期：3–5 天

目标：建立后续所有匹配判断的个人事实底座。

### 任务

1. 简历文本输入；
2. LLM Structured Output → UserProfile；
3. Evidence 抽取；
4. 用户确认/修正；
5. Profile Version；
6. 职业偏好：
   - 目标城市
   - 远程
   - 最低薪资
   - 感兴趣岗位
   - 不接受条件

### 验收

Profile 页面可以明确区分：

- 我真的做过；
- 我了解但缺少项目证据；
- 我完全没有。

---

# Phase 3｜岗位匹配（P0，核心）

建议周期：5–7 天

目标：让用户真正知道“哪些岗位值得投、为什么”。

### 任务

1. JD Requirement Extraction；
2. 确定性硬条件判断；
3. LLM 语义匹配；
4. MatchReport Structured Output；
5. Evidence Linking；
6. 批量匹配队列；
7. 匹配列表 UI；
8. Strong / Good / Stretch / Low 四级推荐。

### 推荐评分结构

```text
硬条件             20
核心技能           30
相关项目           20
领域/经验           10
可迁移能力          10
个人偏好            10
```

分值只是排序辅助；实际展示以 evidence-based reason 为主。

### 验收

至少选 20 个真实岗位人工评审：

- Top 5 是否大体合理；
- 推荐理由是否能引用真实经历；
- 不匹配原因是否能引用 JD。

---

# Phase 4｜目标岗位与 Skill Gap（P0）

建议周期：4–6 天

目标：把岗位池变成用户自己的学习路线，而不是通用课程。

### 任务

1. 创建 JobTarget；
2. 从收藏岗位创建自定义 Target；
3. 聚合技能频率；
4. 归一化同义技能；
5. 市场要求 vs Profile；
6. 生成 SkillGap；
7. 生成 P0/P1 Action Plan；
8. 每项建议关联支持岗位。

### 验收

用户点击任一 Gap，可以看到：

```text
为什么重要
哪些岗位要求
我当前有什么证据
具体缺什么
做到什么算补齐
```

---

# Phase 5｜Job Preparation Pack（P0）

建议周期：3–5 天

目标：让分析直接服务于投递和面试。

### MVP 交付

- 简历修改建议；
- 项目排序建议；
- STAR/项目讲述重点；
- 预计面试问题；
- 面试前补习清单。

### 验收

所有建议只能使用 UserProfile 中已存在的事实，不得虚构项目和成绩。

---

# Phase 6｜Eval + Trace（P0）

建议周期：3–5 天

目标：让这个项目成为真正的 Agent Engineering 作品，而不是 Prompt Demo。

### Eval

- Profile Extraction 数据集；
- Requirement Extraction 数据集；
- Job Match 人工基准集；
- Skill Gap 基准集。

### Trace

至少记录：

```text
run_id
agent_version
model
input_refs
tool_calls
structured_output
latency
token_usage
error
```

### 门禁

- Structured Output parse success ≥ 98%；
- 不得生成 Profile 中不存在的项目事实；
- MatchReport 必须有 evidence；
- Gap P0 必须至少被目标岗位集中的真实要求支持。

---

# Phase 7｜Collector API 同步（P1）

目标：从“下载 JSON → 上传”升级为一键同步。

### 任务

- 插件设置 JobLens Agent API 地址；
- API Token；
- “同步到我的岗位池”；
- 增量导入；
- 同步结果反馈。

注意：保留 JSON 下载能力作为离线和故障兜底。

---

# Phase 8｜个人成长闭环（P1）

目标：实现真正的 `Gap → Action → Evidence → Re-match`。

### 任务

- ActionItem 状态；
- 学习/项目 Evidence 录入；
- Profile 更新；
- 匹配度变化；
- “补完这个能力后影响了哪些岗位”对比。

---

# Phase 9｜产品扩展（P2）

只在 MVP 有真实使用价值后考虑：

- 其他招聘平台 Collector；
- GitHub 项目解析；
- 多份简历版本管理；
- 定时岗位更新；
- 新岗位提醒；
- 面试记录与复盘；
- Offer 比较。

---

# 当前最推荐的开发顺序

```text
1. Collector JSON Import
2. UserProfile
3. 单岗位 Match
4. 批量 Match
5. JobTarget
6. SkillGap
7. Job Preparation Pack
8. Eval
9. Collector API Sync
```

不要先做漂亮 Dashboard，也不要先做 Multi-Agent。
