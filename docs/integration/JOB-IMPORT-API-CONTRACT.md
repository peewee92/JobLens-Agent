# Job Import HTTP API Contract

> P0-1 Slice 6：把已稳定的 `ImportJobsUseCase` 暴露为 HTTP 能力。HTTP 层只负责协议转换、依赖组装和错误映射，不重新实现导入业务。

## 1. Endpoint

```http
POST /api/v1/job-imports
Content-Type: application/json
```

请求体直接接收 Collector report JSON。HTTP 层只要求顶层是 JSON Object；每条 Job 的结构校验仍由 Collector Adapter 逐条完成，以保留“单条错误不影响整批”的业务规则。

## 2. Success

成功创建一次导入批次时返回：

```http
201 Created
```

```json
{
  "importId": "imp_...",
  "sourceVersion": "1.3.1",
  "received": 2,
  "created": 1,
  "updated": 0,
  "skipped": 1,
  "errors": [
    {
      "index": 1,
      "stage": "adapter",
      "code": "invalid_job_payload",
      "message": "company: Field required"
    }
  ]
}
```

只要批次成功提交，即使存在可隔离的单条错误，仍返回 201；这些条目通过 `skipped` 和 `errors` 表达。

## 3. Error Contract

错误响应统一为：

```json
{
  "error": {
    "code": "unsupported_collector_version",
    "message": "unsupported Collector version: 9.9.9"
  }
}
```

状态码映射：

| 场景 | HTTP | code |
| --- | --- | --- |
| 请求不是合法 JSON Object / 缺少 Body | 422 | `request_validation_error` |
| Collector report envelope 无效 | 422 | `invalid_collector_report` |
| Collector version 不支持 | 422 | `unsupported_collector_version` |
| Job / JobSource 持久化身份冲突 | 409 | `import_identity_conflict` |
| 未知服务端错误 | 500 | `internal_server_error` |

未知错误只返回通用消息，不向客户端泄露数据库、堆栈或本地路径。

## 4. Boundary Rules

```text
Router
├── 接收 JSON Object
├── 注入 ImportJobsUseCase
├── 调用 execute()
└── 将 Application Result 序列化为 HTTP Response

ImportJobsUseCase
├── Adapter / Normalizer
├── created / updated / skipped
├── 批次统计
└── Unit of Work commit / rollback
```

禁止 Router：

- 创建 Session；
- 调用 Repository；
- 查询 canonical key；
- 决定 created / updated；
- 调用 commit / rollback。

## 5. Current Non-goals

本接口当前不包含：

- `multipart/form-data` 文件上传；
- HTTP `Idempotency-Key`；
- 并发冲突自动重试；
- 用户鉴权；
- Job Pool 查询；
- Web 上传页面。
