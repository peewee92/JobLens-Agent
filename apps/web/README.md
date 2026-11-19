# JobLens Web

JobLens 的求职任务工作台。先确认事实和岗位，再比较依据、确认目标、保存材料与执行行动。质量检查页是高级入口，不是普通用户的必经步骤。

首次体验推荐从仓库根目录执行 `python3 scripts/demo.py`，详见[项目入口](../../README.md)。以下是独立启动前后端的开发说明，不会替你迁移真实数据库或授权模型。

## Current routes

```text
/                           工作台与明确下一步
/profile                    确认职业事实和求职意向；简历草稿为可选入口
/import                     粘贴岗位或导入采集报告
/jobs                       岗位列表与筛选
/jobs/{jobId}               原文、要求核对、匹配依据与逐次模型授权
/agent                      选择岗位、比较已有报告、确认目标和恢复运行
/agent/analyze              原范围预检；显式启动缺失或过期报告的规则分析
/agent/results/{threadId}   重开当次保存材料，不以实时计算冒充历史
/applications               已有求职工作区
/applications/{id}          行动、人工状态、事实提案与面试准备
/quality                    高级质量检查入口
```

The browser submits Profile/SearchIntent commands and imports to same-origin Next Route Handlers:

```text
Browser
→ POST /api/profile-proposals or /api/profile-proposals/file
→ review/apply in local form state
→ PUT /api/profile | PUT /api/search-intent | POST /api/job-imports
→ POST /api/profile-evals/{id}/review
→ POST /api/requirement-evals/{id}/review
→ POST /api/jobs/{id}/requirement-extractions
→ FastAPI Workflow / Application Use Cases
```

Server-rendered pages call FastAPI using the server-only `JOBLENS_BACKEND_URL` environment variable. The Backend URL is never exposed as a `NEXT_PUBLIC_*` value.

## Install

From the repository root:

```bash
pnpm --dir apps/web install --frozen-lockfile
```

使用工作区根目录的 `pnpm-lock.yaml`；普通启动不应重新生成依赖锁文件。

## Run locally

Terminal 1:

```bash
cd services/backend
# 先按后端说明确认目标数据库并验证迁移，不对已有真实库自动升级
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```bash
cd apps/web
JOBLENS_BACKEND_URL=http://127.0.0.1:8000 pnpm dev
```

Open:

```text
http://127.0.0.1:3000/
http://127.0.0.1:3000/evals/profile
http://127.0.0.1:3000/evals/requirements
http://127.0.0.1:3000/import
http://127.0.0.1:3000/jobs
```

## 工作台交互

- 顶栏可在「暖纸白＋墨绿」和「燕麦白＋深莓红」之间切换。应用共用按钮、字段、状态标签、分页、读取失败提示和浮层；状态不只靠颜色表达。
- 列表关键词、筛选和页码保留在网址中。快速预览关闭后回到原按钮；从完整详情返回也会定位原条目。比较始终区分本页与跨页选择。导入预览只提示可能的重复，新增或复用以保存回执为准。
- 「我的准备」按简历、面试、行动、经历四类显示；窄屏从列表进入条目，返回保留位置。在材料依据变化后，旧报告和旧准备材料仍可查看，不用旧资料提交新材料。人工投递状态和已存在行动的进度可以单独记录。
- 读取失败可以手动重新读取。提交结果不明确时先核对结果，不自动再次发送；需要模型的操作仍逐次授权。旧版分析、已有历史及未确认草稿不会因此被覆盖。
- 状态地图、样例组件与页面地图只用于离线审稿，不属于应用入口。

### V3 本地验收

用独立 SQLite 库、合成 PDF 与岗位文本，在 360、768、1440 px 实际操作了主流程及相关边界。新库主线：核对资料与意向 → 导入岗位 → 分析并核对要求 → 比较并确认目标 → 创建准备工作区。使用离线确定性样本，不接在线模型；不能据此判断真实模型输出质量。

| 实际操作 | 观察结果 |
| --- | --- |
| 损坏 PDF；无可用分析；重新做可完成的离线分析 | 显示损坏或改后缀提示，保留文件名和粘贴入口。无可用分析不会冒充保存成功；有结果时直接打开刚保存的待核对版本。 |
| 粘贴 20 条长标题岗位，含一条完全重复和一条无公司名 | 预览显示缺项和重复；可以分页核对。保存回执区分 19 条新增与 1 条复用，不把未知公司伪装成已核实。 |
| 岗位列表读取超时、筛选后回退、手机打开原文、进入完整详情后返回 | 超时可以按原关键词重读；放弃筛选草稿前有同层提示；可以回到原页、原位置和触发控件。 |
| 跨页勾选、比较有缺项的岗位 | 跨页数量不因翻页归零；报告区分实际参与和未参与的岗位，不把依据不足解释为用户不具备能力。 |
| 手机操作准备类别和条目；重新分析后打开旧准备材料 | 可用方向键切类别，返回保留位置和未提交输入。已保存的旧简历、面试问题及原始报告仍可读；不再显示旧材料的保存与核对按钮。 |

质量页的放行与过期规则另外由自动化冒烟覆盖。未逐个在三个尺寸审核每条高级详情和所有错误组合，也未使用在线供应商重现付费超时、扣费或授权结果。浏览器截图和试用数据不纳入源码。

## Verification

```bash
cd apps/web
pnpm test
pnpm typecheck
pnpm build
pnpm smoke:e2e
pnpm smoke:eval-review
pnpm smoke:requirement-review
```

`smoke:e2e` creates a temporary SQLite database, migrates it, starts real FastAPI and production Next processes, then verifies:

```text
DOCX upload → extracted text → Profile Proposal
→ explicit Profile + Evidence v1 confirmation
→ SearchIntent v1
→ stale-version 409
→ same-origin import proxy
→ filtered Job Pool
→ Job detail
→ two immutable Requirement Extraction versions
→ latest evidence-grounded Requirements
→ Import audit detail
```

`smoke:eval-review` seeds deterministic test-only Profile Fixture/failed-live/eligible-live runs, then verifies history rendering, failed-case Trace display, Fixture 422, reject 201, accept 201, duplicate 409 and accepted baseline refresh.

`smoke:requirement-review` runs the equivalent Requirement governance path and additionally shows missing Requirement and wrong-importance evidence through real FastAPI and production Next processes.

All smoke scripts clean up processes and temporary data after completion.

## Boundary rules

- Client Components are limited to genuine browser interaction: resume/Collector file input, proposal review, Profile/SearchIntent editing, Eval Review commands and explicit Requirement extraction.
- Job Pool filters live in URL search params.
- Server Components fetch list/detail/audit/Eval governance/latest Requirement data.
- Public Web types do not include `sourceRaw`, `candidateRaw`, `canonicalKey`, `profileKey`, or `intentKey`.
- Profile Proposal never auto-calls the confirmed Profile API; the user must adopt, review and save explicitly.
- Profile Skills reference Evidence through request-local keys; the Backend returns opaque Evidence IDs.
- The Web does not run Requirement providers or reimplement idempotency, transaction, grounding or Eval acceptance policy; Backend responses remain authoritative.

## Out of scope

- OCR, image resumes, encrypted PDF passwords and legacy DOC;
- live-provider Profile or Requirement quality claims without credential-backed Eval runs and human review;
- 自动投递、招聘消息和多 Agent 产品编排；
- authentication;
- favorites and ignore state;
- candidate raw browser;
- design-system or client-cache libraries.
