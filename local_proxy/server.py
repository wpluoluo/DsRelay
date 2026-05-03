import json
import os
import hashlib
import itertools
import random
import re
import sys
import time
import uuid
from collections import deque
from pathlib import Path
import logging
from threading import Lock

import requests
from requests.adapters import HTTPAdapter
from flask import Flask, Response, copy_current_request_context, render_template_string, request

from local_proxy.compat.tools import (
    append_preview_text,
    append_preview_tool,
    build_preview_summary,
    build_chat_completion_from_sse,
    configure_tool_compat,
    extract_tool_schemas,
    merge_tool_call_delta,
    normalize_chat_completion_dsml_tool_calls,
    normalize_chat_completion_finish_reasons,
    normalize_chat_completion_text_tool_calls,
    normalize_chat_completion_tool_calls,
    normalize_openai_request_payload,
    normalize_sse_line,
    sanitize_dsml_text,
)
from local_proxy.compat.protocols import (
    build_anthropic_error_payload,
    build_gemini_error_payload,
    convert_anthropic_request_to_openai,
    convert_openai_response_to_anthropic,
    convert_gemini_request_to_openai,
    convert_openai_response_to_gemini,
    map_openai_finish_reason_to_anthropic,
    map_openai_finish_reason_to_gemini,
    openai_message_to_gemini_parts,
    parse_gemini_generate_subpath,
    payload_looks_anthropic,
)
from local_proxy.dashboard import load_dashboard_template
from local_proxy.auth import init_auth, login_page, login_required, logout, is_authenticated
from local_proxy.http.headers import (
    apply_sse_response_headers,
    build_response_headers,
    build_upstream_headers,
    build_upstream_params,
    sanitize_query_string,
)
from local_proxy.http.proxy_auth import (
    make_proxy_api_key_record,
    normalize_proxy_api_key_records,
    parse_proxy_api_keys,
    public_proxy_api_key_record,
    utc_now_text,
    verify_proxy_api_key,
)
from local_proxy.http.async_execution import BackgroundExecution
from local_proxy.http.routes import register_http_routes
from local_proxy.http.streaming import (
    build_anthropic_stream_packets_from_message,
    build_openai_stream_packets_from_chat_completion,
    close_response_quietly,
    format_sse_event,
    format_openai_sse_payload,
    is_client_gone_exception,
    is_text_response,
    iter_response_lines,
    iter_response_lines_with_heartbeat,
    text_indicates_client_gone,
)
from local_proxy.http.validation import inspect_success_payload, openai_stream_events_have_meaningful_output
from local_proxy.providers.images import (
    build_image_generation_plan,
    dashscope_body_has_images,
    dashscope_task_status_url,
    detect_downstream_image_protocol,
    extract_dashscope_task_id,
    normalize_image_generation_response,
)
from local_proxy.runtime.helpers import (
    ensure_proxy_prompt_rules as build_proxy_prompt_rules,
    mask_secret,
    parse_bool,
    parse_int,
)
from local_proxy.runtime.config_payloads import (
    build_runtime_config_payload as assemble_runtime_config_payload,
    export_runtime_config_for_storage as assemble_runtime_config_storage,
)
from local_proxy.runtime.config_storage import (
    load_runtime_config_from_file,
    load_runtime_config_from_db,
    save_runtime_config,
)
from local_proxy.runtime.config_runtime import (
    apply_pool_runtime_state,
    apply_runtime_globals,
    log_runtime_config_update,
    normalize_runtime_config_payload,
)
from local_proxy.runtime.snapshots import (
    build_dashboard_state as assemble_dashboard_state,
    build_runtime_snapshot as assemble_runtime_snapshot,
    read_recent_log_lines as load_recent_log_lines,
)
from local_proxy.runtime.state import CounterStore, RequestRecorder
from local_proxy.runtime.pools import ConnectionPoolState, normalize_pool_url, normalize_proxy_pools
from local_proxy.runtime.policies import (
    DEFAULT_ROUTE_POLICY,
    get_route_policy_for_url,
    normalize_pool_route_policies,
)
from local_proxy.runtime.request_cache import (
    DEFAULT_REQUEST_CACHE_TTL_SECONDS,
    all_tools_read_only,
    build_cache_key,
    build_cache_record,
    build_cached_execution,
    is_cacheable_request,
)
from local_proxy.storage import ProxyStorage
from local_proxy.upstream.capabilities import (
    DEFAULT_MODEL_CAPABILITIES_TEXT,
    clamp_payload_output_tokens,
    extract_completion_token_limit_from_text,
    extract_context_token_limit_from_text,
    find_context_window_overflow,
    find_model_capability,
    normalize_model_capabilities_text,
    parse_model_capabilities,
)
from local_proxy.upstream.models import (
    DEFAULT_MODEL_ALIASES_TEXT,
    build_related_model_name_candidates,
    dedupe_model_candidates,
    discover_model_candidates_from_models,
    extract_model_ids_from_models_payload,
    model_list_url_from_endpoint,
    normalize_model_alias_key,
    normalize_model_aliases_text,
    parse_model_aliases,
)
from local_proxy.upstream.logging_utils import summarize_attempt_routes, summarize_attempts_for_log
from local_proxy.upstream.retry import race_model_candidate_requests
from local_proxy.upstream.orchestrator import request_upstream_with_retries as orchestrated_request_upstream_with_retries
from local_proxy.upstream.router import (
    append_race_attempts as router_append_race_attempts,
    apply_model_candidate_to_request_kwargs,
    build_attempt_url_cycle as router_build_attempt_url_cycle,
    build_model_candidate_order_for_route as router_build_model_candidate_order_for_route,
    build_upstream_url_candidates as router_build_upstream_url_candidates,
    cache_model_list as router_cache_model_list,
    fetch_upstream_model_list as router_fetch_upstream_model_list,
    get_cached_model_list as router_get_cached_model_list,
    get_route_health_entry as router_get_route_health_entry,
    is_route_in_cooldown as router_is_route_in_cooldown,
    mark_route_failure as router_mark_route_failure,
    mark_route_success as router_mark_route_success,
    model_candidate_differs_from_logical,
    order_model_candidates_for_route as router_order_model_candidates_for_route,
    remaining_retry_window_ms as router_remaining_retry_window_ms,
    response_indicates_model_unavailable as router_response_indicates_model_unavailable,
    should_enforce_route_switch_window as router_should_enforce_route_switch_window,
    should_race_model_candidates_for_route as router_should_race_model_candidates_for_route,
)

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


if load_dotenv:
    load_dotenv()


app = Flask(__name__)
init_auth(app)
APP_STARTED_AT_EPOCH = time.time()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
CONFIG_DIR = PROJECT_ROOT / "config"
VAR_DIR = PROJECT_ROOT / "var"
CACHE_DIR = VAR_DIR / "cache"
LOG_DIR = VAR_DIR / "logs"


