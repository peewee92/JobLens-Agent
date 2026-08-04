# Collector v1.4.0 真实数据验收与 v1.4.1 修复记录

## 1. 验收输入

同一轮采集生成的两个文件：

- `boss-job-filter-report-v1.4.0-2026-08-04T01-21-38-135Z.json`
- `boss-job-filter-requirement-review-v1.4.0-2026-08-04T01-21-38-135Z.json`

共同 `generatedAt`：`2026-08-04T01:21:38.115Z`。

## 2. 原始验收结果

| 检查项 | 实际结果 | 结论 |
| --- | ---: | --- |
| 完整报告最终岗位 | 85 | 通过 |
| 完整报告候选记录 | 433 | 通过 |
| 详情补采尝试 | 40 | 通过 |
| 最终岗位中详情成功 | 22 | 通过 |
| Requirement 验收文件样本 | 6 / 20 | 阻断 |
| 验收文件状态 | `blocked` | 行为正确 |
| 报告统计 `fullJd` | 18 | 口径错误 |
| 最终岗位实际 `full_jd` | 6 | 与报告统计不一致 |
| 标题重复拼接 | 85 / 85 | 失败 |
| 公司重复拼接 | 85 / 85 | 失败 |
| 地区重复拼接 | 85 / 85 | 失败 |
| 6 条 `full_jd` 中含页面噪声 | 6 / 6 | 严重失败 |

## 3. 根因

### 3.1 卡片字段重复

`getElementText()` 同时拼接同一 DOM 元素的 `innerText` 和 `textContent`。在 BOSS 当前页面中两者内容相同，导致标题、公司和地区全部重复。

### 3.2 JD 选择器策略错误

v1.4.0 遍历多个详情选择器后选择“文本最长”的结果。宽泛选择器 `[class*="job-detail"]` 会覆盖更精确的 `.job-sec-text`，把以下内容一起作为 JD：

- 下载 App 和扫码分享；
- 招聘者及认证信息；
- 竞争力分析；
- BOSS 安全提示；
- 更多职位与精选职位；
- 城市招聘和页脚。

### 3.3 `full_jd` 门禁错误放行

旧门禁允许宽泛选择器只要命中“岗位职责/任职要求”就成为 `full_jd`。页面中虽然包含真实 JD，但同时混有大量非 JD 文本，仍被错误放行。

### 3.4 统计口径混用

- `statistics.totals.fullJd=18` 统计详情补采候选；
- Requirement 验收文件统计最终保留岗位，实际只有 6 条。

两个字段同名但口径不同，导致 UI 和验收判断产生误导。

## 4. v1.4.1 修复

### 4.1 卡片文本去重

- 可见文本只读取 `innerText || textContent` 一次；
- 属性文本按规范化后的值去重；
- 防止标题、公司和地区成对重复。

### 4.2 JD 提取改为质量优先

选择顺序改为：

1. 精确可信节点，如 `.job-sec-text`；
2. 其他职位描述节点；
3. 宽泛详情容器，但必须先裁剪；
4. 整页正文只作为 `body_fallback`，不能成为正式 JD。

宽泛容器会截取：

```text
职位描述 / 岗位描述
→ 真实 JD
→ 认证资质 / 招聘者 / 竞争力分析 / BOSS 安全提示 / 更多职位之前停止
```

### 4.3 新增可追溯字段

- `descriptionSelectorTrust`
- `descriptionSanitized`
- `descriptionStartMarker`
- `descriptionStopMarker`
- `descriptionNoiseCount`
- `descriptionHasContentSignal`

正式 `full_jd` 必须满足：

- 详情页读取成功；
- 长度达到门槛；
- 有职责、要求、编号列表或足够的动作语义；
- 页面噪声计数为 0；
- 来源可信，或宽泛来源已完成 JD 段落裁剪。

### 4.4 统一统计口径

以下字段只统计最终岗位：

- `detailEnriched`
- `fullJd`
- `requirementReviewEligible`

详情补采候选使用独立字段：

- `detailCohortEnriched`
- `detailCohortFullJd`
- `detailCohortRequirementReviewEligible`

## 5. 离线回放结果

对 v1.4.0 完整报告中 22 条“最终岗位且详情成功”的 description 使用 v1.4.1 规则重算：

| 旧质量 | 新质量（离线重算） | 数量 |
| --- | --- | ---: |
| `partial_jd` | `full_jd` | 16 |
| `full_jd` | 清理页面噪声后保持 `full_jd` | 6 |

预计最终可形成 22 条合格 JD，达到 Requirement 正式验收所需的 20 条门槛。

注意：这是对已采集文本的离线规则回放，不等同于浏览器真实重采。v1.4.1 仍需在登录 BOSS 的真实页面重新运行，确认 DOM 选择器和导出结果。

## 6. 自动化验证

v1.4.1 增加或强化以下回归：

- 同一元素的 `innerText/textContent` 不重复；
- 多行 PUA 解码保留 JD 结构；
- 宽泛页面文本可以准确截取 JD；
- 页面安全提示和推荐职位不能进入 `full_jd`；
- 可信 JD 节点优先于更长的整页容器；
- 最终岗位统计与详情候选统计严格分离；
- Collector v1.4.1 可以导入 Backend；
- Collector v1.4.x 非合格 JD 在模型调用和 Trace 创建前阻断。

## 7. 最终浏览器验收标准

重新采集后必须同时满足：

1. `version = 1.4.1`；
2. 标题、公司和地区没有成对重复；
3. `statistics.totals.fullJd == qualityGate.eligibleCount`；
4. `qualityGate.selectedCount = 20`；
5. `qualityGate.status = ready`；
6. 20 条 description 不含 BOSS 安全提示、竞争力分析、推荐职位和页脚；
7. 每条 `descriptionNoiseCount = 0`；
8. 宽泛选择器来源必须 `descriptionSanitized = true`；
9. Backend 导入成功；
10. 20 条岗位可创建同一 cohort 的 Requirement Extraction，进入人工接受/拒绝流程。
