# 本地转发代理

这是一个基于 Flask 的本地模型转发代理，默认监听 `http://127.0.0.1:18765`，可同时兼容 OpenAI Chat Completions、OpenAI Images、Anthropic Messages（原生）、Gemini GenerateContent（原生）和 Google Imagen/DashScope 图像生成。

## 项目结构

```text
.
├── app.py                      # 服务启动入口
├── start.bat                   # Windows 一键启动入口
├── frontend/
│   └── dashboard.html          # 本地监控控制台（纯 HTML/CSS/JS 单页）
├── config/
│   └── proxy-config.json       # 运行时渠道配置（固定放在规范目录）
├── var/
│   ├── cache/                  # SQLite、模型路由等运行缓存
│   ├── logs/                   # 代理日志和启动日志
│   └── run/                    # 当前启动 PID 信息
├── local_proxy/
│   ├── server.py               # Flask 入口和协议处理编排
│   ├── dashboard.py            # Dashboard 模板加载
│   ├── storage.py              # SQLite 持久化封装
│   ├── http/
│   │   └── routes.py           # HTTP 路由注册
│   ├── runtime/
│   │   └── state.py            # 请求状态、最近请求和计数器
│   ├── upstream/
│   │   ├── retry.py            # 上游重试辅助、模型候选竞速
│   │   └── models.py           # 模型别名、候选名生成、模型列表匹配
│   ├── compat/
│   │   ├── protocols.py        # Gemini / Anthropic / OpenAI 协议转换
│   │   └── tools.py            # DSML、tool_calls、工具参数归一化
│   └── providers/
│       └── images.py           # 图像生成供应商适配器
└── requirements.txt
```

## 前端形态

当前控制台是一个内嵌 CSS/JavaScript 的单页 `frontend/dashboard.html`，由 Flask 在 `/v1` 直接渲染，并通过 `/debug/state`、`/debug/config`、`/debug/pools/test` 等接口刷新状态和保存配置。

这个项目的前端主要是本地运维控制台，不需要 SEO、复杂路由、组件生态或构建产物；纯 HTML 够用，也降低了启动复杂度。只有在后续出现多页面权限体系、复杂表格/图表、可复用组件库或多人协作 UI 开发时，才建议升级到 Vue/React/Vite。

## 已实现

- 转发所有 `/v1/*` 请求到上游
- 自动识别请求协议，兼容 `POST /v1/chat/completions` 与 `POST /v1/messages`
- 兼容 Gemini 原生 `POST /v1beta/models/{model}:generateContent`
- 兼容 Gemini 原生 `POST /v1beta/models/{model}:streamGenerateContent?alt=sse`
- 兼容 OpenAI 图像生成 `POST /v1/images/generations`
- 兼容 Google Imagen `POST /v1beta/models/{model}:predict`
- 兼容 Gemini 图像生成 `POST /v1beta/models/{model}:generateContent` + `responseModalities=["IMAGE"]`
- 兼容 DashScope 千问/万相图像生成，支持同步结果归一化；异步 `task_id` 会短轮询后尽量返回同步图片结果
- 支持 `GET /v1beta/models` / `GET /v1beta/models/{model}`，会把 OpenAI 模型列表转换为 Gemini 模型列表格式
- 支持 Gemini OpenAI 兼容入口 `/v1beta/openai/chat/completions`，自动重写到内部 OpenAI 转发路径
- 支持 Gemini `contents`、`systemInstruction`、`generationConfig`、`tools.functionDeclarations`、`toolConfig.functionCallingConfig` 到 OpenAI Chat 的转换
- 支持 Gemini 文本、图片 inline data / file data、函数调用、函数返回等常见边界内容归一化
- 支持 `x-goog-api-key`、`x-api-key` 和 `?key=` 形式的 Gemini 鉴权输入，并避免把 key 透传为上游 query 参数
- 监控日志会脱敏 `key/api_key/token` 等敏感 query 参数
- `POST /v1/chat/completions` 响应中清洗 DSML 标记
- 对 DeepSeek 工具调用做兼容处理，移除碎片化 DSML 标记
- 支持把 DeepSeek 返回的 DSML `invoke` 伪工具调用自动转换成标准 `tool_calls` / `tool_use`
- 修正 DeepSeek 工具调用里常见的非标准 `tool_calls` / `tool_use` 结束语义
- 修正常见工具参数问题，例如 `bash` 缺少 `command`、`web_search` 缺少 `explanation`、`todo_write` 把数组误传成字符串时自动补正
- 修正智能体工具调用缺少 `run_in_background` 的问题；常规委托默认 `false`，识别并行探索/后台运行语义时自动补 `true`，并兼容 `runInBackground/background/parallel/async/concurrent` 等别名
- 支持模型别名映射，客户端可继续调用短模型名，代理转发前自动改写成上游真实模型名
- 支持自动拆开错误的 `arguments/input/parameters` 包裹层，例如把 `{"arguments":{"command":"ls"}}` 修成标准工具参数
- 支持请求侧归一化：自动修正 `tool_choice`、简写工具 schema、`max_output_tokens`、`input -> messages`、`developer -> system`
- 支持把助手正文里的伪工具轨迹尽量转成标准 `tool_calls`，减少 `Bash / Read / Update Todos` 这类文本式误调用
- 支持把 `Read taskActions.ts`、`Glob: *.ts` 这类文本工具轨迹自动识别并补成标准参数
- 支持注入中文系统提示：强制模型优先中文回复、优先标准工具调用、避免继续输出 DSML 文本
- 当客户端请求 `stream=false` 时，代理仍会对上游使用流式并聚合回标准 JSON
- 支持流式返回
- 支持 CORS，方便本地前端直连
- 支持环境变量和 `.env` 配置
- 支持多上游链路池、1 分钟内随机换路由重试，不会长期卡死在单一路径