def resolve_project_path(raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def has_explicit_config_value(config_payload: dict, key: str) -> bool:
    return isinstance(config_payload, dict) and key in config_payload


def parse_upstream_url_pool() -> list[str]:
    return []


def build_no_upstream_configured_error_payload() -> dict:
    return {
        "error": {
            "message": "未配置可用的上游链路，请先在控制台配置连接池。",
            "type": "invalid_request_error",
            "param": "pools",
            "code": "upstream_not_configured",
        }
    }


def build_upstream_timeout(*, requested_stream: bool) -> int | tuple[int, int]:
    if not requested_stream:
        return REQUEST_TIMEOUT
    connect_timeout = min(max(5, REQUEST_TIMEOUT), STREAM_CONNECT_TIMEOUT_SECONDS)
    read_timeout = max(REQUEST_TIMEOUT, STREAM_READ_TIMEOUT_SECONDS)
    return (connect_timeout, read_timeout)


def openai_stream_expected_choice_count(request_payload: dict | None) -> int:
    if not isinstance(request_payload, dict):
        return 1
    try:
        return max(1, int(request_payload.get("n") or 1))
    except Exception:
        return 1


def openai_stream_event_finish_indexes(event: dict | None) -> set[int]:
    if not isinstance(event, dict):
        return set()
    choices = event.get("choices")
    if not isinstance(choices, list) or not choices:
        return set()
    indexes = set()
    for fallback_index, choice in enumerate(choices):
        if isinstance(choice, dict) and choice.get("finish_reason") is not None:
            try:
                indexes.add(int(choice.get("index", fallback_index) or 0))
            except Exception:
                indexes.add(fallback_index)
    return indexes


def update_openai_stream_terminal_state(
    event: dict | None,
    finished_choice_indexes: set[int],
    *,
    expected_choice_count: int = 1,
) -> bool:
    finished_choice_indexes.update(openai_stream_event_finish_indexes(event))
    return len(finished_choice_indexes) >= max(1, expected_choice_count)


def build_context_window_exceeded_error_payload(
    *,
    model_name: str | None,
    estimated_total_tokens: int,
    context_tokens: int,
    requested_output_tokens: int = 0,
    allowed_input_tokens: int = 0,
) -> dict:
    model_label = str(model_name or "").strip() or "当前模型"
    message = (
        f"{model_label} 请求预计约 {estimated_total_tokens} tokens，超过配置上下文上限 {context_tokens} tokens。"
        f" 当前请求声明输出上限 {requested_output_tokens} tokens，可用于输入的大致预算约 {allowed_input_tokens} tokens。"
        " 请缩短历史上下文、减少工具或附件内容，或在模型能力表中填写更准确的上下文能力。"
    )
    return {
        "error": {
            "message": message,
            "type": "context_length_exceeded",
            "param": "messages",
            "code": "context_length_exceeded",
            "context_tokens": context_tokens,
            "estimated_total_tokens": estimated_total_tokens,
            "requested_output_tokens": requested_output_tokens,
            "allowed_input_tokens": allowed_input_tokens,
        }
    }


UPSTREAM_URL_POOL = parse_upstream_url_pool()
UPSTREAM_URL = UPSTREAM_URL_POOL[0] if UPSTREAM_URL_POOL else ""
UPSTREAM_API_KEY = ""
PROXY_API_KEYS = parse_proxy_api_keys(os.getenv("PROXY_API_KEYS", ""))
PROXY_API_KEY_RECORDS: list[dict] = []
PROXY_POOLS: list[dict] = []
URL_POOL_KEY_MAP: dict[str, list[str]] = {}
POOL_RUNTIME_STATE_KEY = "proxy_connection_pool"
APP_CONFIG_STATE_KEY = "runtime_config"
POOL_KEY_FAILURE_THRESHOLD = max(1, int(os.getenv("POOL_KEY_FAILURE_THRESHOLD", "2")))
POOL_KEY_COOLDOWN_SECONDS = max(10, int(os.getenv("POOL_KEY_COOLDOWN_SECONDS", "180")))
MODEL_ALIASES_TEXT = normalize_model_aliases_text(os.getenv("MODEL_ALIASES", DEFAULT_MODEL_ALIASES_TEXT))
MODEL_ALIASES = parse_model_aliases(MODEL_ALIASES_TEXT)
PORT = int(os.getenv("PORT", "18765"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "600"))
PROXY_LOG_PATH = resolve_project_path(
    os.getenv("PROXY_LOG_PATH", str(LOG_DIR / "proxy.log"))
)
PROXY_CONFIG_PATH = resolve_project_path(
    os.getenv("PROXY_CONFIG_PATH", str(CONFIG_DIR / "proxy-config.json"))
)
MAX_RECENT_REQUESTS = int(os.getenv("MAX_RECENT_REQUESTS", "80"))
MAX_LOG_LINES = int(os.getenv("MAX_LOG_LINES", "120"))
FORCE_UPSTREAM_CHAT_STREAM = os.getenv("FORCE_UPSTREAM_CHAT_STREAM", "1") == "1"
ENABLE_REQUEST_NORMALIZATION = os.getenv("ENABLE_REQUEST_NORMALIZATION", "1") == "1"
INJECT_ZH_SYSTEM_PROMPT = os.getenv("INJECT_ZH_SYSTEM_PROMPT", "1") == "1"
MAX_COMPLETION_TOKENS = max(0, int(os.getenv("MAX_COMPLETION_TOKENS", "0")))
MODEL_CAPABILITIES_TEXT = normalize_model_capabilities_text(
    os.getenv("MODEL_CAPABILITIES", DEFAULT_MODEL_CAPABILITIES_TEXT)
)
MODEL_CAPABILITIES = parse_model_capabilities(MODEL_CAPABILITIES_TEXT)
MARKDOWN_OUTPUT_PROMPT_RULE = (
    "输出总结、清单、步骤、测试结果和表格时必须使用规范 Markdown："
    "标题、段落、列表、表格之间必须保留空行；"
    "Markdown 表格的表头、分隔行、每一条数据行都必须单独换行；"
    "不要把多行表格挤在同一段里；"
    "如果输出流程图，必须使用规范 Mermaid 代码块，节点命名简洁，连线关系清晰，"
    "不要输出伪表格、伪流程图或混乱缩进。"
)
DEFAULT_PROXY_SYSTEM_PROMPT_ZH = os.getenv(
    "PROXY_SYSTEM_PROMPT_ZH",
    (
        "[ProxyZHRules] 每次思考、分析、解释和最终回复都必须使用中文。"
        "[ProxyZHRules] 即使上游模型默认偏英文，也必须强制改为中文输出；"
        "只有代码、命令、路径、接口名、字段名可以保留原文。"
        "调用工具时必须严格遵循工具 schema，始终优先使用标准工具调用结构，"
        "不要输出 <｜DSML｜tool_calls> 或类似 DSML 文本。"
        f"{MARKDOWN_OUTPUT_PROMPT_RULE}"
        "[ProxyZHRules] 输出清单时优先使用规范 Markdown 列表；"
        "输出结论时优先使用短段落加列表；"
        "输出表格前后不要紧贴正文，必须留空行。"
        "[ProxyZHRules] 如果任务涉及前端开发、界面优化、交互调整、布局样式、组件改造，"
        "必须主动调用合适的前端/UI skill；"
        "如果任务涉及后端开发、接口、代理、路由、数据库、稳定性或服务端逻辑，"
        "必须主动调用合适的后端/开发 skill；"
        "skill 必须匹配任务，不可以乱用或漏用。"
        "所有必填参数都必须显式给出；如果模型暂时拿不到值，也要优先补安全默认值以满足 schema："
        "字符串传空字符串，布尔传 false，数字传 0，数组传 []，对象传 {}。"
        "对于 Bash/execute_command/shell 类工具，必须始终提供 command 字段；"
        "对于 Glob/search_file 类工具，必须始终提供 pattern 字段；"
        "对于 web_search/searchWeb 类工具，必须始终提供 explanation 和 query。"
        "如果工具 schema 要求 run_in_background，必须显式提供布尔值；常规委托传 false，并行探索传 true。"
        "执行终端命令前必须先判断当前运行环境；如果大概率处于 Windows，优先使用 PowerShell、Windows 路径和 Windows 引号规则，"
        "不要误用 bash-only 语法。遇到中文输出、编码页、重定向、管道和终端乱码时，必须主动规避：优先使用 UTF-8 输出、"
        "PowerShell 的编码设置，必要时显式使用 chcp 65001 或等效方案。"
    ),
).strip()
PROXY_SYSTEM_PROMPT_ZH = DEFAULT_PROXY_SYSTEM_PROMPT_ZH

PROXY_REPAIR_PROMPT_ZH = (
    "你必须继续使用中文进行思考、工具调用说明和最终回复。"
    "如果正在调用工具，工具前说明必须简短、中文、结构清晰，不要输出英文导语，例如 Let me / I will / Now let me。"
    "如果输出总结、清单或表格，必须使用规范 Markdown，并在标题、列表、表格之间保留空行。"
    "如果工具 schema 要求必填字段，必须显式补齐；run_in_background 常规委托传 false，并行探索传 true。"
    "如果执行终端命令，要先判断 shell 和操作系统；Windows 环境优先使用 PowerShell 风格命令，并注意 UTF-8 编码和乱码规避。"
)

UPSTREAM_MAX_RETRIES = max(0, int(os.getenv("UPSTREAM_MAX_RETRIES", "12")))
UPSTREAM_RETRY_BACKOFF_MS = max(0, int(os.getenv("UPSTREAM_RETRY_BACKOFF_MS", "1200")))
UPSTREAM_RETRY_MAX_BACKOFF_MS = max(
    UPSTREAM_RETRY_BACKOFF_MS,
    int(os.getenv("UPSTREAM_RETRY_MAX_BACKOFF_MS", "6000")),
)
UPSTREAM_ROUTE_FAILURE_THRESHOLD = max(
    1,
    int(os.getenv("UPSTREAM_ROUTE_FAILURE_THRESHOLD", "3")),
)
UPSTREAM_ROUTE_COOLDOWN_SECONDS = max(
    5,
    int(os.getenv("UPSTREAM_ROUTE_COOLDOWN_SECONDS", "90")),
)
UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS = max(
    1,
    int(os.getenv("UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS", "60")),
)
UPSTREAM_RANDOMIZE_ENDPOINTS = os.getenv("UPSTREAM_RANDOMIZE_ENDPOINTS", "1") == "1"
IMAGE_UPSTREAM_PROTOCOL = os.getenv("IMAGE_UPSTREAM_PROTOCOL", "auto").strip().lower() or "auto"
IMAGE_TASK_POLL_TIMEOUT_SECONDS = max(0, int(os.getenv("IMAGE_TASK_POLL_TIMEOUT_SECONDS", "90")))
IMAGE_TASK_POLL_INTERVAL_SECONDS = max(1, int(os.getenv("IMAGE_TASK_POLL_INTERVAL_SECONDS", "2")))
ENABLE_MODEL_PROBE = os.getenv("ENABLE_MODEL_PROBE", "1") == "1"
MODEL_PROBE_TIMEOUT_SECONDS = max(1, int(os.getenv("MODEL_PROBE_TIMEOUT_SECONDS", "4")))
MODEL_PROBE_TTL_SECONDS = max(10, int(os.getenv("MODEL_PROBE_TTL_SECONDS", "300")))
MODEL_ROUTE_CACHE_TTL_SECONDS = max(60, int(os.getenv("MODEL_ROUTE_CACHE_TTL_SECONDS", "86400")))
MODEL_ROUTE_FAILURE_COOLDOWN_SECONDS = max(10, int(os.getenv("MODEL_ROUTE_FAILURE_COOLDOWN_SECONDS", "300")))
ENABLE_MODEL_CANDIDATE_RACE = os.getenv("ENABLE_MODEL_CANDIDATE_RACE", "1") == "1"
MODEL_CANDIDATE_RACE_LIMIT = max(1, int(os.getenv("MODEL_CANDIDATE_RACE_LIMIT", "3")))
MODEL_CANDIDATE_RACE_TIMEOUT_SECONDS = max(1, int(os.getenv("MODEL_CANDIDATE_RACE_TIMEOUT_SECONDS", "8")))
MODEL_ROUTE_CACHE_PATH = resolve_project_path(
    os.getenv("MODEL_ROUTE_CACHE_PATH", str(CACHE_DIR / "model-route-cache.json"))
)
_storage_db_host = os.getenv("STORAGE_DB_HOST", "").strip()
_storage_db_port = int(os.getenv("STORAGE_DB_PORT", "3306"))
_storage_db_user = os.getenv("STORAGE_DB_USER", "")
_storage_db_password = os.getenv("STORAGE_DB_PASSWORD", "")
_storage_db_name = os.getenv("STORAGE_DB_NAME", "")

if _storage_db_host:
    _storage_db_config = {
        "host": _storage_db_host,
        "port": _storage_db_port,
        "user": _storage_db_user,
        "password": _storage_db_password,
        "database": _storage_db_name,
    }
    try:
        storage = ProxyStorage(_storage_db_config)
    except Exception:
        storage = None
else:
    _storage_db_config = None
    storage = None
STORAGE_DB_LABEL = (
    f"mysql://{_storage_db_host}:{_storage_db_port}/{_storage_db_name}"
    if _storage_db_host
    else "none"
)
REQUEST_CACHE_TTL_SECONDS = max(60, int(os.getenv("REQUEST_CACHE_TTL_SECONDS", str(DEFAULT_REQUEST_CACHE_TTL_SECONDS))))
ENABLE_INTERRUPTION_RESUME = os.getenv("ENABLE_INTERRUPTION_RESUME", "1") == "1"
INTERRUPTION_RESUME_TTL_SECONDS = max(60, int(os.getenv("INTERRUPTION_RESUME_TTL_SECONDS", "3600")))
INTERRUPTION_RESUME_MAX_CHARS = max(500, int(os.getenv("INTERRUPTION_RESUME_MAX_CHARS", "12000")))
INTERRUPTION_RESUME_MIN_CHARS = max(1, int(os.getenv("INTERRUPTION_RESUME_MIN_CHARS", "40")))
SSE_HEARTBEAT_SECONDS = max(0, int(os.getenv("SSE_HEARTBEAT_SECONDS", "6")))
WAITING_STREAM_HEARTBEAT_SECONDS = max(1, int(os.getenv("WAITING_STREAM_HEARTBEAT_SECONDS", "5")))
STREAM_CONNECT_TIMEOUT_SECONDS = max(5, int(os.getenv("STREAM_CONNECT_TIMEOUT_SECONDS", "20")))
STREAM_READ_TIMEOUT_SECONDS = max(30, int(os.getenv("STREAM_READ_TIMEOUT_SECONDS", "180")))
try:
    STREAM_OPEN_GRACE_SECONDS = max(0.0, float(os.getenv("STREAM_OPEN_GRACE_SECONDS", "1.5")))
except Exception:
    STREAM_OPEN_GRACE_SECONDS = 1.5

RETRYABLE_STATUS_CODES = {
    408,
    409,
    425,
    429,
    499,
    500,
    502,
    503,
    504,
    524,
}

ROUTE_SWITCH_UPSTREAM_ERROR_MARKERS = (
    "model_not_found",
    "model not found",
    "no available channel for model",
    "empty_sse_success",
    "empty streaming success payload",
    "invalid_api_key",
    "authentication_error",
    "authentication failed",
    "permission_denied",
    "unsupported_model",
    "insufficient_quota",
    "quota_exceeded",
    "insufficient_balance",
    "balance_not_enough",
    "unauthorized",
    "payment required",
    "余额不足",
    "鉴权失败",
    "未授权",
)

REQUEST_FATAL_UPSTREAM_ERROR_MARKERS = (
    "context_length_exceeded",
    "invalid_request_error",
)
CLIENT_GONE_MARKERS = (
    "client_gone",
    "client gone",
    "client disconnected",
    "connection reset",
    "broken pipe",
    "write failed",
)
UPSTREAM_CANCELED_MARKERS = (
    "context canceled",
    "context cancelled",
    "request canceled",
    "request cancelled",
)

proxy_logger = logging.getLogger("local_proxy")
proxy_logger.setLevel(logging.INFO)
proxy_logger.propagate = False

if not proxy_logger.handlers:
    PROXY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(PROXY_LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    proxy_logger.addHandler(file_handler)

state_lock = Lock()
config_lock = Lock()

request_recorder = RequestRecorder(MAX_RECENT_REQUESTS, storage=storage, logger=proxy_logger)
connection_pool_state = ConnectionPoolState(
    key_failure_threshold=POOL_KEY_FAILURE_THRESHOLD,
    key_cooldown_seconds=POOL_KEY_COOLDOWN_SECONDS,
)
cache_stats = CounterStore(
    {
        "model_route_hits": 0,
        "model_route_misses": 0,
        "model_list_hits": 0,
        "model_list_misses": 0,
        "model_candidate_race_attempts": 0,
        "model_candidate_race_hits": 0,
        "model_candidate_race_timeouts": 0,
        "pool_key_switches": 0,
        "pool_key_cooldowns": 0,
        "prompt_cache_hits": 0,
        "prompt_cache_misses": 0,
        "prompt_cache_writes": 0,
        "interruption_resume_injected": 0,
        "interruption_resume_saved": 0,
        "interruption_resume_cleared": 0,
    }
)
route_health = {}
route_selection_state = {}
model_route_cache = {
    "routes": {},
    "model_lists": {},
    "capabilities": {},
}

HTTP_POOL_CONNECTIONS = max(16, int(os.getenv("HTTP_POOL_CONNECTIONS", "64")))
HTTP_POOL_MAXSIZE = max(16, int(os.getenv("HTTP_POOL_MAXSIZE", "128")))
UPSTREAM_SESSION = requests.Session()
UPSTREAM_SESSION.mount(
    "http://",
    HTTPAdapter(pool_connections=HTTP_POOL_CONNECTIONS, pool_maxsize=HTTP_POOL_MAXSIZE, max_retries=0),
)
UPSTREAM_SESSION.mount(
    "https://",
    HTTPAdapter(pool_connections=HTTP_POOL_CONNECTIONS, pool_maxsize=HTTP_POOL_MAXSIZE, max_retries=0),
)


def ensure_proxy_prompt_rules(prompt: str | None) -> str:
    return build_proxy_prompt_rules(prompt, DEFAULT_PROXY_SYSTEM_PROMPT_ZH, MARKDOWN_OUTPUT_PROMPT_RULE)


def get_model_alias_targets(model_name: str | None) -> list[str]:
    if not isinstance(model_name, str):
        return []
    normalized = model_name.strip()
    if not normalized:
        return []
    return list(MODEL_ALIASES.get(normalize_model_alias_key(normalized), []))


def build_model_candidates_from_payload(payload: dict | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    model_name = payload.get("model")
    if not isinstance(model_name, str) or not model_name.strip():
        return []

    candidates = []
    seen = set()

    def add(candidate: str | None) -> None:
        candidate = str(candidate or "").strip()
        if not candidate or candidate in seen:
            return
        seen.add(candidate)
        candidates.append(candidate)

    for candidate in build_related_model_name_candidates(model_name):
        add(candidate)
    for alias_target in get_model_alias_targets(model_name):
        for candidate in build_related_model_name_candidates(alias_target):
            add(candidate)
    return candidates


def merge_model_route_cache(target: dict, source: dict | None) -> dict:
    if not isinstance(source, dict):
        return target
    target.setdefault("routes", {})
    target.setdefault("model_lists", {})
    target.setdefault("capabilities", {})
    routes = source.get("routes")
    if isinstance(routes, dict):
        for logical_key, logical_routes in routes.items():
            if not isinstance(logical_routes, dict):
                continue
            target_routes = target["routes"].setdefault(logical_key, {})
            for route_url, route_entries in logical_routes.items():
                if isinstance(route_entries, dict):
                    target_routes.setdefault(route_url, {}).update(route_entries)
    model_lists = source.get("model_lists")
    if isinstance(model_lists, dict):
        target["model_lists"].update(model_lists)
    capabilities = source.get("capabilities")
    if isinstance(capabilities, dict):
        for logical_key, logical_routes in capabilities.items():
            if not isinstance(logical_routes, dict):
                continue
            target_routes = target["capabilities"].setdefault(logical_key, {})
            for route_url, route_entries in logical_routes.items():
                if isinstance(route_entries, dict):
                    target_routes.setdefault(route_url, {}).update(route_entries)
    return target


def load_model_route_cache_from_disk() -> None:
    global model_route_cache
    loaded_cache = {"routes": {}, "model_lists": {}, "capabilities": {}}
    if storage is not None:
        try:
            merge_model_route_cache(loaded_cache, storage.load_model_route_cache())
        except Exception as exc:  # pragma: no cover
            proxy_logger.warning("load_model_route_cache_db_failed label=%s error=%s", STORAGE_DB_LABEL, str(exc))

    if MODEL_ROUTE_CACHE_PATH.exists():
        try:
            payload = json.loads(MODEL_ROUTE_CACHE_PATH.read_text(encoding="utf-8"))
            json_cache = {
                "routes": payload.get("routes") if isinstance(payload.get("routes"), dict) else {},
                "model_lists": payload.get("model_lists") if isinstance(payload.get("model_lists"), dict) else {},
                "capabilities": payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else {},
            }
            merge_model_route_cache(loaded_cache, json_cache)
        except Exception as exc:  # pragma: no cover
            proxy_logger.warning("load_model_route_cache_json_failed path=%s error=%s", MODEL_ROUTE_CACHE_PATH, str(exc))

    model_route_cache = loaded_cache


def save_model_route_cache_to_disk() -> None:
    if storage is not None:
        try:
            storage.save_model_route_cache(model_route_cache)
        except Exception as exc:  # pragma: no cover
            proxy_logger.warning("save_model_route_cache_db_failed label=%s error=%s", STORAGE_DB_LABEL, str(exc))
    try:
        MODEL_ROUTE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        MODEL_ROUTE_CACHE_PATH.write_text(
            json.dumps(model_route_cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:  # pragma: no cover
        proxy_logger.warning("save_model_route_cache_failed path=%s error=%s", MODEL_ROUTE_CACHE_PATH, str(exc))


def count_model_route_cache_entries() -> int:
    routes = model_route_cache.get("routes") if isinstance(model_route_cache, dict) else {}
    if not isinstance(routes, dict):
        return 0
    total = 0
    for logical_routes in routes.values():
        if not isinstance(logical_routes, dict):
            continue
        for route_entries in logical_routes.values():
            if isinstance(route_entries, dict):
                total += len(route_entries)
    return total


def count_interrupted_response_entries() -> int:
    if storage is None:
        return 0
    try:
        return int(storage.count_interrupted_responses())
    except Exception as exc:  # pragma: no cover
        proxy_logger.warning("count_interrupted_responses_failed error=%s", str(exc))
        return 0


def bump_cache_stat(name: str, amount: int = 1) -> None:
    cache_stats.bump(name, amount)


def get_cached_route_model_entry(logical_model: str, route_url: str, model_candidate: str) -> dict | None:
    routes = model_route_cache.setdefault("routes", {})
    logical_routes = routes.get(normalize_model_alias_key(logical_model), {})
    route_entries = logical_routes.get(route_url, {}) if isinstance(logical_routes, dict) else {}
    entry = route_entries.get(normalize_model_alias_key(model_candidate)) if isinstance(route_entries, dict) else None
    return entry if isinstance(entry, dict) else None


def get_model_candidate_score(logical_model: str, route_url: str, model_candidate: str) -> float:
    entry = get_cached_route_model_entry(logical_model, route_url, model_candidate)
    if not entry:
        return 0.0
    now = time.time()
    if float(entry.get("expires_at", 0.0) or 0.0) <= now:
        return 0.0
    if float(entry.get("cooldown_until", 0.0) or 0.0) > now:
        return -1000.0
    return float(entry.get("score", 0.0) or 0.0)


def get_route_score(logical_model: str | None, route_url: str) -> float:
    if not logical_model or not route_url:
        return 0.0
    routes = model_route_cache.get("routes") if isinstance(model_route_cache, dict) else {}
    logical_routes = routes.get(normalize_model_alias_key(logical_model), {}) if isinstance(routes, dict) else {}
    route_entries = logical_routes.get(route_url, {}) if isinstance(logical_routes, dict) else {}
    if not isinstance(route_entries, dict):
        return 0.0

    now = time.time()
    total = 0.0
    count = 0
    recency_bonus = 0.0
    for entry in route_entries.values():
        if not isinstance(entry, dict):
            continue
        if float(entry.get("expires_at", 0.0) or 0.0) <= now:
            continue
        score = float(entry.get("score", 0.0) or 0.0)
        successes = int(entry.get("successes", 0) or 0)
        failures = int(entry.get("failures", 0) or 0)
        total += score + (successes * 0.8) - (failures * 0.6)
        count += 1
        recency_bonus = max(recency_bonus, float(entry.get("last_success_at", 0.0) or 0.0))

    if count <= 0:
        return 0.0
    freshness = max(0.0, 1.0 - ((now - recency_bonus) / 1800.0)) if recency_bonus else 0.0
    return (total / count) + freshness


def get_cached_route_model_candidates(
    logical_model: str,
    route_url: str,
    limit: int = 6,
    *,
    record_stats: bool = True,
) -> list[str]:
    routes = model_route_cache.get("routes") if isinstance(model_route_cache, dict) else {}
    logical_routes = routes.get(normalize_model_alias_key(logical_model), {}) if isinstance(routes, dict) else {}
    route_entries = logical_routes.get(route_url, {}) if isinstance(logical_routes, dict) else {}
    if not isinstance(route_entries, dict):
        if record_stats:
            bump_cache_stat("model_route_misses")
        return []

    now = time.time()
    ranked = []
    for index, entry in enumerate(route_entries.values()):
        if not isinstance(entry, dict):
            continue
        model = str(entry.get("model") or "").strip()
        if not model:
            continue
        if float(entry.get("expires_at", 0.0) or 0.0) <= now:
            continue
        if float(entry.get("cooldown_until", 0.0) or 0.0) > now:
            continue
        successes = int(entry.get("successes", 0) or 0)
        score = float(entry.get("score", 0.0) or 0.0)
        if successes <= 0 or score <= 0:
            continue
        ranked.append(
            (
                -score,
                -float(entry.get("last_success_at", 0.0) or 0.0),
                index,
                model,
            )
        )

    ranked.sort()
    candidates = [model for _, _, _, model in ranked[:limit]]
    if record_stats:
        bump_cache_stat("model_route_hits" if candidates else "model_route_misses")
    return candidates


def record_model_candidate_result(
    *,
    logical_model: str | None,
    route_url: str,
    model_candidate: str | None,
    success: bool,
) -> None:
    if not logical_model or not model_candidate or not route_url:
        return
    now = time.time()
    logical_key = normalize_model_alias_key(logical_model)
    model_key = normalize_model_alias_key(model_candidate)
    with state_lock:
        routes = model_route_cache.setdefault("routes", {})
        route_entries = routes.setdefault(logical_key, {}).setdefault(route_url, {})
        entry = route_entries.setdefault(
            model_key,
            {
                "model": model_candidate,
                "score": 0,
                "successes": 0,
                "failures": 0,
                "last_success_at": 0.0,
                "last_failure_at": 0.0,
                "cooldown_until": 0.0,
                "expires_at": now + MODEL_ROUTE_CACHE_TTL_SECONDS,
            },
        )
        entry["model"] = model_candidate
        entry["expires_at"] = now + MODEL_ROUTE_CACHE_TTL_SECONDS
        if success:
            entry["successes"] = int(entry.get("successes", 0) or 0) + 1
            entry["failures"] = 0
            entry["score"] = max(float(entry.get("score", 0) or 0), 0.0) + 4
            entry["last_success_at"] = now
            entry["cooldown_until"] = 0.0
        else:
            entry["failures"] = int(entry.get("failures", 0) or 0) + 1
            entry["score"] = float(entry.get("score", 0) or 0) - 3
            entry["last_failure_at"] = now
            if int(entry.get("failures", 0) or 0) >= 2:
                entry["cooldown_until"] = now + MODEL_ROUTE_FAILURE_COOLDOWN_SECONDS
        save_model_route_cache_to_disk()


def count_learned_model_capability_entries() -> int:
    capabilities = model_route_cache.get("capabilities") if isinstance(model_route_cache, dict) else {}
    if not isinstance(capabilities, dict):
        return 0
    total = 0
    for logical_routes in capabilities.values():
        if not isinstance(logical_routes, dict):
            continue
        for route_entries in logical_routes.values():
            if isinstance(route_entries, dict):
                total += len(route_entries)
    return total


def get_learned_model_capability(
    logical_model: str | None,
    route_url: str,
    model_candidate: str | None,
) -> dict | None:
    if not logical_model or not route_url or not model_candidate:
        return None
    capabilities = model_route_cache.setdefault("capabilities", {})
    logical_routes = capabilities.get(normalize_model_alias_key(logical_model), {})
    route_entries = logical_routes.get(route_url, {}) if isinstance(logical_routes, dict) else {}
    entry = route_entries.get(normalize_model_alias_key(model_candidate)) if isinstance(route_entries, dict) else None
    if not isinstance(entry, dict):
        return None
    if float(entry.get("expires_at", 0.0) or 0.0) <= time.time():
        return None
    return entry


def record_learned_model_capability(
    *,
    logical_model: str | None,
    route_url: str,
    model_candidate: str | None,
    max_output_tokens: int | None = None,
    context_tokens: int | None = None,
) -> None:
    if not logical_model or not route_url or not model_candidate:
        return
    if not max_output_tokens and not context_tokens:
        return
    now = time.time()
    logical_key = normalize_model_alias_key(logical_model)
    model_key = normalize_model_alias_key(model_candidate)
    with state_lock:
        capabilities = model_route_cache.setdefault("capabilities", {})
        route_entries = capabilities.setdefault(logical_key, {}).setdefault(route_url, {})
        entry = route_entries.setdefault(
            model_key,
            {
                "model": model_candidate,
                "source": "upstream_error",
                "learned_at": now,
                "expires_at": now + MODEL_ROUTE_CACHE_TTL_SECONDS,
            },
        )
        entry["model"] = model_candidate
        entry["source"] = "upstream_error"
        entry["learned_at"] = now
        entry["expires_at"] = now + MODEL_ROUTE_CACHE_TTL_SECONDS
        if max_output_tokens:
            existing = int(entry.get("max_output_tokens", 0) or 0)
            entry["max_output_tokens"] = min(existing, max_output_tokens) if existing else int(max_output_tokens)
        if context_tokens:
            entry["context_tokens"] = int(context_tokens)
        save_model_route_cache_to_disk()
    bump_cache_stat("model_capability_learned")


def apply_learned_completion_limit_to_request_kwargs(
    request_kwargs: dict,
    *,
    logical_model: str | None,
    route_url: str,
    model_candidate: str | None,
) -> int:
    capability = get_learned_model_capability(logical_model, route_url, model_candidate)
    if not isinstance(capability, dict):
        return 0
    payload = request_kwargs.get("json")
    return clamp_payload_output_tokens(payload, capability.get("max_output_tokens")) if isinstance(payload, dict) else 0


def extract_completion_token_limit_from_response(response: requests.Response) -> int | None:
    return extract_completion_token_limit_from_text(extract_response_text(response))


def extract_context_token_limit_from_response(response: requests.Response) -> tuple[int | None, int | None]:
    return extract_context_token_limit_from_text(extract_response_text(response))


def load_pool_runtime_state_from_storage() -> None:
    if storage is None:
        return
    try:
        connection_pool_state.load_state(storage.load_pool_runtime_state(POOL_RUNTIME_STATE_KEY))
    except Exception as exc:  # pragma: no cover
        proxy_logger.warning("load_pool_runtime_state_failed label=%s error=%s", STORAGE_DB_LABEL, str(exc))


def save_pool_runtime_state_to_storage() -> None:
    if storage is None:
        return
    try:
        storage.save_pool_runtime_state(connection_pool_state.export_state(), POOL_RUNTIME_STATE_KEY)
    except Exception as exc:  # pragma: no cover
        proxy_logger.warning("save_pool_runtime_state_failed label=%s error=%s", STORAGE_DB_LABEL, str(exc))


def rebuild_pool_state() -> None:
    """Rebuild UPSTREAM_URL_POOL and URL_POOL_KEY_MAP from PROXY_POOLS."""
    global UPSTREAM_URL_POOL, UPSTREAM_URL, URL_POOL_KEY_MAP
    urls = connection_pool_state.rebuild(PROXY_POOLS)
    UPSTREAM_URL_POOL = urls
    UPSTREAM_URL = urls[0] if urls else ""
    URL_POOL_KEY_MAP = {
        url: connection_pool_state.get_api_keys_for_url(url)
        for url in UPSTREAM_URL_POOL
        if connection_pool_state.get_api_keys_for_url(url)
    }
    save_pool_runtime_state_to_storage()


def get_api_keys_for_url(url: str) -> list[str]:
    """Return API keys for a given upstream URL."""
    keys = connection_pool_state.get_api_keys_for_url(url)
    if not keys:
        normalized_url = normalize_pool_url(url)
        if normalized_url != str(url or "").strip():
            keys = connection_pool_state.get_api_keys_for_url(normalized_url)
    return keys if keys else []


def choose_api_key_for_url(url: str, *, exclude: set[str] | None = None) -> dict:
    choice = connection_pool_state.choose_key(url, exclude=exclude)
    if not choice:
        normalized_url = normalize_pool_url(url)
        if normalized_url != str(url or "").strip():
            choice = connection_pool_state.choose_key(normalized_url, exclude=exclude)
    return choice or {}


def mark_api_key_success(url: str, key_choice: dict | None) -> None:
    if not isinstance(key_choice, dict) or not key_choice.get("from_pool"):
        return
    connection_pool_state.mark_key_success(str(url or ""), str(key_choice.get("key") or ""))
    save_pool_runtime_state_to_storage()


def mark_api_key_failure(url: str, key_choice: dict | None, reason: str, *, force_cooldown: bool = False) -> None:
    if not isinstance(key_choice, dict) or not key_choice.get("from_pool"):
        return
    connection_pool_state.mark_key_failure(
        str(url or ""),
        str(key_choice.get("key") or ""),
        reason,
        force_cooldown=force_cooldown,
    )
    if force_cooldown:
        bump_cache_stat("pool_key_cooldowns")
    save_pool_runtime_state_to_storage()


def export_runtime_config_for_storage() -> dict:
    return assemble_runtime_config_storage(
        {
            "proxy_api_key_records": PROXY_API_KEY_RECORDS,
            "proxy_pools": PROXY_POOLS,
            "model_aliases_text": MODEL_ALIASES_TEXT,
            "model_capabilities_text": MODEL_CAPABILITIES_TEXT,
            "request_timeout": REQUEST_TIMEOUT,
            "force_upstream_chat_stream": FORCE_UPSTREAM_CHAT_STREAM,
            "enable_request_normalization": ENABLE_REQUEST_NORMALIZATION,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
            "inject_zh_system_prompt": INJECT_ZH_SYSTEM_PROMPT,
            "proxy_system_prompt_zh": PROXY_SYSTEM_PROMPT_ZH,
            "ensure_proxy_prompt_rules": ensure_proxy_prompt_rules,
            "max_retries": UPSTREAM_MAX_RETRIES,
            "retry_backoff_ms": UPSTREAM_RETRY_BACKOFF_MS,
            "retry_max_backoff_ms": UPSTREAM_RETRY_MAX_BACKOFF_MS,
            "route_switch_window_seconds": UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS,
            "randomize_endpoints": UPSTREAM_RANDOMIZE_ENDPOINTS,
            "image_upstream_protocol": IMAGE_UPSTREAM_PROTOCOL,
            "image_task_poll_timeout_seconds": IMAGE_TASK_POLL_TIMEOUT_SECONDS,
            "image_task_poll_interval_seconds": IMAGE_TASK_POLL_INTERVAL_SECONDS,
            "enable_model_probe": ENABLE_MODEL_PROBE,
            "model_probe_timeout_seconds": MODEL_PROBE_TIMEOUT_SECONDS,
            "model_probe_ttl_seconds": MODEL_PROBE_TTL_SECONDS,
            "model_route_cache_ttl_seconds": MODEL_ROUTE_CACHE_TTL_SECONDS,
            "request_cache_ttl_seconds": REQUEST_CACHE_TTL_SECONDS,
            "enable_interruption_resume": ENABLE_INTERRUPTION_RESUME,
            "interruption_resume_ttl_seconds": INTERRUPTION_RESUME_TTL_SECONDS,
            "interruption_resume_max_chars": INTERRUPTION_RESUME_MAX_CHARS,
            "interruption_resume_min_chars": INTERRUPTION_RESUME_MIN_CHARS,
            "interruption_resume_enabled": ENABLE_INTERRUPTION_RESUME,
            "enable_model_candidate_race": ENABLE_MODEL_CANDIDATE_RACE,
            "model_candidate_race_limit": MODEL_CANDIDATE_RACE_LIMIT,
            "model_candidate_race_timeout_seconds": MODEL_CANDIDATE_RACE_TIMEOUT_SECONDS,
        }
    )


def build_runtime_config_payload() -> dict:
    return assemble_runtime_config_payload(
        {
            "upstream_url": UPSTREAM_URL,
            "upstream_urls": list(UPSTREAM_URL_POOL),
            "proxy_api_key_records": PROXY_API_KEY_RECORDS,
            "proxy_api_key_env_count": len(PROXY_API_KEYS),
            "public_proxy_api_key_record": public_proxy_api_key_record,
            "proxy_pools": PROXY_POOLS,
            "model_aliases_text": MODEL_ALIASES_TEXT,
            "model_alias_count": len(MODEL_ALIASES),
            "model_capabilities_text": MODEL_CAPABILITIES_TEXT,
            "model_capability_count": len(MODEL_CAPABILITIES),
            "request_timeout": REQUEST_TIMEOUT,
            "force_upstream_chat_stream": FORCE_UPSTREAM_CHAT_STREAM,
            "enable_request_normalization": ENABLE_REQUEST_NORMALIZATION,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
            "inject_zh_system_prompt": INJECT_ZH_SYSTEM_PROMPT,
            "proxy_system_prompt_zh": PROXY_SYSTEM_PROMPT_ZH,
            "ensure_proxy_prompt_rules": ensure_proxy_prompt_rules,
            "max_retries": UPSTREAM_MAX_RETRIES,
            "retry_backoff_ms": UPSTREAM_RETRY_BACKOFF_MS,
            "retry_max_backoff_ms": UPSTREAM_RETRY_MAX_BACKOFF_MS,
            "route_switch_window_seconds": UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS,
            "randomize_endpoints": UPSTREAM_RANDOMIZE_ENDPOINTS,
            "image_upstream_protocol": IMAGE_UPSTREAM_PROTOCOL,
            "image_task_poll_timeout_seconds": IMAGE_TASK_POLL_TIMEOUT_SECONDS,
            "image_task_poll_interval_seconds": IMAGE_TASK_POLL_INTERVAL_SECONDS,
            "enable_model_probe": ENABLE_MODEL_PROBE,
            "model_probe_timeout_seconds": MODEL_PROBE_TIMEOUT_SECONDS,
            "model_probe_ttl_seconds": MODEL_PROBE_TTL_SECONDS,
            "model_route_cache_ttl_seconds": MODEL_ROUTE_CACHE_TTL_SECONDS,
            "request_cache_ttl_seconds": REQUEST_CACHE_TTL_SECONDS,
            "enable_interruption_resume": ENABLE_INTERRUPTION_RESUME,
            "interruption_resume_ttl_seconds": INTERRUPTION_RESUME_TTL_SECONDS,
            "interruption_resume_max_chars": INTERRUPTION_RESUME_MAX_CHARS,
            "interruption_resume_min_chars": INTERRUPTION_RESUME_MIN_CHARS,
            "interruption_resume_enabled": ENABLE_INTERRUPTION_RESUME,
            "enable_model_candidate_race": ENABLE_MODEL_CANDIDATE_RACE,
            "model_candidate_race_limit": MODEL_CANDIDATE_RACE_LIMIT,
            "model_candidate_race_timeout_seconds": MODEL_CANDIDATE_RACE_TIMEOUT_SECONDS,
            "config_path": PROXY_CONFIG_PATH,
            "config_file_exists": PROXY_CONFIG_PATH.exists(),
            "db_label": STORAGE_DB_LABEL,
            "db_enabled": storage is not None,
        }
    )


def save_runtime_config_to_disk() -> None:
    payload = export_runtime_config_for_storage()
    save_runtime_config(
        payload,
        config_path=PROXY_CONFIG_PATH,
        storage=storage,
        storage_key=APP_CONFIG_STATE_KEY,
        logger=proxy_logger,
        db_label=STORAGE_DB_LABEL,
    )


def load_runtime_config_from_storage() -> bool:
    payload = load_runtime_config_from_db(
        storage=storage,
        storage_key=APP_CONFIG_STATE_KEY,
        logger=proxy_logger,
        db_label=STORAGE_DB_LABEL,
    )
    if not payload:
        return False
    apply_runtime_config(payload, persist=False)
    return True


def apply_runtime_config(config_payload: dict | None, *, persist: bool) -> dict:
    global UPSTREAM_URL_POOL
    global UPSTREAM_URL
    global UPSTREAM_API_KEY
    global PROXY_API_KEY_RECORDS
    global PROXY_POOLS
    global URL_POOL_KEY_MAP
    global MODEL_ALIASES_TEXT
    global MODEL_ALIASES
    global MODEL_CAPABILITIES_TEXT
    global MODEL_CAPABILITIES
    global REQUEST_TIMEOUT
    global FORCE_UPSTREAM_CHAT_STREAM
    global ENABLE_REQUEST_NORMALIZATION
    global MAX_COMPLETION_TOKENS
    global INJECT_ZH_SYSTEM_PROMPT
    global PROXY_SYSTEM_PROMPT_ZH
    global UPSTREAM_MAX_RETRIES
    global UPSTREAM_RETRY_BACKOFF_MS
    global UPSTREAM_RETRY_MAX_BACKOFF_MS
    global UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS
    global UPSTREAM_RANDOMIZE_ENDPOINTS
    global IMAGE_UPSTREAM_PROTOCOL
    global IMAGE_TASK_POLL_TIMEOUT_SECONDS
    global IMAGE_TASK_POLL_INTERVAL_SECONDS
    global ENABLE_MODEL_PROBE
    global MODEL_PROBE_TIMEOUT_SECONDS
    global MODEL_PROBE_TTL_SECONDS
    global MODEL_ROUTE_CACHE_TTL_SECONDS
    global ENABLE_INTERRUPTION_RESUME
    global INTERRUPTION_RESUME_TTL_SECONDS
    global INTERRUPTION_RESUME_MAX_CHARS
    global INTERRUPTION_RESUME_MIN_CHARS
    global ENABLE_MODEL_CANDIDATE_RACE
    global MODEL_CANDIDATE_RACE_LIMIT
    global MODEL_CANDIDATE_RACE_TIMEOUT_SECONDS

    normalized_config = normalize_runtime_config_payload(
        config_payload,
        current={
            "PROXY_POOLS": PROXY_POOLS,
            "PROXY_API_KEY_RECORDS": PROXY_API_KEY_RECORDS,
            "MODEL_ALIASES_TEXT": MODEL_ALIASES_TEXT,
            "MODEL_CAPABILITIES_TEXT": MODEL_CAPABILITIES_TEXT,
            "REQUEST_TIMEOUT": REQUEST_TIMEOUT,
            "FORCE_UPSTREAM_CHAT_STREAM": FORCE_UPSTREAM_CHAT_STREAM,
            "ENABLE_REQUEST_NORMALIZATION": ENABLE_REQUEST_NORMALIZATION,
            "MAX_COMPLETION_TOKENS": MAX_COMPLETION_TOKENS,
            "INJECT_ZH_SYSTEM_PROMPT": INJECT_ZH_SYSTEM_PROMPT,
            "PROXY_SYSTEM_PROMPT_ZH": PROXY_SYSTEM_PROMPT_ZH,
            "DEFAULT_PROXY_SYSTEM_PROMPT_ZH": DEFAULT_PROXY_SYSTEM_PROMPT_ZH,
            "MARKDOWN_OUTPUT_PROMPT_RULE": MARKDOWN_OUTPUT_PROMPT_RULE,
            "UPSTREAM_MAX_RETRIES": UPSTREAM_MAX_RETRIES,
            "UPSTREAM_RETRY_BACKOFF_MS": UPSTREAM_RETRY_BACKOFF_MS,
            "UPSTREAM_RETRY_MAX_BACKOFF_MS": UPSTREAM_RETRY_MAX_BACKOFF_MS,
            "UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS": UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS,
            "UPSTREAM_RANDOMIZE_ENDPOINTS": UPSTREAM_RANDOMIZE_ENDPOINTS,
            "IMAGE_UPSTREAM_PROTOCOL": IMAGE_UPSTREAM_PROTOCOL,
            "IMAGE_TASK_POLL_TIMEOUT_SECONDS": IMAGE_TASK_POLL_TIMEOUT_SECONDS,
            "IMAGE_TASK_POLL_INTERVAL_SECONDS": IMAGE_TASK_POLL_INTERVAL_SECONDS,
            "ENABLE_MODEL_PROBE": ENABLE_MODEL_PROBE,
            "MODEL_PROBE_TIMEOUT_SECONDS": MODEL_PROBE_TIMEOUT_SECONDS,
            "MODEL_PROBE_TTL_SECONDS": MODEL_PROBE_TTL_SECONDS,
            "MODEL_ROUTE_CACHE_TTL_SECONDS": MODEL_ROUTE_CACHE_TTL_SECONDS,
            "ENABLE_INTERRUPTION_RESUME": ENABLE_INTERRUPTION_RESUME,
            "INTERRUPTION_RESUME_TTL_SECONDS": INTERRUPTION_RESUME_TTL_SECONDS,
            "INTERRUPTION_RESUME_MAX_CHARS": INTERRUPTION_RESUME_MAX_CHARS,
            "INTERRUPTION_RESUME_MIN_CHARS": INTERRUPTION_RESUME_MIN_CHARS,
            "ENABLE_MODEL_CANDIDATE_RACE": ENABLE_MODEL_CANDIDATE_RACE,
            "MODEL_CANDIDATE_RACE_LIMIT": MODEL_CANDIDATE_RACE_LIMIT,
            "MODEL_CANDIDATE_RACE_TIMEOUT_SECONDS": MODEL_CANDIDATE_RACE_TIMEOUT_SECONDS,
        },
    )

    with config_lock:
        apply_pool_runtime_state(
            normalized_pools=normalized_config["proxy_pools"],
            rebuild_pool_state=rebuild_pool_state,
            connection_pool_state=connection_pool_state,
            save_pool_runtime_state_to_storage=save_pool_runtime_state_to_storage,
            target_globals=globals(),
        )
        apply_runtime_globals(globals(), normalized_config)
        configure_tool_compat(
            enable_request_normalization=ENABLE_REQUEST_NORMALIZATION,
            inject_zh_system_prompt=INJECT_ZH_SYSTEM_PROMPT,
            proxy_system_prompt_zh=PROXY_SYSTEM_PROMPT_ZH,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
            model_capabilities=MODEL_CAPABILITIES,
        )
        if persist:
            save_runtime_config_to_disk()

    log_runtime_config_update(
        logger=proxy_logger,
        upstream_url_pool=UPSTREAM_URL_POOL,
        model_aliases=MODEL_ALIASES,
        model_capabilities=MODEL_CAPABILITIES,
        state={
            "REQUEST_TIMEOUT": REQUEST_TIMEOUT,
            "UPSTREAM_MAX_RETRIES": UPSTREAM_MAX_RETRIES,
            "UPSTREAM_RANDOMIZE_ENDPOINTS": UPSTREAM_RANDOMIZE_ENDPOINTS,
            "FORCE_UPSTREAM_CHAT_STREAM": FORCE_UPSTREAM_CHAT_STREAM,
            "ENABLE_REQUEST_NORMALIZATION": ENABLE_REQUEST_NORMALIZATION,
            "MAX_COMPLETION_TOKENS": MAX_COMPLETION_TOKENS,
            "INJECT_ZH_SYSTEM_PROMPT": INJECT_ZH_SYSTEM_PROMPT,
            "IMAGE_UPSTREAM_PROTOCOL": IMAGE_UPSTREAM_PROTOCOL,
        },
        persisted=persist,
    )
    return build_runtime_config_payload()


def load_runtime_config_from_disk() -> bool:
    payload = load_runtime_config_from_file(
        config_path=PROXY_CONFIG_PATH,
        logger=proxy_logger,
    )
    if not payload:
        return False
    apply_runtime_config(payload, persist=False)
    return True


load_runtime_config_from_storage() or load_runtime_config_from_disk()
load_pool_runtime_state_from_storage()
configure_tool_compat(
    enable_request_normalization=ENABLE_REQUEST_NORMALIZATION,
    inject_zh_system_prompt=INJECT_ZH_SYSTEM_PROMPT,
    proxy_system_prompt_zh=PROXY_SYSTEM_PROMPT_ZH,
    max_completion_tokens=MAX_COMPLETION_TOKENS,
    model_capabilities=MODEL_CAPABILITIES,
)
load_model_route_cache_from_disk()

DASHBOARD_TEMPLATE = load_dashboard_template(PROJECT_ROOT, proxy_logger)


def should_force_upstream_stream(subpath: str, request_payload: dict | None) -> bool:
    return (
        FORCE_UPSTREAM_CHAT_STREAM
        and subpath == "chat/completions"
        and isinstance(request_payload, dict)
    )


def build_upstream_json_payload(
    subpath: str,
    request_payload: dict | None,
    *,
    request_method: str = "POST",
) -> tuple[dict | None, bool, int, list[str]]:
    if not isinstance(request_payload, dict):
        return None, False, 0, []

    upstream_payload = dict(request_payload)
    request_repairs = 0
    if subpath == "chat/completions":
        upstream_payload, normalization_repairs = normalize_openai_request_payload(upstream_payload)
        request_repairs += normalization_repairs
    model_candidates = build_model_candidates_from_payload(upstream_payload)
    upstream_stream = bool(upstream_payload.get("stream"))
    if request_method.upper() == "POST" and should_force_upstream_stream(subpath, request_payload):
        upstream_payload["stream"] = True
        upstream_stream = True

    return upstream_payload, upstream_stream, request_repairs, model_candidates


def build_route_policy(route_url: str) -> dict:
    return get_route_policy_for_url(PROXY_POOLS, route_url, normalize_pool_url)


def check_payload_against_model_capability(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return None
    capability = find_model_capability(payload.get("model"), MODEL_CAPABILITIES)
    if not isinstance(capability, dict):
        return None
    return find_context_window_overflow(payload, capability)


RESUME_HEADER_NAMES = (
    "X-Proxy-Resume-Key",
    "X-Proxy-Task-Id",
    "X-Proxy-Conversation-Id",
    "X-Conversation-Id",
    "X-Session-Id",
    "X-Thread-Id",
)
RESUME_HINT_PREFIX = "[ProxyResume]"


def stable_resume_hash(payload: object, length: int = 32) -> str:
    try:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        raw = str(payload)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:length]


def extract_text_for_resume(value: object, *, limit: int = 4000) -> str:
    parts: list[str] = []

    def add(text: object) -> None:
        if not isinstance(text, str) or not text:
            return
        if sum(len(part) for part in parts) >= limit:
            return
        parts.append(text)

    if isinstance(value, str):
        add(value)
    elif isinstance(value, list):
        for part in value:
            if isinstance(part, str):
                add(part)
            elif isinstance(part, dict):
                for key in ("text", "content", "input"):
                    add(part.get(key))
    elif isinstance(value, dict):
        for key in ("text", "content", "input"):
            add(value.get(key))

    text = "\n".join(parts)
    if len(text) > limit:
        text = text[-limit:]
    return text.strip()


def extract_last_user_text(payload: dict | None) -> str:
    messages = payload.get("messages") if isinstance(payload, dict) else None
    if not isinstance(messages, list):
        return ""
    for item in reversed(messages):
        if isinstance(item, dict) and item.get("role") == "user":
            return extract_text_for_resume(item.get("content"), limit=4000)
    return ""


def extract_first_instruction_text(payload: dict | None) -> str:
    messages = payload.get("messages") if isinstance(payload, dict) else None
    if not isinstance(messages, list):
        return ""
    for item in messages:
        if isinstance(item, dict) and item.get("role") in {"system", "developer"}:
            return extract_text_for_resume(item.get("content"), limit=2000)
    return ""


def extract_tool_names_for_resume(payload: dict | None) -> list[str]:
    tools = payload.get("tools") if isinstance(payload, dict) else None
    names: list[str] = []
    for item in (tools if isinstance(tools, list) else []):
        if not isinstance(item, dict):
            continue
        function_data = item.get("function") if isinstance(item.get("function"), dict) else {}
        name = str(function_data.get("name") or item.get("name") or "").strip()
        if name:
            names.append(name)
    return sorted(set(names))[:40]


def get_request_header_value(names: tuple[str, ...]) -> tuple[str, str]:
    try:
        headers = request.headers
    except Exception:
        return "", ""
    for name in names:
        value = str(headers.get(name) or "").strip()
        if value:
            return name, value
    return "", ""


def build_interruption_resume_candidates(protocol: str, payload: dict | None) -> list[dict]:
    if not isinstance(payload, dict):
        return []

    model = str(payload.get("model") or "").strip()
    candidates: list[dict] = []
    explicit_name, explicit_value = get_request_header_value(RESUME_HEADER_NAMES)
    if explicit_value:
        candidates.append(
            {
                "key": "resume:v1:explicit:" + stable_resume_hash({"header": explicit_name.lower(), "value": explicit_value}),
                "source": "explicit",
                "load": True,
            }
        )

    last_user_text = extract_last_user_text(payload)
    instruction_text = extract_first_instruction_text(payload)
    if model or last_user_text or instruction_text:
        candidates.append(
            {
                "key": "resume:v1:fingerprint:"
                + stable_resume_hash(
                    {
                        "protocol": protocol,
                        "model": model,
                        "last_user": re.sub(r"\s+", " ", last_user_text).strip()[-2000:],
                        "instruction": re.sub(r"\s+", " ", instruction_text).strip()[:1200],
                        "tools": extract_tool_names_for_resume(payload),
                    }
                ),
                "source": "fingerprint",
                "load": True,
            }
        )

    deduped: list[dict] = []
    seen: set[str] = set()
    for item in candidates:
        key = str(item.get("key") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def build_resume_hint_message(record: dict) -> dict:
    partial_text = str(record.get("partial_text") or "").strip()
    return {
        "role": "system",
        "content": (
            f"{RESUME_HINT_PREFIX} 上一次同任务流式响应在客户端断开时中断。"
            "以下是代理保存的已输出片段末尾，仅用于续接当前任务。"
            "请基于当前请求继续完成未完成内容，避免重复已经完成的部分；"
            "如果当前请求明确要求重新开始，请忽略该片段。\n\n"
            "已输出片段末尾：\n"
            f"{partial_text}"
        ),
    }


def payload_has_resume_hint(payload: dict | None) -> bool:
    messages = payload.get("messages") if isinstance(payload, dict) else None
    if not isinstance(messages, list):
        return False
    for item in messages:
        if isinstance(item, dict) and RESUME_HINT_PREFIX in str(item.get("content") or ""):
            return True
    return False


def apply_interruption_resume_to_payload(protocol: str, payload: dict | None) -> tuple[dict | None, int, dict]:
    candidates = build_interruption_resume_candidates(protocol, payload)
    metrics = {
        "resume_enabled": ENABLE_INTERRUPTION_RESUME,
        "resume_candidates": len(candidates),
        "resume_key_source": "",
        "resume_injected": False,
        "resume_available": False,
        "resume_partial_chars": 0,
        "resume_record_age_seconds": 0,
        "_resume_save_keys": [str(item.get("key") or "") for item in candidates if item.get("key")],
        "_resume_cleanup_keys": [],
    }
    if (
        not ENABLE_INTERRUPTION_RESUME
        or storage is None
        or not isinstance(payload, dict)
        or not isinstance(payload.get("messages"), list)
        or payload_has_resume_hint(payload)
    ):
        return payload, 0, metrics

    record = {}
    matched = {}
    for candidate in candidates:
        if not candidate.get("load"):
            continue
        try:
            record = storage.load_interrupted_response(str(candidate.get("key") or ""))
        except Exception as exc:  # pragma: no cover
            proxy_logger.warning("load_interrupted_resume_failed source=%s error=%s", candidate.get("source"), str(exc))
            record = {}
        if record:
            matched = candidate
            break

    if not record:
        return payload, 0, metrics

    partial_text = str(record.get("partial_text") or "").strip()
    if len(partial_text) < INTERRUPTION_RESUME_MIN_CHARS:
        return payload, 0, metrics

    next_payload = dict(payload)
    messages = list(next_payload.get("messages") or [])
    insert_at = 0
    while insert_at < len(messages) and isinstance(messages[insert_at], dict) and messages[insert_at].get("role") in {"system", "developer"}:
        insert_at += 1
    messages.insert(insert_at, build_resume_hint_message(record))
    next_payload["messages"] = messages

    now = time.time()
    metrics.update(
        {
            "resume_key_source": str(matched.get("source") or ""),
            "resume_injected": True,
            "resume_available": True,
            "resume_partial_chars": len(partial_text),
            "resume_record_age_seconds": max(0, int(now - float(record.get("created_at") or now))),
            "_resume_cleanup_keys": [str(item.get("key") or "") for item in candidates if item.get("key")],
        }
    )
    bump_cache_stat("interruption_resume_injected")
    return next_payload, 1, metrics


def append_resume_text(parts: list[str], text: object) -> None:
    if not isinstance(text, str) or not text:
        return
    parts.append(text)
    total = sum(len(part) for part in parts)
    while parts and total > INTERRUPTION_RESUME_MAX_CHARS:
        overflow = total - INTERRUPTION_RESUME_MAX_CHARS
        if len(parts[0]) <= overflow:
            removed = parts.pop(0)
            total -= len(removed)
            continue
        parts[0] = parts[0][overflow:]
        total = INTERRUPTION_RESUME_MAX_CHARS


def build_resume_partial_text(parts: list[str], fallback: str | None = None) -> str:
    text = "".join(part for part in parts if isinstance(part, str)).strip()
    if not text and fallback:
        text = str(fallback or "").strip()
    if len(text) > INTERRUPTION_RESUME_MAX_CHARS:
        text = text[-INTERRUPTION_RESUME_MAX_CHARS:]
    return text


def save_interruption_resume_snapshot(
    *,
    execution: dict | None,
    protocol: str,
    request_id: str,
    upstream_url: str,
    partial_text: str,
    response_preview: str | None = None,
    bytes_sent: int = 0,
) -> dict:
    if not ENABLE_INTERRUPTION_RESUME or storage is None or not isinstance(execution, dict):
        return {"resume_saved": False}
    text = str(partial_text or "").strip()
    if len(text) < INTERRUPTION_RESUME_MIN_CHARS:
        execution["resume_saved"] = False
        execution["resume_partial_chars"] = len(text)
        return {"resume_saved": False, "resume_partial_chars": len(text)}

    resume_metrics = execution.get("interruption_resume") if isinstance(execution.get("interruption_resume"), dict) else {}
    keys = [str(item or "") for item in resume_metrics.get("_resume_save_keys", []) if str(item or "")]
    if not keys:
        return {"resume_saved": False, "resume_partial_chars": len(text)}

    now = time.time()
    model = ""
    upstream_payload = execution.get("upstream_payload")
    if isinstance(upstream_payload, dict):
        model = str(upstream_payload.get("model") or "")
    saved = 0
    for key in keys:
        try:
            storage.save_interrupted_response(
                {
                    "resume_key": key,
                    "protocol": protocol,
                    "model": model,
                    "partial_text": text,
                    "created_at": now,
                    "expires_at": now + INTERRUPTION_RESUME_TTL_SECONDS,
                    "meta": {
                        "request_id": request_id,
                        "upstream_url": upstream_url,
                        "response_preview": response_preview or "",
                        "bytes_sent": int(bytes_sent or 0),
                    },
                }
            )
            saved += 1
        except Exception as exc:  # pragma: no cover
            proxy_logger.warning("save_interrupted_resume_failed request_id=%s error=%s", request_id, str(exc))

    saved_ok = saved > 0
    if saved_ok:
        bump_cache_stat("interruption_resume_saved")
    execution["resume_saved"] = saved_ok
    execution["resume_partial_chars"] = len(text)
    execution["resume_saved_keys"] = saved
    return {
        "resume_saved": saved_ok,
        "resume_partial_chars": len(text),
        "resume_saved_keys": saved,
    }


def clear_interruption_resume_records(execution: dict | None) -> dict:
    if not ENABLE_INTERRUPTION_RESUME or storage is None or not isinstance(execution, dict):
        return {"resume_cleared": False}
    resume_metrics = execution.get("interruption_resume") if isinstance(execution.get("interruption_resume"), dict) else {}
    if not (bool(resume_metrics.get("resume_injected")) or bool(resume_metrics.get("resume_available"))):
        return {"resume_cleared": False}
    keys = [str(item or "") for item in resume_metrics.get("_resume_cleanup_keys", []) if str(item or "")]
    if not keys:
        return {"resume_cleared": False}
    try:
        storage.delete_interrupted_responses(keys)
    except Exception as exc:  # pragma: no cover
        proxy_logger.warning("clear_interrupted_resume_failed error=%s", str(exc))
        return {"resume_cleared": False}
    bump_cache_stat("interruption_resume_cleared")
    execution["resume_cleared"] = True
    return {"resume_cleared": True}


def apply_route_policy_to_payload(subpath: str, upstream_payload: dict | None, route_policy: dict) -> tuple[dict | None, int, dict]:
    if not isinstance(upstream_payload, dict):
        return upstream_payload, 0, {}
    if subpath != "chat/completions":
        return upstream_payload, 0, {}

    payload = dict(upstream_payload)
    repairs = 0

    reasoning_effort = str(route_policy.get("reasoning_effort") or DEFAULT_ROUTE_POLICY["reasoning_effort"])
    if reasoning_effort and "reasoning_effort" not in payload:
        payload["reasoning_effort"] = reasoning_effort
        repairs += 1

    messages = payload.get("messages")
    if not isinstance(messages, list):
        return payload, repairs, {}

    compression_mode = str(route_policy.get("compression_mode") or "off")
    max_history_messages = int(route_policy.get("max_history_messages") or DEFAULT_ROUTE_POLICY["max_history_messages"])
    max_tool_chars = int(route_policy.get("max_tool_chars") or DEFAULT_ROUTE_POLICY["max_tool_chars"])
    max_input_chars = int(route_policy.get("max_input_chars") or DEFAULT_ROUTE_POLICY["max_input_chars"])
    if compression_mode == "aggressive":
        max_history_messages = min(max_history_messages, 10)
        max_tool_chars = min(max_tool_chars, 8000)
        max_input_chars = min(max_input_chars, 90000)

    def estimate_messages_chars(items):
        try:
            return len(json.dumps(items or [], ensure_ascii=False))
        except Exception:
            return 0

    metrics = {
        "compression_mode": compression_mode,
        "max_history_messages": max_history_messages,
        "max_tool_chars": max_tool_chars,
        "max_input_chars": max_input_chars,
        "original_message_count": len(messages),
        "sent_message_count": len(messages),
        "dropped_message_count": 0,
        "trimmed_content_count": 0,
        "input_chars_before_policy": estimate_messages_chars(messages),
        "input_chars_after_policy": estimate_messages_chars(messages),
    }

    if compression_mode == "off":
        return payload, repairs, metrics

    normalized_messages = [dict(item) if isinstance(item, dict) else item for item in messages]
    if len(normalized_messages) > max_history_messages:
        system_messages = [item for item in normalized_messages if isinstance(item, dict) and item.get("role") == "system"]
        tail_messages = [item for item in normalized_messages if not (isinstance(item, dict) and item.get("role") == "system")]
        normalized_messages = system_messages[:2] + tail_messages[-max(0, max_history_messages - len(system_messages[:2])):]
        repairs += 1

    def trim_content(content):
        local_repairs = 0
        if isinstance(content, str):
            if len(content) > max_tool_chars:
                return content[:max_tool_chars] + "\n[内容已压缩]", 1
            return content, 0
        if isinstance(content, list):
            trimmed = []
            for part in content:
                if isinstance(part, dict):
                    current = dict(part)
                    for key in ("text", "content", "input"):
                        if isinstance(current.get(key), str) and len(current[key]) > max_tool_chars:
                            current[key] = current[key][:max_tool_chars] + "\n[内容已压缩]"
                            local_repairs += 1
                    trimmed.append(current)
                else:
                    trimmed.append(part)
            return trimmed, local_repairs
        return content, 0

    next_messages = []
    total_chars = 0
    trimmed_content_count = 0
    for item in normalized_messages:
        if not isinstance(item, dict):
            next_messages.append(item)
            continue
        current = dict(item)
        if current.get("role") == "assistant" and compression_mode in {"balanced", "aggressive"}:
            if isinstance(current.get("reasoning"), str) and current.get("reasoning"):
                current["reasoning"] = ""
                repairs += 1
        current_content, content_repairs = trim_content(current.get("content"))
        repairs += content_repairs
        trimmed_content_count += content_repairs
        current["content"] = current_content
        total_chars += len(json.dumps(current_content, ensure_ascii=False)) if current_content is not None else 0
        next_messages.append(current)

    while next_messages and total_chars > max_input_chars:
        removable_index = next((idx for idx, item in enumerate(next_messages) if isinstance(item, dict) and item.get("role") != "system"), None)
        if removable_index is None:
            break
        removed = next_messages.pop(removable_index)
        total_chars -= len(json.dumps(removed.get("content"), ensure_ascii=False)) if isinstance(removed, dict) else 0
        repairs += 1

    if compression_mode == "aggressive":
        compacted_messages = []
        for item in next_messages:
            if not isinstance(item, dict):
                compacted_messages.append(item)
                continue
            current = dict(item)
            if current.get("role") == "assistant":
                current.pop("reasoning", None)
                tool_calls = current.get("tool_calls")
                if isinstance(tool_calls, list) and len(tool_calls) > 2:
                    current["tool_calls"] = tool_calls[-2:]
                    repairs += 1
            compacted_messages.append(current)
        next_messages = compacted_messages

    payload["messages"] = next_messages
    metrics["sent_message_count"] = len(next_messages)
    metrics["dropped_message_count"] = max(0, len(messages) - len(next_messages))
    metrics["trimmed_content_count"] = trimmed_content_count
    metrics["input_chars_after_policy"] = estimate_messages_chars(next_messages)

    max_output_tokens = int(route_policy.get("max_output_tokens") or 0)
    if max_output_tokens > 0:
        repairs += clamp_payload_output_tokens(payload, max_output_tokens)
    return payload, repairs, metrics


def execute_upstream_request(
    subpath: str,
    request_payload: dict | None,
    request_id: str,
    *,
    request_method: str = "POST",
    raw_body: bytes | None = None,
) -> dict:
    upstream_urls = build_upstream_url_candidates(subpath)
    requested_stream = bool(isinstance(request_payload, dict) and request_payload.get("stream"))
    if not upstream_urls:
        return {
            "upstream_url": "",
            "upstream_url_pool": [],
            "route_pool_size": 0,
            "tool_schemas": extract_tool_schemas(request_payload),
            "upstream_payload": request_payload if isinstance(request_payload, dict) else None,
            "upstream_stream": requested_stream,
            "upstream_response": None,
            "attempts": [],
            "request_exception": None,
            "retry_count": 0,
            "request_repairs": 0,
            "model_candidates": [],
            "initial_key_choice": {},
            "forced_error_payload": build_no_upstream_configured_error_payload(),
            "forced_error_status": 400,
        }
    upstream_url = upstream_urls[0]
    upstream_payload, upstream_stream, request_repairs, model_candidates = build_upstream_json_payload(
        subpath,
        request_payload,
        request_method=request_method,
    )
    request_protocol = "openai_chat_completions" if subpath == "chat/completions" else subpath.replace("/", "_")
    route_policy = build_route_policy(upstream_url)
    upstream_payload, route_policy_repairs, route_policy_metrics = apply_route_policy_to_payload(subpath, upstream_payload, route_policy)
    request_repairs += route_policy_repairs
    resume_metrics = {}
    if subpath == "chat/completions" and isinstance(upstream_payload, dict):
        upstream_payload, resume_repairs, resume_metrics = apply_interruption_resume_to_payload(
            request_protocol,
            upstream_payload,
        )
        request_repairs += resume_repairs
    capability_overflow = check_payload_against_model_capability(upstream_payload)
    if isinstance(capability_overflow, dict):
        logical_model_name = ""
        if isinstance(upstream_payload, dict):
            logical_model_name = str(upstream_payload.get("model") or "").strip()
        return {
            "upstream_url": upstream_url,
            "upstream_url_pool": upstream_urls,
            "route_pool_size": len(upstream_urls),
            "tool_schemas": extract_tool_schemas(upstream_payload if isinstance(upstream_payload, dict) else request_payload),
            "upstream_payload": upstream_payload,
            "upstream_stream": upstream_stream,
            "upstream_response": None,
            "attempts": [],
            "request_exception": None,
            "retry_count": 0,
            "request_repairs": request_repairs,
            "model_candidates": model_candidates,
            "initial_key_choice": {},
            "route_policy": route_policy,
            "route_policy_metrics": route_policy_metrics,
            "interruption_resume": resume_metrics,
            "forced_error_payload": build_context_window_exceeded_error_payload(
                model_name=logical_model_name,
                estimated_total_tokens=int(capability_overflow.get("estimated_total_tokens") or 0),
                context_tokens=int(capability_overflow.get("context_tokens") or 0),
                requested_output_tokens=int(capability_overflow.get("requested_output_tokens") or 0),
                allowed_input_tokens=int(capability_overflow.get("allowed_input_tokens") or 0),
            ),
            "forced_error_status": 400,
        }
    tool_schemas = extract_tool_schemas(upstream_payload if isinstance(upstream_payload, dict) else request_payload)

    cache_key = build_cache_key(
        protocol=request_protocol,
        path=subpath,
        payload=upstream_payload if isinstance(upstream_payload, dict) else None,
        route_policy=route_policy,
    )
    if storage is not None and is_cacheable_request(
        request_payload=upstream_payload,
        route_policy=route_policy,
        stream=requested_stream,
    ):
        try:
            cached_payload = storage.load_request_cache(cache_key)
        except Exception as exc:  # pragma: no cover
            proxy_logger.warning("load_request_cache_failed key=%s error=%s", cache_key[:12], str(exc))
            cached_payload = {}
        if isinstance(cached_payload, dict) and cached_payload.get("response_body"):
            bump_cache_stat("prompt_cache_hits")
            cached_execution = build_cached_execution(
                cached_payload=cached_payload,
                request_payload=upstream_payload,
                request_repairs=request_repairs,
                model_candidates=model_candidates,
                route_policy=route_policy,
                cache_key=cache_key,
                route_policy_metrics=route_policy_metrics,
            )
            cached_execution["interruption_resume"] = resume_metrics
            return cached_execution
        bump_cache_stat("prompt_cache_misses")

    key_choice = choose_api_key_for_url(upstream_url)
    primary_pool_key = str(key_choice.get("key") or UPSTREAM_API_KEY)
    request_kwargs = {
        "method": request_method,
        "url": upstream_url,
        "headers": build_upstream_headers(upstream_api_key=primary_pool_key),
        "params": build_upstream_params(),
        "stream": True,
        "timeout": build_upstream_timeout(requested_stream=requested_stream),
    }
    if upstream_payload is not None:
        request_kwargs["json"] = upstream_payload
    else:
        request_kwargs["data"] = raw_body or b""

    upstream_response, attempts, request_exception = request_upstream_with_retries(
        request_kwargs,
        subpath=subpath,
        request_id=request_id,
        upstream_urls=upstream_urls,
        model_candidates=model_candidates,
    )
    selected_upstream_url = next(
        (attempt.get("upstream_url") for attempt in reversed(attempts) if attempt.get("upstream_url")),
        upstream_url,
    )
    learned_request_repairs = sum(
        int(attempt.get("learned_request_repairs", 0) or 0)
        for attempt in attempts
        if isinstance(attempt, dict)
    )

    return {
        "upstream_url": selected_upstream_url,
        "upstream_url_pool": upstream_urls,
        "route_pool_size": len(upstream_urls),
        "tool_schemas": tool_schemas,
        "upstream_payload": upstream_payload,
        "upstream_stream": upstream_stream,
        "upstream_response": upstream_response,
        "attempts": attempts,
        "request_exception": request_exception,
        "retry_count": max(0, len(attempts) - 1),
        "request_repairs": request_repairs + learned_request_repairs,
        "model_candidates": model_candidates,
        "route_policy": route_policy,
        "route_policy_metrics": route_policy_metrics,
        "interruption_resume": resume_metrics,
        "cache_hit": False,
        "cache_key": cache_key,
        "initial_key_choice": {
            "pool_name": key_choice.get("pool_name"),
            "key_index": key_choice.get("key_index"),
            "key_count": key_choice.get("key_count"),
            "key_id": key_choice.get("key_id"),
            "from_pool": key_choice.get("from_pool"),
        },
        "logical_model": model_candidates[0] if model_candidates else "",
        "resolved_model": next(
            (str(attempt.get("model") or "") for attempt in reversed(attempts) if str(attempt.get("model") or "").strip()),
            model_candidates[0] if model_candidates else "",
        ),
        "selected_pool_name": next(
            (str(attempt.get("pool_name") or "") for attempt in reversed(attempts) if str(attempt.get("pool_name") or "").strip()),
            str(key_choice.get("pool_name") or ""),
        ),
        "attempted_pool_names": list(dict.fromkeys(
            str(attempt.get("pool_name") or "") for attempt in attempts if str(attempt.get("pool_name") or "").strip()
        )),
        "selected_key_index": next(
            (attempt.get("api_key_index") for attempt in reversed(attempts) if attempt.get("api_key_index") is not None),
            key_choice.get("key_index"),
        ),
    }


def close_execution_upstream_response(execution: dict | None) -> None:
    if not isinstance(execution, dict):
        return
    close_response_quietly(execution.get("upstream_response"))


def start_background_upstream_execution(subpath: str, request_payload: dict | None, request_id: str) -> BackgroundExecution:
    request_method = request.method
    raw_body = request.get_data(cache=True)

    @copy_current_request_context
    def run_execution():
        return execute_upstream_request(
            subpath,
            request_payload,
            request_id,
            request_method=request_method,
            raw_body=raw_body,
        )

    return BackgroundExecution(
        run_execution,
        on_cancel_result=close_execution_upstream_response,
        thread_name=f"upstream-{request_id}",
    )


def wait_background_upstream_execution(
    background_execution: BackgroundExecution,
    timeout_seconds: float,
) -> tuple[bool, dict | None, BaseException | None]:
    outcome = background_execution.wait(timeout_seconds)
    if outcome is None:
        return False, None, None
    kind, payload = outcome
    if kind == "error":
        return True, None, payload if isinstance(payload, BaseException) else RuntimeError(str(payload))
    return True, payload if isinstance(payload, dict) else None, None


def should_retry_upstream_request(subpath: str, method: str) -> bool:
    method = method.upper()
    if method in {"GET", "HEAD"}:
        return True
    return method == "POST"


def extract_response_text(response: requests.Response) -> str:
    try:
        return response.content.decode("utf-8", errors="ignore")
    except Exception:  # pragma: no cover
        return ""


def extract_error_payload_from_text(text: str) -> dict | None:
    raw = text.strip()
    if not raw:
        return None

    if raw.startswith("data:"):
        parts = []
        for line in raw.splitlines():
            if line.startswith("data:"):
                candidate = line[5:].strip()
                if candidate and candidate != "[DONE]":
                    parts.append(candidate)
        if len(parts) == 1:
            raw = parts[0]

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None

    return payload if isinstance(payload, dict) else None


def extract_error_preview_from_response(response: requests.Response, limit: int = 280) -> str:
    text = extract_response_text(response).replace("\n", "\\n")
    return text[:limit]


def extract_upstream_error_searchable_text(response: requests.Response) -> str:
    upstream_payload = extract_error_payload_from_text(extract_response_text(response))
    if isinstance(upstream_payload, dict):
        error_payload = upstream_payload.get("error") if "error" in upstream_payload else upstream_payload
        if isinstance(error_payload, dict):
            searchable = " ".join(
                str(error_payload.get(key, ""))
                for key in ("code", "type", "message", "param")
            ).strip().lower()
            if searchable:
                return searchable

    return extract_error_preview_from_response(response, limit=400).lower()


def classify_upstream_response(response: requests.Response) -> tuple[str, str]:
    status_code = response.status_code
    searchable = extract_upstream_error_searchable_text(response)

    if text_indicates_client_gone(searchable):
        if (
            status_code in RETRYABLE_STATUS_CODES
            or status_code >= 500
            or any(marker in searchable for marker in UPSTREAM_CANCELED_MARKERS)
        ):
            return "switch_route", f"upstream_canceled_{status_code}"
        return "return", f"client_gone_{status_code}"

    if any(marker in searchable for marker in MODEL_UNAVAILABLE_UPSTREAM_ERROR_MARKERS):
        return "switch_route", f"model_unavailable_{status_code}"

    if any(marker in searchable for marker in REQUEST_FATAL_UPSTREAM_ERROR_MARKERS):
        return "return", f"fatal_{status_code}"

    if status_code in {401, 402, 403} or any(
        marker in searchable for marker in ROUTE_SWITCH_UPSTREAM_ERROR_MARKERS
    ):
        return "switch_route", f"route_switch_{status_code}"

    if status_code in {408, 502, 504, 524}:
        return "switch_route", f"route_switch_{status_code}"

    if status_code in RETRYABLE_STATUS_CODES:
        return "retry", f"status_{status_code}"

    return "return", f"status_{status_code}"


def compute_retry_delay_ms(attempt_number: int, response: requests.Response | None = None) -> int:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            return min(int(retry_after) * 1000, UPSTREAM_RETRY_MAX_BACKOFF_MS)

    if attempt_number <= 0:
        return 0

    delay = UPSTREAM_RETRY_BACKOFF_MS * (2 ** (attempt_number - 1))
    return min(delay, UPSTREAM_RETRY_MAX_BACKOFF_MS)


def build_upstream_url_candidates(subpath: str) -> list[str]:
    return router_build_upstream_url_candidates(UPSTREAM_URL_POOL, UPSTREAM_URL, subpath)


def remaining_retry_window_ms(deadline_monotonic: float) -> int:
    return router_remaining_retry_window_ms(deadline_monotonic)


def get_route_health_entry(route_url: str) -> dict:
    return router_get_route_health_entry(route_health, state_lock, route_url)


def is_route_in_cooldown(route_url: str) -> bool:
    return router_is_route_in_cooldown(route_health, state_lock, route_url)


def mark_route_success(route_url: str) -> None:
    router_mark_route_success(route_health, state_lock, route_url)


def mark_route_failure(route_url: str, reason: str) -> None:
    router_mark_route_failure(
        route_health,
        state_lock,
        route_url,
        reason,
        route_cooldown_seconds=UPSTREAM_ROUTE_COOLDOWN_SECONDS,
        route_switch_window_seconds=UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS,
        route_failure_threshold=UPSTREAM_ROUTE_FAILURE_THRESHOLD,
    )


def build_attempt_url_cycle(candidate_urls: list[str], blocked_urls: set[str]) -> list[str]:
    logical_model = route_selection_state.get("__current_logical_model__")
    return router_build_attempt_url_cycle(
        candidate_urls,
        blocked_urls,
        route_health=route_health,
        route_selection_state=route_selection_state,
        state_lock=state_lock,
        randomize_endpoints=UPSTREAM_RANDOMIZE_ENDPOINTS,
        route_score_provider=(lambda route_url: get_route_score(logical_model, route_url)),
    )


def should_enforce_route_switch_window(candidate_urls: list[str], retry_allowed: bool) -> bool:
    return router_should_enforce_route_switch_window(candidate_urls, retry_allowed)


MODEL_UNAVAILABLE_UPSTREAM_ERROR_MARKERS = (
    "model_not_found",
    "model not found",
    "invalid model",
    "model does not exist",
    "requested model does not exist",
    "no available channel for model",
    "unsupported_model",
    "model is not supported",
    "model not exist",
    "模型不存在",
    "模型未找到",
    "模型不支持",
    "无可用渠道",
)


def response_indicates_model_unavailable(response: requests.Response) -> bool:
    return router_response_indicates_model_unavailable(extract_upstream_error_searchable_text, response)


def get_cached_model_list(route_url: str) -> list[str] | None:
    return router_get_cached_model_list(model_route_cache, bump_cache_stat, route_url)


def cache_model_list(route_url: str, models: list[str]) -> None:
    router_cache_model_list(
        model_route_cache,
        state_lock,
        save_model_route_cache_to_disk,
        route_url,
        models,
        model_probe_ttl_seconds=MODEL_PROBE_TTL_SECONDS,
    )


def fetch_upstream_model_list(route_url: str, request_kwargs: dict, request_id: str) -> list[str]:
    return router_fetch_upstream_model_list(
        route_url=route_url,
        request_kwargs=request_kwargs,
        request_id=request_id,
        get_cached=get_cached_model_list,
        cache_list=cache_model_list,
        enabled=ENABLE_MODEL_PROBE,
        request_timeout=REQUEST_TIMEOUT,
        probe_timeout_seconds=MODEL_PROBE_TIMEOUT_SECONDS,
        session=UPSTREAM_SESSION,
        logger=proxy_logger,
        extract_error_preview=extract_error_preview_from_response,
        json_body_from_response=json_body_from_response,
    )


def build_model_candidate_order_for_route(
    route_url: str,
    model_candidates: list[str],
    request_kwargs: dict,
    request_id: str,
) -> dict:
    return router_build_model_candidate_order_for_route(
        route_url=route_url,
        model_candidates=model_candidates,
        request_kwargs=request_kwargs,
        request_id=request_id,
        get_cached_route_candidates=get_cached_route_model_candidates,
        fetch_model_list=fetch_upstream_model_list,
        get_model_candidate_score=get_model_candidate_score,
        logger=proxy_logger,
    )


def order_model_candidates_for_route(
    route_url: str,
    model_candidates: list[str],
    request_kwargs: dict,
    request_id: str,
) -> list[str]:
    return router_order_model_candidates_for_route(
        route_url=route_url,
        model_candidates=model_candidates,
        request_kwargs=request_kwargs,
        request_id=request_id,
        get_cached_route_candidates=get_cached_route_model_candidates,
        fetch_model_list=fetch_upstream_model_list,
        get_model_candidate_score=get_model_candidate_score,
        logger=proxy_logger,
    )


def should_race_model_candidates_for_route(
    *,
    subpath: str,
    method: str,
    order_info: dict,
    ordered_model_candidates: list[str],
) -> bool:
    return router_should_race_model_candidates_for_route(
        subpath=subpath,
        method=method,
        order_info=order_info,
        ordered_model_candidates=ordered_model_candidates,
        enable_model_candidate_race=ENABLE_MODEL_CANDIDATE_RACE,
    )


def append_race_attempts(
    attempts: list[dict],
    race_attempts: list[dict],
    *,
    logical_model: str | None,
    route_url: str,
) -> set[str]:
    return router_append_race_attempts(
        attempts,
        race_attempts,
        logical_model=logical_model,
        route_url=route_url,
        mark_route_success_fn=mark_route_success,
        record_model_candidate_result_fn=record_model_candidate_result,
    )


def request_upstream_with_retries(
    request_kwargs: dict,
    *,
    subpath: str,
    request_id: str,
    upstream_urls: list[str] | None = None,
    model_candidates: list[str] | None = None,
) -> tuple[requests.Response | None, list[dict], requests.RequestException | None]:
    with state_lock:
        route_selection_state["__current_logical_model__"] = model_candidates[0] if model_candidates else ""
    return orchestrated_request_upstream_with_retries(
        request_kwargs,
        subpath=subpath,
        request_id=request_id,
        upstream_urls=upstream_urls,
        model_candidates=model_candidates,
        should_retry_request=should_retry_upstream_request,
        max_retries=UPSTREAM_MAX_RETRIES,
        should_enforce_route_switch_window=should_enforce_route_switch_window,
        route_switch_window_seconds=UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS,
        build_attempt_url_cycle=build_attempt_url_cycle,
        build_model_candidate_order_for_route=build_model_candidate_order_for_route,
        should_race_model_candidates_for_route=should_race_model_candidates_for_route,
        get_api_keys_for_url=get_api_keys_for_url,
        choose_api_key_for_url=choose_api_key_for_url,
        mark_api_key_success=mark_api_key_success,
        mark_api_key_failure=mark_api_key_failure,
        mark_route_success=mark_route_success,
        mark_route_failure=mark_route_failure,
        response_indicates_model_unavailable=response_indicates_model_unavailable,
        classify_upstream_response=classify_upstream_response,
        extract_error_preview_from_response=extract_error_preview_from_response,
        apply_model_candidate_to_request_kwargs=apply_model_candidate_to_request_kwargs,
        apply_learned_completion_limit_to_request_kwargs=apply_learned_completion_limit_to_request_kwargs,
        extract_completion_token_limit_from_response=extract_completion_token_limit_from_response,
        extract_context_token_limit_from_response=extract_context_token_limit_from_response,
        clamp_payload_output_tokens=clamp_payload_output_tokens,
        record_learned_model_capability=record_learned_model_capability,
        record_model_candidate_result=record_model_candidate_result,
        compute_retry_delay_ms=compute_retry_delay_ms,
        remaining_retry_window_ms=remaining_retry_window_ms,
        append_race_attempts=append_race_attempts,
        model_candidate_differs_from_logical=model_candidate_differs_from_logical,
        logger=proxy_logger,
        cache_stat_bump=bump_cache_stat,
        model_candidate_race_limit=MODEL_CANDIDATE_RACE_LIMIT,
        model_candidate_race_timeout_seconds=MODEL_CANDIDATE_RACE_TIMEOUT_SECONDS,
        enable_model_candidate_race=ENABLE_MODEL_CANDIDATE_RACE,
        request_sender=UPSTREAM_SESSION.request,
    )


def record_request_cache_hit(
    request_id: str,
    body: bytes,
    started_at: float,
    requested_stream: bool,
    execution: dict | None = None,
    extra_meta: dict | None = None,
) -> int:
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    merged_extra_meta = dict(extra_meta or {})
    if isinstance(execution, dict):
        clear_interruption_resume_records(execution)
        merged_extra_meta.update(build_request_observability_meta(execution, execution.get("upstream_payload")))
    record_request_finished(
        request_id,
        status_code=200,
        bytes_sent=len(body),
        duration_ms=duration_ms,
        stream=requested_stream,
        sanitized_markers=0,
        repaired_tool_args=0,
        extra_meta=merged_extra_meta,
    )
    return duration_ms


def build_cached_openai_stream_response(
    *,
    request_id: str,
    started_at: float,
    cached_response_body: dict,
    execution: dict | None,
    request_payload: dict | None,
) -> Response:
    packets = build_openai_stream_packets_from_chat_completion(cached_response_body)
    total_bytes = sum(len(packet) for packet in packets)
    duration_ms = record_request_cache_hit(
        request_id,
        b"".join(packets),
        started_at,
        True,
        execution=execution,
        extra_meta=build_request_observability_meta(execution, request_payload),
    )
    proxy_logger.info(
        "request_id=%s 代理缓存命中 协议=openai_chat_completions 路径=%s 流式=true 字节=%s 耗时毫秒=%s key=%s 来源=%s",
        request_id,
        request.path,
        total_bytes,
        duration_ms,
        str((execution or {}).get("cache_key") or "")[:12],
        str((execution or {}).get("cache_source") or "sqlite"),
    )
    return Response(
        packets,
        status=200,
        headers=apply_sse_response_headers(
            {
                "X-Proxy-Retries": "0",
                "X-Proxy-Cache": "hit",
            }
        ),
    )


def estimate_request_payload_bytes(payload: dict | None) -> int:
    if not isinstance(payload, dict):
        return 0
    try:
        return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    except Exception:
        return 0


def build_request_observability_meta(execution: dict | None, request_payload: dict | None) -> dict:
    execution = execution or {}
    upstream_payload = execution.get("upstream_payload")
    effective_payload = upstream_payload if isinstance(upstream_payload, dict) else request_payload
    cached_response_body = execution.get("cached_response_body") if isinstance(execution.get("cached_response_body"), dict) else {}
    logical_model = str(
        execution.get("logical_model")
        or (effective_payload.get("model") if isinstance(effective_payload, dict) else "")
        or ""
    )
    resolved_model = str(
        execution.get("resolved_model")
        or (cached_response_body.get("model") if isinstance(cached_response_body, dict) else "")
        or logical_model
        or ""
    )
    pool_name = str(
        execution.get("selected_pool_name")
        or execution.get("upstream_pool_name")
        or (execution.get("initial_key_choice") or {}).get("pool_name")
        or ""
    )
    api_key_index = execution.get("selected_key_index")
    if api_key_index is None:
        api_key_index = execution.get("upstream_key_index")
    input_bytes = estimate_request_payload_bytes(effective_payload)
    cache_hit = bool(execution.get("cache_hit"))
    route_policy = execution.get("route_policy") if isinstance(execution.get("route_policy"), dict) else {}
    route_policy_metrics = execution.get("route_policy_metrics") if isinstance(execution.get("route_policy_metrics"), dict) else {}
    resume_metrics = execution.get("interruption_resume") if isinstance(execution.get("interruption_resume"), dict) else {}
    requested_stream = bool((effective_payload or {}).get("stream")) if isinstance(effective_payload, dict) else False
    cache_status = "miss"
    cache_note = ""
    if cache_hit:
        cache_status = "hit"
        cache_note = str(execution.get("cache_source") or "sqlite")
    else:
        payload_dict = effective_payload if isinstance(effective_payload, dict) else {}
        if str((route_policy or {}).get("prompt_cache_mode") or "off") != "exact":
            cache_status = "bypass_policy"
            cache_note = "策略未开启"
        elif requested_stream:
            cache_status = "miss_stream"
            cache_note = "流式可缓存"
        elif payload_dict.get("tools") or payload_dict.get("tool_choice"):
            if all_tools_read_only(payload_dict.get("tools")):
                cache_status = "miss_tools_readonly"
                cache_note = "只读工具可缓存"
            else:
                cache_status = "bypass_tools"
                cache_note = "副作用工具不缓存"
        elif payload_dict.get("response_format"):
            cache_status = "bypass_format"
            cache_note = "结构化输出不缓存"
        elif not isinstance(payload_dict.get("messages"), list) or not payload_dict.get("messages"):
            cache_status = "bypass_payload"
            cache_note = "请求不支持缓存"
    return {
        "logical_model": logical_model,
        "resolved_model": resolved_model,
        "pool_name": pool_name,
        "attempted_pool_names": list(execution.get("attempted_pool_names") or []) or ([pool_name] if pool_name else []),
        "api_key_index": api_key_index,
        "input_bytes": input_bytes,
        "cache_read_bytes": input_bytes if cache_hit else 0,
        "cache_hit": cache_hit,
        "cache_source": str(execution.get("cache_source") or ""),
        "cache_status": cache_status,
        "cache_note": cache_note,
        "compression_mode": str(route_policy_metrics.get("compression_mode") or route_policy.get("compression_mode") or ""),
        "max_history_messages": route_policy_metrics.get("max_history_messages"),
        "original_message_count": int(route_policy_metrics.get("original_message_count") or 0),
        "sent_message_count": int(route_policy_metrics.get("sent_message_count") or 0),
        "dropped_message_count": int(route_policy_metrics.get("dropped_message_count") or 0),
        "trimmed_content_count": int(route_policy_metrics.get("trimmed_content_count") or 0),
        "input_chars_before_policy": int(route_policy_metrics.get("input_chars_before_policy") or 0),
        "input_chars_after_policy": int(route_policy_metrics.get("input_chars_after_policy") or 0),
        "resume_enabled": bool(resume_metrics.get("resume_enabled", ENABLE_INTERRUPTION_RESUME)),
        "resume_key_source": str(resume_metrics.get("resume_key_source") or ""),
        "resume_injected": bool(resume_metrics.get("resume_injected")),
        "resume_available": bool(resume_metrics.get("resume_available")),
        "resume_saved": bool(execution.get("resume_saved")),
        "resume_cleared": bool(execution.get("resume_cleared")),
        "resume_partial_chars": int(execution.get("resume_partial_chars") or resume_metrics.get("resume_partial_chars") or 0),
        "resume_record_age_seconds": int(resume_metrics.get("resume_record_age_seconds") or 0),
    }


def build_request_meta(
    *,
    request_id: str,
    sanitized_query: str,
    upstream_url: str,
    stream: bool,
    upstream_stream: bool,
    retry_count: int,
    route_pool_size: int,
    attempt_urls: list[str] | None,
    attempt_route_chain: str,
    protocol: str,
    request_repairs: int,
    execution: dict | None = None,
    request_payload: dict | None = None,
    extra_fields: dict | None = None,
) -> dict:
    request_meta = {
        "request_id": request_id,
        "method": request.method,
        "path": request.path,
        "query": sanitized_query,
        "remote": request.remote_addr,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "upstream_url": upstream_url,
        "stream": stream,
        "upstream_stream": upstream_stream,
        "retry_count": retry_count,
        "route_pool_size": route_pool_size,
        "upstream_attempt_urls": attempt_urls or [],
        "upstream_attempt_chain": attempt_route_chain,
        "protocol": protocol,
        "request_repairs": request_repairs,
    }
    if isinstance(execution, dict):
        request_meta.update(build_request_observability_meta(execution, request_payload))
    if isinstance(extra_fields, dict):
        request_meta.update(extra_fields)
    return request_meta


def build_pending_stream_request_meta(
    *,
    request_id: str,
    sanitized_query: str,
    upstream_urls: list[str] | None,
    protocol: str,
    request_repairs: int,
) -> dict:
    initial_urls = upstream_urls or []
    return build_request_meta(
        request_id=request_id,
        sanitized_query=sanitized_query,
        upstream_url=initial_urls[0] if initial_urls else "",
        stream=True,
        upstream_stream=True,
        retry_count=0,
        route_pool_size=len(initial_urls),
        attempt_urls=initial_urls,
        attempt_route_chain=" -> ".join(initial_urls),
        protocol=protocol,
        request_repairs=request_repairs,
    )


def save_request_cache_entry(
    *,
    execution: dict,
    protocol: str,
    path: str,
    request_payload: dict | None,
    response_body: dict | None,
    upstream_url: str,
) -> None:
    if storage is None or not isinstance(response_body, dict):
        return
    choices = response_body.get("choices") or []
    if choices:
        has_useful_content = False
        for choice in choices:
            message = choice.get("message") or {}
            if (
                (isinstance(message.get("content"), str) and message["content"].strip())
                or message.get("tool_calls")
                or (isinstance(message.get("reasoning"), str) and message["reasoning"].strip())
            ):
                has_useful_content = True
                break
        if not has_useful_content:
            return
    route_policy = execution.get("route_policy") if isinstance(execution, dict) else None
    if not is_cacheable_request(
        request_payload=request_payload,
        route_policy=route_policy if isinstance(route_policy, dict) else {},
        stream=False,
    ):
        return
    try:
        cache_key = str(execution.get("cache_key") or "")
        if not cache_key:
            cache_key = build_cache_key(
                protocol=protocol,
                path=path,
                payload=request_payload,
                route_policy=route_policy if isinstance(route_policy, dict) else {},
            )
        storage.save_request_cache(
            build_cache_record(
                cache_key=cache_key,
                protocol=protocol,
                path=path,
                request_payload=request_payload,
                route_policy=route_policy if isinstance(route_policy, dict) else {},
                response_body=response_body,
                upstream_url=upstream_url,
                model_name=response_body.get("model") if isinstance(response_body, dict) else "",
                pool_name=(execution.get("selected_pool_name") if isinstance(execution, dict) else "") or "",
                key_index=execution.get("selected_key_index") if isinstance(execution, dict) else None,
                ttl_seconds=REQUEST_CACHE_TTL_SECONDS,
            )
        )
        bump_cache_stat("prompt_cache_writes")
    except Exception as exc:  # pragma: no cover
        proxy_logger.warning("save_request_cache_failed key=%s error=%s", str(execution.get("cache_key") or "")[:12], str(exc))


def record_request_started(request_id: str, request_meta: dict) -> None:
    request_recorder.start(request_id, request_meta)


def record_request_finished(
    request_id: str,
    *,
    status_code: int | None,
    bytes_sent: int,
    duration_ms: int,
    stream: bool,
    error: str | None = None,
    sanitized_markers: int = 0,
    response_preview: str | None = None,
    repaired_tool_args: int = 0,
    client_gone: bool = False,
    extra_meta: dict | None = None,
) -> None:
    request_recorder.finish(
        request_id,
        status_code=status_code,
        bytes_sent=bytes_sent,
        duration_ms=duration_ms,
        stream=stream,
        error=error,
        sanitized_markers=sanitized_markers,
        response_preview=response_preview,
        repaired_tool_args=repaired_tool_args,
        client_gone=client_gone,
        extra_meta=extra_meta,
    )


def finalize_request_record(
    request_id: str,
    *,
    started_at: float,
    stream: bool,
    status_code: int | None = None,
    bytes_sent: int = 0,
    error: str | None = None,
    sanitized_markers: int = 0,
    response_preview: str | None = None,
    repaired_tool_args: int = 0,
    client_gone: bool = False,
    extra_meta: dict | None = None,
) -> int:
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    record_request_finished(
        request_id,
        status_code=status_code,
        bytes_sent=bytes_sent,
        duration_ms=duration_ms,
        stream=stream,
        error=error,
        sanitized_markers=sanitized_markers,
        response_preview=response_preview,
        repaired_tool_args=repaired_tool_args,
        client_gone=client_gone,
        extra_meta=extra_meta,
    )
    return duration_ms


def collect_local_model_ids() -> list[str]:
    model_ids: list[str] = []
    seen: set[str] = set()

    def add(model_name: str | None) -> None:
        text = str(model_name or "").strip().removeprefix("models/")
        if not text:
            return
        key = normalize_model_alias_key(text)
        if key in seen:
            return
        seen.add(key)
        model_ids.append(text)

    for logical_model, targets in (MODEL_ALIASES or {}).items():
        add(logical_model)
        for target in targets or []:
            add(target)

    for capability_model in (MODEL_CAPABILITIES or {}).keys():
        add(capability_model)

    model_lists = model_route_cache.get("model_lists") if isinstance(model_route_cache, dict) else {}
    now = time.time()
    if isinstance(model_lists, dict):
        for entry in model_lists.values():
            if not isinstance(entry, dict):
                continue
            if float(entry.get("expires_at", 0.0) or 0.0) <= now:
                continue
            for model_name in entry.get("models") or []:
                add(model_name)

    return sorted(
        model_ids,
        key=lambda item: (
            0 if "/" not in item else 1,
            item.lower(),
        ),
    )


def build_local_openai_models_payload() -> dict:
    created_at = int(APP_STARTED_AT_EPOCH)
    data = [
        {
            "id": model_id,
            "object": "model",
            "created": created_at,
            "owned_by": "local-proxy",
        }
        for model_id in collect_local_model_ids()
    ]
    return {
        "object": "list",
        "data": data,
    }


def local_models_response(*, protocol: str, subpath: str) -> Response:
    request_id = uuid.uuid4().hex[:8]
    started_at = time.perf_counter()
    sanitized_query = sanitize_query_string(request.query_string, secret_masker=mask_secret)
    proxy_logger.info(
        "request_id=%s 入站请求 协议=%s 方法=%s 路径=%s 来源=%s 查询=%s",
        request_id,
        protocol,
        request.method,
        request.path,
        request.remote_addr,
        sanitized_query,
    )

    payload = build_local_openai_models_payload()
    status_code = 200
    response_body: dict = payload

    requested_model_id = ""
    if subpath.startswith("models/") and ":" not in subpath:
        requested_model_id = subpath.split("/", 1)[1].removeprefix("models/")
        available = {
            str(item.get("id") or "").strip(): item
            for item in payload.get("data") or []
            if isinstance(item, dict)
        }
        if requested_model_id in available:
            response_body = available[requested_model_id]
        else:
            status_code = 404
            response_body = {
                "error": {
                    "message": f"模型 {requested_model_id} 未在本地代理的聚合模型列表中找到。",
                    "type": "invalid_request_error",
                    "param": "model",
                    "code": "model_not_found",
                }
            }

    if protocol == "gemini_models":
        response_body = convert_openai_models_response_to_gemini(response_body, subpath)

    body = json.dumps(response_body, ensure_ascii=False).encode("utf-8")
    request_meta = build_request_meta(
        request_id=request_id,
        sanitized_query=sanitized_query,
        upstream_url="local://models",
        stream=False,
        upstream_stream=False,
        retry_count=0,
        route_pool_size=max(0, len(UPSTREAM_URL_POOL)),
        attempt_urls=[],
        attempt_route_chain="",
        protocol=protocol,
        request_repairs=0,
        extra_fields={
            "logical_model": requested_model_id,
            "resolved_model": requested_model_id,
            "pool_name": "local-models",
            "cache_status": "local",
            "cache_note": "本地聚合模型清单",
        },
    )
    record_request_started(request_id, request_meta)
    duration_ms = finalize_request_record(
        request_id,
        started_at=started_at,
        status_code=status_code,
        bytes_sent=len(body),
        stream=False,
        extra_meta={
            "logical_model": requested_model_id,
            "resolved_model": requested_model_id,
            "pool_name": "local-models",
            "cache_status": "local",
            "cache_note": "本地聚合模型清单",
        },
    )
    proxy_logger.info(
        "request_id=%s 本地模型清单 状态=%s 协议=%s 字节=%s 耗时毫秒=%s 模型数=%s",
        request_id,
        status_code,
        protocol,
        len(body),
        duration_ms,
        len(payload.get("data") or []),
    )
    return Response(
        body,
        status=status_code,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Proxy-Retries": "0",
            "X-Proxy-Model-Source": "local-aggregate",
        },
    )


def read_recent_log_lines(limit: int = MAX_LOG_LINES) -> list[str]:
    return load_recent_log_lines(
        log_path=PROXY_LOG_PATH,
        app_started_at_epoch=APP_STARTED_AT_EPOCH,
        limit=limit,
    )


def clear_request_history() -> None:
    request_recorder.clear_history()


def build_runtime_snapshot() -> dict:
    with state_lock:
        route_health_snapshot = {
            route_url: dict(entry)
            for route_url, entry in route_health.items()
        }
    return assemble_runtime_snapshot(
        {
            "app_started_at_epoch": APP_STARTED_AT_EPOCH,
            "python_executable": sys.executable,
            "port": PORT,
            "request_timeout": REQUEST_TIMEOUT,
            "enable_request_normalization": ENABLE_REQUEST_NORMALIZATION,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
            "model_capability_count": len(MODEL_CAPABILITIES),
            "inject_zh_system_prompt": INJECT_ZH_SYSTEM_PROMPT,
            "force_upstream_chat_stream": FORCE_UPSTREAM_CHAT_STREAM,
            "upstream_urls": list(UPSTREAM_URL_POOL),
            "upstream_api_key": UPSTREAM_API_KEY,
            "proxy_api_key_count": len(PROXY_API_KEYS) + len([r for r in PROXY_API_KEY_RECORDS if r.get("enabled") is not False]),
            "proxy_api_key_env_count": len(PROXY_API_KEYS),
            "proxy_api_key_managed_count": len(PROXY_API_KEY_RECORDS),
            "proxy_api_key_managed_enabled_count": len([r for r in PROXY_API_KEY_RECORDS if r.get("enabled") is not False]),
            "mask_secret": mask_secret,
            "model_alias_count": len(MODEL_ALIASES),
            "model_aliases": dict(MODEL_ALIASES),
            "enable_model_probe": ENABLE_MODEL_PROBE,
            "model_probe_timeout_seconds": MODEL_PROBE_TIMEOUT_SECONDS,
            "model_probe_ttl_seconds": MODEL_PROBE_TTL_SECONDS,
            "model_route_cache_ttl_seconds": MODEL_ROUTE_CACHE_TTL_SECONDS,
            "enable_interruption_resume": ENABLE_INTERRUPTION_RESUME,
            "interruption_resume_ttl_seconds": INTERRUPTION_RESUME_TTL_SECONDS,
            "interruption_resume_max_chars": INTERRUPTION_RESUME_MAX_CHARS,
            "interruption_resume_min_chars": INTERRUPTION_RESUME_MIN_CHARS,
            "enable_model_candidate_race": ENABLE_MODEL_CANDIDATE_RACE,
            "model_candidate_race_limit": MODEL_CANDIDATE_RACE_LIMIT,
            "model_candidate_race_timeout_seconds": MODEL_CANDIDATE_RACE_TIMEOUT_SECONDS,
            "count_model_route_cache_entries": count_model_route_cache_entries,
            "count_interrupted_response_entries": count_interrupted_response_entries,
            "count_learned_model_capability_entries": count_learned_model_capability_entries,
            "model_list_cache_entries": model_route_cache.get("model_lists") or {},
            "model_route_cache_path": MODEL_ROUTE_CACHE_PATH,
            "db_label": STORAGE_DB_LABEL,
            "db_enabled": storage is not None,
            "cache_stats_snapshot": cache_stats.snapshot,
            "config_path": PROXY_CONFIG_PATH,
            "config_file_exists": PROXY_CONFIG_PATH.exists(),
            "max_retries": UPSTREAM_MAX_RETRIES,
            "retry_backoff_ms": UPSTREAM_RETRY_BACKOFF_MS,
            "retry_max_backoff_ms": UPSTREAM_RETRY_MAX_BACKOFF_MS,
            "route_failure_threshold": UPSTREAM_ROUTE_FAILURE_THRESHOLD,
            "route_cooldown_seconds": UPSTREAM_ROUTE_COOLDOWN_SECONDS,
            "route_switch_window_seconds": UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS,
            "randomize_endpoints": UPSTREAM_RANDOMIZE_ENDPOINTS,
            "retryable_status_codes": RETRYABLE_STATUS_CODES,
            "http_pool_connections": HTTP_POOL_CONNECTIONS,
            "http_pool_maxsize": HTTP_POOL_MAXSIZE,
            "pool_key_failure_threshold": POOL_KEY_FAILURE_THRESHOLD,
            "pool_key_cooldown_seconds": POOL_KEY_COOLDOWN_SECONDS,
            "connection_pool_snapshot": connection_pool_state.snapshot,
            "image_upstream_protocol": IMAGE_UPSTREAM_PROTOCOL,
            "image_task_poll_timeout_seconds": IMAGE_TASK_POLL_TIMEOUT_SECONDS,
            "image_task_poll_interval_seconds": IMAGE_TASK_POLL_INTERVAL_SECONDS,
            "route_health": route_health_snapshot,
            "capabilities": [
                "OpenAI Chat Completions",
                "OpenAI Images Generations",
                "Anthropic Messages",
                "Gemini GenerateContent",
                "Gemini streamGenerateContent",
                "Google Imagen predict",
                "Gemini image GenerateContent",
                "DashScope Qwen/Wanxiang image generation",
                "Gemini native tools -> OpenAI functions",
                "DSML invoke -> tool_calls/tool_use",
                "Assistant text transcript -> tool_calls",
                "Request-side tool schema normalization",
                "Model-aware completion token auto-clamp",
                "Route-level token limit learning",
                "Model alias normalization",
                "run_in_background tool-argument repair",
                "Chinese system prompt injection",
                "Upstream retry shield",
                "Multi-route failover",
                "Runtime channel config console",
                "SQLite request and model-route persistence",
                "Model-route cache hit metrics",
                "Controlled model candidate race",
                "Client disconnect upstream stream cleanup",
            ],
        }
    )


def dashboard_state() -> dict:
    with state_lock:
        route_health_snapshot = {
            route_url: dict(entry)
            for route_url, entry in route_health.items()
        }
    return assemble_dashboard_state(
        {
            "upstream_url": UPSTREAM_URL,
            "upstream_urls": list(UPSTREAM_URL_POOL),
            "proxy_pools": PROXY_POOLS,
            "log_path": PROXY_LOG_PATH,
            "build_runtime_snapshot": build_runtime_snapshot,
            "build_runtime_config_payload": build_runtime_config_payload,
            "request_recorder_snapshot": request_recorder.snapshot,
            "route_health": route_health_snapshot,
            "connection_pool_snapshot": connection_pool_state.snapshot,
            "read_recent_log_lines": read_recent_log_lines,
        }
    )


def response_indicates_client_gone(response: requests.Response) -> bool:
    searchable = extract_upstream_error_searchable_text(response)
    return any(marker in searchable for marker in CLIENT_GONE_MARKERS)


def build_openai_error_payload(
    *,
    status_code: int,
    preview: str,
    retry_count: int,
    upstream_payload: dict | None = None,
) -> dict:
    upstream_error = (upstream_payload or {}).get("error") if isinstance(upstream_payload, dict) else {}
    if not isinstance(upstream_error, dict):
        upstream_error = {}

    if status_code in {408, 504, 524}:
        default_type = "upstream_timeout"
        default_code = "upstream_timeout"
        default_message = "Upstream timed out after proxy retries."
    elif status_code in {429}:
        default_type = "upstream_rate_limited"
        default_code = "upstream_rate_limited"
        default_message = "Upstream rate limited this request."
    elif status_code >= 500:
        default_type = "upstream_service_error"
        default_code = "upstream_service_error"
        default_message = "Upstream service returned a temporary error."
    else:
        default_type = "upstream_error"
        default_code = "upstream_error"
        default_message = "Upstream returned an error."

    error_payload = {
        "message": upstream_error.get("message") or default_message,
        "type": upstream_error.get("type") or default_type,
        "param": upstream_error.get("param") or "",
        "code": upstream_error.get("code") or default_code,
        "proxy_retries": retry_count,
        "upstream_status": status_code,
    }
    if preview:
        error_payload["upstream_preview"] = preview

    return {"error": error_payload}


def classify_upstream_request_failure(
    request_exception: BaseException | None,
    *,
    forced_error_status: int | None = None,
    forced_error_payload: dict | None = None,
) -> dict:
    default_status = int(forced_error_status or 502)
    default_message = "Upstream request failed before a complete response was received."
    default_code = "upstream_request_failed"
    default_type = "upstream_connection_error"
    anthropic_error_type = "api_error"

    if isinstance(forced_error_payload, dict):
        error_block = forced_error_payload.get("error")
        if isinstance(error_block, dict):
            default_message = str(error_block.get("message") or default_message)
            default_code = str(error_block.get("code") or default_code)
            default_type = str(error_block.get("type") or default_type)

    text = str(request_exception or default_message).strip()
    lowered = text.lower()

    if is_client_gone_exception(request_exception) or text_indicates_client_gone(lowered):
        return {
            "status_code": 499,
            "message": "Client closed the downstream connection before the response completed.",
            "error_code": "client_gone",
            "error_type": "client_gone",
            "anthropic_error_type": "api_error",
            "client_gone": True,
        }

    if isinstance(request_exception, requests.Timeout) or any(
        marker in lowered for marker in ("read timed out", "connect timeout", "timed out", "timeout")
    ):
        return {
            "status_code": 504,
            "message": "Upstream timed out before the proxy received a complete response.",
            "error_code": "upstream_timeout",
            "error_type": "upstream_timeout",
            "anthropic_error_type": "overloaded_error",
            "client_gone": False,
        }

    if any(
        marker in lowered
        for marker in (
            "remotedisconnected",
            "remote end closed connection",
            "connection reset",
            "connection aborted",
            "connection refused",
            "connection broken",
            "incompleteread",
        )
    ):
        return {
            "status_code": 502,
            "message": "Upstream closed the connection before sending a complete response.",
            "error_code": "upstream_connection_closed",
            "error_type": "upstream_connection_closed",
            "anthropic_error_type": "api_error",
            "client_gone": False,
        }

    if default_status in {408, 504, 524}:
        anthropic_error_type = "overloaded_error"
        default_code = "upstream_timeout"
        default_type = "upstream_timeout"
        default_message = text or "Upstream timed out before the proxy received a complete response."
    elif default_status == 429:
        anthropic_error_type = "rate_limit_error"
        default_code = "upstream_rate_limited"
        default_type = "upstream_rate_limited"
        default_message = text or "Upstream rate limited this request."
    elif default_status >= 500:
        default_message = text or "Upstream service returned a temporary error."

    return {
        "status_code": default_status,
        "message": default_message,
        "error_code": default_code,
        "error_type": default_type,
        "anthropic_error_type": anthropic_error_type,
        "client_gone": False,
    }


def build_openai_error_payload_from_failure(
    *,
    request_exception: BaseException | None,
    retry_count: int,
    forced_error_status: int | None = None,
    forced_error_payload: dict | None = None,
) -> tuple[dict, dict]:
    failure = classify_upstream_request_failure(
        request_exception,
        forced_error_status=forced_error_status,
        forced_error_payload=forced_error_payload,
    )
    payload = build_openai_error_payload(
        status_code=int(failure["status_code"]),
        preview=str(request_exception or failure["message"]),
        retry_count=retry_count,
        upstream_payload={
            "error": {
                "message": failure["message"],
                "type": failure["error_type"],
                "code": failure["error_code"],
            }
        },
    )
    return payload, failure


def build_anthropic_error_payload_from_failure(
    *,
    request_exception: BaseException | None,
    retry_count: int,
    forced_error_status: int | None = None,
    forced_error_payload: dict | None = None,
) -> tuple[dict, dict]:
    failure = classify_upstream_request_failure(
        request_exception,
        forced_error_status=forced_error_status,
        forced_error_payload=forced_error_payload,
    )
    payload = build_anthropic_error_payload(
        status_code=int(failure["status_code"]),
        message=failure["message"],
        retry_count=retry_count,
        preview=str(request_exception or failure["message"]),
    )
    error_block = payload.get("error")
    if isinstance(error_block, dict):
        error_block["type"] = str(failure["anthropic_error_type"])
    return payload, failure


def build_proxy_error_response(
    *,
    upstream_response: requests.Response,
    requested_stream: bool,
    retry_count: int,
) -> tuple[bytes, str, str | None]:
    raw_text = extract_response_text(upstream_response)
    preview = raw_text.replace("\n", "\\n")[:280]
    upstream_payload = extract_error_payload_from_text(raw_text)

    if (
        isinstance(upstream_payload, dict)
        and "error" in upstream_payload
        and "application/json" in (upstream_response.headers.get("Content-Type", "").lower())
        and requested_stream is False
    ):
        response_body = upstream_payload
    else:
        response_body = build_openai_error_payload(
            status_code=upstream_response.status_code,
            preview=preview,
            retry_count=retry_count,
            upstream_payload=upstream_payload,
        )

    return (
        json.dumps(response_body, ensure_ascii=False).encode("utf-8"),
        preview,
        response_body.get("error", {}).get("message") if isinstance(response_body, dict) else None,
    )


def build_openai_malformed_success_payload(*, issue: dict, retry_count: int) -> dict:
    return build_openai_error_payload(
        status_code=502,
        preview=issue.get("preview", ""),
        retry_count=retry_count,
        upstream_payload={
            "error": {
                "message": issue.get("message") or "Upstream returned a malformed success payload.",
                "type": "upstream_malformed_success",
                "code": issue.get("code") or "upstream_malformed_success",
            }
        },
    )


def build_anthropic_malformed_success_payload(*, issue: dict, retry_count: int) -> dict:
    return build_anthropic_error_payload(
        status_code=502,
        message=issue.get("message") or "Upstream returned a malformed success payload.",
        retry_count=retry_count,
        preview=issue.get("preview", ""),
    )


def build_gemini_malformed_success_payload(*, issue: dict, retry_count: int) -> dict:
    return build_gemini_error_payload(
        status_code=502,
        message=issue.get("message") or "Upstream returned a malformed success payload.",
        retry_count=retry_count,
        preview=issue.get("preview", ""),
    )


def retry_malformed_success_once(
    *,
    route_hint: str,
    request_id: str,
    upstream_url: str,
    request_payload: dict | None,
    execution: dict | None,
    issue: dict,
) -> dict | None:
    malformed_success_fallbacks = int((execution or {}).get("malformed_success_fallbacks") or 0)
    if malformed_success_fallbacks >= 2 or not isinstance(request_payload, dict):
        return None

    proxy_logger.warning(
        "request_id=%s 异常成功体，准备同请求切换线路 次数=%s 当前线路=%s 原因=%s",
        request_id,
        malformed_success_fallbacks + 1,
        upstream_url,
        str(issue.get("code") or "malformed_success"),
    )
    mark_route_failure(upstream_url, str(issue.get("code") or "malformed_success"))
    next_execution = execute_upstream_request(route_hint, request_payload, request_id)
    if isinstance(next_execution, dict):
        next_execution["malformed_success_fallbacks"] = malformed_success_fallbacks + 1
    return next_execution if isinstance(next_execution, dict) else None


def log_and_record_malformed_success(
    *,
    request_id: str,
    upstream_url: str,
    route_hint: str,
    requested_stream: bool,
    started_at: float,
    retry_count: int,
    issue: dict,
    bytes_sent: int,
    sanitized_markers: int = 0,
    repaired_tool_args: int = 0,
) -> int:
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    preview = issue.get("preview", "")
    proxy_logger.error(
        "request_id=%s 上游=%s 路由=%s 状态=200 异常成功体=%s 流式=%s 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 预览=%s",
        request_id,
        upstream_url,
        route_hint,
        issue.get("code") or "unknown",
        str(requested_stream).lower(),
        bytes_sent,
        duration_ms,
        sanitized_markers,
        repaired_tool_args,
        retry_count,
        preview,
    )
    record_request_finished(
        request_id,
        status_code=502,
        bytes_sent=bytes_sent,
        duration_ms=duration_ms,
        stream=requested_stream,
        error=issue.get("code") or "upstream_malformed_success",
        sanitized_markers=sanitized_markers,
        response_preview=preview or None,
        repaired_tool_args=repaired_tool_args,
    )
    return duration_ms



def detect_inbound_protocol(subpath: str, request_payload: dict | None) -> str:
    if parse_gemini_generate_subpath(subpath):
        return "gemini_generate_content"

    if subpath == "messages":
        return "anthropic_messages"

    if request.headers.get("anthropic-version"):
        if payload_looks_anthropic(request_payload) or subpath == "chat/completions":
            return "anthropic_messages"

    if payload_looks_anthropic(request_payload):
        return "anthropic_messages"

    if subpath == "chat/completions":
        return "openai_chat_completions"

    return "passthrough"

def extract_upstream_error_message(upstream_response: requests.Response) -> tuple[str, str]:
    raw_text = extract_response_text(upstream_response)
    preview = raw_text.replace("\n", "\\n")[:280]
    payload = extract_error_payload_from_text(raw_text)
    if isinstance(payload, dict):
        error_payload = payload.get("error")
        if isinstance(error_payload, dict) and error_payload.get("message"):
            return str(error_payload["message"]), preview
    return f"Upstream returned HTTP {upstream_response.status_code}.", preview


def consume_openai_sse_events(upstream_response: requests.Response, tool_schemas: dict) -> dict:
    choice_states = {}
    sanitized_markers = 0
    repaired_tool_args = 0
    preview_parts = []
    response_events = []
    raw_error_lines = []
    total_bytes = 0
    skip_next_blank = False
    finished_choice_indexes: set[int] = set()

    for raw_line in iter_response_lines(upstream_response):
        text = raw_line.decode("utf-8", errors="ignore")
        if text == "" and skip_next_blank:
            skip_next_blank = False
            continue

        total_bytes += len(raw_line) + 1
        normalized_line, removed, repaired_count, event = normalize_sse_line(text, choice_states, tool_schemas)
        sanitized_markers += removed
        repaired_tool_args += repaired_count

        if normalized_line is None:
            skip_next_blank = True
            continue
        if normalized_line:
            skip_next_blank = False

        if event:
            if "error" in event and "choices" not in event:
                raw_error_lines.append(json.dumps(event, ensure_ascii=False))
                continue
            response_events.append(event)
            choices = event.get("choices") or []
            for choice in choices:
                delta = choice.get("delta") or {}
                if isinstance(delta.get("content"), str) and len(" ".join(preview_parts)) < 240:
                    append_preview_text(preview_parts, delta.get("content"))
                for tool_call in delta.get("tool_calls") or []:
                    function_data = tool_call.get("function") or {}
                    append_preview_tool(
                        preview_parts,
                        function_data.get("name"),
                        function_data.get("arguments"),
                        tool_schemas,
                    )

            if update_openai_stream_terminal_state(event, finished_choice_indexes):
                break

        if normalized_line and not normalized_line.startswith("data:"):
            raw_error_lines.append(normalized_line)

    return {
        "response_events": response_events,
        "raw_error_lines": raw_error_lines,
        "sanitized_markers": sanitized_markers,
        "repaired_tool_args": repaired_tool_args,
        "preview_parts": preview_parts,
        "total_bytes": total_bytes,
    }


def normalize_openai_response_body(response_body: dict, tool_schemas: dict) -> tuple[dict, int]:
    repaired_tool_args = 0
    repaired_tool_args += normalize_chat_completion_dsml_tool_calls(response_body, tool_schemas)
    repaired_tool_args += normalize_chat_completion_text_tool_calls(response_body, tool_schemas)
    repaired_tool_args += normalize_chat_completion_tool_calls(response_body, tool_schemas)
    normalize_chat_completion_finish_reasons(response_body)
    return response_body, repaired_tool_args


def read_upstream_openai_response_body(upstream_response: requests.Response, tool_schemas: dict) -> dict:
    content_type = upstream_response.headers.get("Content-Type", "")
    if "text/event-stream" in content_type.lower():
        consumed = consume_openai_sse_events(upstream_response, tool_schemas)
        openai_body = build_chat_completion_from_sse(consumed["response_events"])
        openai_body, additional_repairs = normalize_openai_response_body(openai_body, tool_schemas)
        consumed["repaired_tool_args"] += additional_repairs
        return {
            "openai_body": openai_body,
            "sanitized_markers": consumed["sanitized_markers"],
            "repaired_tool_args": consumed["repaired_tool_args"],
            "preview_parts": consumed["preview_parts"],
            "total_bytes": consumed["total_bytes"],
            "raw_error_lines": consumed["raw_error_lines"],
        }

    raw_body = upstream_response.content
    try:
        response_body = json.loads(raw_body.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        response_body = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:16]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": None,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": raw_body.decode("utf-8", errors="ignore"),
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        }

    repaired_tool_args = 0
    if isinstance(response_body, dict):
        response_body, repaired_tool_args = normalize_openai_response_body(response_body, tool_schemas)
    else:
        response_body = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:16]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": None,
            "choices": [],
            "usage": {},
        }

    preview_parts = []
    for choice in response_body.get("choices") or []:
        message = choice.get("message") or {}
        append_preview_text(preview_parts, message.get("content"))
        for tool_call in message.get("tool_calls") or []:
            function_data = tool_call.get("function") or {}
            append_preview_tool(
                preview_parts,
                function_data.get("name"),
                function_data.get("arguments"),
                tool_schemas,
            )
    return {
        "openai_body": response_body,
        "sanitized_markers": 0,
        "repaired_tool_args": repaired_tool_args,
        "preview_parts": preview_parts,
        "total_bytes": len(raw_body),
        "raw_error_lines": [],
    }


def convert_openai_stream_event_to_gemini_chunks(event: dict, stream_state: dict, tool_schemas: dict) -> list[dict]:
    chunks = []
    model = event.get("model")
    usage = event.get("usage") or {}

    for choice in event.get("choices") or []:
        choice_index = int(choice.get("index", 0) or 0)
        choice_state = stream_state.setdefault(
            choice_index,
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                },
                "tool_calls_emitted": False,
            },
        )
        delta = choice.get("delta") or {}
        parts = []
        content_text = delta.get("content")
        if isinstance(content_text, str) and content_text:
            choice_state["message"]["content"] = f"{choice_state['message'].get('content', '')}{content_text}"
            parts.append({"text": content_text})

        for tool_call_delta in delta.get("tool_calls") or []:
            merge_tool_call_delta(choice_state["message"], tool_call_delta)

        finish_reason = choice.get("finish_reason")
        if finish_reason is not None and not choice_state.get("tool_calls_emitted"):
            tool_parts = [
                part
                for part in openai_message_to_gemini_parts(choice_state["message"], tool_schemas)
                if "functionCall" in part
            ]
            if tool_parts:
                parts.extend(tool_parts)
                choice_state["tool_calls_emitted"] = True

        if not parts and finish_reason is None:
            continue

        candidate = {
            "index": choice_index,
            "content": {
                "role": "model",
            },
        }
        if parts:
            candidate["content"]["parts"] = parts
        if finish_reason is not None:
            candidate["finishReason"] = map_openai_finish_reason_to_gemini(finish_reason)
        chunk = {
            "candidates": [candidate],
            "modelVersion": model,
        }
        if usage:
            prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
            completion_tokens = int(usage.get("completion_tokens", 0) or 0)
            chunk["usageMetadata"] = {
                "promptTokenCount": prompt_tokens,
                "candidatesTokenCount": completion_tokens,
                "totalTokenCount": int(usage.get("total_tokens", prompt_tokens + completion_tokens) or 0),
            }
        chunks.append(chunk)

    if usage and not chunks:
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        chunks.append(
            {
                "usageMetadata": {
                    "promptTokenCount": prompt_tokens,
                    "candidatesTokenCount": completion_tokens,
                    "totalTokenCount": int(usage.get("total_tokens", prompt_tokens + completion_tokens) or 0),
                },
                "modelVersion": model,
            }
        )
    return chunks


