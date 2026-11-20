# P1：本地岗位链接预览与人工保存

## 1. 用户闭环

本地正式版在 `/import` 接受一条公开岗位链接。服务用确定性规则提取岗位名、公司和正文；成功只回填可编辑草稿。用户核对后仍由现有 `POST /api/v1/job-imports/manual` 保存，保留手动导入的来源语义。不修改插件、数据库结构、岗位要求或匹配流程；不自动登录、不绕过验证、不批量抓取、不投递、不调用模型。

## 2. 接口与范围

- HTTP：`POST /api/v1/job-imports/url-capture`。请求和响应见 [请求 Schema](../../packages/contracts/schemas/url-job-capture-request.schema.json)、[响应 Schema](../../packages/contracts/schemas/url-job-capture-response.schema.json)、[响应示例](../../packages/contracts/examples/url-job-capture-response.example.json)。格式或请求参数错误返回 `422`，模式禁用或命中非公网地址返回 `403`，其他采集结果返回 `200` 与结构化状态，不缓存。
- 本地正式启动器默认启用。独立开发服务须绑定回环地址、明确设置 `JOBLENS_URL_CAPTURE=1`，并在网页端配置同源的 `WEB_BASE_URL` 和回环后端 `JOBLENS_BACKEND_URL`。浏览器跨源提交会被拒绝。公开演示和自带模型演示在读取请求体和会话前返回 `403`；邀请制云后端不挂载此路由，云网页不显示入口。
- MCP：本地 STDIO 工具 `capture_job_url`，使用同样的 `url`、`renderMode`、`timeoutMs`，直接返回响应契约；合法请求被网络策略拒绝时返回 `blocked`。标记为只读、非破坏、幂等、会访问外部网络（`openWorldHint`）、`localOnly`、`providerCostClass: none`、`humanGateRequirement: confirm_before_import`。不读取职业上下文。已有三个 MCP 工具的输入、输出和行为不变。

## 3. 提取与防护

1. **共享受控客户端。** 只接收 HTTP(S) 标准端口，不带凭据或系统代理。对所有解析结果做公网单播检查，使用已验证 IP 建连，同时保留域名及 TLS 校验；每次重定向重新校验，最多 5 跳。每个正文最多 2 MB，全程累计最多 5 MB。只请求未压缩内容；目标若坚持返回压缩格式则停止，不解压不受信任的内容。
2. **静态优先。** `auto` 优先从单条 JSON-LD JobPosting 提取完整草稿，再尝试静态主体；有脚本但缺少可用文本时才启动浏览器。Greenhouse 托管的单岗位页缺少公司字段时，仅在页面标题明确写出雇主、且标题中的岗位名与页面岗位标题一致时取该公司，并优先读取岗位正文区。`playwright` 跳过静态提取，但仍通过同一客户端获取和验证主文档。任何路径遇到登录墙、验证码或目标站 `401/403/429` 均转人工，不重试或绕过。
3. **本机浏览器限制。** Playwright 启动配套 Chromium，开启浏览器原生沙箱，使用临时上下文和只拒绝、不转发的回环代理，取消隐式直连例外，不配置直连回退，并限制浏览器 DNS、QUIC 和 WebRTC 非代理流量。不使用 Docker 或系统级网络沙箱。启动后先以本地探针验证回环请求确实经过拒绝代理，失败则不执行网页脚本。该设计是应用层限制，不是通用安全沙箱，不得开放到网络服务。
4. **拦截回填。** 注册上下文拦截之后才打开页面。主文档复用后端已取到的内容；允许的后续请求只有最终岗位页同源的 `GET`，类型限 document / script / xhr / fetch，不加载子框架。拒绝图片、字体、媒体、样式表、跨源请求、写请求、下载、WebSocket 和 Service Worker。另计最多 25 次子请求，同一子请求的重定向也计数，不能由浏览器自动跟随。任何越界或非公网目标立即停止代取，不返回部分草稿。
5. **总预算和降级。** `timeoutMs` 默认 15 秒，范围 3–25 秒；DNS、下载、浏览器启动、正文提取共用同一个截止时间。超时关闭出站许可并取消进行中的请求，浏览器和代理随后清理。若未安装 Playwright 或 Chromium，返回 `playwright_not_installed`；网络限制不能建立则返回 `browser_isolation_unavailable`；两者不影响静态抓取，并提供人工粘贴入口。
6. **只返回可核对的内容。** 渲染优先提取页面主体，必要时从无障碍树提取，不截图。不根据站点品牌猜雇主。草稿须通过 `ManualJobInput` 校验；其余状态不返回草稿。正文沿用质量门禁：0 字符为 `unavailable`，1–39 为 `card_only`，180 字符起且有职责或要求结构为 `full_jd`，其他为 `partial_jd`。截断上限 50,000 字符，诊断记录实际长度，`providerCalls` 恒为 `0`。

## 4. 本地运行

静态抓取随基础安装提供；可选浏览器依赖不会影响基础测试或启动。

```bash
(cd services/backend && uv sync --locked --extra browser && .venv/bin/python -m playwright install chromium)
python3 scripts/local.py
```

打开终端显示的网页，到「我的岗位 → 添加岗位」，或访问 `/import`。点击「抓取预览」后核对草稿；已有未保存内容会先询问是否替换。遇访问验证、浏览器不可用或跨站依赖无法渲染时，改用插件或手动粘贴。

## 5. 可复现验收

```bash
(cd services/backend && .venv/bin/python -m pytest tests/test_url_capture_*.py tests/test_mcp_server_protocol.py tests/test_public_demo.py tests/test_cloud_workspace_boundary.py -q)
(cd services/backend && JOBLENS_TEST_CHROMIUM=1 .venv/bin/python -m pytest tests/test_url_capture_chromium.py -q)
(cd apps/web && pnpm test && pnpm exec next typegen && pnpm typecheck && pnpm build)
git diff --check
```

Chromium 测试使用合成招聘页，覆盖脚本和同源数据加载、回环网络观测、被禁止的资源、重定向策略和预算/超时取消；不请求真实招聘站。网页验收按「抓取 → 草稿 → 人工保存」检查请求与入库分界，另验证登录/验证码提示、替换确认和抓取期间防重复提交。真实公开岗位页冒烟是可选项，应与合成回放单独报告。

**技术决策与失败复现。** 页面级请求拦截不是浏览器网络边界。把 Chromium 的 DNS 禁用规则误用到拒绝代理本身时，探针会发现代理未收到连接，抓取返回 `browser_isolation_unavailable`，而不是放开直连。仅为绑定的回环代理保留解析例外，探针仍要求请求不能直达本地目标。面试讲解可从这条失败回放入手，再展示唯一有出站权限的 HTTP 客户端如何校验并绑定 IP，以及为什么写库仍由用户决定。
