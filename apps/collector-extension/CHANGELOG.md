# Changelog

## 1.4.3

- 修复 v1.4.2 在 40 个详情名额中只为已通过岗位预留 20 个，导致近重复 JD 出现后无法凑齐 20 条独立正式样本的问题。
- `matched` 模式默认按正式样本数的 1.5 倍预取已通过岗位：40 个详情名额中优先安排 30 个已通过岗位，剩余最多 10 个用于全国远程候选。
- 标题仅空格/标点不同且公司、地区、薪资相同的岗位卡片会延后详情补采，避免明显重复卡片优先消耗名额。
- 完整报告与诊断新增详情目标计划计数，区分已通过岗位、远程候选和被延后的已通过岗位。
- 保持 20 条独立 `full_jd` 的正式门槛不变；不足时仍输出 `blocked`。
- Backend 增加 Collector v1.4.3 导入与 Requirement Extraction 门禁兼容。

## 1.4.2

- 清除可信 JD 节点尾部残留的招聘者姓名、活跃状态、公司和 HR 身份信息。
- Requirement 正式样本新增近重复 JD 去重，避免同一岗位被多个代招链接重复计入 20 条验收。
- 新增 `distinctEligibleCount`、`nearDuplicateCount`、`selectionPolicy` 与 `excludedNearDuplicates` 证据字段。
- `ready` 改为要求 20 条独立完整 JD，而不是只要求 20 条合格岗位记录。
- 详情候选统计改为按唯一职位 URL 计数，保证 `detailCohortEnriched` 不超过实际详情页补采数量。
- Backend 增加 Collector v1.4.2 导入与 Requirement Extraction 门禁兼容。

## 1.4.1

- 修复岗位卡片 `innerText + textContent` 重复拼接，标题、公司和地区不再成对重复。
- 详情采集从“最长文本优先”改为“可信选择器优先 + 整页容器裁剪兜底”。
- 整页容器会截取 `职位描述` 到认证、招聘者、安全提示或推荐职位之前的 JD 段落。
- 增加选择器可信等级、裁剪标记、起止标记与页面噪声计数，错误的整页文本不再标记为 `full_jd`。
- 修复报告统计口径：`fullJd` 和 `requirementReviewEligible` 只统计最终岗位；详情候选使用独立的 `detailCohort*` 字段。
- Backend 增加 Collector v1.4.1 导入和 Requirement Extraction 门禁兼容。

## 1.4.0

- 默认补采筛选通过岗位和远程候选，并为 Requirement 验收预留最多 20 个通过岗位名额。
- 详情 JD 保留换行、编号和职责/要求结构。
- 新增 `descriptionSource`、`descriptionQuality`、`descriptionLength`、`descriptionHash` 和验收资格字段。
- 将详情页读取成功与完整 JD 质量分离；页面正文兜底不能作为正式验收证据。
- 新增 `full_jd / partial_jd / card_only / unavailable` 质量分级和诊断计数。
- 自动导出 `boss-job-filter-requirement-review-v1.4.0-*.json`；只有 20 条完整 JD 时标记 `ready`。
- 完整报告增加 `source/sourceUrl/sourceVersion`，可直接进入 JobLens 1.4.0 导入与抽取门禁。

## 1.3.1

- 产品正式名称由“BOSS AI 岗位整理器”调整为“岗位筛选”。
- AI/大模型仅保留为默认关键词模板和典型使用场景，不再限制插件定位。
- 弹窗、运行页、浏览器标题和插件 Action 标题统一使用“岗位筛选”。
- 导出文件名前缀由 `boss-ai-jobs` 调整为 `boss-job-filter`。
- 内部公共库由 `BossAiLib` 重命名为 `BossJobFilterLib`，测试标记同步去 AI 化。
- 保持 v1.3.0 的多城市、远程、薪资解码、筛选、统计与导出逻辑不变。

## 1.3.0

- 将固定武汉范围升级为多城市搜索，默认仍为武汉。
- 内置中国大陆 31 个省级地区、368 个城市/地区及 BOSS 搜索城市编码。
- 新增接近 BOSS 使用习惯的城市选择器：已选城市、热门城市、省份导航、城市网格和搜索。
- 支持最多同时选择 20 个城市，并实时计算预计搜索组数和最大页数。
- 新增最近城市存储和旧版武汉配置迁移。
- 搜索任务新增 `scopeType`、`cityName`、`provinceName`、`cityCode` 和 `cityOrder`。
- 去重后保留岗位命中的全部城市、省份和城市编码。
- CSV、完整报告、诊断和页面产出统计新增城市维度。
- 岗位地点文本兜底提取不再写死武汉。
- 城市岗位分类逻辑不再判断 `scope === 武汉`，支持任意已选城市。
- 最终排序按照用户城市选择顺序优先，再排列全国远程结果。
- 新增城市数据完整性、任务生成、多城市分类、跨城市去重和排序测试。

## 1.2.1

- 修复重复职位合并时搜索词字符串指数增长造成的 `RangeError: Invalid string length`。
- 搜索词、页码和长文本字段改为有界集合与长度限制。
- 新增重复命中次数、首次命中和最后命中时间。
- 异常时自动导出错误现场 JSON。

## 1.2.0

- 支持 BOSS 私有字体薪资数字解码。
- 新增多来源薪资提取、远程详情补采、岗位分类、技能和完整诊断。