def proxy_response(
    upstream_response: requests.Response,
    sanitize_dsml: bool,
    request_id: str,
    upstream_url: str,
    started_at: float,
    requested_stream: bool,
    route_hint: str,
    tool_schemas: dict,
    retry_count: int,
    protocol: str | None = None,
    request_payload: dict | None = None,
    execution: dict | None = None,
) -> Response:
    content_type = upstream_response.headers.get("Content-Type", "")
    response_headers = build_response_headers(upstream_response.headers)
    response_headers["X-Proxy-Retries"] = str(retry_count)
    empty_stream_fallbacks = int((execution or {}).get("empty_sse_fallbacks") or 0)

    if upstream_response.status_code >= 400:
        client_gone = response_indicates_client_gone(upstream_response)
        body, response_preview, error_message = build_proxy_error_response(
            upstream_response=upstream_response,
            requested_stream=requested_stream,
            retry_count=retry_count,
        )
        proxy_logger.info(
            "request_id=%s 上游=%s 状态=%s 流式=%s 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 预览=%s",
            request_id,
            upstream_url,
            upstream_response.status_code,
            str(requested_stream).lower(),
            len(body),
            int((time.perf_counter() - started_at) * 1000),
            0,
            0,
            retry_count,
            response_preview or "",
        )
        finalize_request_record(
            request_id,
            started_at=started_at,
            status_code=upstream_response.status_code,
            bytes_sent=len(body),
            stream=requested_stream,
            error="client_gone" if client_gone else (error_message if upstream_response.status_code >= 500 else None),
            sanitized_markers=0,
            response_preview=response_preview or None,
            repaired_tool_args=0,
            client_gone=client_gone,
            extra_meta=build_request_observability_meta(execution, request_payload),
        )
        response_headers["Content-Type"] = "application/json; charset=utf-8"
        return Response(body, status=upstream_response.status_code, headers=response_headers)

    if requested_stream and "text/event-stream" not in content_type.lower():
        consumed = read_upstream_openai_response_body(upstream_response, tool_schemas)
        issue = inspect_success_payload(
            route_hint=route_hint,
            content_type=content_type,
            body=upstream_response.content,
            response_body=consumed["openai_body"],
        )
        if issue:
            next_execution = retry_malformed_success_once(
                route_hint=route_hint,
                request_id=request_id,
                upstream_url=upstream_url,
                request_payload=request_payload,
                execution=execution,
                issue=issue,
            )
            next_response = next_execution.get("upstream_response") if isinstance(next_execution, dict) else None
            if next_response is not None:
                return proxy_response(
                    next_response,
                    sanitize_dsml=sanitize_dsml,
                    request_id=request_id,
                    upstream_url=str(next_execution.get("upstream_url") or upstream_url),
                    started_at=started_at,
                    requested_stream=False,
                    route_hint=route_hint,
                    tool_schemas=next_execution.get("tool_schemas") if isinstance(next_execution.get("tool_schemas"), dict) else tool_schemas,
                    retry_count=int(next_execution.get("retry_count") or retry_count),
                    protocol=protocol,
                    request_payload=request_payload,
                    execution=next_execution,
                )
            payload = build_openai_malformed_success_payload(issue=issue, retry_count=retry_count)
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            close_response_quietly(upstream_response)
            log_and_record_malformed_success(
                request_id=request_id,
                upstream_url=upstream_url,
                route_hint=route_hint,
                requested_stream=True,
                started_at=started_at,
                retry_count=retry_count,
                issue=issue,
                bytes_sent=len(body),
                sanitized_markers=consumed["sanitized_markers"],
                repaired_tool_args=consumed["repaired_tool_args"],
            )
            response_headers["Content-Type"] = "application/json; charset=utf-8"
            return Response(body, status=502, headers=response_headers)

        packets = build_openai_stream_packets_from_chat_completion(consumed["openai_body"])
        total_bytes = sum(len(packet) for packet in packets)
        response_preview = build_preview_summary(consumed["preview_parts"])
        close_response_quietly(upstream_response)
        resume_clear_meta = clear_interruption_resume_records(execution)
        proxy_logger.info(
            "request_id=%s 上游=%s 状态=%s 流式=true 合成来源=%s 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 预览=%s",
            request_id,
            upstream_url,
            upstream_response.status_code,
            content_type or "unknown",
            total_bytes,
            int((time.perf_counter() - started_at) * 1000),
            consumed["sanitized_markers"],
            consumed["repaired_tool_args"],
            retry_count,
            response_preview or "",
        )
        finalize_request_record(
            request_id,
            started_at=started_at,
            status_code=upstream_response.status_code,
            bytes_sent=total_bytes,
            stream=True,
            sanitized_markers=consumed["sanitized_markers"],
            response_preview=None,
            repaired_tool_args=consumed["repaired_tool_args"],
            extra_meta=build_request_observability_meta(execution, request_payload) | resume_clear_meta,
        )
        if isinstance(consumed.get("openai_body"), dict):
            save_request_cache_entry(
                execution=execution or {},
                protocol=protocol or "openai_chat_completions",
                path=route_hint,
                request_payload=request_payload,
                response_body=consumed["openai_body"],
                upstream_url=upstream_url,
            )
        apply_sse_response_headers(response_headers)
        return Response(packets, status=upstream_response.status_code, headers=response_headers)

    if "text/event-stream" in content_type.lower():
        apply_sse_response_headers(response_headers)
        choice_states = {}

        if requested_stream:
            prebuffered_raw_lines: list[bytes] = []
            preflight_heartbeat_count = 0
            preflight_raw_line_count = 0
            stream_iter = iter_response_lines_with_heartbeat(upstream_response, SSE_HEARTBEAT_SECONDS)
            preflight_empty_issue = None
            try:
                while True:
                    raw_line = next(stream_iter)
                    if raw_line is None:
                        preflight_heartbeat_count += 1
                        continue
                    preflight_raw_line_count += 1
                    prebuffered_raw_lines.append(raw_line)
                    break
            except StopIteration:
                preflight_empty_issue = {
                    "code": "empty_sse_success",
                    "message": "Upstream returned an empty streaming success payload.",
                    "preview": json.dumps(
                        {
                            "content_type": upstream_response.headers.get("Content-Type", ""),
                            "heartbeat_count": preflight_heartbeat_count,
                            "raw_line_count": preflight_raw_line_count,
                            "nonempty_line_count": 0,
                            "first_upstream_event_ms": None,
                            "first_data_event_ms": None,
                            "last_nonempty_line": "",
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }

            if preflight_empty_issue:
                mark_route_failure(upstream_url, preflight_empty_issue["code"])
                if empty_stream_fallbacks < 2 and isinstance(request_payload, dict):
                    proxy_logger.warning(
                        "request_id=%s 流式首包为空，准备同请求切换线路 次数=%s 当前线路=%s 原因=%s",
                        request_id,
                        empty_stream_fallbacks + 1,
                        upstream_url,
                        preflight_empty_issue["code"],
                    )
                    close_response_quietly(upstream_response)
                    next_execution = execute_upstream_request(route_hint, request_payload, request_id)
                    if isinstance(next_execution, dict):
                        next_execution["empty_sse_fallbacks"] = empty_stream_fallbacks + 1
                    next_response = next_execution.get("upstream_response") if isinstance(next_execution, dict) else None
                    if next_response is not None:
                        return proxy_response(
                            next_response,
                            sanitize_dsml=sanitize_dsml,
                            request_id=request_id,
                            upstream_url=str(next_execution.get("upstream_url") or upstream_url),
                            started_at=started_at,
                            requested_stream=requested_stream,
                            route_hint=route_hint,
                            tool_schemas=next_execution.get("tool_schemas") if isinstance(next_execution.get("tool_schemas"), dict) else tool_schemas,
                            retry_count=int(next_execution.get("retry_count") or retry_count),
                            protocol=protocol,
                            request_payload=request_payload,
                            execution=next_execution,
                        )

                payload = build_openai_malformed_success_payload(issue=preflight_empty_issue, retry_count=retry_count)
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                close_response_quietly(upstream_response)
                log_and_record_malformed_success(
                    request_id=request_id,
                    upstream_url=upstream_url,
                    route_hint=route_hint,
                    requested_stream=True,
                    started_at=started_at,
                    retry_count=retry_count,
                    issue=preflight_empty_issue,
                    bytes_sent=len(body),
                )
                response_headers["Content-Type"] = "application/json; charset=utf-8"
                return Response(body, status=502, headers=response_headers)

            def generate():
                total_bytes = 0
                stream_error = None
                stream_client_gone = False
                sanitized_markers = 0
                repaired_tool_args = 0
                preview_parts = []
                resume_text_parts: list[str] = []
                response_events = []
                stream_tail_lines = []
                terminal_finish_reasons = []
                saw_done = False
                emitted_data = False
                buffered_sse_payloads: list[bytes] = []
                skip_next_blank = False
                finished_choice_indexes: set[int] = set()
                expected_choice_count = openai_stream_expected_choice_count(request_payload)
                heartbeat_count = preflight_heartbeat_count
                raw_line_count = 0
                nonempty_line_count = 0
                first_upstream_event_ms = None
                first_data_event_ms = None
                last_nonempty_line = ""
                try:
                    issue = None
                    for raw_line in itertools.chain(prebuffered_raw_lines, stream_iter):
                        if raw_line is None:
                            heartbeat_payload = b": keep-alive\n\n"
                            heartbeat_count += 1
                            total_bytes += len(heartbeat_payload)
                            yield heartbeat_payload
                            continue
                        raw_line_count += 1
                        terminal_event = False
                        text = raw_line.decode("utf-8", errors="ignore")
                        if first_upstream_event_ms is None:
                            first_upstream_event_ms = int((time.perf_counter() - started_at) * 1000)
                        if text != "":
                            nonempty_line_count += 1
                            last_nonempty_line = text[:400]
                        if text == "" and skip_next_blank:
                            skip_next_blank = False
                            continue

                        normalized_line, removed, repaired_count, event = normalize_sse_line(text, choice_states, tool_schemas)
                        sanitized_markers += removed
                        repaired_tool_args += repaired_count

                        if normalized_line is None:
                            skip_next_blank = True
                            continue
                        if not emitted_data and normalized_line == "":
                            skip_next_blank = False
                            continue
                        if normalized_line == "data: [DONE]":
                            if not openai_stream_events_have_meaningful_output(response_events):
                                close_response_quietly(upstream_response)
                                break
                            saw_done = True
                            payload = b"data: [DONE]\n\n"
                            total_bytes += len(payload)
                            yield payload
                            close_response_quietly(upstream_response)
                            break
                        elif normalized_line.startswith("data:"):
                            if first_data_event_ms is None:
                                first_data_event_ms = int((time.perf_counter() - started_at) * 1000)
                            stream_tail_lines.append(normalized_line[:600])
                            if len(stream_tail_lines) > 8:
                                stream_tail_lines.pop(0)
                        if normalized_line:
                            skip_next_blank = False

                        if event:
                            terminal_event = update_openai_stream_terminal_state(
                                event,
                                finished_choice_indexes,
                                expected_choice_count=expected_choice_count,
                            )
                            response_events.append(event)
                            choices = event.get("choices") or []
                            for choice in choices:
                                delta = choice.get("delta") or {}
                                content_delta = delta.get("content")
                                if isinstance(content_delta, str):
                                    append_resume_text(resume_text_parts, content_delta)
                                    if len(" ".join(preview_parts)) < 240:
                                        append_preview_text(preview_parts, content_delta)
                                if len(" ".join(preview_parts)) < 240:
                                    for tool_call in delta.get("tool_calls") or []:
                                        function_data = tool_call.get("function") or {}
                                        append_preview_tool(
                                            preview_parts,
                                            function_data.get("name"),
                                            function_data.get("arguments"),
                                            tool_schemas,
                                        )
                                finish_reason = choice.get("finish_reason")
                                if finish_reason is not None:
                                    terminal_finish_reasons.append(str(finish_reason))
                                    if len(terminal_finish_reasons) > 8:
                                        terminal_finish_reasons.pop(0)

                        payload = f"{normalized_line}\n".encode("utf-8")
                        event_has_output = openai_stream_events_have_meaningful_output(response_events)
                        if event_has_output and not emitted_data:
                            emitted_data = True
                            for buffered_payload in buffered_sse_payloads:
                                total_bytes += len(buffered_payload)
                                yield buffered_payload
                            buffered_sse_payloads.clear()
                        if emitted_data:
                            total_bytes += len(payload)
                            yield payload
                        else:
                            buffered_sse_payloads.append(payload)
                        if terminal_event:
                            event_separator = b"\n"
                            if emitted_data:
                                total_bytes += len(event_separator)
                                yield event_separator
                            else:
                                buffered_sse_payloads.append(event_separator)
                            close_response_quietly(upstream_response)
                            break

                    if (
                        upstream_response.status_code < 400
                        and not openai_stream_events_have_meaningful_output(response_events)
                    ):
                        issue = {
                            "code": "empty_sse_success",
                            "message": (
                                "Upstream returned a streaming success payload with no usable output."
                                if response_events
                                else "Upstream returned an empty streaming success payload."
                            ),
                            "preview": json.dumps(
                                {
                                    "content_type": upstream_response.headers.get("Content-Type", ""),
                                    "heartbeat_count": heartbeat_count,
                                    "raw_line_count": raw_line_count,
                                    "nonempty_line_count": nonempty_line_count,
                                    "first_upstream_event_ms": first_upstream_event_ms,
                                    "first_data_event_ms": first_data_event_ms,
                                    "last_nonempty_line": last_nonempty_line,
                                },
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        }
                        mark_route_failure(upstream_url, issue["code"])
                        if total_bytes == 0 and empty_stream_fallbacks < 2 and isinstance(request_payload, dict):
                            stream_error = issue["code"]
                            proxy_logger.warning(
                                "request_id=%s 流式空载成功，生成阶段同请求切换线路 次数=%s 当前线路=%s",
                                request_id,
                                empty_stream_fallbacks + 1,
                                upstream_url,
                            )
                            close_response_quietly(upstream_response)
                            next_execution = execute_upstream_request(route_hint, request_payload, request_id)
                            if isinstance(next_execution, dict):
                                next_execution["empty_sse_fallbacks"] = empty_stream_fallbacks + 1
                            next_response = next_execution.get("upstream_response") if isinstance(next_execution, dict) else None
                            if next_response is not None:
                                next_proxy_response = proxy_response(
                                    next_response,
                                    sanitize_dsml=sanitize_dsml,
                                    request_id=request_id,
                                    upstream_url=str(next_execution.get("upstream_url") or upstream_url),
                                    started_at=started_at,
                                    requested_stream=requested_stream,
                                    route_hint=route_hint,
                                    tool_schemas=next_execution.get("tool_schemas") if isinstance(next_execution.get("tool_schemas"), dict) else tool_schemas,
                                    retry_count=int(next_execution.get("retry_count") or retry_count),
                                    protocol=protocol,
                                    request_payload=request_payload,
                                    execution=next_execution,
                                )
                                response_body = next_proxy_response.response
                                if isinstance(response_body, (bytes, bytearray)):
                                    yield bytes(response_body)
                                else:
                                    yield from response_body
                                return
                        error_packet = format_openai_sse_payload(
                            build_openai_malformed_success_payload(issue=issue, retry_count=retry_count)
                        )
                        stream_error = issue["code"]
                        total_bytes += len(error_packet)
                        yield error_packet

                    if upstream_response.status_code < 400 and not saw_done:
                        done_payload = b"data: [DONE]\n\n"
                        saw_done = True
                        total_bytes += len(done_payload)
                        yield done_payload
                except GeneratorExit as exc:  # pragma: no cover
                    if not saw_done:
                        stream_client_gone = True
                        stream_error = "client_gone"
                    close_response_quietly(upstream_response)
                    raise
                except Exception as exc:  # pragma: no cover
                    if is_client_gone_exception(exc):
                        stream_client_gone = True
                        stream_error = "client_gone"
                        close_response_quietly(upstream_response)
                    else:
                        stream_error = str(exc)
                    raise
                finally:
                    close_response_quietly(upstream_response)
                    duration_ms = int((time.perf_counter() - started_at) * 1000)
                    response_preview = build_preview_summary(preview_parts)
                    resume_save_meta = {}
                    if stream_client_gone:
                        resume_save_meta = save_interruption_resume_snapshot(
                            execution=execution,
                            protocol=protocol or "openai_chat_completions",
                            request_id=request_id,
                            upstream_url=upstream_url,
                            partial_text=build_resume_partial_text(resume_text_parts, response_preview),
                            response_preview=response_preview,
                            bytes_sent=total_bytes,
                        )
                    elif not stream_error:
                        resume_save_meta = clear_interruption_resume_records(execution)
                    tail_summary = " || ".join(stream_tail_lines[-4:])
                    finish_reason_summary = ", ".join(terminal_finish_reasons[-4:])
                    if stream_client_gone:
                        proxy_logger.info(
                            "request_id=%s 上游=%s 状态=%s 流式=true 客户端已断开=true 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 预览=%s 结束原因=%s 末尾片段=%s",
                            request_id,
                            upstream_url,
                            upstream_response.status_code,
                            total_bytes,
                            duration_ms,
                            sanitized_markers,
                            repaired_tool_args,
                            retry_count,
                            response_preview,
                            finish_reason_summary,
                            tail_summary,
                        )
                    elif stream_error:
                        proxy_logger.error(
                            "request_id=%s 上游=%s 状态=%s 流式=true 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 错误=%s 预览=%s 结束原因=%s 末尾片段=%s",
                            request_id,
                            upstream_url,
                            upstream_response.status_code,
                            total_bytes,
                            duration_ms,
                            sanitized_markers,
                            repaired_tool_args,
                            retry_count,
                            stream_error,
                            response_preview or issue.get("preview", "") if 'issue' in locals() else response_preview,
                            finish_reason_summary,
                            tail_summary,
                        )
                    else:
                        proxy_logger.info(
                            "request_id=%s 上游=%s 状态=%s 流式=true 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 预览=%s 结束原因=%s 末尾片段=%s",
                            request_id,
                            upstream_url,
                            upstream_response.status_code,
                            total_bytes,
                            duration_ms,
                            sanitized_markers,
                            repaired_tool_args,
                            retry_count,
                            response_preview if upstream_response.status_code >= 400 else "",
                            finish_reason_summary,
                            tail_summary,
                        )
                    finalize_request_record(
                        request_id,
                        started_at=started_at,
                        status_code=upstream_response.status_code,
                        bytes_sent=total_bytes,
                        stream=True,
                        error=stream_error,
                        sanitized_markers=sanitized_markers,
                        response_preview=response_preview if upstream_response.status_code >= 400 else None,
                        repaired_tool_args=repaired_tool_args,
                        client_gone=stream_client_gone,
                        extra_meta=build_request_observability_meta(execution, request_payload) | resume_save_meta,
                    )
                    if (
                        not stream_error
                        and not stream_client_gone
                        and response_events
                        and isinstance(aggregated_body := build_chat_completion_from_sse(response_events), dict)
                    ):
                        save_request_cache_entry(
                            execution=execution or {},
                            protocol=protocol or "openai_chat_completions",
                            path=route_hint,
                            request_payload=request_payload,
                            response_body=aggregated_body,
                            upstream_url=upstream_url,
                        )

            return Response(
                generate(),
                status=upstream_response.status_code,
                headers=response_headers,
            )

        total_bytes = 0
        sanitized_markers = 0
        repaired_tool_args = 0
        preview_parts = []
        response_events = []
        raw_error_lines = []
        skip_next_blank = False

        try:
            for raw_line in iter_response_lines(upstream_response):
                text = raw_line.decode("utf-8", errors="ignore")
                if text == "" and skip_next_blank:
                    skip_next_blank = False
                    continue
                total_bytes += len(raw_line) + 1
                normalized_line, removed, repaired_count, event = normalize_sse_line(text, choice_states, tool_schemas)
                sanitized_markers += removed
                repaired_tool_args += repaired_count

                if normalized_line is None:
                    skip_next_blank = True
                    continue
                if normalized_line:
                    skip_next_blank = False

                if event:
                    if "error" in event and "choices" not in event:
                        raw_error_lines.append(json.dumps(event, ensure_ascii=False))
                        continue
                    response_events.append(event)
                    choices = event.get("choices") or []
                    for choice in choices:
                        delta = choice.get("delta") or {}
                        if isinstance(delta.get("content"), str) and len(" ".join(preview_parts)) < 240:
                            append_preview_text(preview_parts, delta.get("content"))
                        for tool_call in delta.get("tool_calls") or []:
                            function_data = tool_call.get("function") or {}
                            append_preview_tool(
                                preview_parts,
                                function_data.get("name"),
                                function_data.get("arguments"),
                                tool_schemas,
                            )

                if normalized_line and not normalized_line.startswith("data:"):
                    raw_error_lines.append(normalized_line)
        except Exception as exc:  # pragma: no cover
            proxy_logger.error(
                "request_id=%s 上游=%s 状态=%s 流式=false 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 错误=%s 预览=%s",
                request_id,
                upstream_url,
                upstream_response.status_code,
                total_bytes,
                int((time.perf_counter() - started_at) * 1000),
                sanitized_markers,
                repaired_tool_args,
                retry_count,
                str(exc),
                build_preview_summary(preview_parts) or "",
            )
            finalize_request_record(
                request_id,
                started_at=started_at,
                status_code=upstream_response.status_code,
                bytes_sent=total_bytes,
                stream=False,
                error=str(exc),
                sanitized_markers=sanitized_markers,
                response_preview=build_preview_summary(preview_parts),
                repaired_tool_args=repaired_tool_args,
                extra_meta=build_request_observability_meta(execution, request_payload),
            )
            raise

        if raw_error_lines and not response_events:
            body_text = "\n".join(raw_error_lines)
            response_preview = body_text.replace("\n", "\\n")[:280]
            proxy_logger.info(
                "request_id=%s 上游=%s 状态=%s 流式=false 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 预览=%s",
                request_id,
                upstream_url,
                upstream_response.status_code,
                total_bytes,
                int((time.perf_counter() - started_at) * 1000),
                sanitized_markers,
                repaired_tool_args,
                retry_count,
                response_preview,
            )
            finalize_request_record(
                request_id,
                started_at=started_at,
                status_code=upstream_response.status_code,
                bytes_sent=len(body_text.encode('utf-8')),
                stream=False,
                sanitized_markers=sanitized_markers,
                response_preview=response_preview,
                repaired_tool_args=repaired_tool_args,
                extra_meta=build_request_observability_meta(execution, request_payload),
            )
            response_headers["Content-Type"] = "application/json"
            return Response(body_text.encode("utf-8"), status=upstream_response.status_code, headers=response_headers)

        aggregated_body = build_chat_completion_from_sse(response_events)
        repaired_tool_args += normalize_chat_completion_dsml_tool_calls(aggregated_body, tool_schemas)
        repaired_tool_args += normalize_chat_completion_text_tool_calls(aggregated_body, tool_schemas)
        repaired_tool_args += normalize_chat_completion_tool_calls(aggregated_body, tool_schemas)
        normalize_chat_completion_finish_reasons(aggregated_body)
        issue = inspect_success_payload(
            route_hint=route_hint,
            content_type=content_type,
            response_body=aggregated_body,
            response_events=response_events,
            raw_error_lines=raw_error_lines,
        )
        resume_clear_meta = {}
        if issue:
            next_execution = retry_malformed_success_once(
                route_hint=route_hint,
                request_id=request_id,
                upstream_url=upstream_url,
                request_payload=request_payload,
                execution=execution,
                issue=issue,
            )
            next_response = next_execution.get("upstream_response") if isinstance(next_execution, dict) else None
            if next_response is not None:
                return proxy_response(
                    next_response,
                    sanitize_dsml=sanitize_dsml,
                    request_id=request_id,
                    upstream_url=str(next_execution.get("upstream_url") or upstream_url),
                    started_at=started_at,
                    requested_stream=False,
                    route_hint=route_hint,
                    tool_schemas=next_execution.get("tool_schemas") if isinstance(next_execution.get("tool_schemas"), dict) else tool_schemas,
                    retry_count=int(next_execution.get("retry_count") or retry_count),
                    protocol=protocol,
                    request_payload=request_payload,
                    execution=next_execution,
                )
            payload = build_openai_malformed_success_payload(issue=issue, retry_count=retry_count)
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            close_response_quietly(upstream_response)
            log_and_record_malformed_success(
                request_id=request_id,
                upstream_url=upstream_url,
                route_hint=route_hint,
                requested_stream=False,
                started_at=started_at,
                retry_count=retry_count,
                issue=issue,
                bytes_sent=len(body),
                sanitized_markers=sanitized_markers,
                repaired_tool_args=repaired_tool_args,
            )
            response_headers["Content-Type"] = "application/json; charset=utf-8"
            return Response(body, status=502, headers=response_headers)
        body_bytes = json.dumps(aggregated_body, ensure_ascii=False).encode("utf-8")
        response_preview = build_preview_summary(preview_parts)
        close_response_quietly(upstream_response)
        resume_clear_meta = clear_interruption_resume_records(execution)
        proxy_logger.info(
            "request_id=%s 上游=%s 状态=%s 流式=false 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 预览=%s",
            request_id,
            upstream_url,
            upstream_response.status_code,
            len(body_bytes),
            int((time.perf_counter() - started_at) * 1000),
            sanitized_markers,
            repaired_tool_args,
            retry_count,
            response_preview if upstream_response.status_code >= 400 else "",
        )
        finalize_request_record(
            request_id,
            started_at=started_at,
            status_code=upstream_response.status_code,
            bytes_sent=len(body_bytes),
            stream=False,
            sanitized_markers=sanitized_markers,
            response_preview=response_preview if upstream_response.status_code >= 400 else None,
            repaired_tool_args=repaired_tool_args,
            extra_meta=build_request_observability_meta(execution, request_payload) | resume_clear_meta,
        )
        if isinstance(aggregated_body, dict):
            save_request_cache_entry(
                execution=execution or {},
                protocol=protocol or "openai_chat_completions",
                path=route_hint,
                request_payload=request_payload,
                response_body=aggregated_body,
                upstream_url=upstream_url,
            )
        response_headers["Content-Type"] = "application/json; charset=utf-8"
        return Response(body_bytes, status=upstream_response.status_code, headers=response_headers)

    body = upstream_response.content
    sanitized_markers = 0
    repaired_tool_args = 0
    json_body = None
    if sanitize_dsml and is_text_response(content_type):
        cleaned_text, sanitized_markers = sanitize_dsml_text(body.decode("utf-8", errors="ignore"))
        body = cleaned_text.encode("utf-8")

    if "application/json" in content_type.lower():
        try:
            json_body = json.loads(body.decode("utf-8", errors="ignore"))
        except json.JSONDecodeError:
            json_body = None
        if sanitize_dsml and isinstance(json_body, dict):
            repaired_tool_args += normalize_chat_completion_dsml_tool_calls(json_body, tool_schemas)
            repaired_tool_args += normalize_chat_completion_text_tool_calls(json_body, tool_schemas)
            repaired_tool_args += normalize_chat_completion_tool_calls(json_body, tool_schemas)
            normalize_chat_completion_finish_reasons(json_body)
            if repaired_tool_args or json_body.get("choices"):
                body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")

    issue = inspect_success_payload(
        route_hint=route_hint,
        content_type=content_type,
        body=body,
        json_body=json_body,
        response_body=json_body if isinstance(json_body, dict) else None,
    )
    if issue:
        payload = build_openai_malformed_success_payload(issue=issue, retry_count=retry_count)
        malformed_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        close_response_quietly(upstream_response)
        log_and_record_malformed_success(
            request_id=request_id,
            upstream_url=upstream_url,
            route_hint=route_hint,
            requested_stream=False,
            started_at=started_at,
            retry_count=retry_count,
            issue=issue,
            bytes_sent=len(malformed_body),
            sanitized_markers=sanitized_markers,
            repaired_tool_args=repaired_tool_args,
        )
        response_headers["Content-Type"] = "application/json; charset=utf-8"
        return Response(malformed_body, status=502, headers=response_headers)

    duration_ms = int((time.perf_counter() - started_at) * 1000)
    response_preview = None
    if upstream_response.status_code >= 400 and is_text_response(content_type):
        response_preview = body.decode("utf-8", errors="ignore").replace("\n", "\\n")[:280]
    close_response_quietly(upstream_response)
    resume_clear_meta = clear_interruption_resume_records(execution) if upstream_response.status_code < 400 else {}
    proxy_logger.info(
        "request_id=%s 上游=%s 状态=%s 流式=false 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 预览=%s",
        request_id,
        upstream_url,
        upstream_response.status_code,
        len(body),
        duration_ms,
        sanitized_markers,
        repaired_tool_args,
        retry_count,
        response_preview or "",
    )
    record_request_finished(
        request_id,
        status_code=upstream_response.status_code,
        bytes_sent=len(body),
        duration_ms=duration_ms,
        stream=False,
        sanitized_markers=sanitized_markers,
        response_preview=response_preview,
        repaired_tool_args=repaired_tool_args,
        extra_meta=build_request_observability_meta(execution, request_payload) | resume_clear_meta,
    )
    if isinstance(json_body, dict):
        save_request_cache_entry(
            execution=execution or {},
            protocol=protocol or "openai_chat_completions",
            path=route_hint,
            request_payload=request_payload,
            response_body=json_body,
            upstream_url=upstream_url,
        )

    return Response(body, status=upstream_response.status_code, headers=response_headers)


def add_cors_headers(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = (
        "Authorization, Content-Type, X-API-Key, X-Goog-API-Key, X-DashScope-Async, X-DashScope-Sse"
    )
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    return response


def proxy_api_auth_error_response(status_code: int, message: str, code: str) -> Response:
    payload = {
        "error": {
            "message": message,
            "type": "authentication_error",
            "param": None,
            "code": code,
        }
    }
    return Response(
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        status=status_code,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "WWW-Authenticate": 'Bearer realm="local-proxy"',
        },
    )


def require_proxy_api_key() -> Response | None:
    if request.method == "OPTIONS":
        return None

    result = verify_proxy_api_key(request, PROXY_API_KEYS, PROXY_API_KEY_RECORDS)
    if result.ok:
        return None

    if result.reason == "proxy_api_key_not_configured":
        proxy_logger.warning(
            "代理入口鉴权未配置，拒绝请求 path=%s remote=%s",
            request.path,
            request.remote_addr,
        )
        return proxy_api_auth_error_response(
            503,
            "代理入口 API Key 未配置，请设置 PROXY_API_KEYS 后重启服务。",
            "proxy_api_key_not_configured",
        )

    proxy_logger.warning(
        "代理入口鉴权失败 path=%s remote=%s reason=%s source=%s",
        request.path,
        request.remote_addr,
        result.reason,
        result.source or "-",
    )
    return proxy_api_auth_error_response(
        401,
        "代理入口 API Key 无效或缺失。",
        result.reason or "proxy_api_key_invalid",
    )


def health():
    runtime = build_runtime_snapshot()
    return {
        "ok": True,
        "upstream_url": UPSTREAM_URL,
        "upstream_urls": list(UPSTREAM_URL_POOL),
        "runtime": runtime,
    }


def debug_state():
    return dashboard_state()


def debug_config():
    if request.method == "OPTIONS":
        return Response(status=204)

    if request.method == "GET":
        return {
            "ok": True,
            "config": build_runtime_config_payload(),
            "runtime": build_runtime_snapshot(),
            "upstream_url": UPSTREAM_URL,
            "upstream_urls": list(UPSTREAM_URL_POOL),
            "upstream_url_count": len(UPSTREAM_URL_POOL),
        }

    payload = request.get_json(silent=True) or {}
    config = apply_runtime_config(payload, persist=True)
    return {
        "ok": True,
        "message": "配置已保存并生效。",
        "config": config,
        "runtime": build_runtime_snapshot(),
        "upstream_url": UPSTREAM_URL,
        "upstream_urls": list(UPSTREAM_URL_POOL),
        "upstream_url_count": len(UPSTREAM_URL_POOL),
    }


def debug_pool_test():
    if request.method == "OPTIONS":
        return Response(status=204)

    payload = request.get_json(silent=True) or {}
    pool_name = str(payload.get("pool_name") or "").strip()
    pool_index = payload.get("pool_index")

    target_index = None
    target_pool = None
    for idx, pool in enumerate(PROXY_POOLS):
        if pool_name and str(pool.get("name") or "").strip() == pool_name:
            target_index = idx
            target_pool = pool
            break
        if target_pool is None and pool_index is not None:
            try:
                if idx == int(pool_index):
                    target_index = idx
                    target_pool = pool
                    break
            except Exception:
                pass

    if target_pool is None:
        return {"ok": False, "message": "未找到对应的连接池。"}, 404

    urls = [str(u or "").strip() for u in target_pool.get("urls") or [] if str(u or "").strip()]
    keys = []
    for item in target_pool.get("keys") or []:
        if isinstance(item, dict):
            value = str(item.get("key") or "").strip()
        else:
            value = str(item or "").strip()
        if value:
            keys.append(value)

    if not urls:
        return {"ok": False, "message": "该连接池未配置可测试的上游地址。"}, 400

    timeout_seconds = min(max(5, REQUEST_TIMEOUT), 20)
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=4, pool_maxsize=8, max_retries=0)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    results = []
    summary_ok = False
    try:
        for raw_url in urls:
            normalized_url = normalize_pool_url(raw_url)
            models_url = model_list_url_from_endpoint(normalized_url)
            route_entry = {
                "url": normalized_url,
                "models_url": models_url,
                "keys": [],
            }
            if not keys:
                route_entry["keys"].append(
                    {
                        "key_preview": "",
                        "ok": False,
                        "status_code": None,
                        "latency_ms": 0,
                        "message": "未配置 API Key",
                    }
                )
                results.append(route_entry)
                continue

            for key in keys:
                started = time.perf_counter()
                try:
                    response = session.get(
                        models_url,
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Accept": "application/json",
                        },
                        timeout=timeout_seconds,
                    )
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    preview = extract_error_preview_from_response(response)[:220]
                    item_ok = response.status_code < 400
                    if item_ok:
                        summary_ok = True
                    route_entry["keys"].append(
                        {
                            "key_preview": mask_secret(key),
                            "ok": item_ok,
                            "status_code": response.status_code,
                            "latency_ms": latency_ms,
                            "message": "OK" if item_ok else (preview or f"HTTP {response.status_code}"),
                        }
                    )
                except requests.RequestException as exc:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    route_entry["keys"].append(
                        {
                            "key_preview": mask_secret(key),
                            "ok": False,
                            "status_code": None,
                            "latency_ms": latency_ms,
                            "message": str(exc),
                        }
                    )
            results.append(route_entry)
    finally:
        session.close()

    return {
        "ok": True,
        "pool_index": target_index,
        "pool_name": str(target_pool.get("name") or f"连接池 {int(target_index or 0) + 1}"),
        "pool_enabled": bool(target_pool.get("enabled", True)),
        "summary_ok": summary_ok,
        "tested_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
    }


def debug_requests_clear():
    if request.method == "OPTIONS":
        return Response(status=204)
    clear_request_history()
    return {"ok": True, "message": "请求历史已清空。"}


def proxy_api_key_public_payload(*, generated_key: str = "") -> dict:
    return {
        "ok": True,
        "keys": [public_proxy_api_key_record(record) for record in PROXY_API_KEY_RECORDS],
        "env_key_count": len(PROXY_API_KEYS),
        "managed_key_count": len(PROXY_API_KEY_RECORDS),
        "managed_enabled_count": len([record for record in PROXY_API_KEY_RECORDS if record.get("enabled") is not False]),
        "generated_key": generated_key,
    }


def persist_proxy_api_key_records() -> None:
    global PROXY_API_KEY_RECORDS
    PROXY_API_KEY_RECORDS = normalize_proxy_api_key_records(PROXY_API_KEY_RECORDS)
    save_runtime_config_to_disk()


def debug_proxy_api_keys():
    global PROXY_API_KEY_RECORDS

    if request.method == "OPTIONS":
        return Response(status=204)

    if request.method == "GET":
        return proxy_api_key_public_payload()

    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "create").strip().lower()

    if action == "create":
        record, generated_key = make_proxy_api_key_record(payload.get("name"))
        PROXY_API_KEY_RECORDS.append(record)
        persist_proxy_api_key_records()
        return proxy_api_key_public_payload(generated_key=generated_key)

    key_id = str(payload.get("id") or "").strip()
    target = None
    for record in PROXY_API_KEY_RECORDS:
        if str(record.get("id") or "") == key_id:
            target = record
            break
    if target is None:
        return {"ok": False, "message": "未找到入口 Key。"}, 404

    if action == "update":
        if "name" in payload:
            target["name"] = str(payload.get("name") or "").strip()[:80] or "NEWAPI"
        if "enabled" in payload:
            target["enabled"] = payload.get("enabled") is not False
        target["updated_at"] = utc_now_text()
        persist_proxy_api_key_records()
        return proxy_api_key_public_payload()

    if action == "delete":
        PROXY_API_KEY_RECORDS = [
            record
            for record in PROXY_API_KEY_RECORDS
            if str(record.get("id") or "") != key_id
        ]
        persist_proxy_api_key_records()
        return proxy_api_key_public_payload()

    return {"ok": False, "message": "不支持的入口 Key 操作。"}, 400


