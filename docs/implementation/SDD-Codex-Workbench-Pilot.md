# JobLens：SDD + Codex 工作台试点

> 创建于 2026-10-16。本文件只配置工作流程，不修改业务代码、不改变 vNext 1.3 MCP 完成状态。

## 试点决定

- **主要编码工具**：本机已检测 Codex CLI 0.142.5。
- **规范工具**：推荐 OpenSpec（尚未安装），不与 Spec Kit 混装。
- **现有核心事实**：根目录 `AGENTS.md`；`packages/contracts`；`docs/decisions/`；`docs/implementation/`；`.github/workflows/ci.yml`；后端 eval 与测试。
- **当前分支**：`codex/vnext13-mcp-stdio`。已有未跟踪文档 `docs/implementation/P1-JobLens-MCP-Transport-Layer-Development-Plan.md`、`docs/interview-labs.md`，不得覆盖／删除。
- **主线约束**：vNext 1.3 当前验收证据已经足以进行人工收尾判断。不得为保持 AI 自动运行而反复制造门禁任务或直接扩展 vNext 2.0。

## 日常采用的三个模式

| 模式 | 适用范围 | 执行要求 |
| --- | --- | --- |
| 快速修复 | 可复现的小 bug、样式、文案 | 现状 → 失败复现 → 最小修复 → 相关测试 |
| 规范迭代 | 功能切片、跨模块行为变化 | Existing spec/contract → 变更规范 → 评审 → 实现 → 证据 → 同步规范 |
| 重要变更 | 权限、状态恢复、MCP 公共接口、数据库、Agent Runtime | 先冻结契约，评审错误边界、兼容、权限、回滚，再实施与集成 |

## 本地安装步骤（待执行）

在确认未跟踪文件均得到保护后，由用户在 Mac 终端执行：

```bash
npm install -g @fission-ai/openspec@latest
cd /Users/willpeng/project/JobLens-Agent
git status --short
openspec init --tools codex
openspec list
```

初始化后预期由 OpenSpec 生成 `openspec/`、`.agents/skills/openspec-*/SKILL.md`。**不要手工伪造** OpenSpec 的内部规范文件或覆盖其自动管理的 Skill。

在 Codex 对话中（不是终端）按需输入：

- `$openspec-explore`：读代码和契约、思考需求；不做实现。
- `$openspec-propose`：规范、设计和任务草案。
- 人工审查边界与验收。
- `$openspec-apply-change`：实现最小切片并跑针对性测试。
- 独立审查真实 diff、回归和用户可观察行为。
- `$openspec-sync-specs`、`$openspec-archive-change`：通过验收后更新权威规范并归档。

不依赖 OpenSpec 的日常执行提示词：

> 请读取 AGENTS.md、当前 git 状态、已有 contracts/ADR、相关代码和测试；先判断这是快速修复、规范迭代还是重要变更。仅提议一个能推进 JobLens 核心业务的最小切片，定义可观察验收标准、不做事项、异常场景、目标文件、测试命令与停止条件。未经我确认不改公共契约、不调用收费 Provider、不提交或推送。确认后实施、真实验证并报告证据和风险。避免陷入不断增加测试案例而不推进主需求的循环。

## 面向 JobLens 的第一批真实候选需求

下述**仅作为候选**，不等同于未实现；真正开始前须核对最新代码、现有 issue 与 vNext 计划：

1. 从真实用户的「岗位选择 → 排名解释」挑选一个用户可观察的体验缺口，先确认是否已经实现。
2. 从「投递工作台 → 简历和面试准备」挑选一个已有 workflow 到 UI 的端到端缺口。
3. 面试展示需求：若数据和权限均允许，使用纯合成 fixture 打通 3 分钟演示与失败回放；不新增未经核实的生产能力。

## JobLens 验证门禁（分层，不要每次都全量）

- 最小切片：相关 FastAPI 测试 / 组件测试 / 静态检查。
- 修改 MCP 接口：SDK discovery、工具调用、拒绝路径、敏感字段投影、STDIO 回归。
- 修改 Agent 决策：现有 eval + 路由回归；不能用「模型说成功」替代事实。
- 修改共享 Contract：Schema 校验、消费者适配、关键 E2E；需要其他 owner 明确确认。
- 合并前：根据影响范围执行必要的更全面测试及 `git diff --check`。
- 真实 Provider 调用、推送、合并和发布一律单独审批。

## 试点成功标准（两周内统计，非虚构结果）

比较三个中型需求：
- 实际通过用户验收的功能数（目标：至少 2 个）；
- 每个需求重复返工次数；
- 首次验证失败能否通过代码/trace 定位；
- SDD 规范维护耗时占比（如明显超过 25% 且无返工收益，简化流程）；
- 开发者能否独立解释一次契约、失败、重试、权限或成本取舍。

个人学习卡放在私人学习仓库；公司专有内容不得进入公开个人项目。
