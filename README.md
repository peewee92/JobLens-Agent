# JobLens Agent

> 基于真实招聘岗位数据的个人求职与职业转型 Agent。

JobLens Agent 不是一个只会“帮你改简历”的聊天机器人。它把 **个人经历、求职目标与真实岗位市场** 连接起来，帮助用户完成：

```text
职业画像 → 岗位采集 → 岗位匹配 → 能力差距 → 行动计划 → 简历/面试准备 → 再匹配
```

## MVP 目标

第一阶段只打通五个高价值问题：

1. 我当前更适合哪些岗位？
2. 这个具体岗位是否值得我投？
3. 我与目标岗位之间真正缺什么？
4. 下一步最值得补哪些技能和项目证据？
5. 针对具体岗位，我的简历和面试应该怎么准备？

## 项目结构

```text
JobLens-Agent/
├── apps/
│   ├── web/                    # 求职 Agent Web UI
│   └── collector-extension/    # 已有“岗位筛选”Chrome 插件
├── services/
│   ├── api/                    # 用户、岗位、分析结果 API
│   └── agent/                  # Career Agent Runtime 与 Tools
├── packages/
│   └── contracts/              # 核心领域模型与跨端契约
├── docs/
│   ├── product/                # MVP PRD
│   ├── roadmap/                # 实施路线图
│   ├── architecture/           # 系统架构
│   ├── integration/            # Collector 接入协议
│   └── decisions/              # ADR / 关键决策
├── data/samples/               # 示例数据
└── scripts/                    # 开发与验证脚本
```

## 现有资产

`apps/collector-extension` 已包含岗位筛选插件 v1.3.1，当前负责：

- BOSS 岗位搜索与采集
- 多城市与全国远程
- 薪资过滤与 BOSS 字体混淆解码
- 岗位去重
- 详情补采
- 基础技能标签
- CSV / JSON / diagnostics 导出

在新系统中，它被定位为 **Job Collector**，只负责获取真实岗位数据，不承担职业判断与 LLM 分析。

## 推荐技术栈

第一阶段建议：

- Web：Next.js + TypeScript
- API：FastAPI + Pydantic
- Database：SQLite（MVP）→ PostgreSQL
- Agent：Python，自研最小 Agent Runtime 起步，后续可接 OpenAI Agents SDK
- Structured Output：Pydantic / JSON Schema
- Eval：pytest + 固定评测数据集

## 文档入口

- [MVP 产品需求](docs/product/PRD-MVP.md)
- [产品与工程路线图](docs/roadmap/ROADMAP.md)
- [系统架构](docs/architecture/SYSTEM-ARCHITECTURE.md)
- [Collector 接入契约](docs/integration/COLLECTOR-CONTRACT.md)
- [MVP 范围决策](docs/decisions/0001-mvp-scope.md)

## 当前阶段

MVP 主线（Phase 0–6，详见 [路线图](docs/roadmap/ROADMAP.md)）：

```text
Phase 0：仓库与契约基线 ✅
Phase 1：Collector JSON 导入   ← 现在就从这里开始（POST /api/v1/job-imports）
Phase 2：Career Profile
Phase 3：Job Match
Phase 4：Skill Gap
Phase 5：Resume / Interview Pack
Phase 6：Eval + Trace + 闭环验证
```

Phase 7–9（P1/P2：Collector API 同步、个人成长闭环、产品扩展）见路线图。