def v1_root():
    if request.method == "OPTIONS":
        return Response(status=204)

    accept_header = request.headers.get("Accept", "").lower()
    if "text/html" in accept_header:
        if not is_authenticated():
            from flask import redirect as _redirect

            return _redirect("/login")
        dashboard_html = DASHBOARD_TEMPLATE.replace(
            "</body>",
            '<div style="position:fixed;bottom:20px;right:20px;z-index:9999"><a href="/logout" style="display:inline-block;padding:8px 16px;background:#ef4444;color:#fff;border-radius:8px;text-decoration:none;font-size:13px;font-weight:600;box-shadow:0 2px 8px rgba(239,68,68,.35)">退出登录</a></div></body>',
        )
        return render_template_string(
            dashboard_html,
            port=PORT,
        )

    auth_error = require_proxy_api_key()
    if auth_error is not None:
        return auth_error

    return {
        "ok": True,
        "message": "本地代理运行中。用浏览器打开当前地址即可查看控制台并管理渠道配置。",
        "upstream_url": UPSTREAM_URL,
        "upstream_urls": list(UPSTREAM_URL_POOL),
        "dashboard_state_url": "/debug/state",
        "config_api_url": "/debug/config",
        "supported_protocols": [
            "OpenAI Chat Completions",
            "OpenAI Images Generations",
            "Anthropic Messages",
            "Gemini GenerateContent",
            "Google Imagen predict",
            "DashScope Qwen/Wanxiang image generation",
        ],
        "protocol_auto_detect": True,
        "request_normalization": ENABLE_REQUEST_NORMALIZATION,
        "inject_zh_system_prompt": INJECT_ZH_SYSTEM_PROMPT,
        "retry_max_retries": UPSTREAM_MAX_RETRIES,
        "route_switch_window_seconds": UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS,
    }


