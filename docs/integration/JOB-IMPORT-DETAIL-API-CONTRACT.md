# Job Import Detail API Contract

## Endpoint

```http
GET /api/v1/job-imports/{importId}
```

返回一次已完成导入的审计详情。该接口只读，不重跑导入，也不修改批次。

## Success · 200

```json
{
  "importId": "imp_...",
  "sourceVersion": "1.3.1",
  "collectorVersion": "1.3.1",
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
  ],
  "searchIntentSnapshot": {},
  "sourceSnapshot": {"candidateCount": 0},
  "collectedAt": "2026-07-21T00:00:00Z",
  "createdAt": "2026-08-02T12:00:00Z",
  "items": [
    {
      "inputIndex": 0,
      "outcome": "created",
      "jobId": "job_...",
      "jobSourceId": "src_...",
      "errorCode": null,
      "errorMessage": null
    },
    {
      "inputIndex": 1,
      "outcome": "error",
      "jobId": null,
      "jobSourceId": null,
      "errorCode": "invalid_job_payload",
      "errorMessage": "company: Field required"
    }
  ]
}
```

## Public-data boundary

普通详情可以返回：

- 批次统计；
- SearchIntent / Source Snapshot；
- 每条 input 的 outcome 与关联 Job ID；
- 脱敏后的错误 index/stage/code/message。

不得返回：

- `errors[*].raw`；
- `JobSource.sourceRaw`；
- canonical key；
- normalized source URL；
- SQLAlchemy / SQLite 内部信息。

数据库可为诊断保留原始错误输入，但公开 API 必须仅投影允许字段。

## Ordering

`items` 固定按：

```text
inputIndex ASC
```

保证与 Collector report 原始顺序一致。

## Errors

```text
批次不存在 → 404 job_import_not_found
未知服务端错误 → 500 internal_server_error
```

## Scope exclusions

本切片不实现：

- 批次列表；
- 删除 / 重跑；
- items 分页；
- candidates 完整返回；
- raw payload 管理员接口。
