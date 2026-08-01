# ADR-0003：数据库策略

## 状态

Accepted

## 决策

- **MVP：SQLite**。开发、本地运行、演示、评测全部基于单个 SQLite 文件；
- **Production / P1：PostgreSQL**。规模、并发或部署需要时切换到 PostgreSQL；
- 切换**只换 SQLAlchemy engine**，领域模型与 Repository 接口不变；
- 迁移统一由 Alembic 管理，SQLite 与 PostgreSQL 共用同一套迁移脚本（注意避开数据库专有类型）。

## 约束

- 不在 MVP 阶段引入 Redis / 消息队列 / 向量数据库等额外存储；
- 语义匹配在 MVP 用 LLM + 确定性检索即可，不提前上向量库；
- `sourceRaw` 等原始数据原样保留，不因“已结构化”而丢弃。

## 原因

- SQLite 让开发者零配置即可本地跑通闭环，符合“先形成可验证闭环”的路线图基调；
- 用 SQLAlchemy 抽象后，后期切换 PostgreSQL 成本极低；
- 过早引入多存储只会增加运维与一致性负担，且当前数据量远未到瓶颈。

## 影响

- `SYSTEM-ARCHITECTURE.md` §9 表结构同时适用于 MVP 与 P1；
- 部署文档需在 P1 补 PostgreSQL 连接配置，但代码改动限于 engine 初始化。