def gemini_version_root():
    if request.method == "OPTIONS":
        return Response(status=204)
    auth_error = require_proxy_api_key()
    if auth_error is not None:
        return auth_error
    return {
        "ok": True,
        "message": "本地代理 Gemini 兼容入口运行中。",
        "generate_content": f"{request.path.rstrip('/')}/models/{{model}}:generateContent",
        "stream_generate_content": f"{request.path.rstrip('/')}/models/{{model}}:streamGenerateContent?alt=sse",
        "imagen_predict": f"{request.path.rstrip('/')}/models/{{model}}:predict",
        "openai_compat": f"{request.path.rstrip('/')}/openai/chat/completions",
    }


def gemini_error_response(
    *,
    status_code: int,
    message: str,
    retry_count: int,
    preview: str = "",
) -> Response:
    body = json.dumps(
        build_gemini_error_payload(
            status_code=status_code,
            message=message,
            retry_count=retry_count,
            preview=preview,
        ),
        ensure_ascii=False,
    ).encode("utf-8")
    return Response(
        body,
        status=status_code,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Proxy-Retries": str(retry_count),
        },
    )


def convert_openai_model_to_gemini(model_payload) -> dict:
    if isinstance(model_payload, str):
        model_id = model_payload
    elif isinstance(model_payload, dict):
        model_id = str(model_payload.get("id") or model_payload.get("name") or "")
    else:
        model_id = ""
    model_id = model_id.removeprefix("models/")
    model_name = f"models/{model_id}" if model_id else "models/unknown"
    return {
        "name": model_name,
        "baseModelId": model_id,
        "version": "",
        "displayName": model_id,
        "description": "Proxied OpenAI-compatible model exposed through Gemini-compatible schema.",
        "inputTokenLimit": 0,
        "outputTokenLimit": 0,
        "supportedGenerationMethods": [
            "generateContent",
            "streamGenerateContent",
        ],
    }


