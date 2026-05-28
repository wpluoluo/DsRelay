# Local Proxy — AI API 统一代理网关

> 一个轻量、高性能的本地 AI API 代理网关，支持多协议转换、智能模型路由、自动重试与链路切换，为 AI 开发工具链提供统一的 API 接入层。

---

## 目录

- [项目简介](#项目简介)
- [核心特性](#核心特性)
- [架构概览](#架构概览)
- [快速开始](#快速开始)
  - [环境要求](#环境要求)
  - [首次初始化](#首次初始化)
  - [日常启动](#日常启动)
- [配置说明](#配置说明)
  - [环境变量](#环境变量)
  - [渠道配置](#渠道配置)
- [客户端接入](#客户端接入)
  - [OpenAI Chat Completions](#openai-chat-completions)
  - [Anthropic Messages](#anthropic-messages)
  - [Gemini GenerateContent](#gemini-generatecontent)
  - [图像生成](#图像生成)
- [模型路由机制](#模型路由机制)
- [监控面板](#监控面板)
- [项目结构](#项目结构)
- [常见问题](#常见问题)
- [许可证](#许可证)

---

## 项目简介

**Local Proxy** 是一个部署在本地开发环境中的 AI API 代理网关。推荐拓扑为 `客户端 -> NEWAPI -> 代理 -> 上游模型`：客户端、NEWAPI、本项目和上游模型之间的鉴权彼此独立，代理负责协议转换、路由和上游认证。

- **协议统一**：客户端只需使用 OpenAI 兼容协议，代理自动转换为 Anthropic、Gemini 等原生协议
- **智能路由**：支持多上游链路、每条线路独立支持模型列表、线路模型映射、自动探测与竞速选择
- **高可用**：请求失败自动重试、链路切换、退避策略，确保服务连续性
- **请求修复**：自动修正常见客户端请求格式问题、工具调用参数问题
- **监控运维**：提供 Web 监控面板，实时查看请求状态、路由缓存、链路健康

---

## 核心特性

### 协议兼容

| 协议 | 客户端入口 | 说明 |
|------|-----------|------|
| OpenAI Chat Completions | `POST /v1/chat/completions` | 原生支持，也是内部统一协议 |
| OpenAI Images | `POST /v1/images/generations` | 图像生成 |
| Anthropic Messages | `POST /v1/messages` | 自动转换为 OpenAI 格式转发 |
| Gemini GenerateContent | `POST /v1beta/models/{model}:generateContent` | 自动转换为 OpenAI 格式转发 |
| Gemini 流式生成 | `POST /v1beta/models/{model}:streamGenerateContent?alt=sse` | 流式支持 |
| Google Imagen | `POST /v1beta/models/{model}:predict` | 图像生成 |
| DashScope 图像生成 | 自动识别 | 支持同步/异步任务轮询 |
| Gemini OpenAI 兼容入口 | `POST /v1beta/openai/chat/completions` | 自动重写到 OpenAI 转发路径 |

### 智能路由

- **线路支持模型**：每条链路可手工声明自己明确支持的上游模型列表，避免慢线路被自动探测误导
- **线路模型映射**：每条链路可单独声明“请求模型 -> 上游真实模型”，避免跨线路误判
- **模型探测**：短超时探测上游 `/models` 接口，发现同语义模型名
- **候选竞速**：首次请求时并发尝试多个候选模型名，取最快成功者
- **路由记忆**：成功路由持久化到 SQLite，后续请求直接命中
- **多链路支持**：配置多条上游链路，随机切换避免单点故障

### 请求修复与归一化

- 自动修正 `tool_choice`、简写工具 schema、`max_output_tokens` 等常见格式差异
- 清理 DSML（DeepSeek Markup Language）标记
- 自动将 DSML `invoke` 伪工具调用转换为标准 `tool_calls` / `tool_use`
- 修正工具参数缺失问题（如 `bash` 缺少 `command`、`web_search` 缺少 `explanation`）
- 自动补正 `run_in_background` 等智能体工具调用语义
- 注入中文系统提示，约束模型优先中文回复和标准工具调用

### 高可用机制

- 请求超时控制（默认 600 秒）
- 上游重试策略：对 `500/502/503/504/429` 状态码自动重试（默认最多 12 次）
- 指数退避 + 最大退避上限
- 链路切换窗口：60 秒内随机切换不同上游链路
- SSE 心跳保活：上游长时间无数据时发送心跳，防止客户端断开
- 客户端断开检测：及时关闭上游流式连接，减少资源浪费

### 安全特性

- 敏感参数脱敏：日志中自动隐藏 `key`、`api_key`、`token` 等字段
- 三层鉴权隔离：客户端 Key 由 NEWAPI 校验，入口 Key 专用于 NEWAPI 调用本项目，上游 Key 仅用于代理调用模型服务
- 认证隔离：代理不会向上游透传入站 `Authorization`、`x-api-key`、`x-goog-api-key` 或敏感查询参数
- 上游认证：代理仅使用自身连接池配置的上游 API Key 调用模型服务
- 环境隔离：启动脚本确保使用项目虚拟环境，拒绝外部 Python 环境

---

## 架构概览

```
┌─────────────────┐     ┌─────────────────────────────────────┐     ┌──────────────────┐
│                 │     │          Local Proxy                 │     │                  │
│   AI 客户端      │────▶│   NEWAPI     │────▶│  ┌──────────┐  ┌────────────────┐  │────▶│  上游 AI 服务     │
│   (IDE/脚本)     │     │  (认证入口)   │     │  │ 协议转换  │  │ 模型路由/重试   │  │     │  (OpenAI/Anthropic│
│                 │     │  │ (compat/) │  │ (upstream/)    │  │     │   /Gemini 等)    │
└─────────────────┘     │  ├──────────┤  ├────────────────┤  │     └──────────────────┘
                        │  │ 请求修复  │  │ 缓存系统       │  │
                        │  │ (tools.py)│  │ (SQLite/JSON)  │  │
                        │  ├──────────┤  ├────────────────┤  │
                        │  │ 图像生成  │  │ 监控面板       │  │
                        │  │ (images) │  │ (dashboard)    │  │
                        │  └──────────┘  └────────────────┘  │
                        └─────────────────────────────────────┘
```

### 模块说明

| 模块 | 路径 | 职责 |
|------|------|------|
| 服务入口 | `app.py` | 启动入口，校验虚拟环境 |
| 核心服务 | `local_proxy/server.py` | Flask 应用，请求处理编排 |
| 协议兼容 | `local_proxy/compat/` | OpenAI / Anthropic / Gemini 协议互转 |
| 工具兼容 | `local_proxy/compat/tools.py` | DSML 清洗、工具参数归一化 |
| HTTP 处理 | `local_proxy/http/` | 路由、流式响应、请求头、验证 |
| 图像生成 | `local_proxy/providers/images.py` | 多供应商图像生成适配 |
| 运行时 | `local_proxy/runtime/` | 状态管理、配置、缓存、连接池 |
| 上游通信 | `local_proxy/upstream/` | 模型路由、重试、能力探测 |
| 持久化 | `local_proxy/storage.py` | SQLite 封装 |
| 监控面板 | `frontend/dashboard.html` | 单页 Web 控制台 |
| 启动脚本 | `scripts/start-proxy.ps1` | Windows PowerShell 启动管理 |

---

## 快速开始

### 环境要求

- Python 3.10 或更高版本
- Windows 操作系统（启动脚本基于 PowerShell）
- 有效的上游 AI 服务 API Key

### 首次初始化

```powershell
# 1. 创建虚拟环境
python -m venv .venv

# 2. 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 3. 安装依赖
pip install -r requirements.txt

# 4. 复制配置文件
Copy-Item .env.example .env
Copy-Item config\proxy-config.example.json config\proxy-config.json
```

### 配置上游服务

编辑 `.env` 文件，至少配置以下参数：

```ini
# 上游 API 地址
UPSTREAM_URL=https://your-upstream-service.example/v1

# 上游 API 密钥
UPSTREAM_API_KEY=sk-your-upstream-key
```

编辑 `config/proxy-config.json`，按线路配置连接池、支持模型和模型映射。

> **注意**：`.env` 和 `config/proxy-config.json` 已被 Git 忽略，避免密钥泄露。

### 日常启动

**方式一：双击启动（推荐）**

直接双击 `start.bat`，启动脚本会自动完成以下操作：

1. 创建必要的运行目录（`var/logs/`、`var/cache/`、`var/run/`）
2. 停止已有的本项目代理进程
3. 检查 18765 端口是否被占用
4. 使用项目虚拟环境启动代理服务
5. 等待健康检查通过（最长 25 秒）
6. 将 PID 信息写入 `var/run/proxy.pid.json`

**方式二：命令行启动**

```powershell
.\.venv\Scripts\python.exe app.py
```

### 验证启动

```powershell
# 健康检查
Invoke-RestMethod -Uri "http://127.0.0.1:18765/health"
```

成功响应示例：

```json
{
  "status": "ok",
  "pid": 26548,
  "uptime": "0:05:23",
  "port": 18765,
  "runtime": { ... }
}
```

---

## 配置说明

### 环境变量

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `UPSTREAM_URL` | — | 上游 API 基础地址 |
| `UPSTREAM_URLS` | — | 多条上游链路，支持逗号/分号/换行分隔 |
| `UPSTREAM_API_KEY` | — | 上游 API 密钥 |
| `PROXY_API_KEYS` | — | NEWAPI 调用本项目的独立入口 Key，支持逗号/分号/换行分隔多个 Key；也可在控制台“入口鉴权”生成托管 Key |
| `PORT` | `18765` | 代理监听端口 |
| `REQUEST_TIMEOUT` | `600` | 请求超时时间（秒） |
| `SSE_HEARTBEAT_SECONDS` | `12` | SSE 心跳间隔（秒） |
| `STREAM_OPEN_GRACE_SECONDS` | `1.5` | 流式请求等待上游首包后开始向下游发送连接心跳的宽限时间（秒） |
| `STREAM_FIRST_EVENT_TIMEOUT_SECONDS` | `6` | 流式请求在收到 `text/event-stream` 后，等待首个有效数据事件的最长时间（秒）；超时会把当前线路视为空流并切换下一条线路 |
| `STREAM_ROUTE_SWITCH_CONNECT_TIMEOUT_SECONDS` | `6` | 多线路流式请求在切线阶段使用的上游建连/首阶段读取超时（秒），用于尽快放弃坏线路 |
| `MAX_COMPLETION_TOKENS` | `0` | 全局输出 Token 上限（0 表示关闭） |
| `FORCE_UPSTREAM_CHAT_STREAM` | `1` | 强制以流式调用上游 |
| `ENABLE_REQUEST_NORMALIZATION` | `1` | 启用请求格式自动修复 |
| `INJECT_ZH_SYSTEM_PROMPT` | `1` | 注入中文系统提示 |
| `UPSTREAM_MAX_RETRIES` | `12` | 上游最大重试次数 |
| `UPSTREAM_RETRY_BACKOFF_MS` | `1200` | 重试初始退避时间（毫秒） |
| `UPSTREAM_RETRY_MAX_BACKOFF_MS` | `6000` | 重试最大退避时间（毫秒） |
| `UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS` | `60` | 链路切换窗口（秒） |
| `UPSTREAM_RANDOMIZE_ENDPOINTS` | `1` | 随机化端点选择 |
| `ENABLE_MODEL_PROBE` | `1` | 启用模型探测 |
| `MODEL_PROBE_TIMEOUT_SECONDS` | `4` | 模型探测超时（秒） |
| `MODEL_PROBE_TTL_SECONDS` | `300` | 模型探测结果缓存时间（秒） |
| `MODEL_ROUTE_CACHE_TTL_SECONDS` | `86400` | 路由缓存 TTL（秒） |
| `ENABLE_MODEL_CANDIDATE_RACE` | `1` | 启用模型候选竞速 |
| `MODEL_CANDIDATE_RACE_LIMIT` | `3` | 竞速并发候选数 |
| `MODEL_CANDIDATE_RACE_TIMEOUT_SECONDS` | `8` | 竞速超时（秒） |
| `IMAGE_UPSTREAM_PROTOCOL` | `auto` | 图像生成协议（auto/openai/google/dashscope） |
| `IMAGE_TASK_POLL_TIMEOUT_SECONDS` | `90` | 图像异步任务轮询超时（秒） |
| `IMAGE_TASK_POLL_INTERVAL_SECONDS` | `2` | 图像异步任务轮询间隔（秒） |
| `MODEL_CAPABILITIES` | — | 模型能力表（格式：`模型名=上下文Token,最大输出Token`） |
| `PROXY_CONFIG_PATH` | `config/proxy-config.json` | 渠道配置文件路径 |
| `PROXY_LOG_PATH` | `var/logs/proxy.log` | 代理日志路径 |
| `SQLITE_DB_PATH` | `var/cache/proxy-cache.sqlite3` | SQLite 数据库路径 |
| `SHARED_DOCKER_NETWORK` | `1panel-network` | Docker 共享网络名，容器访问外部 MySQL 时使用 |
| `HOST_GATEWAY_HOSTNAME` | `host.docker.internal` | 宿主机网关别名 |
| `HOST_GATEWAY_ADDRESS` | `host-gateway` | 宿主机网关地址写法 |

### 远程部署与双机配置

仓库内置 `scripts/deploy-remote.ps1`，支持：

- 单目标部署：兼容原有 `DEPLOY_SSH_*` / `DEPLOY_STORAGE_DB_*` 变量。
- 多目标部署：在本地 `.env` 中配置 `DEPLOY_TARGETS=legacy,baota`，再为每个目标填写 `DEPLOY_<目标名>_*` 变量。
- `key` 与 `password` 两种 SSH 认证方式。
- 宝塔 / 1Panel / 纯 Docker 环境共用，只要目标机上存在 `docker`、`docker compose` 和可用的共享网络。

常用目标变量如下：

| 变量 | 说明 |
|------|------|
| `DEPLOY_<TARGET>_SSH_HOST` | 服务器 IP 或域名 |
| `DEPLOY_<TARGET>_SSH_PORT` | SSH 端口 |
| `DEPLOY_<TARGET>_SSH_USER` | SSH 用户 |
| `DEPLOY_<TARGET>_SSH_AUTH_MODE` | `key` 或 `password` |
| `DEPLOY_<TARGET>_SSH_KEY_PATH` | 私钥路径（`key` 模式） |
| `DEPLOY_<TARGET>_SSH_PASSWORD` | SSH 密码（`password` 模式，仅本地 `.env` 使用） |
| `DEPLOY_<TARGET>_REMOTE_PATH` | 远端部署目录 |
| `DEPLOY_<TARGET>_SERVICE_NAME` | `docker compose` 服务名 |
| `DEPLOY_<TARGET>_COMPOSE_FILE` | 指定目标机使用的 compose 文件，例如 `docker-compose.host.yml` |
| `DEPLOY_<TARGET>_APP_PORT` | 代理健康检查端口 |
| `DEPLOY_<TARGET>_SHARED_DOCKER_NETWORK` | 目标机共享网络名 |
| `DEPLOY_<TARGET>_STORAGE_DB_*` | 目标机远端 `.env` 中需要写入的 MySQL 连接参数 |

示例：

```powershell
# 部署到单台
.\scripts\deploy-remote.ps1 -Target legacy

# 一次部署到 .env 里声明的全部目标
.\scripts\deploy-remote.ps1 -AllTargets
```

如果目标机是宝塔面板，且数据库使用宿主机现有 MySQL，推荐直接让 `local-proxy` 使用 `docker-compose.host.yml` 运行在 host network；这样容器内可以直接访问 `127.0.0.1:3306`，同时避免桥接网络访问宿主机 MySQL 不通的问题。

如果目标机需要直接连接宿主机 MySQL，可以把：

- `DEPLOY_<TARGET>_COMPOSE_FILE=docker-compose.host.yml`
- `DEPLOY_<TARGET>_STORAGE_DB_HOST=127.0.0.1`

这样 `local-proxy` 会以 host network 方式运行，容器内可直接访问服务器本机的 `3306`。

### 渠道配置

渠道配置文件 `config/proxy-config.json` 支持配置多个上游连接池，每个池可独立配置 URL、密钥和路由策略。

```json
{
  "pools": [
    {
      "name": "primary",
      "enabled": true,
      "priority": 100,
      "urls": ["https://your-upstream.example/v1"],
      "keys": [{"key": "sk-your-upstream-key"}],
      "supported_models_text": "deepseek-ai/deepseek-v4-flash\ndeepseek-ai/deepseek-v4-pro",
      "model_aliases_text": "deepseek-v4-flash-free=deepseek-ai/deepseek-v4-flash\ndeepseek-v4-pro=deepseek-ai/deepseek-v4-pro",
      "route_policy": {
        "reasoning_effort": "high",
        "prompt_cache_mode": "exact",
        "prompt_cache_hints_mode": "auto",
        "prompt_cache_provider": "auto",
        "prompt_cache_retention": "",
        "text_upstream_protocol": "auto",
        "route_cooldown_seconds": 90,
        "route_cooldown_multiplier": 2,
        "route_cooldown_max_seconds": 900,
        "max_output_tokens": 0
      }
    }
  ]
}
```

**路由策略参数说明：**

| 参数 | 说明 |
|------|------|
| `supported_models_text` | 该线路显式支持的上游模型 ID 列表，按行填写；填写后只会在该列表内选候选 |
| `model_aliases_text` | 该线路的“请求模型 -> 上游真实模型”映射，按行填写 |
| `reasoning_effort` | 推理努力程度（low / medium / high） |
| `text_upstream_protocol` | 文本请求上游协议（auto / openai / responses） |
| `prompt_cache_mode` | 本地精确缓存模式 |
| `prompt_cache_hints_mode` | 上游前缀缓存 Hint 模式 |
| `prompt_cache_provider` | Hint 提供方 |
| `prompt_cache_retention` | Hint 保留期 |
| `route_cooldown_seconds` | 线路基础冷却秒数 |
| `route_cooldown_multiplier` | 连续失败后的冷却倍率 |
| `route_cooldown_max_seconds` | 线路最大冷却秒数 |
| `max_output_tokens` | 输出 Token 上限（0 表示不限制） |

---

## 客户端接入

代理默认监听 `http://127.0.0.1:18765`。推荐部署拓扑为 `客户端 -> NEWAPI -> 代理 -> 上游模型`，鉴权边界如下：

- 客户端 -> NEWAPI：由 NEWAPI 校验客户端 Key。
- NEWAPI -> 本项目：由本项目校验 `PROXY_API_KEYS`，这是独立入口 Key。
- 本项目 -> 上游模型：由代理使用连接池里的上游 API Key。

`PROXY_API_KEYS` 和客户端 Key、上游模型 Key 都没有关系，不能混用。NEWAPI 调用本项目时应携带：

```text
Authorization: Bearer <PROXY_API_KEY>
```

也兼容 `X-API-Key`、`X-Goog-API-Key`、`?key=`、`?api_key=` 和 `?apikey=`。

也可以在管理控制台的“入口鉴权”菜单生成和管理托管入口 Key。托管 Key 生成格式为 `sk-` 加 48 位字母数字，例如 `sk-R3FgLkpc3lVrpotlu9tV9rNvvQLRsupzsozwG7pHo11vcbqr`。明文只在创建时返回一次；运行配置里只保存哈希、预览、名称和启停状态。启用 MySQL 持久化时，这些托管入口 Key 记录会随运行配置写入 MySQL 的 `app_config` 表。

### OpenAI Chat Completions

将客户端 Base URL 指向代理地址：

```text
http://127.0.0.1:18765/v1
```

**PowerShell 示例：**

```powershell
$headers = @{
  "Content-Type" = "application/json"
  "Authorization" = "Bearer your-proxy-api-key"
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

### Anthropic Messages

将客户端 Base URL 指向同一地址，客户端请求 `/v1/messages`：

```text
http://127.0.0.1:18765/v1/messages
```

代理会自动识别 Anthropic 协议请求，转换为 OpenAI 格式转发到上游，再将响应转换回 Anthropic 格式返回。

### Gemini GenerateContent

将客户端 Base URL 指向：

```text
http://127.0.0.1:18765/v1beta
```

**PowerShell 示例：**

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
  -Headers @{
    "Content-Type" = "application/json"
    "Authorization" = "Bearer your-proxy-api-key"
  } `
  -Body $body
```

代理校验入口 Key 后，会移除入站请求中的认证字段，并使用连接池中配置的上游 Key 调用对应模型服务。

### 图像生成

**OpenAI Images（标准格式）：**

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
  -Headers @{
    "Content-Type" = "application/json"
  } `
  -Body $body
```

**Google Imagen（原生格式）：**

```powershell
$body = @{
  instances = @(@{ prompt = "A clean studio product photo of a translucent blue robot" })
  parameters = @{ sampleCount = 1; aspectRatio = "1:1" }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:18765/v1beta/models/imagen-4.0-generate-001:predict" `
  -Headers @{
    "Content-Type" = "application/json"
  } `
  -Body $body
```

图像生成协议自动识别规则：
- 根据下游请求路径自动识别 OpenAI / Google Imagen / Gemini 图像 / DashScope 形态
- 根据上游 URL 自动选择 OpenAI 兼容、Google 或 DashScope 协议
- 可通过 `IMAGE_UPSTREAM_PROTOCOL` 强制指定协议

---

## 模型路由机制

模型路由是代理的核心能力之一，决策流程如下：

```
客户端请求（携带原始模型名）
        │
        ▼
┌─────────────────────────────────┐
│ 1. 检查 SQLite 路由记忆          │
│    └─ 命中 → 使用上次成功模型名   │
│    └─ 未命中 → 继续              │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│ 2. 模型探测（短超时查询 /models） │
│    └─ 发现同语义模型名 → 使用     │
│    └─ 未发现 → 继续              │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│ 3. 候选竞速（ENABLE_MODEL_RACE） │
│    └─ 并发尝试 N 个候选模型名     │
│    └─ 取最快被上游接受者          │
│    └─ 关闭其他候选连接            │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│ 4. 错误重试                      │
│    └─ model_not_found 等错误     │
│    └─ 切换候选名继续尝试          │
│    └─ 写入路由记忆                │
└─────────────────────────────────┘
```

### 线路模型映射配置

在控制台“连接池管理 -> 管理连接池”中，先填写“该线路支持模型”，再填写“该线路模型映射”：

```text
# 该线路支持模型（逐行填写上游真实模型 ID）
deepseek-ai/deepseek-v4-flash
deepseek-ai/deepseek-v4-pro
```

```text
# 该线路模型映射（格式：请求模型=该线路上游模型）
deepseek-v4-flash-free=deepseek-ai/deepseek-v4-flash
opencode/deepseek-v4-flash-free=deepseek-ai/deepseek-v4-flash
deepseek-v4-pro=deepseek-ai/deepseek-v4-pro
```

### 模型能力表

模型能力表应以官方文档或官方 Models API 为准；代理不再根据上游报错自动学习并缓存 token 上限。

```text
# 格式：模型名=上下文Token,最大输出Token
deepseek-v4-flash=1048576,393216
deepseek-v4-pro=1048576,393216
gpt-5.5=1050000,128000
```

---

## 监控面板

浏览器打开 `http://127.0.0.1:18765/v1` 即可访问实时监控面板。

### 面板功能

| 功能 | 说明 |
|------|------|
| 实时请求状态 | 查看当前正在处理的请求列表 |
| 请求历史 | 最近请求的详细记录，包括耗时、协议类型 |
| 路由缓存 | 模型路由记忆命中、模型列表缓存命中、候选竞速命中 |
| 链路测试 | 测试各上游链路的连通性 |
| 配置管理 | 在线修改渠道配置、每条线路支持模型和模型映射 |
| 连接池策略 | 调整协议、缓存、冷却等线路策略参数 |
| 客户端断开计数 | 记录客户端主动断开连接的情况 |
| 最近日志 | 实时滚动显示代理运行日志 |

### 调试接口

| 接口 | 说明 |
|------|------|
| `GET /health` | 健康检查，返回进程、运行时长、配置等信息 |
| `GET /debug/state` | 当前运行时状态 |
| `GET /debug/config` | 当前配置信息 |
| `GET /debug/pools/test` | 链路池连通性测试 |

---

## 项目结构

```
.
├── app.py                          # 服务启动入口
├── start.bat                       # Windows 一键启动脚本
├── requirements.txt                # Python 依赖清单
├── .env.example                    # 环境变量模板
├── config/
│   ├── proxy-config.example.json   # 渠道配置模板
│   └── proxy-config.json           # 运行时渠道配置（已忽略）
├── frontend/
│   └── dashboard.html              # Web 监控控制台（单页应用）
├── scripts/
│   └── start-proxy.ps1             # PowerShell 启动管理脚本
├── var/                            # 运行时数据目录（自动创建）
│   ├── cache/                      # SQLite 缓存、模型路由缓存
│   ├── logs/                       # 代理日志和启动日志
│   └── run/                        # 运行 PID 信息
└── local_proxy/
    ├── __init__.py
    ├── server.py                   # Flask 应用主逻辑
    ├── dashboard.py                # 监控面板模板加载
    ├── storage.py                  # SQLite 持久化封装
    ├── compat/                     # 协议兼容层
    │   ├── protocols.py            # Gemini / Anthropic / OpenAI 协议转换
    │   └── tools.py                # DSML 清洗、工具调用归一化
    ├── http/                       # HTTP 处理层
    │   ├── routes.py               # 路由注册
    │   ├── streaming.py            # SSE 流式响应
    │   ├── headers.py              # 请求/响应头处理
    │   ├── validation.py           # 响应验证
    │   └── async_execution.py      # 后台异步执行
    ├── providers/                  # 供应商适配器
    │   └── images.py               # 图像生成（OpenAI / Google / DashScope）
    ├── runtime/                    # 运行时
    │   ├── state.py                # 请求状态管理
    │   ├── config_runtime.py       # 运行时配置
    │   ├── config_payloads.py      # 配置负载
    │   ├── config_storage.py       # 配置持久化
    │   ├── pools.py                # 连接池管理
    │   ├── policies.py             # 路由策略
    │   ├── request_cache.py        # 请求缓存
    │   ├── snapshots.py            # 状态快照
    │   └── helpers.py              # 辅助函数
    └── upstream/                   # 上游通信层
        ├── orchestrator.py         # 请求编排
        ├── router.py               # 模型路由
        ├── retry.py                # 重试机制
        ├── models.py               # 线路支持模型 / 模型映射解析与候选
        ├── capabilities.py         # 能力探测
        └── logging_utils.py        # 日志工具
```

---

## 常见问题

### 启动失败：端口被占用

启动脚本会检测 18765 端口占用情况：
- 如果是本项目已有进程，会自动停止
- 如果是其他程序占用，会在日志中报错，需手动释放端口

### 请求返回 401 / 认证失败

- 客户端侧 401：检查 NEWAPI 中配置的客户端 Key、渠道和目标地址
- 代理入口 401：检查 NEWAPI 调用本项目时携带的 Key 是否匹配 `PROXY_API_KEYS` 或控制台“入口鉴权”中的托管 Key
- 上游侧 401：检查代理控制台连接池中配置的上游 API Key
- 代理会剥离入站认证字段，不会把 NEWAPI 的入口 Key 或客户端 Key 透传给上游

### 请求返回 503 / 代理入口 Key 未配置

模型代理入口要求配置独立入口 Key。如果 NEWAPI 或客户端直接请求 `/v1/*`、`/v1beta/*`、`/v1alpha/*` 时收到 `proxy_api_key_not_configured`，请在 `.env` 中设置 `PROXY_API_KEYS` 并重启服务，或在控制台“入口鉴权”生成并启用托管 Key。

### 模型返回 "model not found"

- 检查对应线路的模型映射是否正确配置
- 检查对应线路的支持模型列表是否已显式包含目标上游模型
- 检查上游服务是否支持该模型
- 代理会自动尝试候选模型名并记住成功路由

### 流式响应中断

- `SSE_HEARTBEAT_SECONDS` 控制心跳间隔，默认 12 秒
- 如果上游长时间无数据，代理会发送 SSE 注释心跳保持连接
- 可适当降低心跳间隔值

### 请求超时

- `REQUEST_TIMEOUT` 默认 600 秒，可根据需要调整
- 对于长思考模型，建议适当增大超时时间
- `UPSTREAM_MAX_RETRIES` 控制重试次数，过多重试可能累积超时

---

## 许可证

本项目仅供学习和个人使用。请遵守上游 AI 服务提供商的使用条款和相关法律法规。

---

> **提示**：英文版文档请参阅 [README.en.md](README.en.md)。