## 启动

### 首次初始化

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
Copy-Item config\proxy-config.example.json config\proxy-config.json
```

编辑 `.env` 和 `config/proxy-config.json`，至少填入你的上游地址和 API Key。真实配置文件会被 Git 忽略，避免把密钥提交到仓库。

### 日常启动

双击 `start.bat` 一键启动，或在终端中：

```powershell
.\.venv\Scripts\python.exe app.py
```

`start.bat` 会检查 `.env`、只停止本项目已有代理进程、确认 18765 端口没有被其它程序占用，然后用项目虚拟环境启动代理服务。它不会再强制杀掉任意占用 18765 端口的外部进程；如果端口被非本项目进程占用，会在 `var/logs/server.bootstrap.log` 中报错。

启动脚本会把运行文件固定写入规范目录：

- 渠道配置：`config/proxy-config.json`
- 日志文件：`var/logs/`
- 运行缓存：`var/cache/`

## 关键配置

```env
UPSTREAM_URL=https://open.juece.cloud/v1
# UPSTREAM_URLS=https://open.juece.cloud/v1;https://your-second-endpoint.example/v1
UPSTREAM_API_KEY=sk-your-upstream-key
MODEL_ALIASES=deepseek-v4-flash=deepseek-ai/deepseek-v4-flash;deepseek-v4-pro=deepseek-ai/deepseek-v4-pro
ENABLE_MODEL_PROBE=1
MODEL_PROBE_TIMEOUT_SECONDS=4
MODEL_PROBE_TTL_SECONDS=300
MODEL_ROUTE_CACHE_TTL_SECONDS=86400
ENABLE_MODEL_CANDIDATE_RACE=1
MODEL_CANDIDATE_RACE_LIMIT=3
MODEL_CANDIDATE_RACE_TIMEOUT_SECONDS=8
PROXY_CONFIG_PATH=config/proxy-config.json
PROXY_LOG_PATH=var/logs/proxy.log
SQLITE_DB_PATH=var/cache/proxy-cache.sqlite3
MODEL_ROUTE_CACHE_PATH=var/cache/model-route-cache.json
PORT=18765
REQUEST_TIMEOUT=600
SSE_HEARTBEAT_SECONDS=12
MAX_COMPLETION_TOKENS=0
MODEL_CAPABILITIES=deepseek-v4-flash=1048576,393216;deepseek-v4-pro=1048576,393216;gpt-5.5=1000000,128000;gpt-5.4=1000000,128000;claude-opus-4-7=1000000,128000;claude-opus-4-6=1000000,128000
FORCE_UPSTREAM_CHAT_STREAM=1
ENABLE_REQUEST_NORMALIZATION=1
INJECT_ZH_SYSTEM_PROMPT=1
# PROXY_SYSTEM_PROMPT_ZH=自定义中文系统提示
UPSTREAM_MAX_RETRIES=12
UPSTREAM_RETRY_BACKOFF_MS=1200
UPSTREAM_RETRY_MAX_BACKOFF_MS=6000
UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS=60
UPSTREAM_RANDOMIZE_ENDPOINTS=1
IMAGE_UPSTREAM_PROTOCOL=auto
IMAGE_TASK_POLL_TIMEOUT_SECONDS=90
IMAGE_TASK_POLL_INTERVAL_SECONDS=2
```

## 调用方式

把客户端的 Base URL 指到：

```text
http://127.0.0.1:18765/v1
```

模型别名可以在控制台“模型别名映射”里配置，也可以用环境变量配置。格式是：

```text
客户端模型名=上游模型名
```

例如客户端仍然请求 `deepseek-v4-flash`，代理实际转发为：

```text
deepseek-v4-flash=deepseek-ai/deepseek-v4-flash
deepseek-v4-pro=deepseek-ai/deepseek-v4-pro
```

模型路由不是简单“永远改写”。代理会先保留客户端原始模型名并按下面顺序决策：

1. 命中 SQLite / JSON 模型路由记忆时，直接使用上次在该上游链路成功的实际模型名。
2. 只有没有可用记忆或记忆过期时，才短超时探测上游 `/models`，如果发现同语义模型名，例如 `deepseek-ai/deepseek-v4-flash`、`deepseek-ai/deepseek-v4-flash:free`，会优先使用实际可用名。
3. 如果 `/models` 不能给出明确答案，并且开启 `ENABLE_MODEL_CANDIDATE_RACE=1`，第一次请求会受控并发尝试前 `MODEL_CANDIDATE_RACE_LIMIT` 个候选名；谁先被上游接受，就立即关闭其它候选连接并记住成功名称。
4. 只有上游返回 `model_not_found` / `unsupported_model` / `no available channel for model` 这类模型不可用错误时，才按候选名继续尝试，并把成功或失败写入路由记忆。

这能兼顾两种情况：如果上游本身支持 `deepseek-v4-flash`，就原样透传；如果某条链路只支持 `deepseek-ai/deepseek-v4-flash`，代理会学习并记住这条链路的实际模型名。

请求历史、模型路由记忆、模型列表缓存默认会持久化到 `var/cache/proxy-cache.sqlite3`。控制台会显示路由记忆命中、模型列表缓存命中、候选竞速命中和客户端断开计数。`var/cache/model-route-cache.json` 会同步写入，方便手工查看。

例如：

```powershell
$headers = @{
  "Content-Type" = "application/json"
  "Authorization" = "Bearer local-or-upstream-key"
}

