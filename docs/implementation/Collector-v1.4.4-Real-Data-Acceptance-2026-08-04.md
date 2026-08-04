# Collector v1.4.4 真实数据验收与 v1.4.5 修复记录

Date: 2026-08-04
Status: v1.4.4 Requirement 输入通过；完整 Collector 数据因远程假阳性不通过，已修复为 v1.4.5

## 1. 验收输入

同一采集批次包含：

- `boss-job-filter-requirement-review-v1.4.4-2026-08-04T07-28-40-611Z.json`
- `boss-job-filter-diagnostics-v1.4.4-2026-08-04T07-28-40-611Z.json`
- `boss-job-filter-report-v1.4.4-2026-08-04T07-28-40-611Z.json`
- `boss-job-filter-v1.4.4-2026-08-04T07-28-40-611Z.csv`

验收覆盖版本、契约、20 条正式 JD、长度与 FNV-1a 指纹、近重复、Report/Diagnostics/CSV 对账、远程三态、正文噪声、岗位证据和字符编码。

## 2. 通过项

### Requirement 数据门禁

```text
eligibleCount = 31
distinctEligibleCount = 29
nearDuplicateCount = 2
selectedCount = 20
qualityGate.status = ready
blockers = []
```

两条近重复均为“大模型工程化部署”，相似度为 `0.9471` 和 `1.0`。20 条正式样本全部满足：详情成功、`full_jd`、岗位证据为 true、页面噪声为 0、验收资格为 true、阻断原因为空、版本为 1.4.4。实际正文长度和 FNV 指纹均与字段一致，每条 URL 都能在完整 Report 中找到且字段相同。

v1.4.4 的岗位证据门禁生效：上一批纯公司介绍不再进入正式样本；成都精灵云 FDE 本次抓到真实岗位定位、职责和要求。

### 四个导出一致

```text
Report jobs = 79
CSV rows = 79
Report candidates = 419
Diagnostics uniqueCardsBeforeFilter = 419
rawCards = 1138
duplicateRawHits = 719
1138 - 719 = 419
```

CSV 中岗位、公司、JD 质量、长度、指纹、岗位证据、职责/要求计数、噪声、验收资格和远程状态均与 Report 一致。

### 详情采集

```text
detailAttempted = 40
detailSucceeded = 40
detailFailed = 0
detailCohortFullJd = 38
detailCohortPartialJd = 2
```

30 个已通过岗位 + 10 个远程候选的配额策略有效，能够稳定选满 20 条独立 JD。

## 3. 阻断问题

### 3.1 远程识别存在 3 个最终岗位假阳性

1. `AI Agent工程师｜卓里奇`
   - 当前标题和 JD 没有远程办公；
   - 整页 `detailText` 底部推荐岗位出现“AI Agent 大模型应用工程师（全国远程）”；
   - 推荐职位污染当前岗位。

2. `交付工程师（FDE）｜某大型智能硬件上市公司`
   - JD 是“客户现场或远程支持”；
   - 这是客户支持方式，不是员工远程办公。

3. `AI Agent 架构师｜道通科技`
   - JD 是“后台数据研判、远程监测”；
   - 这是产品能力，不是工作地点。

v1.4.4 显示：

```text
candidateRemoteConfirmed = 5
final remoteConfirmed = 3
```

按 v1.4.5 规则回放应为：

```text
candidateRemoteConfirmed = 2
final remoteConfirmed = 0
```

剩余两条候选的标题明确写有“兼职远程”和“全远程”，但分别因兼职过滤和薪资阈值未进入最终结果。

### 3.2 JD 编码噪声

真实数据中发现：

- `description` 有 142 个康熙部首/CJK 兼容字或零宽空格；
- `detailText` 有 162 个；
- 其中零宽空格 26 个；
- 示例：`⼯程能⼒ / ⽀持 / ⾼并发 / ⽤户` 看起来正常，但编码不同。

这会影响技能匹配、evidence span、正文哈希和近重复判断。

## 4. v1.4.5 修复

### 受边界约束的远程证据

`detectRemote` 不再读取整页 `detailText`，只使用：

```text
title / area / tags / rawText / 已裁剪 description
```

推荐岗位、页脚和全站文本不能再污染当前职位。

### 区分远程办公和远程业务语义

以下不再自动视为远程办公：

```text
远程支持 / 远程监测 / 远程控制 / 远程运维
远程诊断 / 远程设备 / 远程系统 / 远程服务
```

以下继续有效：

```text
全国远程 / 全远程 / 纯远程 / 兼职远程
可远程 / 支持远程 / 接受远程
远程办公 / 远程工作 / 居家办公 / 工作地点不限
```

“不接受居家办公”保持 rejected；“不接受全远程，可远程办公两天”保持 confirmed/medium。

### JD 字符规范化

`clean` 和 `cleanMultiline` 统一：

- 康熙部首和 CJK 兼容字映射为普通汉字；
- 移除 `U+200B / U+2060 / U+FEFF`；
- 不全局改变普通中文全角标点；
- Backend 仍保留原始 `source_raw`，规范化正文是带版本的可复现派生数据。

## 5. 同批数据回放

正文规范化后，Requirement 结果保持：

```text
eligible = 31
distinct = 29
near duplicates = 2
selected = 20
status = ready
```

远程结果修正为：

```text
candidate confirmed = 2
final confirmed = 0
```

## 6. 批准边界

- v1.4.4 Requirement 输入数据：通过；
- v1.4.4 全量岗位事实：远程字段不通过；
- v1.4.5 修复实现：自动化测试通过，等待一次真实浏览器重采做文件级确认；
- Requirement Extractor 模型质量：未因此自动通过，仍需 20 条同 cohort Extraction 的人工接受/拒绝。
