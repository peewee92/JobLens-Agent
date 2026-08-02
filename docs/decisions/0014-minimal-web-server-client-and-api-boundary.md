# ADR-0014 · Minimal Web 的 Server / Client / API 边界

- **Status:** Accepted
- **Date:** 2026-08-02
- **Related:** ADR-0002、ADR-0006、ADR-0010、P0-1 Job Data Foundation

## Context

P0-1 Backend 已具备导入、Job Pool 查询、Job 详情和 Import 审计能力，但用户只能通过 curl 使用。需要一个最小浏览器闭环，同时避免把 Backend URL、业务规则和原始数据暴露到客户端。

## Decision

初始化 `apps/web` 为 Next.js App Router + TypeScript 应用。

### Server / Client Component

默认页面使用 Server Components：

```text
/jobs
/jobs/{jobId}
/imports/{importId}
```

它们通过 server-only API Client 调用 FastAPI。

只有文件选择与提交使用 Client Component：

```text
/import → ImportForm
```

### Write proxy

浏览器不直接访问 FastAPI。导入通过：

```text
Browser
→ POST /api/job-imports (Next Route Handler)
→ POST /api/v1/job-imports (FastAPI)
```

`JOBLENS_BACKEND_URL` 是 server-only 环境变量，不使用 `NEXT_PUBLIC_*`。

### URL-driven query state

Job Pool 的：

```text
q / city / minSalaryK / remoteStatus / source / sort / limit / offset
```

全部写入 URL search params。刷新、前进后退、复制链接和测试均可复现同一查询。

### Contract boundary

Web 只消费公开 Contract，不定义或展示：

```text
sourceRaw
candidateRaw
canonicalKey
normalizedSourceUrl
errors.raw
```

幂等、事务、created/updated 和审计规则仍完全属于 Backend Use Case。

### Verification

除 TypeScript 与 production build 外，增加跨进程 smoke E2E：

```text
Temporary SQLite
→ Alembic
→ Real FastAPI
→ Production Next
→ Import proxy
→ Job Pool
→ Job detail
→ Import audit
```

## Consequences

### Positive

- 用户第一次可以不使用 curl 完成岗位数据闭环；
- FastAPI 无需增加 CORS；
- Backend 地址不会进入浏览器 Bundle；
- Server Components 减少客户端数据获取和状态样板；
- URL 筛选天然可分享和复现；
- Agent/业务规则仍留在稳定 Use Case。

### Cost / Limits

- Next Server 必须能访问 FastAPI；
- 当前手写 TypeScript Contract，尚未从 OpenAPI 自动生成；
- 没有 JS lockfile，依赖通过 exact versions 固定直接版本，但 transitive dependency 仍可能变化；
- 没有浏览器自动化框架，smoke E2E 通过真实 HTTP 和渲染 HTML验证；
- 当前不是完整产品 Dashboard。