$body = @{
  model = "gpt-4o-mini"
  stream = $true
  messages = @(
    @{ role = "user"; content = "你好" }
  )
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:18765/v1/chat/completions" `
  -Headers $headers `
  -Body $body
```

Anthropic Messages（原生）客户端把 Base URL 也指向同一个地址即可，客户端会请求：

```text
http://127.0.0.1:18765/v1/messages
```

Gemini GenerateContent（原生）客户端可把 Base URL 指到：

```text
http://127.0.0.1:18765/v1beta
```

例如：

```powershell
$body = @{
  contents = @(
    @{
      role = "user"
      parts = @(
        @{ text = "你好，用一句话介绍自己" }
      )
    }
  )
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:18765/v1beta/models/gemini-2.5-flash:generateContent" `
  -Headers @{ "Content-Type" = "application/json"; "x-goog-api-key" = "local-or-upstream-key" } `
  -Body $body
```

OpenAI Images 客户端可直接请求：

```powershell
$body = @{
  model = "gpt-image-1"
  prompt = "一只玻璃质感的蓝色小机器人，产品摄影风格"
  size = "1024x1024"
  n = 1
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:18765/v1/images/generations" `
  -Headers @{ "Content-Type" = "application/json"; "Authorization" = "Bearer local-or-upstream-key" } `
  -Body $body
```

Google Imagen 原生客户端可请求：

```powershell
$body = @{
  instances = @(@{ prompt = "A clean studio product photo of a translucent blue robot" })
  parameters = @{ sampleCount = 1; aspectRatio = "1:1" }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:18765/v1beta/models/imagen-4.0-generate-001:predict" `
  -Headers @{ "Content-Type" = "application/json"; "x-goog-api-key" = "local-or-upstream-key" } `
  -Body $body
```

## 说明

- 如果请求里带了 `Authorization`，会优先透传给上游
- 如果请求里没带 `Authorization`，会自动使用 `UPSTREAM_API_KEY`
- `GET /health` 可用于检查代理是否启动成功
- `GET /health` 会返回当前进程、运行时长、重试配置和能力列表
- 浏览器打开 `http://127.0.0.1:18765/v1` 会看到实时监控面板
- 监控面板会显示检测到的协议、请求修复次数、DSML 清洗次数、工具参数修复次数、重试次数、链路尝试顺序和最近日志
- Gemini 原生请求会被转换成内部 OpenAI Chat Completions 请求，因此可以复用代理已有的请求修复、工具参数修复、DSML 清洗、上游重试和多链路切换能力
- 图像生成会根据下游请求路径识别 OpenAI / Google Imagen / Gemini 图像 / DashScope 形态，并根据上游 URL 自动选择 OpenAI 兼容、Google 或 DashScope 协议。必要时可用 `IMAGE_UPSTREAM_PROTOCOL=openai|google|dashscope` 强制指定
- DashScope 图像异步任务默认最多轮询 90 秒，可通过 `IMAGE_TASK_POLL_TIMEOUT_SECONDS` 和 `IMAGE_TASK_POLL_INTERVAL_SECONDS` 调整
- `FORCE_UPSTREAM_CHAT_STREAM=1` 时，`/v1/chat/completions` 会强制以流式调用上游，再按客户端需要返回流式或普通 JSON
- `SSE_HEARTBEAT_SECONDS=12` 会在上游长时间没有流式片段时给客户端发送 SSE 注释心跳，减少客户端等待首包或中途空窗时断开
- `ENABLE_REQUEST_NORMALIZATION=1` 时，代理会在转发前尽量修正常见客户端请求格式差异
- `MAX_COMPLETION_TOKENS=0` 表示关闭全局输出硬上限；代理会优先按 `MODEL_CAPABILITIES` 的模型能力表精确钳制 `max_completion_tokens` / `max_tokens`
- `MODEL_CAPABILITIES` 支持 `模型名=上下文Token,最大输出Token`，例如 `deepseek-v4-flash=1048576,393216`；如果上游返回 `supports at most ... completion tokens`，代理会学习这条链路的真实上限并重试
- `INJECT_ZH_SYSTEM_PROMPT=1` 时，代理会自动注入中文系统提示，约束模型尽量不要再输出 `<｜DSML｜tool_calls>` 文本并显式补齐必填参数
- `UPSTREAM_URLS` 可配置多条上游链路，支持逗号、分号或换行分隔
- `UPSTREAM_MAX_RETRIES` / `UPSTREAM_RETRY_BACKOFF_MS` / `UPSTREAM_RETRY_MAX_BACKOFF_MS` 可控制代理层重试，默认会对 `500/502/503/504/429` 最多重试 12 次
- `UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS=60` 时，单次请求会在最多 60 秒窗口内随机切换不同上游链路，优先避免在单一路由上死磕
- 当客户端中途断开导致 `client_gone` / `context canceled` 时，代理会尽快关闭上游流式连接，记录为“客户端断开”而不是普通代理错误；这不能阻止客户端主动断开，但能减少上游继续输出造成的浪费
- `ENABLE_MODEL_CANDIDATE_RACE=1` 只在没有路由记忆且模型探测不明确时触发，适合上游网关会随机映射模型名的链路；如果特别在意首轮重复请求成本，可以在控制台关闭
- 如果检测到 `model_not_found`、鉴权失败、余额不足、渠道不可用这类路由级永久错误，代理会立即放弃当前链路并切换其它候选链路；只有所有链路都失败或窗口耗尽，才把错误返回客户端
- `context_length_exceeded`、`invalid_request_error` 这类请求本身有问题的错误，不会无意义地跨链路重试
- 代理层可以缓解协议格式问题、工具参数格式问题、上游临时性故障，但无法替代客户端本身的业务逻辑判断
