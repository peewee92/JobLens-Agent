# 云端个人工作台：隔离迁移和发布检查

## 需求卡

- **对象：** 已有本地求职资料的用户，以及受邀使用线上个人工作台的用户。
- **当前行为：** 本地用 SQLite；线上公开体验用 Render 临时 SQLite，每个访客各有一个合成会话。公开体验仍保持现状。
- **目标行为：** 同一网址的 `/private` 进入受邀个人工作台。已核对的资料、岗位、原始分析与准备记录存到账号专属 PostgreSQL；换会话和后端进程重启不丢失。未登录、未获邀、公开浏览和其他账号均不能读取或修改。
- **不做：** 不自动注册、不接管本地库、不覆盖旧报告、不启用收费模型、不将正式数据导入公开演示。数据库未核验前不发布个人入口。
- **契约：** 前端负责校验托管登录；后端只认来自独立网页服务的短时签名身份，按稳定的账号 ID 选库。浏览器提交的 `actorId`、项目 ID 和查询参数不负责选库。保留既有业务接口和本地 SQLite 入口。

## 发布顺序

1. 先在独立 PostgreSQL 库跑全量 Alembic 迁移和合成数据导入。确认全部入选数据通过逐行校验，目标不为空时拒绝重跑；线上连接必须验证数据库证书与主机名。
2. 用两个测试账号和两套独立数据库验证登录、写入、重新登录和后端重启。运行角色不使用迁移管理员权限：关闭业务库对 `PUBLIC` 的连接权限，每个账号的运行角色只被授予对应库的连接和业务表权限，不给修改迁移版本的权限。验证账号和数据库角色的双层隔离，不把两套账号接到一个业务库。
3. 独立的 FastAPI 使用 `services/backend/Dockerfile.private`，健康检查路径 `/api/v1/health`；运行时设置 `JOBLENS_CLOUD_WORKSPACES`（账号 ID 到 PostgreSQL 直连地址的 JSON 映射）和 `JOBLENS_CLOUD_PROXY_SECRET`。代码和镜像不放连接凭证。不要用新的库替换 `joblens-demo-api` 的临时库。
4. 独立的 Next.js 构建设置 `NEXT_PUBLIC_JOBLENS_PRIVATE_BUILD=1`，以及服务端的 `JOBLENS_CLOUD_FRONTEND_ORIGIN`、`JOBLENS_CLOUD_BACKEND_URL`、`JOBLENS_CLOUD_PROXY_SECRET`、`NEON_AUTH_BASE_URL` 和 `NEON_AUTH_COOKIE_SECRET`。两个应用使用相同的服务间签名密钥，登录 Cookie 签名密钥单独设置。把正式网站域名加到 Neon Auth 可信域名，关闭公开注册。登录 Cookie 只限于 `/private`。
5. 先走受控预览，再为公开网页设置 `JOBLENS_PRIVATE_UPSTREAM_URL`，仅让 `/private` 转发到独立私有前端。确认 `/`、未登录页面、两位测试用户读写、退出登录和旧链接，然后才开启正式入口。失败先撤去入口的转发配置，不删除或回滚业务数据。
6. 只在用户确认具体源文件、账号已经开通且归属可核验、账号工作库为空时，导入个人记录。原 SQLite 只读，继续保留，不切换本地配置。确认远端数据只从该账号可访问，再告知用户结果。

## 第一次登录

由维护者在 Neon Auth 创建一个受邀账号，不设临时密码，不开放注册。私有网页通过服务端变量 `JOBLENS_CLOUD_CODE_EMAILS` 允许受邀邮箱使用一次性验证码；其他邮箱不会触发发信，界面不会公开谁受邀。账号在 Neon 中核实邮箱之前，不得读写其工作台。库仍按账号的固定 ID 分配，不按邮箱选库。邮件由 [Neon Auth](https://neon.com/docs/auth/guides/plugins/email-otp) 发送，用户只在个人工作台输入验证码，不发到聊天或维护者手里。如果共享邮件服务送达不稳定，保留登录失败状态，不启用公开注册来绕过。

## 迁移工具

在 `services/backend` 下执行。默认只自动创建只读临时快照，打印分表数量，不连接目标，不输出记录内容：

```bash
uv sync --extra cloud
uv run --extra cloud python -m scripts.migrate_private_workspace --source /绝对路径/已确认的本地库.db
```

确认目标库已初始化且为空后，通过操作系统或部署平台的安全方式把管理员直连地址放入 `JOBLENS_MIGRATION_DATABASE_URL`（不要写进命令或提交），然后显式指定目标：

```bash
uv run --extra cloud python -m scripts.migrate_private_workspace \
  --source /绝对路径/已确认的本地库.db --apply --expected-database joblens_private
```

保留业务表及关联；不复制模型授权、评估库、原始调用输入、输出或错误。导入使用一个事务，内容不符会回滚；迁移管理员不作为应用运行账号。

## 双账号复测

在验收域名上运行 `node apps/web/scripts/smoke-private-workspace.mjs`。由操作系统提供 `JOBLENS_CLOUD_SMOKE_ORIGIN` 和 `JOBLENS_CLOUD_SMOKE_ACCOUNTS`（两组纯合成账号的受限文件，不提交），重启私有后端后加 `--after-restart`。它检查未登录和跨来源提交、两个账号不能读到对方岗位、能保存自己的资料和岗位、退出后不能访问、重新登录和后端重启后数据仍在，以及同一会话中的公开演示不会展示个人记录。

还没挂正式域名时，私有前端预览可以加 `--private-only` 验证账号隔离；这一模式跳过演示测试，不能替代同域名整体验收。验收脚本会测试未受邀地址不能建立会话，不会向真实邮箱发验证码。

当前通过：独立的本地生产构建连接 **实际 Neon 免费库与托管登录**，用两组纯合成账号完成上述检查；旧有本地 SQLite 网页冒烟也通过。Computer Use 实测从公开演示进入个人工作台、错误密码可重试、返回公开演示。生产 `/private` 和迁移真实资料仍有各自的验收门，不能用这些结果代替。

## 可复现决策和失败记录

- **决策：** 公开与个人工作台分构建、分后端，再用网址的 `/private` 归并，不用浏览器里一个全站开关决定写到哪个数据库。已有本地 SQLite 接口保留。
- **实测故障：** 初次连接中，本机二进制 `libpq` 的 `sslrootcert=system` 没找到可用的证书链；用 `certifi` 提供的公共根证书集，仍严格验证证书与主机名。已用合成数据实际迁往云端并读回。
- **面试表述：** 先保住公开访问和本地数据，再在隔离的托管库验证迁移；用服务端会话、按账号选库和数据库权限分别验证边界，而不是把 SQLite 换成网络地址就对外开放。
