# 岗位筛选 v1.4.2

一个运行在已登录 BOSS 直聘 Chrome 会话中的通用岗位搜索、采集、筛选与导出工具。

产品名称不再限定为“AI 岗位整理器”。**AI/大模型只作为默认关键词模板和功能说明中的一个使用场景**：你可以把关键词替换为前端、产品、实施、交付、解决方案、FDE、销售或任何其他岗位。

插件支持多城市搜索、全国远程识别、BOSS 私有字体薪资解码、薪资与相关度过滤、详情补采、JD 质量分级、去重统计，并导出 CSV、完整报告 JSON、诊断 JSON 与 JobLens Requirement 验收数据集。

## v1.4.2：独立样本与招聘者尾部治理

- 可信 JD 节点也会清除招聘者姓名、活跃状态、公司和 HR 身份尾部；
- 清理后不足 180 字的 JD 会重新降级，不会因招聘者信息凑够长度；
- Requirement 验收样本会按 JD 正文近似度去重，同一职位被不同猎头或公司重复发布时只保留一个代表样本；
- `qualityGate` 新增 `distinctEligibleCount / nearDuplicateCount`，只有 20 条独立完整 JD 才标记为 `ready`；
- 导出新增 `selectionPolicy / excludedNearDuplicates`，记录近重复阈值、被排除岗位及代表岗位；
- `detailCohort*` 改为按唯一职位 URL 计数，避免跨城市/远程搜索范围重复统计；
- Collector 报告版本升级为 `1.4.2`，Backend 同时兼容 `1.3.1 / 1.4.0 / 1.4.1 / 1.4.2`。

## v1.4.1：真实数据验收修复

- 修复卡片 `innerText` 与 `textContent` 重复拼接造成的标题、公司和地区重复；
- JD 选择从“最长文本优先”改为“可信详情节点优先”；
- 宽泛详情容器必须先截取 `职位描述` 到认证、招聘者、安全提示或推荐职位之前的正文；
- 新增 `descriptionSelectorTrust / descriptionSanitized / descriptionStartMarker / descriptionStopMarker / descriptionNoiseCount`；
- 含 BOSS 安全提示、竞争力分析、推荐职位、页脚等页面噪声的内容不能进入 `full_jd`；
- `statistics.totals.fullJd` 与验收文件统一统计最终岗位，详情候选另用 `detailCohort*` 字段；
- Collector 报告版本升级为 `1.4.1`，Backend 同时兼容 `1.3.1 / 1.4.0 / 1.4.1`。

## v1.4.0：JobLens Requirement 验收数据

- 默认详情补采改为“筛选通过岗位 + 远程候选”，并为已通过岗位预留最多 20 个详情名额；
- 保留 JD 的换行、编号和职责/要求结构，便于人工对照 evidenceSpan；
- 将“详情页读取成功”与“完整 JD 可验收”分离；
- 新增 `full_jd / partial_jd / card_only / unavailable` 四级质量标记；
- 页面全文兜底、过短文本和高噪声文本不能进入 Requirement 验收；
- 新增 `descriptionSource / descriptionLength / descriptionHash / requirementReviewEligible` 等可追溯字段；
- 自动导出最多 20 条 `full_jd` 的 Requirement 验收数据集；不足 20 条时明确输出 `blocked`，不使用卡片摘要凑数；
- Collector 报告版本升级为 `1.4.0`，JobLens Backend 同时兼容 `1.3.1` 和 `1.4.0`。

## v1.3.1：产品定位与命名调整

- 插件正式名称从 `BOSS AI 岗位整理器` 改为 `岗位筛选`；
- 弹窗、运行页、浏览器标题和插件标题统一改为 `岗位筛选`；
- AI/大模型保留为默认搜索词模板，但不再作为产品类别限制；
- 导出文件名从 `boss-ai-jobs-*` 改为 `boss-job-filter-*`；
- 内部公共库从 `BossAiLib` 改为 `BossJobFilterLib`；
- 测试开关从 `__BOSS_AI_TEST__` 改为 `__BOSS_JOB_FILTER_TEST__`；
- 原有搜索、城市、薪资、远程、统计和导出逻辑保持不变。

## 默认关键词只是模板

首次安装仍会预填一组 AI/大模型方向关键词，这是为了让插件开箱即可使用，也是一个典型使用场景。你可以全部删除并换成自己的目标岗位，例如：

```text
高级前端开发工程师
前端架构师
Electron 开发工程师
产品经理
解决方案工程师
实施工程师
交付工程师
```

插件不会根据产品名称强制岗位必须包含 `AI`。实际搜索范围完全由“搜索词”输入框中的内容决定。

## 城市选择

- 默认选择武汉；
- 支持中国大陆 31 个省级地区、368 个城市/地区；
- 采用“已选城市 + 热门城市 + 省份导航 + 城市网格 + 城市搜索”的选择方式；
- 支持同时选择最多 20 个城市，插件会分别执行搜索；
- “全国远程”是独立搜索范围，可以与任意城市组合；
- 自动保存最近选择的城市。

> 省份用于组织和查找城市，不代表一次请求覆盖整个省。BOSS 搜索 URL 使用具体城市编码。

## 搜索任务计算

```text
搜索任务数 = 搜索词数量 ×（已选城市数量 + 是否启用全国远程）
最大页面数 = 搜索任务数 × 每个搜索词页数
```

选择过多城市和关键词会显著增加访问次数，插件会实时显示预计任务规模。

## 主要能力

- 任意岗位关键词搜索，不限定 AI 岗位；
- 多城市批量搜索，默认武汉；
- 全国远程卡片识别与详情页确认；
- 解码 BOSS 私有字体薪资；
- 多来源薪资提取和动态数字映射；
- 按薪资阈值、岗位相关度和兼职/实习/助理条件筛选；
- 岗位分类、技能、城市、公司、搜索词贡献等统计；
- 稳定去重并记录重复命中次数；
- 异常时自动导出错误现场 JSON；
- CSV、完整报告 JSON、诊断 JSON 和 Requirement 验收数据集自动下载；
- 完整 JD 质量分级与 20 条正式验收门禁。

## 新版导出文件名

```text
boss-job-filter-v1.4.2-*.csv
boss-job-filter-report-v1.4.2-*.json
boss-job-filter-diagnostics-v1.4.2-*.json
boss-job-filter-requirement-review-v1.4.2-*.json
boss-job-filter-error-v1.4.2-*.json
```

旧版本已经保存的历史运行结果仍然可以通过插件读取和下载，不需要迁移。

## 安装或升级

1. 解压 `boss-job-filter-extension-v1.4.2.zip`。
2. Chrome 打开 `chrome://extensions/`。
3. 开启“开发者模式”。
4. 删除或停用旧版，避免同时存在多个版本。
5. 点击“加载已解压的扩展程序”。
6. 选择解压后的 `boss-job-filter-extension-v1.4.2` 文件夹。
7. 确认插件显示名称为 `岗位筛选`，版本为 `1.4.2`。

## 安全与限制

- 插件不会绕过验证码或安全验证；遇到验证需要人工完成。
- 请控制搜索规模和运行频率。
- BOSS 页面结构可能变化，真实页面选择器和字段仍需在本机登录环境中验证；`body_fallback` 不会被当成正式 JD。
- Requirement 正式人工质量验收需要 20 条独立 `full_jd`；详情页读取成功数、合格岗位记录数和独立 JD 样本数是三个不同指标。
- 插件只读取职位搜索和详情页面，不会自动投递或发送消息。
