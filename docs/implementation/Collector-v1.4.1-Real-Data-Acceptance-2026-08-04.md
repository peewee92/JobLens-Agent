# Collector v1.4.1 真实数据验收与 v1.4.2 修复记录

## 1. 验收输入

本次使用同一轮真实 BOSS 登录会话导出的两个文件：

- `boss-job-filter-report-v1.4.1-2026-08-04T03-00-14-756Z.json`
- `boss-job-filter-requirement-review-v1.4.1-2026-08-04T03-00-14-756Z.json`

两份文件的 `version`、`generatedAt` 和配置一致。

## 2. v1.4.1 已通过项

### 2.1 卡片字段去重通过

最终 77 条岗位的标题、公司和地区未再出现 `innerText + textContent` 成对重复。

### 2.2 报告与验收文件一致

- 完整报告最终岗位：77
- 最终岗位详情成功：24
- 最终岗位 `full_jd`：24
- 最终岗位 Requirement 合格：24
- 验收文件 `eligibleCount`：24
- 验收文件 `selectedCount`：20
- 验收文件状态：`ready`

验收文件中的 20 条岗位均能在完整报告中按 URL 找到，所有共享字段一致。

### 2.3 JD 主体页面噪声治理通过

20 条已选 description 中未发现：

- BOSS 安全提示
- 竞争力分析
- 更多职位 / 精选职位
- 城市招聘 / 页脚
- 页面更新时间

所有入选记录均满足：

- `descriptionQuality=full_jd`
- `requirementReviewEligible=true`
- `descriptionNoiseCount=0`
- `descriptionLength` 与真实字符串长度一致
- `descriptionHash` 与 FNV-1a 32 位重算一致
- URL 唯一

## 3. v1.4.1 未通过项

### 3.1 可信选择器仍残留招聘者资料尾部

一条“大模型应用开发工程师”JD 的 description 尾部包含：

- 招聘者称呼
- `2月内活跃`
- 公司名
- `HR`

原 description 长度为 188。去掉招聘者资料后只剩 169 字，低于正式 `full_jd` 的 180 字门槛。

因此该岗位在 v1.4.1 中被错误标记为 `full_jd`，应降级为 `partial_jd`。

根因：

- `.job-sec-text` 被标记为 trusted；
- 原裁剪只覆盖固定的 `刚刚活跃 / 今日活跃 / 本周活跃 / 近两周活跃 / 本月活跃`；
- 未覆盖 `2月内活跃`；
- trusted selector 仍可能包含招聘者资料，不能完全跳过尾部治理。

### 3.2 20 条样本包含同一 JD 的近重复发布

完整报告中有 4 条“大模型工程化部署”岗位，来自不同公司或代招来源，但 JD 主体几乎相同。

按 NFKC 归一化、仅保留字母数字后计算字符 5-gram Jaccard，相似度为：

- 0.9471
- 0.9704
- 0.9755
- 1.0000

v1.4.1 的 20 条样本中包含其中 3 条，导致样本数量虽然达到 20，但有效独立案例不足 20。

Requirement Extractor 人工质量验收需要独立输入，否则同一份 JD 会重复影响错误率、证据跨度和 Requirement 数量统计。

### 3.3 详情候选统计超过 detailLimit

配置：

```text
detailLimit = 40
```

报告统计：

```text
detailCohortEnriched = 41
```

实际成功详情页 URL 为 40 个。同一职位 URL 同时存在于武汉搜索范围和全国远程搜索范围，候选数组中出现两次，统计按候选行计数而不是按详情页 URL 计数。

该问题不代表插件访问了 41 个详情页，但会让统计违反配置上限并误导验收。

## 4. v1.4.2 修复

### 4.1 招聘者尾部裁剪

新增招聘者资料尾部识别：

```text
姓名/称呼
刚刚、今日、本周、近两周、本月或 N 月内活跃
公司 / 身份信息
```

命中后：

- 截断招聘者资料；
- `descriptionSanitized=true`；
- `descriptionStopMarker=recruiter_profile`；
- 使用清理后的正文重新计算长度、哈希、噪声和质量等级。

若未被裁剪，质量检查也会把该结构计为页面噪声，防止 trusted selector 绕过门禁。

### 4.2 Requirement 独立样本选择

新增 JD 近重复识别：

```text
normalize = NFKC + lowercase + alphanumeric only
features = character 5-grams
similarity = Jaccard
near duplicate threshold = 0.82
```

质量门禁新增：

- `distinctEligibleCount`
- `nearDuplicateCount`
- `selectionPolicy`
- `excludedNearDuplicates`

`ready` 条件从“20 条合格岗位记录”调整为“20 条独立完整 JD”。

### 4.3 详情候选按唯一 URL 统计

`detailCohortEnriched / FullJd / RequirementReviewEligible` 改为按 `sourceUrl / url` 去重后统计，保证统计值与真实详情页补采数量一致。

## 5. 同一批真实数据的 v1.4.2 规则回放

对 v1.4.1 的 24 条合格岗位重新计算：

1. 招聘者尾部岗位清理后从 188 字降为 169 字，转为 `partial_jd`；
2. 剩余原始合格岗位：23；
3. 4 条大模型工程化部署近重复岗位保留 1 条，排除 3 条；
4. 独立合格岗位：20；
5. 正式选择：20；
6. 预期状态：`ready`。

预期 v1.4.2 质量门禁：

```json
{
  "requiredSampleSize": 20,
  "eligibleCount": 23,
  "distinctEligibleCount": 20,
  "nearDuplicateCount": 3,
  "selectedCount": 20,
  "status": "ready",
  "blockers": []
}
```

详情统计预期：

```text
detailCohortEnriched = 40
```

## 6. 回归覆盖

新增或强化测试：

- `N月内活跃` 招聘者尾部裁剪；
- 未裁剪招聘者资料不能成为 `full_jd`；
- 近重复 JD 不重复进入正式 20 条样本；
- 阻断原因使用 `insufficient_distinct_full_jd_jobs`；
- 被排除近重复岗位包含代表 URL 与相似度；
- 跨搜索范围的同 URL 详情只统计一次；
- Collector v1.4.1 与 v1.4.2 均可导入 Backend；
- 所有 Collector 1.4.x 均执行 Requirement Extraction 输入门禁。

## 7. 最终浏览器复验条件

重新加载 v1.4.2 后，同类搜索至少验证：

1. `version=1.4.2`；
2. `detailCohortEnriched <= detailLimit`；
3. 招聘者姓名、活跃状态、公司和 HR 身份不出现在 description；
4. `eligibleCount >= distinctEligibleCount`；
5. `nearDuplicateCount` 与 `excludedNearDuplicates.length` 一致；
6. `ready` 时 `distinctEligibleCount >= 20` 且 `selectedCount=20`；
7. 20 条正式样本两两相似度均低于阈值；
8. description 的长度、哈希、噪声和来源证据全部一致。
