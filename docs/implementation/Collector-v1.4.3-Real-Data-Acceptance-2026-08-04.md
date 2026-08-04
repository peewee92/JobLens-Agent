# Collector v1.4.3 真实数据验收与 v1.4.4 修复记录

Date: 2026-08-04

## 1. 验收输入

本轮使用同一次真实采集生成的四个文件：

- `boss-job-filter-report-v1.4.3-2026-08-04T06-11-41-847Z.json`
- `boss-job-filter-diagnostics-v1.4.3-2026-08-04T06-11-41-847Z.json`
- `boss-job-filter-requirement-review-v1.4.3-2026-08-04T06-11-41-847Z.json`
- `boss-job-filter-v1.4.3-2026-08-04T06-11-41-847Z.csv`

## 2. v1.4.3 正确通过的部分

### 2.1 详情配额修复生效

```text
detailLimit = 40
detailTargetsPlannedAccepted = 30
detailTargetsPlannedRemoteCandidates = 10
detailTargetsDeferredAccepted = 26
detailAttempted = 40
detailSucceeded = 40
detailFailed = 0
```

说明 v1.4.3 已按预期把 30 个详情名额优先给最终可保留岗位，并保留 10 个全国远程候选名额。

### 2.2 独立样本门禁表面达到 ready

原始导出为：

```text
eligibleCount = 30
distinctEligibleCount = 27
nearDuplicateCount = 3
selectedCount = 20
status = ready
blockers = []
```

3 条近重复均是“大模型工程化部署”代招岗位，与代表岗位的相似度分别为 `0.9471 / 1 / 0.9755`，排除证据正确。

### 2.3 四个文件交叉一致

- Report 最终岗位 76 条；CSV 76 行；URL 集合一致且无重复；
- CSV 的标题、公司、地点、薪资、JD 质量、JD 长度、JD 指纹和验收资格与 Report 一致；
- Review 的 20 条岗位均可按 URL 在 Report 中找到，共享字段一致；
- 20 条 description 的 UTF-16 长度和 FNV-1a 32 指纹均可重算一致；
- 20 条 URL 和 descriptionHash 均唯一；
- 未发现 BOSS 安全提示、竞争力分析、推荐职位、页脚或招聘者活跃信息残留；
- 详情候选统计未超过实际 40 个补采页面。

## 3. 发现的阻断问题

### 3.1 纯公司介绍被误判为 full_jd

正式 20 条样本中包含：

```text
AI 智能体开发工程师
公司：联想利泰
URL：https://www.zhipin.com/job_detail/1577d7e4ffec3a780nJ72Ni6E1ZW.html
```

该 description 共 636 字，但内容全部是：

- 公司成立时间与总部；
- IT 服务业务介绍；
- 服务行业和客户；
- 奥运会、世博会服务经历；
- 公司使命与愿景。

没有岗位职责、任职要求、技能条件或经验门槛，不能作为 `JobRequirement` 的来源证据。

完整 Report 中还有第二条同类误判：

```text
FDE工程师
公司：成都精灵云
URL：https://www.zhipin.com/job_detail/0ecf74f4e5e3f3590nB909u_GFVZ.html
```

其 868 字正文同样只有公司、产品、团队和荣誉介绍。

### 3.2 根因

v1.4.3 的 `hasContentSignal` 满足以下任一条件即成立：

```text
标准职责/要求标题
或存在编号列表
或“负责/开发/设计/熟悉/优先”等动作词达到 3 次
```

公司介绍和荣誉列表也可能：

- 使用编号；
- 多次出现“研发、开发、服务、经验”等泛化词；
- 文本长度超过 180；
- 来自可信 `.job-sec-text` 节点。

因此长度、来源和页面噪声门禁都通过，但正文并不包含可提取的岗位要求。

### 3.3 孤立格式符

`武汉领格卓越教育科技｜AI Agent 开发工程师` 的正文以单独 `】` 开头。它不改变语义，但会污染 evidence span 和人工对照显示。

### 3.4 远程否定短语被误判为正向证据

Report 中 3 条最终岗位被标记为 `remoteStatus=confirmed`。逐条检查详情证据后：

```text
卓里奇｜AI Agent工程师
证据：AI Agent 大模型应用工程师（全国远程）
结论：confirmed 正确

武汉领格卓越教育科技｜AI Agent 开发工程师
证据：不接受居家办公
结论：应为 rejected，原结果错误

多益网络｜AI开发工程师
证据：不接受居家办公
结论：应为 rejected，原结果错误
```

根因是 `REMOTE_POSITIVE` 可命中“居家办公”，而原 `REMOTE_NEGATIVE` 只覆盖“不接受远程”，未覆盖“不接受居家办公”。diagnostics 又使用全部候选口径输出 `remoteConfirmed=5`，而 Report 使用最终岗位口径输出 `remoteConfirmed=3`，同名字段的统计范围也不一致。

## 4. v1.4.4 修复