def convert_openai_models_response_to_gemini(response_body: dict, subpath: str) -> dict:
    if "data" in response_body and isinstance(response_body.get("data"), list):
        return {
            "models": [
                convert_openai_model_to_gemini(model)
                for model in response_body.get("data") or []
            ]
        }
    if "id" in response_body or "name" in response_body:
        return convert_openai_model_to_gemini(response_body)
    model_id = str(subpath or "").split("/", 1)[-1] if "/" in str(subpath or "") else ""
    if model_id:
        return convert_openai_model_to_gemini(model_id)
    return {"models": []}


def gemini_models_proxy(subpath: str):
    return local_models_response(protocol="gemini_models", subpath=subpath)


def gemini_generate_content(subpath: str, request_payload: dict | None):
    path_meta = parse_gemini_generate_subpath(subpath)
    if not path_meta:
        return gemini_error_response(
            status_code=404,
            message="Gemini endpoint not found.",
            retry_count=0,
        )

    request_id = uuid.uuid4().hex[:8]
    started_at = time.perf_counter()
    requested_stream = bool(path_meta.get("stream"))
    openai_payload, gemini_request_repairs = convert_gemini_request_to_openai(request_payload or {}, path_meta)
    sanitized_query = sanitize_query_string(request.query_string, secret_masker=mask_secret)
    proxy_logger.info(
        "request_id=%s 入站请求 协议=gemini_generate_content 方法=%s 路径=%s 来源=%s 查询=%s",
        request_id,
        request.method,
        request.path,
        request.remote_addr,
        sanitized_query,
    )

    execution = None
    if requested_stream:
        background_execution = start_background_upstream_execution("chat/completions", openai_payload, request_id)
        ready, async_execution, async_error = wait_background_upstream_execution(
            background_execution,
            STREAM_OPEN_GRACE_SECONDS,
        )
        if not ready:
            initial_urls = build_upstream_url_candidates("chat/completions")
            record_request_started(
                request_id,
                build_pending_stream_request_meta(
                    request_id=request_id,
                    sanitized_query=sanitized_query,
                    upstream_urls=initial_urls,
                    protocol="gemini_generate_content",
                    request_repairs=gemini_request_repairs,
                ),
            )
            return gemini_stream_response_with_connect_heartbeat(
                background_execution=background_execution,
                request_id=request_id,
                started_at=started_at,
                observability_payload=openai_payload,
            )
        if async_error is not None:
            initial_urls = build_upstream_url_candidates("chat/completions")
            execution = {
                "upstream_url": initial_urls[0] if initial_urls else "",
                "tool_schemas": {},
                "upstream_stream": True,
                "upstream_response": None,
                "attempts": [],
                "request_exception": async_error,
                "retry_count": 0,
                "route_pool_size": len(initial_urls),
                "request_repairs": 0,
            }
        else:
            execution = async_execution
    else:
        execution = execute_upstream_request("chat/completions", openai_payload, request_id)

    execution = execution or {}
    upstream_url = execution["upstream_url"]
    tool_schemas = execution["tool_schemas"]
    upstream_response = execution["upstream_response"]
    retry_count = execution["retry_count"]
    attempts = execution["attempts"]
    request_exception = execution["request_exception"]
    attempt_urls, attempt_route_chain = summarize_attempt_routes(attempts)

    request_meta = build_request_meta(
        request_id=request_id,
        sanitized_query=sanitized_query,
        upstream_url=upstream_url,
        stream=requested_stream,
        upstream_stream=execution["upstream_stream"],
        retry_count=retry_count,
        route_pool_size=execution["route_pool_size"],
        attempt_urls=attempt_urls,
        attempt_route_chain=attempt_route_chain,
        protocol="gemini_generate_content",
        request_repairs=gemini_request_repairs + execution["request_repairs"],
        execution=execution,
        request_payload=openai_payload,
    )
    record_request_started(request_id, request_meta)

    if retry_count > 0:
        proxy_logger.warning(
            "request_id=%s 上游尝试摘要=%s",
            request_id,
            summarize_attempts_for_log(attempts),
        )

    if upstream_response is None:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        forced_error_payload = execution.get("forced_error_payload")
        forced_error_status = int(execution.get("forced_error_status") or 502)
        error_message = str(request_exception) if request_exception else "upstream request failed"
        if isinstance(forced_error_payload, dict):
            error_block = forced_error_payload.get("error")
            if isinstance(error_block, dict):
                error_message = str(error_block.get("message") or error_message)
        record_request_finished(
            request_id,
            status_code=forced_error_status if isinstance(forced_error_payload, dict) else 502,
            bytes_sent=len(error_message.encode("utf-8")),
            duration_ms=duration_ms,
            stream=requested_stream,
            error=error_message,
            sanitized_markers=0,
            response_preview=error_message,
            repaired_tool_args=0,
            extra_meta=build_request_observability_meta(execution, openai_payload),
        )
        return gemini_error_response(
            status_code=forced_error_status if isinstance(forced_error_payload, dict) else 502,
            message=error_message,
            retry_count=retry_count,
            preview=error_message,
        )

    if upstream_response.status_code >= 400:
        client_gone = response_indicates_client_gone(upstream_response)
        error_message, preview = extract_upstream_error_message(upstream_response)
        body_preview = preview or error_message
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        body = json.dumps(
            build_gemini_error_payload(
                status_code=upstream_response.status_code,
                message=error_message,
                retry_count=retry_count,
                preview=preview,
            ),
            ensure_ascii=False,
        ).encode("utf-8")
        record_request_finished(
            request_id,
            status_code=upstream_response.status_code,
            bytes_sent=len(body),
            duration_ms=duration_ms,
            stream=requested_stream,
            error="client_gone" if client_gone else (error_message if upstream_response.status_code >= 500 else None),
            sanitized_markers=0,
            response_preview=body_preview,
            repaired_tool_args=0,
            client_gone=client_gone,
        )
        return Response(
            body,
            status=upstream_response.status_code,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Proxy-Retries": str(retry_count),
            },
        )

    if requested_stream:
        return handle_gemini_stream_response(
            upstream_response=upstream_response,
            request_id=request_id,
            upstream_url=upstream_url,
            started_at=started_at,
            tool_schemas=tool_schemas,
            retry_count=retry_count,
            observability_meta=build_request_observability_meta(execution, openai_payload) | {"_upstream_openai_payload": openai_payload, "_execution": execution},
        )

    if execution.get("cache_hit") and isinstance(execution.get("cached_response_body"), dict):
        body = json.dumps(execution["cached_response_body"], ensure_ascii=False).encode("utf-8")
        duration_ms = record_request_cache_hit(
            request_id,
            body,
            started_at,
            requested_stream,
            execution=execution,
            extra_meta=build_request_observability_meta(execution, request_payload),
        )
        proxy_logger.info(
            "request_id=%s 代理缓存命中 协议=gemini_generate_content 路径=%s 字节=%s 耗时毫秒=%s key=%s 来源=%s",
            request_id,
            request.path,
            len(body),
            duration_ms,
            str(execution.get("cache_key") or "")[:12],
            str(execution.get("cache_source") or "sqlite"),
        )
        return Response(
            body,
            status=200,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Proxy-Retries": "0",
                "X-Proxy-Cache": "hit",
            },
        )

    consumed = read_upstream_openai_response_body(upstream_response, tool_schemas)
    gemini_body = convert_openai_response_to_gemini(consumed["openai_body"], tool_schemas)
    body = json.dumps(gemini_body, ensure_ascii=False).encode("utf-8")
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    response_preview = build_preview_summary(consumed["preview_parts"])
    proxy_logger.info(
        "request_id=%s 上游=%s 状态=%s 协议=gemini_generate_content 流式=false 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 预览=%s",
        request_id,
        upstream_url,
        upstream_response.status_code,
        len(body),
        duration_ms,
        consumed["sanitized_markers"],
        consumed["repaired_tool_args"],
        retry_count,
        response_preview or "",
    )
    save_request_cache_entry(
        execution=execution,
        protocol="gemini_generate_content",
        path="chat/completions",
        request_payload=openai_payload,
        response_body=gemini_body,
        upstream_url=upstream_url,
    )
    record_request_finished(
        request_id,
        status_code=upstream_response.status_code,
        bytes_sent=len(body),
        duration_ms=duration_ms,
        stream=False,
        sanitized_markers=consumed["sanitized_markers"],
        response_preview=response_preview if upstream_response.status_code >= 400 else None,
        repaired_tool_args=consumed["repaired_tool_args"],
    )
    return Response(
        body,
        status=200,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Proxy-Retries": str(retry_count),
        },
    )


def anthropic_messages():
    if request.method == "OPTIONS":
        return Response(status=204)
    auth_error = require_proxy_api_key()
    if auth_error is not None:
        return auth_error

    request_id = uuid.uuid4().hex[:8]
    started_at = time.perf_counter()
    request_payload = request.get_json(silent=True) or {}
    requested_stream = bool(request_payload.get("stream"))
    openai_payload = convert_anthropic_request_to_openai(request_payload)
    sanitized_query = sanitize_query_string(request.query_string, secret_masker=mask_secret)
    proxy_logger.info(
        "request_id=%s 入站请求 协议=anthropic_messages 方法=%s 路径=%s 来源=%s 查询=%s",
        request_id,
        request.method,
        request.path,
        request.remote_addr,
        sanitized_query,
    )

    execution = None
    if requested_stream:
        background_execution = start_background_upstream_execution("chat/completions", openai_payload, request_id)
        ready, async_execution, async_error = wait_background_upstream_execution(
            background_execution,
            STREAM_OPEN_GRACE_SECONDS,
        )
        if not ready:
            initial_urls = build_upstream_url_candidates("chat/completions")
            record_request_started(
                request_id,
                {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.path,
                    "query": sanitized_query,
                    "remote": request.remote_addr,
                    "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "upstream_url": initial_urls[0] if initial_urls else "",
                    "stream": True,
                    "upstream_stream": True,
                    "retry_count": 0,
                    "route_pool_size": len(initial_urls),
                    "upstream_attempt_urls": initial_urls,
                    "upstream_attempt_chain": " -> ".join(initial_urls),
                    "protocol": "anthropic_messages",
                    "request_repairs": 0,
                },
            )
            return anthropic_stream_response_with_connect_heartbeat(
                background_execution=background_execution,
                request_id=request_id,
                started_at=started_at,
                request_payload=request_payload,
                observability_payload=openai_payload,
            )
        if async_error is not None:
            initial_urls = build_upstream_url_candidates("chat/completions")
            execution = {
                "upstream_url": initial_urls[0] if initial_urls else "",
                "tool_schemas": {},
                "upstream_stream": True,
                "upstream_response": None,
                "attempts": [],
                "request_exception": async_error,
                "retry_count": 0,
                "route_pool_size": len(initial_urls),
                "request_repairs": 0,
            }
        else:
            execution = async_execution
    else:
        execution = execute_upstream_request("chat/completions", openai_payload, request_id)

    execution = execution or {}
    upstream_url = execution["upstream_url"]
    tool_schemas = execution["tool_schemas"]
    upstream_response = execution["upstream_response"]
    retry_count = execution["retry_count"]
    attempts = execution["attempts"]
    request_exception = execution["request_exception"]
    attempt_urls, attempt_route_chain = summarize_attempt_routes(attempts)
    request_meta = build_request_meta(
        request_id=request_id,
        sanitized_query=sanitized_query,
        upstream_url=upstream_url,
        stream=requested_stream,
        upstream_stream=execution["upstream_stream"],
        retry_count=retry_count,
        route_pool_size=execution["route_pool_size"],
        attempt_urls=attempt_urls,
        attempt_route_chain=attempt_route_chain,
        protocol="anthropic_messages",
        request_repairs=0,
        execution=execution,
        request_payload=openai_payload,
    )
    record_request_started(request_id, request_meta)

    if retry_count > 0:
        proxy_logger.warning(
            "request_id=%s 上游尝试摘要=%s",
            request_id,
            summarize_attempts_for_log(attempts),
        )

    if upstream_response is None:
        forced_error_payload = execution.get("forced_error_payload")
        forced_error_status = int(execution.get("forced_error_status") or 502)
        payload, failure = build_anthropic_error_payload_from_failure(
            request_exception=request_exception,
            retry_count=retry_count,
            forced_error_status=forced_error_status,
            forced_error_payload=forced_error_payload if isinstance(forced_error_payload, dict) else None,
        )
        error_message = str(failure["message"])
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        proxy_logger.error(
            "request_id=%s 上游=%s 状态=%s 协议=anthropic_messages 耗时毫秒=%s 重试次数=%s 错误=%s",
            request_id,
            upstream_url,
            int(failure["status_code"]),
            int((time.perf_counter() - started_at) * 1000),
            retry_count,
            error_message,
        )
        finalize_request_record(
            request_id,
            started_at=started_at,
            status_code=int(failure["status_code"]),
            bytes_sent=len(body),
            stream=requested_stream,
            error=error_message,
            sanitized_markers=0,
            response_preview=str(request_exception or error_message),
            repaired_tool_args=0,
            client_gone=bool(failure["client_gone"]),
            extra_meta=build_request_observability_meta(execution, openai_payload),
        )
        return Response(
            body,
            status=int(failure["status_code"]),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Proxy-Retries": str(retry_count),
            },
        )

    if upstream_response.status_code >= 400:
        client_gone = response_indicates_client_gone(upstream_response)
        error_message, preview = extract_upstream_error_message(upstream_response)
        payload = build_anthropic_error_payload(
            status_code=upstream_response.status_code,
            message=error_message,
            retry_count=retry_count,
            preview=preview,
        )
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        proxy_logger.info(
            "request_id=%s 上游=%s 状态=%s 协议=anthropic_messages 耗时毫秒=%s 重试次数=%s 预览=%s",
            request_id,
            upstream_url,
            upstream_response.status_code,
            duration_ms,
            retry_count,
            preview,
        )
        record_request_finished(
            request_id,
            status_code=upstream_response.status_code,
            bytes_sent=len(body),
            duration_ms=duration_ms,
            stream=requested_stream,
            error="client_gone" if client_gone else (error_message if upstream_response.status_code >= 500 else None),
            sanitized_markers=0,
            response_preview=preview,
            repaired_tool_args=0,
            client_gone=client_gone,
            extra_meta=build_request_observability_meta(execution, openai_payload),
        )
        return Response(
            body,
            status=upstream_response.status_code,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Proxy-Retries": str(retry_count),
            },
        )

    if requested_stream:
        return handle_anthropic_stream_response(
            upstream_response=upstream_response,
            request_id=request_id,
            upstream_url=upstream_url,
            started_at=started_at,
            request_payload=request_payload,
            tool_schemas=tool_schemas,
            retry_count=retry_count,
            observability_meta=build_request_observability_meta(execution, openai_payload) | {"_upstream_openai_payload": openai_payload, "_execution": execution},
        )

    content_type = upstream_response.headers.get("Content-Type", "")
    if "text/event-stream" in content_type.lower():
        consumed = consume_openai_sse_events(upstream_response, tool_schemas)
        openai_body = build_chat_completion_from_sse(consumed["response_events"])
        consumed["repaired_tool_args"] += normalize_chat_completion_dsml_tool_calls(openai_body, tool_schemas)
        consumed["repaired_tool_args"] += normalize_chat_completion_text_tool_calls(openai_body, tool_schemas)
        consumed["repaired_tool_args"] += normalize_chat_completion_tool_calls(openai_body, tool_schemas)
        normalize_chat_completion_finish_reasons(openai_body)
        clear_interruption_resume_records(execution)
    else:
        consumed = read_upstream_openai_response_body(upstream_response, tool_schemas)
        openai_body = consumed["openai_body"]

    issue = inspect_success_payload(
        route_hint="chat/completions",
        content_type=content_type,
        body=upstream_response.content if "text/event-stream" not in content_type.lower() else None,
        response_body=openai_body,
        response_events=consumed.get("response_events"),
        raw_error_lines=consumed.get("raw_error_lines"),
    )
    if issue:
        next_execution = retry_malformed_success_once(
            route_hint="chat/completions",
            request_id=request_id,
            upstream_url=upstream_url,
            request_payload=openai_payload,
            execution=execution,
            issue=issue,
        )
        next_response = next_execution.get("upstream_response") if isinstance(next_execution, dict) else None
        if next_response is not None:
            next_retry_count = int(next_execution.get("retry_count") or retry_count)
            if requested_stream:
                return handle_anthropic_stream_response(
                    upstream_response=next_response,
                    request_id=request_id,
                    upstream_url=str(next_execution.get("upstream_url") or upstream_url),
                    started_at=started_at,
                    request_payload=request_payload,
                    tool_schemas=next_execution.get("tool_schemas") if isinstance(next_execution.get("tool_schemas"), dict) else tool_schemas,
                    retry_count=next_retry_count,
                    observability_meta=build_request_observability_meta(next_execution, openai_payload) | {"_execution": next_execution},
                )
            if "text/event-stream" in str(next_response.headers.get("Content-Type", "")).lower():
                upstream_response = next_response
                retry_count = next_retry_count
                tool_schemas = next_execution.get("tool_schemas") if isinstance(next_execution.get("tool_schemas"), dict) else tool_schemas
                content_type = upstream_response.headers.get("Content-Type", "")
                consumed = consume_openai_sse_events(upstream_response, tool_schemas)
                openai_body = build_chat_completion_from_sse(consumed["response_events"])
                consumed["repaired_tool_args"] += normalize_chat_completion_dsml_tool_calls(openai_body, tool_schemas)
                consumed["repaired_tool_args"] += normalize_chat_completion_text_tool_calls(openai_body, tool_schemas)
                consumed["repaired_tool_args"] += normalize_chat_completion_tool_calls(openai_body, tool_schemas)
                normalize_chat_completion_finish_reasons(openai_body)
                issue = inspect_success_payload(
                    route_hint="chat/completions",
                    content_type=content_type,
                    body=None,
                    response_body=openai_body,
                    response_events=consumed.get("response_events"),
                    raw_error_lines=consumed.get("raw_error_lines"),
                )
                if not issue:
                    anthropic_body = convert_openai_response_to_anthropic(openai_body, tool_schemas)
                    body = json.dumps(anthropic_body, ensure_ascii=False).encode("utf-8")
                    response_preview = build_preview_summary(consumed["preview_parts"])
                    close_response_quietly(upstream_response)
                    proxy_logger.info(
                        "request_id=%s 上游=%s 状态=%s 协议=anthropic_messages 流式=false 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 预览=%s",
                        request_id,
                        str(next_execution.get("upstream_url") or upstream_url),
                        upstream_response.status_code,
                        len(body),
                        int((time.perf_counter() - started_at) * 1000),
                        consumed["sanitized_markers"],
                        consumed["repaired_tool_args"],
                        retry_count,
                        response_preview or "",
                    )
                    save_request_cache_entry(
                        execution=next_execution,
                        protocol="anthropic_messages",
                        path="chat/completions",
                        request_payload=openai_payload,
                        response_body=anthropic_body,
                        upstream_url=str(next_execution.get("upstream_url") or upstream_url),
                    )
                    finalize_request_record(
                        request_id,
                        started_at=started_at,
                        status_code=upstream_response.status_code,
                        bytes_sent=len(body),
                        stream=False,
                        sanitized_markers=consumed["sanitized_markers"],
                        response_preview=None,
                        repaired_tool_args=consumed["repaired_tool_args"],
                        extra_meta=build_request_observability_meta(next_execution, openai_payload),
                    )
                    return Response(
                        body,
                        status=200,
                        headers={
                            "Content-Type": "application/json; charset=utf-8",
                            "X-Proxy-Retries": str(retry_count),
                        },
                    )
        payload = build_anthropic_malformed_success_payload(issue=issue, retry_count=retry_count)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        close_response_quietly(upstream_response)
        log_and_record_malformed_success(
            request_id=request_id,
            upstream_url=upstream_url,
            route_hint="anthropic_messages",
            requested_stream=False,
            started_at=started_at,
            retry_count=retry_count,
            issue=issue,
            bytes_sent=len(body),
            sanitized_markers=consumed["sanitized_markers"],
            repaired_tool_args=consumed["repaired_tool_args"],
        )
        return Response(
            body,
            status=502,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Proxy-Retries": str(retry_count),
            },
        )

    anthropic_body = convert_openai_response_to_anthropic(openai_body, tool_schemas)
    body = json.dumps(anthropic_body, ensure_ascii=False).encode("utf-8")
    response_preview = build_preview_summary(consumed["preview_parts"])
    close_response_quietly(upstream_response)
    clear_interruption_resume_records(execution)
    proxy_logger.info(
        "request_id=%s 上游=%s 状态=%s 协议=anthropic_messages 流式=false 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 预览=%s",
        request_id,
        upstream_url,
        upstream_response.status_code,
        len(body),
        int((time.perf_counter() - started_at) * 1000),
        consumed["sanitized_markers"],
        consumed["repaired_tool_args"],
        retry_count,
        response_preview or "",
    )
    save_request_cache_entry(
        execution=execution,
        protocol="anthropic_messages",
        path="chat/completions",
        request_payload=openai_payload,
        response_body=anthropic_body,
        upstream_url=upstream_url,
    )
    finalize_request_record(
        request_id,
        started_at=started_at,
        status_code=upstream_response.status_code,
        bytes_sent=len(body),
        stream=False,
        sanitized_markers=consumed["sanitized_markers"],
        response_preview=response_preview if upstream_response.status_code >= 400 else None,
        repaired_tool_args=consumed["repaired_tool_args"],
        extra_meta=build_request_observability_meta(execution, openai_payload),
    )
    return Response(
        body,
        status=200,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Proxy-Retries": str(retry_count),
        },
    )


