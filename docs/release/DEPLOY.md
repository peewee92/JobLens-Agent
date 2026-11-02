# 免费公开演示部署

Render 免费后端与 Vercel 网页均已发布；入口为 https://joblens-agent.vercel.app/demo ，线上完整路径与网络边界见验收记录。当前证据见 [交付状态](STATUS.md)。主方案：Vercel Hobby + Render Free + 临时 SQLite。

## 1. 发布前检查

- 不要执行 `git add .`：当前工作区有大量既有改动，须逐项检查与选择；真实数据库、备份、密钥和原始私人资料不得提交。
- 确保新增演示代码、迁移、锁文件、截图和相关文档进入同一待发布版本。视频单独上传 GitHub Release，公开前检查脱敏；不要把本机视频路径作为公开成果。
- 从该提交全新克隆，执行根 README 的安装与本地演示；检查网页测试、类型、构建和后端测试。未提交工作区不能称为“干净克隆已通过”。

## 2. Render 后端

注册／登录由维护者完成，选择免费方案；若平台要求升级或账户验证无法完成，停止，不创建付费资源。

- 使用仓库根目录 `render.yaml` 创建 Blueprint，或者手工创建 Docker Web Service。
- Dockerfile：`services/backend/Dockerfile.demo`，构建上下文：仓库根目录。
- `JOBLENS_DEMO_PROXY_SECRET`：至少 32 字符的随机密钥，仅保存在两侧平台的服务端设置；Blueprint 可自动生成。不要贴到聊天、公开日志或 NEXT_PUBLIC 配置。
- `JOBLENS_DEMO_FRONTEND_ORIGIN`：Vercel 的固定生产来源，例如 `https://你的项目.vercel.app`，无末尾斜线。
- 保持一个进程。入口必须是 `app.demo.public_main:app`，禁止把普通本地入口 `app.main:app` 直接公开。
- 不上传 `.env`、数据库或模型密钥。不配置持久磁盘、数据库付费实例和自动升级。
- `/api/v1/health` 是公开健康检查。启动时迁移并初始化合成模板，失败则退出；只有完成后才进入服务状态。

本地等价检查（不会触碰真实库）：

```bash
cd services/backend
JOBLENS_DEMO_PROXY_SECRET=替换为至少32字符的本地测试随机值 \
JOBLENS_DEMO_FRONTEND_ORIGIN=http://localhost:3100 \
.venv/bin/python -m uvicorn app.demo.public_main:app --host 127.0.0.1 --port 8100 --workers 1 --no-access-log
```

如 Docker 引擎可用，可从仓库根目录构建：

```bash
docker build -f services/backend/Dockerfile.demo -t joblens-demo:local .
```

## 3. Vercel 网页

创建个人 Hobby 项目，根目录选 `apps/web`；连接同一仓库与已审核的发布分支。设置以下**服务端**环境变量：

| 配置 | 值 |
| --- | --- |
| `JOBLENS_PUBLIC_DEMO` | `1` |
| `JOBLENS_BACKEND_URL` | Render 的 HTTPS 服务地址，无尾斜线 |
| `JOBLENS_DEMO_PROXY_SECRET` | 与 Render 相同 |
| `JOBLENS_DEMO_FRONTEND_ORIGIN` | Vercel 固定生产来源，与 Render 相同 |
| `JOBLENS_RELEASE_VERSION` | 审核后的版本号或提交标识 |

先创建 Vercel 项目取得固定生产域名，再配置 Render 来源；最后补齐网页后端地址并重新部署。预览分支域名不自动加入允许来源。

公开页为 `/demo`；点击开始后才创建临时样本库。Cookie 在生产环境为 Secure、HttpOnly、SameSite=Lax，令牌不返回浏览器脚本。后端需代理凭证；更换凭证时两侧同时更新。

Vercel 路由时限配置为 60 秒。Render 冷启动可能接近或超过此值；失败时提示手动重试，绝不自动重放写操作。创建请求结果丢失可能暂占一个会话，过期后回收。

## 4. 上线验收（必须实际填写结果）

- 无痕窗口 A、B 分别开始体验；A 创建的运行与工作区不能在 B 读取。
- 三个样本出现有支持／不足／硬冲突；确认目标、开始行动、刷新保留。
- 上传、修改背景、模型授权和管理接口被后端拒绝。
- 停止／重启服务后旧会话提示重新开始；过期、限流与容量满有明确提示。
- 在免费实例实测最多五位并行访客，记录内存、启动耗时；不足先优化，不升级套餐。
- 两个真实国内网络分别检查入口与核心路径，记录日期、网络与失败点；境外没测就写未测。
- 健康检查成功不代表业务可用；远端 CI、本地测试、公开浏览器路径分别记录。

不使用定时保活规避休眠。不承诺免费子域名在国内稳定；不可达时保留公开视频与本地演示，不声称上线验收通过。

## 5. 回滚与成本

回滚到上一已审核提交，并重建合成模板；访客临时进度会失效。不要带旧临时数据库跨版本恢复。免费额度耗尽应暂停而非自动升级；平台条款或费用提示变化时先停止发布。

套餐依据（2026-11-02 设计调研，创建资源时复核）：

- [Vercel Hobby](https://vercel.com/docs/plans/hobby)：个人非商业免费，当前项目使用生成的 vercel.app 地址。
- [Render Free](https://render.com/docs/free)：750 小时/月/工作区，15 分钟闲置休眠，临时磁盘丢失；免费 PostgreSQL 30 天过期。
- [Neon](https://neon.com/pricing)：后续持久化候选，本版不接入。
- [Supabase](https://supabase.com/pricing)：后续认证／存储候选，本版不接入。
- [EdgeOne 域名限制](https://edgeone.cloud.tencent.com/pages/document/175191784523485184)：默认域名及预览链接的访问限制不适合作为本版零域名成本主入口。
- [CloudBase](https://cloudbase.net/pricing)：免费体验与续期有条件，不为额度重写业务。
- [Hugging Face](https://huggingface.co/docs/huggingface_hub/guides/manage-spaces)：新建计算空间的订阅条件需注意，不能仅看 CPU 小时免费。