### 4.1 新增岗位证据内容门禁

`full_jd` 现在必须满足 `descriptionHasRoleEvidenceSignal=true`。

通过方式：

1. 含标准岗位段落标题，例如 `岗位职责 / 工作职责 / 任职要求 / 任职资格 / 岗位要求 / 能力要求 / 硬性要求`；或
2. 无标准标题，但同时出现至少 2 个职责动作证据和至少 2 个任职条件证据；或
3. 存在编号结构，并具有至少 5 个职责动作证据或至少 4 个任职条件证据。

职责动作包括负责、主导、参与、设计、构建、开发、建设、优化、维护、推进、协同、制定、实现、搭建、输出、解决、保障、研究、探索、集成和调研等。

任职条件包括学历、本科/硕士/博士、工作年限、经验、熟悉、精通、掌握、具备、优先、加分项和技术栈等。

纯公司介绍被降级为：

```text
descriptionQuality = partial_jd
requirementReviewEligible = false
requirementReviewIneligibilityReasons = [missing_job_evidence, missing_full_jd]
```

### 4.2 新增可追踪字段

```text
descriptionHasRoleEvidenceSignal
descriptionResponsibilitySignalCount
descriptionRequirementSignalCount
```

字段进入完整 Report、diagnostics、CSV 和 Requirement review dataset contract。

### 4.3 清理开头孤立闭合符

详情正文开头的 `】 / ] / ） / )` 会在 JD 清理阶段移除，不改变后续正文结构。

### 4.4 修复远程否定识别和统计口径

远程检测会先从每个字段中移除明确否定短语，再对剩余文本判断正向或强证据：

```text
不接受居家办公 → rejected
不支持远程办公 → rejected
非全远程，需要到岗 → rejected
不接受全远程，可远程办公两天 → confirmed / medium
全国远程 → confirmed / high
```

这样可以防止否定句内的“居家办公/远程”再次被正向正则命中，同时保留一句话中独立存在的混合办公正向证据。

diagnostics 调整为：

```text
remoteConfirmed = 最终岗位口径
candidateRemoteConfirmed = 全部候选口径
```

## 5. 同一批真实数据按 v1.4.4 规则回放

将 v1.4.3 Report 的 76 条最终岗位重新执行 v1.4.4 质量判断：

```text
原始合格：30 → 28
独立合格：27 → 25
近重复：3
正式选择：20
状态：ready
```

只因 JD 内容门禁排除：

1. `联想利泰｜AI 智能体开发工程师`；
2. `成都精灵云｜FDE工程师`。

远程状态回放：

```text
最终 remoteConfirmed：3 → 1
候选 remoteConfirmed：5 → 3
```

两条“不接受居家办公”岗位改为 `rejected`；卓里奇“全国远程”保留为 `confirmed`，置信度从 medium 提升为 high。

没有误伤：

- 无标准标题但包含完整编号职责和任职条件的 `AI场景挖掘/AI与智能体应用开发`；
- 无标准标题但包含工程职责和资格条件的 4 条“大模型工程化部署”岗位；
- 只有明确任职要求、但仍能提供可验证要求事实的 `Harness工程师`。

剔除错误样本后，第 20 条正式样本由 `亿量科技｜企业级 AI Agent 工程师｜AI CRM 赛道` 补入。

## 6. 验收结论

### Collector 数据门禁

v1.4.3 的详情配额、跨文件一致性、哈希、页面噪声、招聘者尾部和近重复治理通过；岗位证据内容门禁未通过，因此原 v1.4.3 `ready` 不可作为最终正式数据证据。

v1.4.4 修复后，同一批真实数据仍可形成 20 条独立且包含岗位证据的完整 JD，规则回放为 `ready`。

### Requirement Extractor 质量

本记录只批准 Collector 输入数据质量，不代表 Requirement Extractor 模型质量已批准。后续仍需：

```text
导入 20 条 v1.4.4 正式样本
→ 使用同一真实 provider/model/prompt 生成 immutable extraction versions
→ 创建 20-case coherent manual review batch
→ 人工逐条对照 JD、Requirements、evidence spans 和 Trace
→ 记录 accepted/rejected 与 issue codes
```

在 20 条人工判断完成且批次保持 current、coherent、non-fixture 之前，不能把 Requirement 模型标记为 Accepted Baseline，也不能进入 Match。

## 7. 工程验证

```text
Collector 所有 JavaScript 测试通过
scripts/verify.sh 通过
Backend：270 passed
Web：38 passed
TypeScript typecheck 通过
Next.js production build 通过
Alembic：No new upgrade operations detected
git diff --check 通过
v1.4.4 schema/example 版本、岗位证据字段、哈希和计数关键约束检查通过
```

当前 Python 环境未安装 `jsonschema`，因此没有宣称完成 Draft 2020-12 库级验证；已完成 JSON 解析、Schema 关键约束和 Example 与 Collector 实际质量计算结果的一致性检查。