def json_body_from_response(response: requests.Response | None) -> dict:
    if response is None:
        return {}
    try:
        payload = json.loads(response.content.decode("utf-8", errors="ignore"))
    except (AttributeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def build_image_error_payload(
    *,
    downstream_protocol: str,
    status_code: int,
    message: str,
    retry_count: int,
    preview: str = "",
) -> dict:
    if downstream_protocol == "gemini_image_generate_content":
        return build_gemini_error_payload(
            status_code=status_code,
            message=message,
            retry_count=retry_count,
            preview=preview,
        )
    if downstream_protocol == "dashscope_image":
        return {
            "code": "ProxyImageError",
            "message": message,
            "upstream_status": status_code,
            "proxy_retries": retry_count,
            **({"upstream_preview": preview} if preview else {}),
        }
    return build_openai_error_payload(
        status_code=status_code,
        preview=preview or message,
        retry_count=retry_count,
        upstream_payload=None,
    )


def poll_dashscope_image_task(plan: dict, upstream_body: dict, request_id: str) -> dict:
    if plan.get("provider") != "dashscope":
        return upstream_body
    if dashscope_body_has_images(upstream_body):
        return upstream_body

    task_id = extract_dashscope_task_id(upstream_body)
    if not task_id or IMAGE_TASK_POLL_TIMEOUT_SECONDS <= 0:
        return upstream_body

    upstream_urls = plan.get("upstream_urls") or []
    if not upstream_urls:
        return upstream_body
    task_url = dashscope_task_status_url(upstream_urls[0], task_id)
    deadline = time.monotonic() + IMAGE_TASK_POLL_TIMEOUT_SECONDS
    last_body = upstream_body
    poll_attempt = 0

    while time.monotonic() < deadline:
        poll_attempt += 1
        time.sleep(min(IMAGE_TASK_POLL_INTERVAL_SECONDS, max(0.1, deadline - time.monotonic())))
        try:
            response = UPSTREAM_SESSION.get(
                task_url,
                headers=plan.get("headers") or {},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            proxy_logger.warning(
                "request_id=%s dashscope_image_poll_exception task_id=%s attempt=%s error=%s",
                request_id,
                task_id,
                poll_attempt,
                str(exc),
            )
            continue

        last_body = json_body_from_response(response)
        output = last_body.get("output") if isinstance(last_body.get("output"), dict) else {}
        task_status = str(output.get("task_status") or output.get("status") or "").upper()
        proxy_logger.info(
            "request_id=%s dashscope_image_poll task_id=%s attempt=%s status_code=%s task_status=%s",
            request_id,
            task_id,
            poll_attempt,
            response.status_code,
            task_status,
        )

        if response.status_code >= 400:
            return last_body or upstream_body
        if dashscope_body_has_images(last_body):
            return last_body
        if task_status in {"SUCCEEDED", "SUCCESS", "FAILED", "CANCELED", "UNKNOWN"}:
            return last_body

    proxy_logger.warning(
        "request_id=%s dashscope_image_poll_timeout task_id=%s timeout_seconds=%s",
        request_id,
        task_id,
        IMAGE_TASK_POLL_TIMEOUT_SECONDS,
    )
    return last_body or upstream_body


def image_generation_proxy(subpath: str, request_payload: dict | None):
    if request.method == "OPTIONS":
        return Response(status=204)
    if request.method != "POST":
        return Response(
            json.dumps(
                {"error": {"message": "Image generation endpoint requires POST.", "type": "invalid_request_error"}},
                ensure_ascii=False,
            ).encode("utf-8"),
            status=405,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

    request_id = uuid.uuid4().hex[:8]
    started_at = time.perf_counter()
    aliased_payload = request_payload if isinstance(request_payload, dict) else {}
    model_candidates = build_model_candidates_from_payload(aliased_payload)
    model_alias_repairs = 0
    pool_keys = get_api_keys_for_url(upstream_url)
    primary_pool_key = pool_keys[0] if pool_keys else UPSTREAM_API_KEY
    plan = build_image_generation_plan(
        subpath=subpath,
        payload=aliased_payload if isinstance(aliased_payload, dict) else {},
        upstream_url_pool=UPSTREAM_URL_POOL,
        inbound_headers=build_upstream_headers(upstream_api_key=primary_pool_key),
        inbound_params=build_upstream_params(),
        api_key=primary_pool_key or UPSTREAM_API_KEY,
        upstream_protocol_override=IMAGE_UPSTREAM_PROTOCOL,
    )
    downstream_protocol = plan["downstream_protocol"]
    upstream_urls = plan["upstream_urls"]
    upstream_url = upstream_urls[0] if upstream_urls else ""
    request_kwargs = {
        "method": "POST",
        "url": upstream_url,
        "headers": plan["headers"],
        "params": plan["params"],
        "json": plan["upstream_payload"],
        "stream": False,
        "timeout": REQUEST_TIMEOUT,
    }
    upstream_response, attempts, request_exception = request_upstream_with_retries(
        request_kwargs,
        subpath="images/generations",
        request_id=request_id,
        upstream_urls=upstream_urls,
        model_candidates=model_candidates,
    )
    retry_count = max(0, len(attempts) - 1)
    model_alias_repairs = 1 if any(attempt.get("model_alias_applied") for attempt in attempts) else 0
    selected_upstream_url = next(
        (attempt.get("upstream_url") for attempt in reversed(attempts) if attempt.get("upstream_url")),
        upstream_url,
    )
    attempt_urls, attempt_route_chain = summarize_attempt_routes(attempts)
    sanitized_query = sanitize_query_string(request.query_string, secret_masker=mask_secret)
    request_meta = build_request_meta(
        request_id=request_id,
        sanitized_query=sanitized_query,
        upstream_url=selected_upstream_url,
        stream=False,
        upstream_stream=False,
        retry_count=retry_count,
        route_pool_size=len(upstream_urls),
        attempt_urls=attempt_urls,
        attempt_route_chain=attempt_route_chain,
        protocol=downstream_protocol,
        request_repairs=model_alias_repairs,
        execution=execution,
        request_payload=request_payload,
        extra_fields={"upstream_protocol": plan["provider"]},
    )
    record_request_started(request_id, request_meta)
    proxy_logger.info(
        "request_id=%s 入站请求 协议=%s 上游协议=%s 模式=%s 方法=%s 路径=%s 来源=%s 查询=%s",
        request_id,
        downstream_protocol,
        plan["provider"],
        plan.get("provider_mode"),
        request.method,
        request.path,
        request.remote_addr,
        sanitized_query,
    )
    if retry_count > 0:
        proxy_logger.warning(
            "request_id=%s 上游尝试摘要=%s",
            request_id,
            summarize_attempts_for_log(attempts),
        )

    if upstream_response is None:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        error_message = str(request_exception) if request_exception else "upstream image request failed"
        payload = build_image_error_payload(
            downstream_protocol=downstream_protocol,
            status_code=502,
            message=error_message,
            retry_count=retry_count,
            preview=error_message,
        )
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        record_request_finished(
            request_id,
            status_code=502,
            bytes_sent=len(body),
            duration_ms=duration_ms,
            stream=False,
            error=error_message,
            response_preview=error_message,
        )
        return Response(
            body,
            status=502,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Proxy-Retries": str(retry_count),
            },
        )

    if upstream_response.status_code >= 400:
        client_gone = response_indicates_client_gone(upstream_response)
        error_message, preview = extract_upstream_error_message(upstream_response)
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        payload = build_image_error_payload(
            downstream_protocol=downstream_protocol,
            status_code=upstream_response.status_code,
            message=error_message,
            retry_count=retry_count,
            preview=preview,
        )
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        record_request_finished(
            request_id,
            status_code=upstream_response.status_code,
            bytes_sent=len(body),
            duration_ms=duration_ms,
            stream=False,
            error="client_gone" if client_gone else (error_message if upstream_response.status_code >= 500 else None),
            response_preview=preview,
            client_gone=client_gone,
        )
        return Response(
            body,
            status=upstream_response.status_code,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Proxy-Retries": str(retry_count),
            },
        )

    upstream_body = json_body_from_response(upstream_response)
    if plan.get("provider") == "dashscope":
        upstream_body = poll_dashscope_image_task(plan, upstream_body, request_id)
    response_payload = normalize_image_generation_response(upstream_body, plan, request_id)
    body = json.dumps(response_payload, ensure_ascii=False).encode("utf-8")
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    image_count = len(response_payload.get("data") or response_payload.get("predictions") or [])
    proxy_logger.info(
        "request_id=%s 上游=%s 状态=%s 协议=%s 上游协议=%s 字节=%s 耗时毫秒=%s 重试次数=%s 图片数=%s",
        request_id,
        selected_upstream_url,
        upstream_response.status_code,
        downstream_protocol,
        plan["provider"],
        len(body),
        duration_ms,
        retry_count,
        image_count,
    )
    record_request_finished(
        request_id,
        status_code=upstream_response.status_code,
        bytes_sent=len(body),
        duration_ms=duration_ms,
        stream=False,
        response_preview=f"images={image_count}",
    )
    return Response(
        body,
        status=200,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Proxy-Retries": str(retry_count),
            "X-Proxy-Upstream-Protocol": plan["provider"],
        },
    )


def openai_stream_response_with_connect_heartbeat(
    *,
    background_execution: BackgroundExecution,
    request_id: str,
    started_at: float,
    sanitize_dsml: bool,
    route_hint: str,
    request_payload: dict | None = None,
) -> Response:
    heartbeat_interval = max(1, WAITING_STREAM_HEARTBEAT_SECONDS or 5)

    def generate():
        delegated = False
        recorded_waiting_finish = False
        waiting_bytes = 0
        waiting_error = None
        waiting_preview = None
        keepalive_payload = b": keep-alive\n\n"
        try:
            while True:
                ready, execution, execution_error = wait_background_upstream_execution(
                    background_execution,
                    heartbeat_interval,
                )
                if ready:
                    break
                proxy_logger.info(
                    "request_id=%s 协议=openai_chat_completions 等待上游首包中 心跳已发送=true 已发送字节=%s",
                    request_id,
                    waiting_bytes + len(keepalive_payload),
                )
                waiting_bytes += len(keepalive_payload)
                yield keepalive_payload

            if execution_error is not None:
                waiting_error = str(execution_error)
                error_payload = build_openai_error_payload(
                    status_code=502,
                    preview=waiting_error,
                    retry_count=0,
                    upstream_payload=None,
                )
                packet = format_openai_sse_payload(error_payload)
                waiting_bytes += len(packet)
                yield packet
                done_payload = b"data: [DONE]\n\n"
                waiting_bytes += len(done_payload)
                yield done_payload
                waiting_preview = waiting_error
                return

            execution = execution or {}
            upstream_url = execution.get("upstream_url", "")
            attempts = execution.get("attempts") or []
            retry_count = int(execution.get("retry_count", 0) or 0)
            if retry_count > 0:
                proxy_logger.warning(
                    "request_id=%s 上游尝试摘要=%s",
                    request_id,
                    summarize_attempts_for_log(attempts),
                )

            upstream_response = execution.get("upstream_response")
            if upstream_response is None:
                waiting_error = str(execution.get("request_exception") or "upstream request failed")
                error_payload = build_openai_error_payload(
                    status_code=502,
                    preview=waiting_error,
                    retry_count=retry_count,
                    upstream_payload=None,
                )
                packet = format_openai_sse_payload(error_payload)
                waiting_bytes += len(packet)
                yield packet
                done_payload = b"data: [DONE]\n\n"
                waiting_bytes += len(done_payload)
                yield done_payload
                waiting_preview = waiting_error
                return

            if upstream_response.status_code >= 400:
                body, response_preview, error_message = build_proxy_error_response(
                    upstream_response=upstream_response,
                    requested_stream=True,
                    retry_count=retry_count,
                )
                waiting_error = "client_gone" if response_indicates_client_gone(upstream_response) else error_message
                packet = f"data: {body.decode('utf-8', errors='ignore')}\n\n".encode("utf-8")
                waiting_bytes += len(packet)
                yield packet
                done_payload = b"data: [DONE]\n\n"
                waiting_bytes += len(done_payload)
                yield done_payload
                waiting_preview = response_preview
                close_response_quietly(upstream_response)
                return

            delegated = True
            stream_response = proxy_response(
                upstream_response,
                sanitize_dsml=sanitize_dsml,
                request_id=request_id,
                upstream_url=upstream_url,
                started_at=started_at,
                requested_stream=True,
                route_hint=route_hint,
                tool_schemas=execution.get("tool_schemas") or {},
                retry_count=retry_count,
                protocol="openai_chat_completions",
                request_payload=request_payload or {},
                execution=execution,
            )
            yield from stream_response.response
        except GeneratorExit:  # pragma: no cover
            background_execution.cancel()
            if not delegated:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                proxy_logger.info(
                    "request_id=%s 流式=true 上游未返回前客户端已断开=true 字节=%s 耗时毫秒=%s",
                    request_id,
                    waiting_bytes,
                    duration_ms,
                )
                record_request_finished(
                    request_id,
                    status_code=None,
                    bytes_sent=waiting_bytes,
                    duration_ms=duration_ms,
                    stream=True,
                    error="client_gone",
                    response_preview=waiting_preview,
                    client_gone=True,
                )
                recorded_waiting_finish = True
            raise
        except Exception as exc:  # pragma: no cover
            background_execution.cancel()
            if not delegated:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                proxy_logger.error(
                    "request_id=%s stream=true pre_upstream_error=%s bytes=%s duration_ms=%s",
                    request_id,
                    str(exc),
                    waiting_bytes,
                    duration_ms,
                )
                record_request_finished(
                    request_id,
                    status_code=502,
                    bytes_sent=waiting_bytes,
                    duration_ms=duration_ms,
                    stream=True,
                    error=str(exc),
                    response_preview=waiting_preview,
                )
                recorded_waiting_finish = True
            raise
        finally:
            if not delegated and waiting_error is not None and not recorded_waiting_finish:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                proxy_logger.info(
                    "request_id=%s stream=true pre_upstream_terminal_error=%s bytes=%s duration_ms=%s preview=%s",
                    request_id,
                    waiting_error,
                    waiting_bytes,
                    duration_ms,
                    waiting_preview or "",
                )
                record_request_finished(
                    request_id,
                    status_code=502 if waiting_error != "client_gone" else None,
                    bytes_sent=waiting_bytes,
                    duration_ms=duration_ms,
                    stream=True,
                    error=waiting_error,
                    response_preview=waiting_preview,
                    client_gone=waiting_error == "client_gone",
                )

    return Response(
        generate(),
        status=200,
        headers=apply_sse_response_headers({"X-Proxy-Retries": "0"}),
    )


def handle_gemini_stream_response(
    *,
    upstream_response: requests.Response,
    request_id: str,
    upstream_url: str,
    started_at: float,
    tool_schemas: dict,
    retry_count: int,
    observability_meta: dict | None = None,
) -> Response:
    content_type = upstream_response.headers.get("Content-Type", "")

    def generate():
        total_bytes = 0
        sanitized_markers = 0
        repaired_tool_args = 0
        stream_error = None
        stream_client_gone = False
        preview_parts = []
        resume_text_parts: list[str] = []
        resume_execution = (observability_meta or {}).get("_execution")
        if not isinstance(resume_execution, dict):
            resume_execution = None
        stream_state = {}
        choice_states = {}
        skip_next_blank = False
        finished_choice_indexes: set[int] = set()
        upstream_openai_payload = (observability_meta or {}).get("_upstream_openai_payload")
        if not isinstance(upstream_openai_payload, dict):
            upstream_openai_payload = None
        expected_choice_count = openai_stream_expected_choice_count(upstream_openai_payload)
        emitted_any = False
        terminal_chunk_sent = False
        try:
            if "text/event-stream" not in content_type.lower():
                consumed = read_upstream_openai_response_body(upstream_response, tool_schemas)
                gemini_body = convert_openai_response_to_gemini(consumed["openai_body"], tool_schemas)
                packet = f"data: {json.dumps(gemini_body, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")
                total_bytes += len(packet)
                for choice in consumed["openai_body"].get("choices") or []:
                    message = choice.get("message") or {}
                    append_preview_text(preview_parts, message.get("content"))
                    append_resume_text(resume_text_parts, message.get("content"))
                yield packet
                return

            for raw_line in iter_response_lines_with_heartbeat(upstream_response, SSE_HEARTBEAT_SECONDS):
                if raw_line is None:
                    heartbeat_payload = b": keep-alive\n\n"
                    total_bytes += len(heartbeat_payload)
                    yield heartbeat_payload
                    continue
                text = raw_line.decode("utf-8", errors="ignore")
                if text == "" and skip_next_blank:
                    skip_next_blank = False
                    continue

                normalized_line, removed, repaired_count, event = normalize_sse_line(text, choice_states, tool_schemas)
                sanitized_markers += removed
                repaired_tool_args += repaired_count

                if normalized_line is None:
                    skip_next_blank = True
                    continue
                if normalized_line:
                    skip_next_blank = False
                if not event:
                    continue
                if "error" in event and "choices" not in event:
                    stream_error = json.dumps(event.get("error"), ensure_ascii=False)
                    continue

                terminal_event = update_openai_stream_terminal_state(
                    event,
                    finished_choice_indexes,
                    expected_choice_count=expected_choice_count,
                )
                for chunk in convert_openai_stream_event_to_gemini_chunks(event, stream_state, tool_schemas):
                    for candidate in chunk.get("candidates") or []:
                        for part in ((candidate.get("content") or {}).get("parts") or []):
                            if part.get("text"):
                                part_text = part.get("text")
                                append_preview_text(preview_parts, part_text)
                                append_resume_text(resume_text_parts, part_text)
                            function_call = part.get("functionCall")
                            if isinstance(function_call, dict):
                                append_preview_tool(
                                    preview_parts,
                                    function_call.get("name"),
                                    function_call.get("args"),
                                    tool_schemas,
                                )
                    packet = f"data: {json.dumps(chunk, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")
                    total_bytes += len(packet)
                    emitted_any = True
                    if any(candidate.get("finishReason") for candidate in chunk.get("candidates") or []):
                        terminal_chunk_sent = True
                    yield packet
                if terminal_event:
                    close_response_quietly(upstream_response)
                    break

            if not emitted_any:
                issue = {
                    "code": "empty_sse_success",
                    "message": "Upstream returned an empty streaming success payload.",
                    "preview": json.dumps(
                        {
                            "content_type": content_type,
                            "emitted_any": False,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
                packet = f"data: {json.dumps(build_gemini_malformed_success_payload(issue=issue, retry_count=retry_count), ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")
                stream_error = issue["code"]
                total_bytes += len(packet)
                yield packet
        except GeneratorExit as exc:  # pragma: no cover
            if not terminal_chunk_sent:
                stream_client_gone = True
                stream_error = "client_gone"
            close_response_quietly(upstream_response)
            raise
        except Exception as exc:  # pragma: no cover
            if is_client_gone_exception(exc):
                stream_client_gone = True
                stream_error = "client_gone"
                close_response_quietly(upstream_response)
            else:
                stream_error = str(exc)
            raise
        finally:
            close_response_quietly(upstream_response)
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            response_preview = build_preview_summary(preview_parts)
            resume_meta = {}
            if stream_client_gone:
                resume_meta = save_interruption_resume_snapshot(
                    execution=resume_execution,
                    protocol="gemini_generate_content",
                    request_id=request_id,
                    upstream_url=upstream_url,
                    partial_text=build_resume_partial_text(resume_text_parts, response_preview),
                    response_preview=response_preview,
                    bytes_sent=total_bytes,
                )
            elif not stream_error:
                resume_meta = clear_interruption_resume_records(resume_execution)
            proxy_logger.info(
                "request_id=%s 上游=%s 状态=%s 协议=gemini_generate_content 流式=true 客户端已断开=%s 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 预览=%s 错误=%s",
                request_id,
                upstream_url,
                upstream_response.status_code,
                str(stream_client_gone).lower(),
                total_bytes,
                duration_ms,
                sanitized_markers,
                repaired_tool_args,
                retry_count,
                response_preview or "",
                stream_error or "",
            )
            record_request_finished(
                request_id,
                status_code=upstream_response.status_code,
                bytes_sent=total_bytes,
                duration_ms=duration_ms,
                stream=True,
                error=stream_error,
                sanitized_markers=sanitized_markers,
                response_preview=response_preview if upstream_response.status_code >= 400 else None,
                repaired_tool_args=repaired_tool_args,
                client_gone=stream_client_gone,
                extra_meta=(observability_meta or {}) | resume_meta,
            )

    return Response(
        generate(),
        status=200,
        headers=apply_sse_response_headers({"X-Proxy-Retries": str(retry_count)}),
    )


def handle_anthropic_stream_response(
    *,
    upstream_response: requests.Response,
    request_id: str,
    upstream_url: str,
    started_at: float,
    request_payload: dict,
    tool_schemas: dict,
    retry_count: int,
    observability_meta: dict | None = None,
) -> Response:
    content_type = upstream_response.headers.get("Content-Type", "")
    anthropic_stream_fallbacks = int((observability_meta or {}).get("anthropic_stream_fallbacks") or 0)
    upstream_openai_payload = dict((observability_meta or {}).get("_upstream_openai_payload") or {})
    if "text/event-stream" not in content_type.lower():
        consumed = read_upstream_openai_response_body(upstream_response, tool_schemas)
        issue = inspect_success_payload(
            route_hint="chat/completions",
            content_type=content_type,
            body=upstream_response.content,
            response_body=consumed["openai_body"],
        )
        if issue:
            payload = build_anthropic_malformed_success_payload(issue=issue, retry_count=retry_count)
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            close_response_quietly(upstream_response)
            log_and_record_malformed_success(
                request_id=request_id,
                upstream_url=upstream_url,
                route_hint="anthropic_messages",
                requested_stream=True,
                started_at=started_at,
                retry_count=retry_count,
                issue=issue,
                bytes_sent=len(body),
                sanitized_markers=consumed["sanitized_markers"],
                repaired_tool_args=consumed["repaired_tool_args"],
            )
            return Response(
                body,
                status=502,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "X-Proxy-Retries": str(retry_count),
                },
            )

        anthropic_body = convert_openai_response_to_anthropic(consumed["openai_body"], tool_schemas)
        packets = build_anthropic_stream_packets_from_message(anthropic_body)
        total_bytes = sum(len(packet) for packet in packets)
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        response_preview = build_preview_summary(consumed["preview_parts"])
        close_response_quietly(upstream_response)
        resume_clear_meta = clear_interruption_resume_records((observability_meta or {}).get("_execution"))
        proxy_logger.info(
            "request_id=%s 上游=%s 状态=%s 协议=anthropic_messages 流式=true 合成来源=%s 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 预览=%s",
            request_id,
            upstream_url,
            upstream_response.status_code,
            content_type or "unknown",
            total_bytes,
            duration_ms,
            consumed["sanitized_markers"],
            consumed["repaired_tool_args"],
            retry_count,
            response_preview or "",
        )
        record_request_finished(
            request_id,
            status_code=upstream_response.status_code,
            bytes_sent=total_bytes,
            duration_ms=duration_ms,
            stream=True,
            sanitized_markers=consumed["sanitized_markers"],
            repaired_tool_args=consumed["repaired_tool_args"],
            extra_meta=(observability_meta or {}) | resume_clear_meta,
        )
        return Response(
            packets,
            status=200,
            headers=apply_sse_response_headers({"X-Proxy-Retries": str(retry_count)}),
        )

    def generate():
        total_bytes = 0
        sanitized_markers = 0
        repaired_tool_args = 0
        preview_parts = []
        stream_error = None
        resume_text_parts: list[str] = []
        resume_execution = (observability_meta or {}).get("_execution")
        if not isinstance(resume_execution, dict):
            resume_execution = None
        message_started = False
        message_id = f"msg_{uuid.uuid4().hex[:24]}"
        message_model = request_payload.get("model")
        next_block_index = 0
        active_text_block_index = None
        active_thinking_block_index = None
        last_reasoning_text = ""
        open_tool_blocks = {}
        saw_tool_use = False
        last_stop_reason = "end_turn"
        choice_states = {}
        skip_next_blank = False
        output_tokens = 0
        stream_client_gone = False
        message_stop_sent = False
        finished_choice_indexes: set[int] = set()
        expected_choice_count = openai_stream_expected_choice_count(upstream_openai_payload)
        prebuffered_raw_lines: list[bytes] = []
        preflight_heartbeat_count = 0
        preflight_raw_line_count = 0
        stream_iter = iter_response_lines_with_heartbeat(upstream_response, SSE_HEARTBEAT_SECONDS)

        try:
            preflight_empty_issue = None
            try:
                while True:
                    raw_line = next(stream_iter)
                    if raw_line is None:
                        preflight_heartbeat_count += 1
                        continue
                    preflight_raw_line_count += 1
                    prebuffered_raw_lines.append(raw_line)
                    break
            except StopIteration:
                preflight_empty_issue = {
                    "code": "empty_sse_success",
                    "message": "Upstream returned an empty streaming success payload.",
                    "preview": json.dumps(
                        {
                            "content_type": content_type,
                            "heartbeat_count": preflight_heartbeat_count,
                            "raw_line_count": preflight_raw_line_count,
                            "nonempty_line_count": 0,
                            "first_upstream_event_ms": None,
                            "first_data_event_ms": None,
                            "last_nonempty_line": "",
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }

            if preflight_empty_issue:
                mark_route_failure(upstream_url, preflight_empty_issue["code"])
                if anthropic_stream_fallbacks < 2 and isinstance(request_payload, dict):
                    proxy_logger.warning(
                        "request_id=%s Anthropic流首包为空，准备同请求切换线路 次数=%s 当前线路=%s 原因=%s",
                        request_id,
                        anthropic_stream_fallbacks + 1,
                        upstream_url,
                        preflight_empty_issue["code"],
                    )
                    close_response_quietly(upstream_response)
                    retry_payload = upstream_openai_payload or convert_anthropic_request_to_openai(request_payload)
                    next_execution = execute_upstream_request("chat/completions", retry_payload, request_id)
                    if isinstance(next_execution, dict):
                        next_meta = dict(observability_meta or {})
                        next_meta["anthropic_stream_fallbacks"] = anthropic_stream_fallbacks + 1
                        next_response = next_execution.get("upstream_response")
                        if next_response is not None:
                            next_stream = handle_anthropic_stream_response(
                                upstream_response=next_response,
                                request_id=request_id,
                                upstream_url=str(next_execution.get("upstream_url") or upstream_url),
                                started_at=started_at,
                                request_payload=request_payload,
                                tool_schemas=next_execution.get("tool_schemas") if isinstance(next_execution.get("tool_schemas"), dict) else tool_schemas,
                                retry_count=int(next_execution.get("retry_count") or retry_count),
                                observability_meta=build_request_observability_meta(next_execution, retry_payload) | {"_upstream_openai_payload": retry_payload, "_execution": next_execution} | next_meta,
                            )
                            yield from next_stream.response
                            return

                payload = build_anthropic_malformed_success_payload(issue=preflight_empty_issue, retry_count=retry_count)
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                close_response_quietly(upstream_response)
                log_and_record_malformed_success(
                    request_id=request_id,
                    upstream_url=upstream_url,
                    route_hint="anthropic_messages",
                    requested_stream=True,
                    started_at=started_at,
                    retry_count=retry_count,
                    issue=preflight_empty_issue,
                    bytes_sent=len(body),
                )
                yield format_sse_event("error", payload)
                return

            for raw_line in itertools.chain(prebuffered_raw_lines, stream_iter):
                if raw_line is None:
                    heartbeat_payload = b": keep-alive\n\n"
                    total_bytes += len(heartbeat_payload)
                    yield heartbeat_payload
                    continue
                text = raw_line.decode("utf-8", errors="ignore")
                if text == "" and skip_next_blank:
                    skip_next_blank = False
                    continue

                normalized_line, removed, repaired_count, event = normalize_sse_line(text, choice_states, tool_schemas)
                sanitized_markers += removed
                repaired_tool_args += repaired_count

                if normalized_line is None:
                    skip_next_blank = True
                    continue
                if normalized_line:
                    skip_next_blank = False

                if not event:
                    continue

                terminal_event = update_openai_stream_terminal_state(
                    event,
                    finished_choice_indexes,
                    expected_choice_count=expected_choice_count,
                )
                if not message_started:
                    message_id = event.get("id") or message_id
                    message_model = event.get("model") or message_model
                    start_payload = {
                        "type": "message_start",
                        "message": {
                            "id": message_id,
                            "type": "message",
                            "role": "assistant",
                            "model": message_model,
                            "content": [],
                            "stop_reason": None,
                            "stop_sequence": None,
                            "usage": {
                                "input_tokens": 0,
                                "output_tokens": 0,
                            },
                        },
                    }
                    packet = format_sse_event("message_start", start_payload)
                    total_bytes += len(packet)
                    yield packet
                    message_started = True

                usage = event.get("usage") or {}
                output_tokens = usage.get("completion_tokens", output_tokens)

                for choice in event.get("choices") or []:
                    delta = choice.get("delta") or {}

                    reasoning_text = delta.get("reasoning_content")
                    if not isinstance(reasoning_text, str) or not reasoning_text:
                        choice_reasoning = choice.get("reasoning")
                        if isinstance(choice_reasoning, str) and choice_reasoning:
                            if choice_reasoning.startswith(last_reasoning_text):
                                reasoning_text = choice_reasoning[len(last_reasoning_text):]
                            else:
                                reasoning_text = choice_reasoning
                            last_reasoning_text = choice_reasoning
                    elif isinstance(reasoning_text, str) and reasoning_text:
                        last_reasoning_text = f"{last_reasoning_text}{reasoning_text}"
                    if isinstance(reasoning_text, str) and reasoning_text:
                        if active_text_block_index is not None:
                            packet = format_sse_event(
                                "content_block_stop",
                                {
                                    "type": "content_block_stop",
                                    "index": active_text_block_index,
                                },
                            )
                            total_bytes += len(packet)
                            yield packet
                            active_text_block_index = None
                        if active_thinking_block_index is None:
                            active_thinking_block_index = next_block_index
                            next_block_index += 1
                            packet = format_sse_event(
                                "content_block_start",
                                {
                                    "type": "content_block_start",
                                    "index": active_thinking_block_index,
                                    "content_block": {
                                        "type": "thinking",
                                        "thinking": "",
                                        "signature": "proxy-synthetic",
                                    },
                                },
                            )
                            total_bytes += len(packet)
                            yield packet
                        packet = format_sse_event(
                            "content_block_delta",
                            {
                                "type": "content_block_delta",
                                "index": active_thinking_block_index,
                                "delta": {
                                    "type": "thinking_delta",
                                    "thinking": reasoning_text,
                                },
                            },
                        )
                        total_bytes += len(packet)
                        yield packet

                    content_text = delta.get("content")
                    if isinstance(content_text, str) and content_text:
                        if active_thinking_block_index is not None:
                            packet = format_sse_event(
                                "content_block_stop",
                                {
                                    "type": "content_block_stop",
                                    "index": active_thinking_block_index,
                                },
                            )
                            total_bytes += len(packet)
                            yield packet
                            active_thinking_block_index = None
                        if active_text_block_index is None:
                            active_text_block_index = next_block_index
                            next_block_index += 1
                            packet = format_sse_event(
                                "content_block_start",
                                {
                                    "type": "content_block_start",
                                    "index": active_text_block_index,
                                    "content_block": {
                                        "type": "text",
                                        "text": "",
                                    },
                                },
                            )
                            total_bytes += len(packet)
                            yield packet
                        append_preview_text(preview_parts, content_text)
                        append_resume_text(resume_text_parts, content_text)
                        packet = format_sse_event(
                            "content_block_delta",
                            {
                                "type": "content_block_delta",
                                "index": active_text_block_index,
                                "delta": {
                                    "type": "text_delta",
                                    "text": content_text,
                                },
                            },
                        )
                        total_bytes += len(packet)
                        yield packet

                    for tool_call in delta.get("tool_calls") or []:
                        function_data = tool_call.get("function") or {}
                        if active_thinking_block_index is not None:
                            packet = format_sse_event(
                                "content_block_stop",
                                {
                                    "type": "content_block_stop",
                                    "index": active_thinking_block_index,
                                },
                            )
                            total_bytes += len(packet)
                            yield packet
                            active_thinking_block_index = None
                        if active_text_block_index is not None:
                            packet = format_sse_event(
                                "content_block_stop",
                                {
                                    "type": "content_block_stop",
                                    "index": active_text_block_index,
                                },
                            )
                            total_bytes += len(packet)
                            yield packet
                            active_text_block_index = None

                        tool_index = tool_call.get("index", 0)
                        block_index = open_tool_blocks.get(tool_index)
                        if block_index is None:
                            block_index = next_block_index
                            next_block_index += 1
                            open_tool_blocks[tool_index] = block_index
                            saw_tool_use = True
                            packet = format_sse_event(
                                "content_block_start",
                                {
                                    "type": "content_block_start",
                                    "index": block_index,
                                    "content_block": {
                                        "type": "tool_use",
                                        "id": tool_call.get("id") or f"toolu_{uuid.uuid4().hex[:24]}",
                                        "name": function_data.get("name", ""),
                                        "input": {},
                                    },
                                },
                            )
                            total_bytes += len(packet)
                            yield packet

                        arguments_text = function_data.get("arguments")
                        if isinstance(arguments_text, str) and arguments_text:
                            append_preview_tool(
                                preview_parts,
                                function_data.get("name"),
                                arguments_text,
                                tool_schemas,
                            )
                            packet = format_sse_event(
                                "content_block_delta",
                                {
                                    "type": "content_block_delta",
                                    "index": block_index,
                                    "delta": {
                                        "type": "input_json_delta",
                                        "partial_json": arguments_text,
                                    },
                                },
                            )
                            total_bytes += len(packet)
                            yield packet

                    if choice.get("finish_reason") is not None:
                        last_stop_reason = map_openai_finish_reason_to_anthropic(choice.get("finish_reason")) or "end_turn"
                if terminal_event:
                    close_response_quietly(upstream_response)
                    break

            final_stop_reason = last_stop_reason
            if saw_tool_use and final_stop_reason in {None, "", "end_turn"}:
                final_stop_reason = "tool_use"

            if active_text_block_index is not None:
                packet = format_sse_event(
                    "content_block_stop",
                    {
                        "type": "content_block_stop",
                        "index": active_text_block_index,
                    },
                )
                total_bytes += len(packet)
                yield packet

            if active_thinking_block_index is not None:
                packet = format_sse_event(
                    "content_block_stop",
                    {
                        "type": "content_block_stop",
                        "index": active_thinking_block_index,
                    },
                )
                total_bytes += len(packet)
                yield packet

            for block_index in list(open_tool_blocks.values()):
                packet = format_sse_event(
                    "content_block_stop",
                    {
                        "type": "content_block_stop",
                        "index": block_index,
                    },
                )
                total_bytes += len(packet)
                yield packet

            if not message_started:
                packet = format_sse_event(
                    "message_start",
                    {
                        "type": "message_start",
                        "message": {
                            "id": message_id,
                            "type": "message",
                            "role": "assistant",
                            "model": message_model,
                            "content": [],
                            "stop_reason": None,
                            "stop_sequence": None,
                            "usage": {"input_tokens": 0, "output_tokens": 0},
                        },
                    },
                )
                total_bytes += len(packet)
                yield packet
                packet = format_sse_event(
                    "message_delta",
                    {
                        "type": "message_delta",
                        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                        "usage": {"output_tokens": output_tokens},
                    },
                )
                total_bytes += len(packet)
                yield packet
                packet = format_sse_event("message_stop", {"type": "message_stop"})
                total_bytes += len(packet)
                message_stop_sent = True
                yield packet
            elif message_started:
                packet = format_sse_event(
                    "message_delta",
                    {
                        "type": "message_delta",
                        "delta": {
                            "stop_reason": final_stop_reason,
                            "stop_sequence": None,
                        },
                        "usage": {
                            "output_tokens": output_tokens,
                        },
                    },
                )
                total_bytes += len(packet)
                yield packet

                packet = format_sse_event("message_stop", {"type": "message_stop"})
                message_stop_sent = True
                total_bytes += len(packet)
                yield packet
        except GeneratorExit as exc:  # pragma: no cover
            if not message_stop_sent:
                stream_client_gone = True
                stream_error = "client_gone"
            close_response_quietly(upstream_response)
            raise
        except Exception as exc:  # pragma: no cover
            if is_client_gone_exception(exc):
                stream_client_gone = True
                stream_error = "client_gone"
                close_response_quietly(upstream_response)
            else:
                stream_error = str(exc)
            raise
        finally:
            close_response_quietly(upstream_response)
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            response_preview = build_preview_summary(preview_parts)
            resume_meta = {}
            if stream_client_gone:
                resume_meta = save_interruption_resume_snapshot(
                    execution=resume_execution,
                    protocol="anthropic_messages",
                    request_id=request_id,
                    upstream_url=upstream_url,
                    partial_text=build_resume_partial_text(resume_text_parts, response_preview),
                    response_preview=response_preview,
                    bytes_sent=total_bytes,
                )
            elif not stream_error:
                resume_meta = clear_interruption_resume_records(resume_execution)
            if stream_client_gone:
                proxy_logger.info(
                    "request_id=%s 上游=%s 状态=%s 协议=anthropic_messages 流式=true 客户端已断开=true 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 预览=%s",
                    request_id,
                    upstream_url,
                    upstream_response.status_code,
                    total_bytes,
                    duration_ms,
                    sanitized_markers,
                    repaired_tool_args,
                    retry_count,
                    response_preview,
                )
            elif stream_error:
                proxy_logger.error(
                    "request_id=%s 上游=%s 状态=%s 协议=anthropic_messages 流式=true 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 错误=%s 预览=%s",
                    request_id,
                    upstream_url,
                    upstream_response.status_code,
                    total_bytes,
                    duration_ms,
                    sanitized_markers,
                    repaired_tool_args,
                    retry_count,
                    stream_error,
                    response_preview,
                )
            else:
                proxy_logger.info(
                    "request_id=%s 上游=%s 状态=%s 协议=anthropic_messages 流式=true 字节=%s 耗时毫秒=%s 清洗标记=%s 工具参数修复=%s 重试次数=%s 预览=%s",
                    request_id,
                    upstream_url,
                    upstream_response.status_code,
                    total_bytes,
                    duration_ms,
                    sanitized_markers,
                    repaired_tool_args,
                    retry_count,
                    response_preview or "",
                )
            record_request_finished(
                request_id,
                status_code=upstream_response.status_code,
                bytes_sent=total_bytes,
                duration_ms=duration_ms,
                stream=True,
                error=stream_error,
                sanitized_markers=sanitized_markers,
                response_preview=response_preview if upstream_response.status_code >= 400 else None,
                repaired_tool_args=repaired_tool_args,
                client_gone=stream_client_gone,
                extra_meta=(observability_meta or {}) | resume_meta,
            )

    return Response(
        generate(),
        status=200,
        headers=apply_sse_response_headers({"X-Proxy-Retries": str(retry_count)}),
    )


def gemini_stream_response_with_connect_heartbeat(
    *,
    background_execution: BackgroundExecution,
    request_id: str,
    started_at: float,
    observability_payload: dict | None = None,
    tool_schemas_fallback: dict | None = None,
) -> Response:
    heartbeat_interval = max(1, WAITING_STREAM_HEARTBEAT_SECONDS or 5)

    def generate():
        delegated = False
        recorded_waiting_finish = False
        waiting_bytes = 0
        waiting_error = None
        waiting_preview = None
        keepalive_payload = b": keep-alive\n\n"
        try:
            while True:
                ready, execution, execution_error = wait_background_upstream_execution(
                    background_execution,
                    heartbeat_interval,
                )
                if ready:
                    break
                waiting_bytes += len(keepalive_payload)
                yield keepalive_payload

            if execution_error is not None:
                waiting_error = str(execution_error)
                packet = format_openai_sse_payload(
                    build_gemini_error_payload(
                        status_code=502,
                        message=waiting_error,
                        retry_count=0,
                        preview=waiting_error,
                    )
                )
                waiting_bytes += len(packet)
                yield packet
                waiting_preview = waiting_error
                return

            execution = execution or {}
            upstream_url = execution.get("upstream_url", "")
            attempts = execution.get("attempts") or []
            retry_count = int(execution.get("retry_count", 0) or 0)
            if retry_count > 0:
                proxy_logger.warning(
                    "request_id=%s 上游尝试摘要=%s",
                    request_id,
                    summarize_attempts_for_log(attempts),
                )

            upstream_response = execution.get("upstream_response")
            if upstream_response is None:
                waiting_error = str(execution.get("request_exception") or "upstream request failed")
                packet = format_openai_sse_payload(
                    build_gemini_error_payload(
                        status_code=502,
                        message=waiting_error,
                        retry_count=retry_count,
                        preview=waiting_error,
                    )
                )
                waiting_bytes += len(packet)
                yield packet
                waiting_preview = waiting_error
                return

            if upstream_response.status_code >= 400:
                client_gone = response_indicates_client_gone(upstream_response)
                error_message, preview = extract_upstream_error_message(upstream_response)
                waiting_error = "client_gone" if client_gone else error_message
                packet = format_openai_sse_payload(
                    build_gemini_error_payload(
                        status_code=upstream_response.status_code,
                        message=error_message,
                        retry_count=retry_count,
                        preview=preview,
                    )
                )
                waiting_bytes += len(packet)
                yield packet
                waiting_preview = preview or error_message
                close_response_quietly(upstream_response)
                return

            delegated = True
            stream_response = handle_gemini_stream_response(
                upstream_response=upstream_response,
                request_id=request_id,
                upstream_url=upstream_url,
                started_at=started_at,
                tool_schemas=execution.get("tool_schemas") or tool_schemas_fallback or {},
                retry_count=retry_count,
                observability_meta=build_request_observability_meta(execution, observability_payload or {}) | {"_upstream_openai_payload": observability_payload or {}, "_execution": execution},
            )
            yield from stream_response.response
        except GeneratorExit:  # pragma: no cover
            background_execution.cancel()
            if not delegated:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                proxy_logger.info(
                    "request_id=%s 协议=gemini_generate_content 流式=true 上游未返回前客户端已断开=true 字节=%s 耗时毫秒=%s",
                    request_id,
                    waiting_bytes,
                    duration_ms,
                )
                record_request_finished(
                    request_id,
                    status_code=None,
                    bytes_sent=waiting_bytes,
                    duration_ms=duration_ms,
                    stream=True,
                    error="client_gone",
                    response_preview=waiting_preview,
                    client_gone=True,
                    extra_meta=build_request_observability_meta(execution, observability_payload or {}),
                )
                recorded_waiting_finish = True
            raise
        except Exception as exc:  # pragma: no cover
            background_execution.cancel()
            if not delegated:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                proxy_logger.error(
                    "request_id=%s protocol=gemini_generate_content stream=true pre_upstream_error=%s bytes=%s duration_ms=%s",
                    request_id,
                    str(exc),
                    waiting_bytes,
                    duration_ms,
                )
                record_request_finished(
                    request_id,
                    status_code=502,
                    bytes_sent=waiting_bytes,
                    duration_ms=duration_ms,
                    stream=True,
                    error=str(exc),
                    response_preview=waiting_preview,
                    extra_meta=build_request_observability_meta(execution, observability_payload or {}),
                )
                recorded_waiting_finish = True
            raise
        finally:
            if not delegated and waiting_error is not None and not recorded_waiting_finish:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                proxy_logger.info(
                    "request_id=%s protocol=gemini_generate_content stream=true pre_upstream_terminal_error=%s bytes=%s duration_ms=%s preview=%s",
                    request_id,
                    waiting_error,
                    waiting_bytes,
                    duration_ms,
                    waiting_preview or "",
                )
                record_request_finished(
                    request_id,
                    status_code=502 if waiting_error != "client_gone" else None,
                    bytes_sent=waiting_bytes,
                    duration_ms=duration_ms,
                    stream=True,
                    error=waiting_error,
                    response_preview=waiting_preview,
                    client_gone=waiting_error == "client_gone",
                    extra_meta=build_request_observability_meta(execution, observability_payload or {}),
                )

    return Response(
        generate(),
        status=200,
        headers=apply_sse_response_headers({"X-Proxy-Retries": "0"}),
    )


def anthropic_stream_response_with_connect_heartbeat(
    *,
    background_execution: BackgroundExecution,
    request_id: str,
    started_at: float,
    request_payload: dict | None,
    observability_payload: dict | None = None,
    tool_schemas_fallback: dict | None = None,
) -> Response:
    heartbeat_interval = max(1, WAITING_STREAM_HEARTBEAT_SECONDS or 5)

    def generate():
        delegated = False
        recorded_waiting_finish = False
        waiting_bytes = 0
        waiting_error = None
        waiting_preview = None
        keepalive_payload = format_sse_event("ping", {"type": "ping"})
        try:
            while True:
                ready, execution, execution_error = wait_background_upstream_execution(
                    background_execution,
                    heartbeat_interval,
                )
                if ready:
                    break
                waiting_bytes += len(keepalive_payload)
                yield keepalive_payload

            if execution_error is not None:
                waiting_error = str(execution_error)
                packet = format_sse_event(
                    "error",
                    build_anthropic_error_payload(
                        status_code=502,
                        message=waiting_error,
                        retry_count=0,
                        preview=waiting_error,
                    ),
                )
                waiting_bytes += len(packet)
                yield packet
                waiting_preview = waiting_error
                return

            execution = execution or {}
            upstream_url = execution.get("upstream_url", "")
            attempts = execution.get("attempts") or []
            retry_count = int(execution.get("retry_count", 0) or 0)
            if retry_count > 0:
                proxy_logger.warning(
                    "request_id=%s 上游尝试摘要=%s",
                    request_id,
                    summarize_attempts_for_log(attempts),
                )

            upstream_response = execution.get("upstream_response")
            if upstream_response is None:
                waiting_error = str(execution.get("request_exception") or "upstream request failed")
                packet = format_sse_event(
                    "error",
                    build_anthropic_error_payload(
                        status_code=502,
                        message=waiting_error,
                        retry_count=retry_count,
                        preview=waiting_error,
                    ),
                )
                waiting_bytes += len(packet)
                yield packet
                waiting_preview = waiting_error
                return

            if upstream_response.status_code >= 400:
                client_gone = response_indicates_client_gone(upstream_response)
                error_message, preview = extract_upstream_error_message(upstream_response)
                waiting_error = "client_gone" if client_gone else error_message
                packet = format_sse_event(
                    "error",
                    build_anthropic_error_payload(
                        status_code=upstream_response.status_code,
                        message=error_message,
                        retry_count=retry_count,
                        preview=preview,
                    ),
                )
                waiting_bytes += len(packet)
                yield packet
                waiting_preview = preview or error_message
                close_response_quietly(upstream_response)
                return

            delegated = True
            stream_response = handle_anthropic_stream_response(
                upstream_response=upstream_response,
                request_id=request_id,
                upstream_url=upstream_url,
                started_at=started_at,
                request_payload=request_payload or {},
                tool_schemas=execution.get("tool_schemas") or tool_schemas_fallback or {},
                retry_count=retry_count,
                observability_meta=build_request_observability_meta(execution, observability_payload or {}) | {"_upstream_openai_payload": observability_payload or {}, "_execution": execution},
            )
            yield from stream_response.response
        except GeneratorExit:  # pragma: no cover
            background_execution.cancel()
            if not delegated:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                proxy_logger.info(
                    "request_id=%s 协议=anthropic_messages 流式=true 上游未返回前客户端已断开=true 字节=%s 耗时毫秒=%s",
                    request_id,
                    waiting_bytes,
                    duration_ms,
                )
                record_request_finished(
                    request_id,
                    status_code=None,
                    bytes_sent=waiting_bytes,
                    duration_ms=duration_ms,
                    stream=True,
                    error="client_gone",
                    response_preview=waiting_preview,
                    client_gone=True,
                    extra_meta=build_request_observability_meta(execution, observability_payload or {}),
                )
                recorded_waiting_finish = True
            raise
        except Exception as exc:  # pragma: no cover
            background_execution.cancel()
            if not delegated:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                proxy_logger.error(
                    "request_id=%s protocol=anthropic_messages stream=true pre_upstream_error=%s bytes=%s duration_ms=%s",
                    request_id,
                    str(exc),
                    waiting_bytes,
                    duration_ms,
                )
                record_request_finished(
                    request_id,
                    status_code=502,
                    bytes_sent=waiting_bytes,
                    duration_ms=duration_ms,
                    stream=True,
                    error=str(exc),
                    response_preview=waiting_preview,
                    extra_meta=build_request_observability_meta(execution, observability_payload or {}),
                )
                recorded_waiting_finish = True
            raise
        finally:
            if not delegated and waiting_error is not None and not recorded_waiting_finish:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                proxy_logger.info(
                    "request_id=%s protocol=anthropic_messages stream=true pre_upstream_terminal_error=%s bytes=%s duration_ms=%s preview=%s",
                    request_id,
                    waiting_error,
                    waiting_bytes,
                    duration_ms,
                    waiting_preview or "",
                )
                record_request_finished(
                    request_id,
                    status_code=502 if waiting_error != "client_gone" else None,
                    bytes_sent=waiting_bytes,
                    duration_ms=duration_ms,
                    stream=True,
                    error=waiting_error,
                    response_preview=waiting_preview,
                    client_gone=waiting_error == "client_gone",
                    extra_meta=build_request_observability_meta(execution, observability_payload or {}),
                )

    return Response(
        generate(),
        status=200,
        headers=apply_sse_response_headers({"X-Proxy-Retries": "0"}),
    )


def proxy_entrypoint(subpath: str):
    if request.method == "OPTIONS":
        return Response(status=204)
    auth_error = require_proxy_api_key()
    if auth_error is not None:
        return auth_error

    request_payload = request.get_json(silent=True)
    inbound_subpath = str(subpath or "").strip("/")
    upstream_subpath = inbound_subpath
    if inbound_subpath.startswith("openai/"):
        upstream_subpath = inbound_subpath[len("openai/"):]

    is_gemini_versioned_path = request.path.startswith("/v1beta/") or request.path.startswith("/v1alpha/")
    if request.method == "GET" and is_gemini_versioned_path and (
        inbound_subpath == "models" or (inbound_subpath.startswith("models/") and ":" not in inbound_subpath)
    ):
        return gemini_models_proxy(inbound_subpath)

    if request.method == "GET" and (
        upstream_subpath == "models" or (upstream_subpath.startswith("models/") and ":" not in upstream_subpath)
    ):
        return local_models_response(protocol="passthrough", subpath=upstream_subpath)

    if detect_downstream_image_protocol(inbound_subpath, request_payload):
        return image_generation_proxy(inbound_subpath, request_payload)

    detected_protocol = detect_inbound_protocol(inbound_subpath, request_payload)
    if detected_protocol == "gemini_generate_content":
        return gemini_generate_content(inbound_subpath, request_payload)
    if detected_protocol == "anthropic_messages":
        return anthropic_messages()

    sanitize_dsml = upstream_subpath == "chat/completions"
    request_id = uuid.uuid4().hex[:8]
    started_at = time.perf_counter()
    requested_stream = bool(request_payload.get("stream")) if isinstance(request_payload, dict) else False
    sanitized_query = sanitize_query_string(request.query_string, secret_masker=mask_secret)
    proxy_logger.info(
        "request_id=%s 入站请求 协议=%s 方法=%s 路径=%s 来源=%s 查询=%s",
        request_id,
        detected_protocol,
        request.method,
        request.path,
        request.remote_addr,
        sanitized_query,
    )

    execution = None
    if requested_stream and upstream_subpath == "chat/completions":
        background_execution = start_background_upstream_execution(upstream_subpath, request_payload, request_id)
        ready, async_execution, async_error = wait_background_upstream_execution(
            background_execution,
            STREAM_OPEN_GRACE_SECONDS,
        )
        if not ready:
            initial_urls = build_upstream_url_candidates(upstream_subpath)
            record_request_started(
                request_id,
                build_pending_stream_request_meta(
                    request_id=request_id,
                    sanitized_query=sanitized_query,
                    upstream_urls=initial_urls,
                    protocol=detected_protocol,
                    request_repairs=0,
                ),
            )
            return openai_stream_response_with_connect_heartbeat(
                background_execution=background_execution,
                request_id=request_id,
                started_at=started_at,
                sanitize_dsml=sanitize_dsml,
                route_hint=upstream_subpath,
                request_payload=request_payload if isinstance(request_payload, dict) else {},
            )
        if async_error is not None:
            async_urls = build_upstream_url_candidates(upstream_subpath)
            execution = {
                "upstream_url": async_urls[0] if async_urls else "",
                "tool_schemas": {},
                "upstream_stream": True,
                "upstream_response": None,
                "attempts": [],
                "request_exception": async_error,
                "retry_count": 0,
                "route_pool_size": len(async_urls),
                "request_repairs": 0,
            }
        else:
            execution = async_execution
    else:
        execution = execute_upstream_request(upstream_subpath, request_payload, request_id)

    execution = execution or {}
    upstream_url = execution["upstream_url"]
    tool_schemas = execution["tool_schemas"]
    upstream_stream = execution["upstream_stream"]
    upstream_response = execution["upstream_response"]
    attempts = execution["attempts"]
    request_exception = execution["request_exception"]
    retry_count = execution["retry_count"]
    attempt_urls, attempt_route_chain = summarize_attempt_routes(attempts)
    request_meta = build_request_meta(
        request_id=request_id,
        sanitized_query=sanitized_query,
        upstream_url=upstream_url,
        stream=requested_stream,
        upstream_stream=upstream_stream,
        retry_count=retry_count,
        route_pool_size=execution["route_pool_size"],
        attempt_urls=attempt_urls,
        attempt_route_chain=attempt_route_chain,
        protocol=detected_protocol,
        request_repairs=execution["request_repairs"],
        execution=execution,
        request_payload=request_payload,
    )
    record_request_started(request_id, request_meta)

    if execution.get("cache_hit") and isinstance(execution.get("cached_response_body"), dict):
        if requested_stream and upstream_subpath == "chat/completions":
            return build_cached_openai_stream_response(
                request_id=request_id,
                started_at=started_at,
                cached_response_body=execution["cached_response_body"],
                execution=execution,
                request_payload=request_payload,
            )
        if not requested_stream:
            body = json.dumps(execution["cached_response_body"], ensure_ascii=False).encode("utf-8")
            duration_ms = record_request_cache_hit(
                request_id,
                body,
                started_at,
                requested_stream,
                execution=execution,
                extra_meta=build_request_observability_meta(execution, request_payload),
            )
            proxy_logger.info(
                "request_id=%s 代理缓存命中 协议=%s 路径=%s 字节=%s 耗时毫秒=%s key=%s 来源=%s",
                request_id,
                detected_protocol,
                request.path,
                len(body),
                duration_ms,
                str(execution.get("cache_key") or "")[:12],
                str(execution.get("cache_source") or "sqlite"),
            )
            return Response(
                body,
                status=200,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "X-Proxy-Retries": "0",
                    "X-Proxy-Cache": "hit",
                },
            )

    if upstream_response is None:
        forced_error_payload = execution.get("forced_error_payload")
        forced_error_status = int(execution.get("forced_error_status") or 502)
        error_payload, failure = build_openai_error_payload_from_failure(
            request_exception=request_exception,
            retry_count=retry_count,
            forced_error_status=forced_error_status,
            forced_error_payload=forced_error_payload if isinstance(forced_error_payload, dict) else None,
        )
        error_message = str(failure["message"])
        proxy_logger.error(
            "request_id=%s 上游=%s 错误=%s 耗时毫秒=%s 重试次数=%s",
            request_id,
            upstream_url,
            error_message,
            int((time.perf_counter() - started_at) * 1000),
            retry_count,
        )
        body = json.dumps(error_payload, ensure_ascii=False).encode("utf-8")
        finalize_request_record(
            request_id,
            started_at=started_at,
            status_code=int(failure["status_code"]),
            bytes_sent=len(body),
            stream=requested_stream,
            error=error_message,
            sanitized_markers=0,
            response_preview=str(request_exception or error_message),
            repaired_tool_args=0,
            client_gone=bool(failure["client_gone"]),
            extra_meta=build_request_observability_meta(execution, request_payload),
        )
        return Response(
            body,
            status=int(failure["status_code"]),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Proxy-Retries": str(retry_count),
            },
        )

    if retry_count > 0:
        proxy_logger.warning(
            "request_id=%s 上游尝试摘要=%s",
            request_id,
            summarize_attempts_for_log(attempts),
        )

    return proxy_response(
        upstream_response,
        sanitize_dsml=sanitize_dsml,
        request_id=request_id,
        upstream_url=upstream_url,
        started_at=started_at,
        requested_stream=requested_stream,
        route_hint=upstream_subpath,
        tool_schemas=tool_schemas,
        retry_count=retry_count,
        protocol=detected_protocol,
        request_payload=request_payload,
        execution=execution,
    )


def proxy(subpath: str):
    return proxy_entrypoint(subpath)


def proxy_gemini_versioned(subpath: str):
    return proxy_entrypoint(subpath)


def dashboard_redirect():
    from flask import redirect

    return redirect("/v1", code=302)


register_http_routes(
    app,
    {
        "add_cors_headers": add_cors_headers,
        "health": health,
        "debug_state": login_required(debug_state),
        "debug_config": login_required(debug_config),
        "debug_pool_test": login_required(debug_pool_test),
        "debug_requests_clear": login_required(debug_requests_clear),
        "debug_proxy_api_keys": login_required(debug_proxy_api_keys),
        "v1_root": v1_root,
        "gemini_version_root": gemini_version_root,
        "anthropic_messages": anthropic_messages,
        "proxy": proxy,
        "proxy_gemini_versioned": proxy_gemini_versioned,
    },
)

app.add_url_rule("/", endpoint="dashboard_redirect", view_func=dashboard_redirect)
app.add_url_rule("/login", endpoint="login_page", view_func=login_page, methods=["GET", "POST"])
app.add_url_rule("/logout", endpoint="logout", view_func=logout)

def run_proxy_app() -> None:
    host = "0.0.0.0"
    threads = max(4, int(os.getenv("WAITRESS_THREADS", "16")))
    channel_timeout = max(60, int(os.getenv("WAITRESS_CHANNEL_TIMEOUT", "1200")))
    cleanup_interval = max(5, int(os.getenv("WAITRESS_CLEANUP_INTERVAL", "30")))

    try:
        from waitress import serve
    except Exception:
        app.run(host=host, port=PORT, debug=False, threaded=True)
        return

    serve(
        app,
        host=host,
        port=PORT,
        threads=threads,
        channel_timeout=channel_timeout,
        cleanup_interval=cleanup_interval,
        ident="local-proxy",
    )


if __name__ == "__main__":
    run_proxy_app()
