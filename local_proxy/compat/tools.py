import json
import logging
import re
import sys
import time
import uuid
import json

from local_proxy.upstream.capabilities import (
    clamp_payload_output_tokens,
    find_model_capability,
)


INJECT_ZH_SYSTEM_PROMPT = False
PROXY_SYSTEM_PROMPT_ZH = ""
ENABLE_REQUEST_NORMALIZATION = True
MAX_COMPLETION_TOKENS = 0
MODEL_CAPABILITIES = {}


def _coerce_non_negative_int(value) -> int:
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    try:
        return max(0, int(float(str(value).strip())))
    except Exception:
        return 0


def normalize_openai_usage_payload(usage: dict | None) -> dict:
    usage = dict(usage) if isinstance(usage, dict) else {}
    prompt_details = usage.get("prompt_tokens_details")
    prompt_details = prompt_details if isinstance(prompt_details, dict) else {}
    cached_tokens = _coerce_non_negative_int(
        prompt_details.get("cached_tokens")
        or usage.get("cache_read_input_tokens")
        or usage.get("prompt_cache_hit_tokens")
    )
    cache_creation_tokens = _coerce_non_negative_int(
        prompt_details.get("cache_creation_tokens") or usage.get("cache_creation_input_tokens")
    )
    prompt_cache_hit_tokens = _coerce_non_negative_int(
        usage.get("prompt_cache_hit_tokens") or cached_tokens
    )
    prompt_cache_miss_tokens = _coerce_non_negative_int(usage.get("prompt_cache_miss_tokens"))
    prompt_tokens = _coerce_non_negative_int(usage.get("prompt_tokens") or usage.get("input_tokens"))
    total_tokens = _coerce_non_negative_int(usage.get("total_tokens"))
    if prompt_tokens <= 0 and (prompt_cache_hit_tokens > 0 or prompt_cache_miss_tokens > 0):
        prompt_tokens = prompt_cache_hit_tokens + prompt_cache_miss_tokens
        usage["prompt_tokens"] = prompt_tokens
    if total_tokens <= 0:
        completion_tokens = _coerce_non_negative_int(
            usage.get("completion_tokens") or usage.get("output_tokens")
        )
        if prompt_tokens > 0 or completion_tokens > 0:
            usage["total_tokens"] = prompt_tokens + completion_tokens
    if cached_tokens > 0:
        prompt_details["cached_tokens"] = cached_tokens
        usage["cache_read_input_tokens"] = cached_tokens
        usage["prompt_cache_hit_tokens"] = prompt_cache_hit_tokens
    if cache_creation_tokens > 0:
        prompt_details["cache_creation_tokens"] = cache_creation_tokens
        usage["cache_creation_input_tokens"] = cache_creation_tokens
    if prompt_cache_miss_tokens > 0:
        usage["prompt_cache_miss_tokens"] = prompt_cache_miss_tokens
    if prompt_details:
        usage["prompt_tokens_details"] = prompt_details
    return usage


def configure_tool_compat(
    *,
    enable_request_normalization: bool = True,
    inject_zh_system_prompt: bool,
    proxy_system_prompt_zh: str,
    max_completion_tokens: int | None = None,
    model_capabilities: dict | None = None,
) -> None:
    global ENABLE_REQUEST_NORMALIZATION
    global INJECT_ZH_SYSTEM_PROMPT
    global PROXY_SYSTEM_PROMPT_ZH
    global MAX_COMPLETION_TOKENS
    global MODEL_CAPABILITIES

    ENABLE_REQUEST_NORMALIZATION = bool(enable_request_normalization)
    INJECT_ZH_SYSTEM_PROMPT = bool(inject_zh_system_prompt)
    PROXY_SYSTEM_PROMPT_ZH = str(proxy_system_prompt_zh or "").strip()
    if max_completion_tokens is not None:
        try:
            MAX_COMPLETION_TOKENS = max(0, int(str(max_completion_tokens).strip()))
        except Exception:
            MAX_COMPLETION_TOKENS = 0
    if model_capabilities is not None:
        MODEL_CAPABILITIES = dict(model_capabilities or {})


def normalize_completion_token_limits(request_payload: dict) -> int:
    model_capability = find_model_capability(request_payload.get("model"), MODEL_CAPABILITIES)
    model_output_limit = None
    if isinstance(model_capability, dict):
        model_output_limit = model_capability.get("max_output_tokens")
    repairs = clamp_payload_output_tokens(request_payload, model_output_limit)
    repairs += clamp_payload_output_tokens(request_payload, MAX_COMPLETION_TOKENS)
    return repairs


def canonicalize_dsml_marker_seed(text: str | None) -> str:
    if not isinstance(text, str):
        return ""
    stripped = text.lstrip()
    if not stripped:
        return ""
    return re.sub(r"[\s|｜_/\-]+", "", stripped).lower()

DSML_PATTERN = re.compile(
    r"<\s*[|｜]\s*DSML\s*[|｜]\s*tool_[a-z_]*(?:\s*[|｜]>)?",
    re.IGNORECASE,
)
DSML_LOOSE_PATTERN = re.compile(
    r"<\s*/?\s*[|｜]\s*DSML\s*[|｜]\s*(?:tool_[a-z_]*|invoke|parameter|/[a-z_]+)?(?:[^>\n\r]*)>?",
    re.IGNORECASE,
)
DSML_ANY_TAG_PATTERN = re.compile(
    r"<\s*/?\s*[|｜]\s*DSML\s*[|｜]\s*[a-z_/]+(?:[^>]*)>",
    re.IGNORECASE,
)
DSML_INLINE_FRAGMENT_PATTERN = re.compile(
    r"<(?:\s|[|｜_/-])*(?:D(?:\s|[|｜_/-])*S(?:\s|[|｜_/-])*M(?:\s|[|｜_/-])*L)"
    r"(?:\s|[|｜_/-])*(?:t(?:\s|[|｜_/-])*o(?:\s|[|｜_/-])*o(?:\s|[|｜_/-])*l)"
    r"(?:\s|[|｜_/-])*(?:_?(?:\s|[|｜_/-])*c(?:\s|[|｜_/-])*a(?:\s|[|｜_/-])*l(?:\s|[|｜_/-])*l(?:\s|[|｜_/-])*s)",
    re.IGNORECASE,
)
DSML_LEADING_FRAGMENT_PATTERN = re.compile(
    r"^\s*<(?:\s|[|｜_/-])*(?:D(?:\s|[|｜_/-])*S(?:\s|[|｜_/-])*M(?:\s|[|｜_/-])*L)"
    r"(?:\s|[|｜_/-])*(?:t(?:\s|[|｜_/-])*o(?:\s|[|｜_/-])*o(?:\s|[|｜_/-])*l)"
    r"(?:\s|[|｜_/-])*(?:_?(?:\s|[|｜_/-])*c(?:\s|[|｜_/-])*a(?:\s|[|｜_/-])*l(?:\s|[|｜_/-])*l(?:\s|[|｜_/-])*s)"
    r"(?:\s|[|｜_/\->])*",
    re.IGNORECASE,
)
DSML_ARTIFACT_LINE_PATTERN = re.compile(
    r"(?im)^[ \t]*<\s*/?\s*[|｜]\s*DSML\s*[|｜][^\n\r>]*(?:>)?[ \t]*$"
)
DSML_TAG_START_PATTERN = re.compile(
    r"<\s*[|｜]\s*DSML\s*[|｜]\s*(?:tool_[a-z_]*|invoke|parameter|/[a-z_]+)",
    re.IGNORECASE,
)
DSML_INVOKE_PATTERN = re.compile(
    r"<\s*[|｜]\s*DSML\s*[|｜]\s*invoke\b(?P<attrs>[^>]*)>"
    r"(?P<body>.*?)"
    r"<\s*/\s*[|｜]\s*DSML\s*[|｜]\s*invoke\s*>",
    re.IGNORECASE | re.DOTALL,
)
DSML_PARAMETER_PATTERN = re.compile(
    r"<\s*[|｜]\s*DSML\s*[|｜]\s*parameter\b(?P<attrs>[^>]*)>"
    r"(?P<body>.*?)"
    r"<\s*/\s*[|｜]\s*DSML\s*[|｜]\s*parameter\s*>",
    re.IGNORECASE | re.DOTALL,
)
XML_ATTR_PATTERN = re.compile(r'([a-zA-Z_][a-zA-Z0-9_-]*)\s*=\s*"([^"]*)"')
DSML_MARKER_VARIANTS = (
    "<|DSML|tool_calls",
    "<｜DSML｜tool_calls",
)
CANONICAL_DSML_MARKER_VARIANTS = tuple(
    canonicalize_dsml_marker_seed(item)
    for item in DSML_MARKER_VARIANTS
)
TOOL_USE_ERROR_BLOCK_PATTERN = re.compile(
    r"<tool_use_error>.*?</tool_use_error>",
    re.IGNORECASE | re.DOTALL,
)
SIMPLE_FILEISH_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_./\\:@*?\-\[\]\(\)]+$")
VALIDATION_NOISE_LINE_PATTERN = re.compile(
    r"(?i)^(?:Expected 'function' type\.|.*parameter is REQUIRED.*|Specify run_in_background=.*|提交反馈|错误类型[:：]?|错误码[:：]?|Request ID[:：]?|Message ID[:：]?|Write failed|Read failed|Glob failed|Bash failed)$"
)
VALIDATION_NOISE_VALUE_LABEL_PATTERN = re.compile(
    r"(?i)^(?:错误类型[:：]?|错误码[:：]?|Request ID[:：]?|Message ID[:：]?)$"
)
ENGLISH_TOOL_LEADIN_PATTERN = re.compile(
    r"(?is)^\s*(?:now\s+let\s+me|let\s+me|i(?:'|’)ll|i\s+will|first[, ]+i(?:'|’)ll|first[, ]+i\s+will)\b.*?(?=(?:\|\s*工具:|工具:|$))"
)
DSML_ORPHAN_FRAGMENT_LINE_PATTERN = re.compile(
    r"(?im)^[ \t]*(?:_?calls|tool_?calls|dsml|tool|_c|alls|tool_?c|_calls)[ \t]*$"
)
MARKDOWN_TABLE_SEPARATOR_LINE_PATTERN = re.compile(
    r"(?m)^\s*\|(?:\s*:?-{3,}:?\s*\|){1,}\s*$"
)
MARKDOWN_TABLE_ROW_START_PATTERN = re.compile(
    r"^\|[^|\n]+(?:\|[^|\n]+){1,}\|"
)
MARKDOWN_TABLE_ROW_BOUNDARY_PATTERN = re.compile(
    r"(?<=\|)[^\S\n]+(?=\|[^|\n]+(?:\|[^|\n]+){1,}\|)"
)
MARKDOWN_COLLAPSED_SEPARATOR_PREFIX_PATTERN = re.compile(
    r"(?m)^(\s*\|(?:\s*:?-{3,}:?\s*\|){2,})(\s+\|.+)$"
)
MARKDOWN_COLLAPSED_SEPARATOR_SUFFIX_PATTERN = re.compile(
    r"(?m)^(.+\|)(\s+\|(?:\s*:?-{3,}:?\s*\|){2,}\s*)$"
)

BASH_LIKE_TOOL_NAMES = {
    "bash",
    "shell",
    "shell_command",
    "run_command",
    "terminal",
}

WINDOWS_DRIVE_CD_PATTERN = re.compile(
    r'(?im)(^|\s)(cd)\s+([A-Za-z]):\\([^"\n\r;&|]+)'
)

COMMAND_ALIASES = (
    "cmd",
    "commands",
    "commandText",
    "command_text",
    "bashCommand",
    "bash_command",
    "shellCommand",
    "shell_command",
    "script",
    "shell",
    "bash",
    "input",
    "text",
    "code",
    "commandLine",
    "command_line",
)

COMMON_FIELD_ALIASES = {
    "command": COMMAND_ALIASES + ("cmdline",),
    "query": ("q", "search", "search_query", "keyword", "keywords"),
    "filePath": ("path", "file_path", "filepath", "file"),
    "target_directory": ("targetDirectory", "directory", "dir", "folder", "path"),
    "targetDirectory": ("target_directory", "directory", "dir", "folder", "path"),
    "pattern": (
        "query",
        "q",
        "glob",
        "globpattern",
        "regex",
        "regexp",
        "search",
        "search_query",
        "keyword",
        "keywords",
        "needle",
        "term",
        "terms",
        "text",
        "content",
    ),
    "explanation": ("reason", "justification", "summary", "comment", "description"),
    "justification": ("reason", "explanation", "summary", "comment", "description"),
    "run_in_background": (
        "runInBackground",
        "runInBg",
        "run_in_bg",
        "run_background",
        "background",
        "background_mode",
        "backgroundExecution",
        "background_execution",
        "in_background",
        "backgroundTask",
        "background_task",
        "parallel",
        "parallelize",
        "parallel_exploration",
        "parallelExploration",
        "async",
        "async_mode",
        "concurrent",
        "concurrency",
        "non_blocking",
        "nonBlocking",
    ),
}

TOOL_NAME_ALIAS_GROUPS = (
    ("execute_command", "bash", "shell", "shell_command", "run_command", "terminal"),
    ("web_search", "searchweb", "search_web", "search-web"),
    ("read_file", "readfile", "read"),
    ("edit", "edit_file", "editfile", "edit file"),
    ("search_file", "searchfile", "find_file", "glob", "globpattern", "grep", "ripgrep"),
    ("write_file", "writefile", "write file", "write", "create_file", "create file"),
    ("list_dir", "listdir", "list_directory", "ls"),
    ("todo_write", "todowrite", "update_todos", "update todos", "todos"),
    ("mcp_get_tool_description", "mcpgettooldescription"),
    ("task", "Task", "delegate", "delegation", "agent", "agent_task", "spawn_agent", "subagent", "sub_agent", "subtask", "explore", "exploration"),
    ("skill", "load_skill", "skill_load"),
    ("webfetch", "web_fetch", "fetch", "fetch_url"),
    ("websearch", "web_search", "search_web", "searchweb"),
    ("grep", "rg", "ripgrep"),
    ("glob", "find_file", "search_file"),
    ("list", "list_dir", "list_directory", "ls"),
)

EDIT_PATH_FIELD_CANONICALS = {"filepath", "path", "file", "targetfile", "targetfilepath"}
EDIT_OLD_FIELD_CANONICALS = {"oldstring", "oldtext", "search", "searchtext", "before"}
EDIT_NEW_FIELD_CANONICALS = {"newstring", "newtext", "replacement", "replace", "after"}
EMPTY_TOOL_META_FIELD_CANONICALS = {
    "comment",
    "description",
    "explanation",
    "justification",
    "reason",
    "requiresapproval",
    "timeout",
    "timeoutms",
}
RUN_IN_BACKGROUND_FIELD_CANONICAL = "runinbackground"
RUN_IN_BACKGROUND_TRUE_MARKERS = (
    "run_in_background=true",
    "runinbackground=true",
    "background=true",
    "parallel=true",
    "async=true",
    "parallel exploration",
    "parallel explore",
    "parallel research",
    "parallel investigation",
    "background exploration",
    "run in background",
    "non-blocking",
    "non blocking",
    "concurrent exploration",
    "并行探索",
    "并行调研",
    "并行研究",
    "后台探索",
    "后台运行",
    "不要阻塞",
)
RUN_IN_BACKGROUND_FALSE_MARKERS = (
    "run_in_background=false",
    "runinbackground=false",
    "background=false",
    "parallel=false",
    "async=false",
    "task delegation",
    "delegate and wait",
    "blocking",
    "run synchronously",
    "同步执行",
    "常规委托",
    "等待结果",
)
TASK_LIKE_TOOL_NAME_MARKERS = (
    "task",
    "delegate",
    "delegation",
    "agent",
    "agenttask",
    "subagent",
    "sub_agent",
    "subtask",
    "spawnagent",
    "explore",
    "exploration",
)
TASK_CONTROL_TOOL_NAME_MARKERS = (
    "taskstop",
    "taskcancel",
    "taskstatus",
    "taskresult",
    "taskresults",
    "tasklist",
    "stoptask",
    "canceltask",
)
SEARCH_INPUT_FIELD_CANONICALS = {
    "pattern",
    "query",
    "q",
    "glob",
    "globpattern",
    "regex",
    "regexp",
    "search",
    "searchquery",
    "keyword",
    "keywords",
    "needle",
    "term",
    "terms",
    "text",
    "content",
}
PREVIEW_TOOL_ARGUMENT_PRIORITY = (
    "command",
    "query",
    "pattern",
    "filePath",
    "path",
    "target_directory",
    "targetDirectory",
    "description",
    "prompt",
)


def clean_dsml_markers(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    cleaned, _ = sanitize_dsml_text(text)
    return cleaned


def sanitize_dsml_text(text: str) -> tuple[str, int]:
    if not isinstance(text, str) or not text:
        return text, 0

    cleaned_text, removed = DSML_PATTERN.subn("", text)
    cleaned_text, removed_loose = DSML_LOOSE_PATTERN.subn("", cleaned_text)
    cleaned_text, removed_inline = DSML_INLINE_FRAGMENT_PATTERN.subn("", cleaned_text)
    cleaned_text, removed_lines = DSML_ARTIFACT_LINE_PATTERN.subn("", cleaned_text)
    cleaned_text, removed_orphan_lines = DSML_ORPHAN_FRAGMENT_LINE_PATTERN.subn("", cleaned_text)
    cleaned_text, removed_spacing = re.subn(r"[ \t]+\n", "\n", cleaned_text)
    cleaned_text, removed_blank_runs = re.subn(r"\n{3,}", "\n\n", cleaned_text)
    return (
        cleaned_text,
        removed + removed_loose + removed_inline + removed_lines + removed_orphan_lines + removed_spacing + removed_blank_runs,
    )


def strip_all_dsml_tags(text: str) -> tuple[str, int]:
    partially_cleaned, removed = sanitize_dsml_text(text)
    fully_cleaned, removed_all = DSML_ANY_TAG_PATTERN.subn("", partially_cleaned)
    return fully_cleaned, removed + removed_all


def strip_tool_use_error_blocks(text: str) -> tuple[str, int]:
    if not isinstance(text, str) or not text:
        return text, 0
    return TOOL_USE_ERROR_BLOCK_PATTERN.subn("", text)


def strip_validation_noise_lines(text: str) -> tuple[str, int]:
    if not isinstance(text, str) or not text:
        return text, 0

    cleaned_lines = []
    removed = 0
    skip_next_value = False
    for line in text.replace("\r", "").split("\n"):
        stripped_line = line.strip()
        if skip_next_value and stripped_line:
            removed += 1
            skip_next_value = False
            continue
        if VALIDATION_NOISE_LINE_PATTERN.match(stripped_line):
            removed += 1
            if VALIDATION_NOISE_VALUE_LABEL_PATTERN.match(stripped_line):
                skip_next_value = True
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines), removed


def text_contains_markdown_table_separator(text: str | None) -> bool:
    return bool(isinstance(text, str) and MARKDOWN_TABLE_SEPARATOR_LINE_PATTERN.search(text))


def text_contains_markdown_table_row_boundary(text: str | None) -> bool:
    return bool(isinstance(text, str) and MARKDOWN_TABLE_ROW_BOUNDARY_PATTERN.search(text))


def starts_with_markdown_table_row(text: str | None) -> bool:
    return bool(isinstance(text, str) and MARKDOWN_TABLE_ROW_START_PATTERN.match(text.lstrip()))


def count_markdown_table_cells(line: str | None) -> int:
    stripped = str(line or "").strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return 0
    return len(stripped[1:-1].split("|"))


def is_markdown_table_separator_row(line: str | None) -> bool:
    return bool(isinstance(line, str) and MARKDOWN_TABLE_SEPARATOR_LINE_PATTERN.match(line.strip()))


def split_collapsed_markdown_table_rows(line: str, column_count: int) -> tuple[list[str], int]:
    if column_count <= 0:
        return [line], 0

    indent = re.match(r"^\s*", line or "").group(0)
    if len(indent) <= 1:
        indent = ""
    stripped = str(line or "").strip()
    raw_cells = [cell.strip() for cell in stripped[1:-1].split("|")]
    candidate_cells = list(raw_cells)
    cell_count = len(candidate_cells)
    if cell_count > column_count and cell_count % column_count != 0 and re.search(r"\|\s+\|", stripped):
        non_empty_cells = [cell for cell in candidate_cells if cell]
        if len(non_empty_cells) > column_count and len(non_empty_cells) % column_count == 0:
            candidate_cells = non_empty_cells
            cell_count = len(candidate_cells)

    if cell_count <= column_count or cell_count % column_count != 0:
        return [line], 0

    rows = []
    for index in range(0, len(candidate_cells), column_count):
        row_cells = candidate_cells[index:index + column_count]
        rows.append(f"{indent}| " + " | ".join(row_cells) + " |")
    return rows, max(0, len(rows) - 1)


def repair_markdown_table_layout(
    text: str,
    *,
    initial_in_table: bool = False,
    initial_column_count: int = 0,
) -> tuple[str, int, bool, int]:
    if not isinstance(text, str) or "|" not in text:
        return text, 0, bool(initial_in_table), int(initial_column_count or 0)

    repaired = 0
    normalized = text
    normalized, changed = MARKDOWN_COLLAPSED_SEPARATOR_PREFIX_PATTERN.subn(r"\1\n\2", normalized)
    repaired += changed
    normalized, changed = MARKDOWN_COLLAPSED_SEPARATOR_SUFFIX_PATTERN.subn(r"\1\n\2", normalized)
    repaired += changed

    lines = normalized.split("\n")
    repaired_lines = []
    in_table = bool(initial_in_table)
    column_count = int(initial_column_count or 0)
    pending_header_cells = 0

    for line in lines:
        stripped = line.strip()
        if is_markdown_table_separator_row(stripped):
            separator_cells = count_markdown_table_cells(stripped)
            if separator_cells:
                column_count = separator_cells
            elif pending_header_cells:
                column_count = pending_header_cells
            in_table = True
            repaired_lines.append(line)
            continue

        row_cells = count_markdown_table_cells(stripped)
        if row_cells >= 2:
            if in_table and column_count:
                split_rows, changed = split_collapsed_markdown_table_rows(line, column_count)
                repaired += changed
                repaired_lines.extend(split_rows)
            else:
                repaired_lines.append(line)
                pending_header_cells = row_cells
            continue

        repaired_lines.append(line)
        if stripped:
            in_table = False
            column_count = 0
            pending_header_cells = 0

    return "\n".join(repaired_lines), repaired, in_table, column_count


def normalize_markdown_output_text(text: str) -> tuple[str, int]:
    if not isinstance(text, str) or not text or "|" not in text:
        return text, 0

    parts = re.split(r"(```.*?```)", text, flags=re.DOTALL)
    repaired = 0
    normalized_parts = []

    for index, part in enumerate(parts):
        if index % 2 == 1:
            normalized_parts.append(part)
            continue

        normalized_part, changed, _, _ = repair_markdown_table_layout(part)
        repaired += changed
        normalized_part, changed = re.subn(
            r"(\|[^\n]*\|)\n\s*\n(\|\s*:?-{3,}[^\n]*\|)",
            r"\1\n\2",
            normalized_part,
        )
        repaired += changed
        normalized_part, changed = re.subn(
            r"(\|\s*:?-{3,}[^\n]*\|)\n\s*\n(\|[^\n]*\|)",
            r"\1\n\2",
            normalized_part,
        )
        repaired += changed
        normalized_part, changed = re.subn(r"\n{3,}", "\n\n", normalized_part)
        repaired += changed

        normalized_parts.append(normalized_part)

    return "".join(normalized_parts), repaired


def normalize_markdown_output_fragment(fragment: str, state: dict) -> tuple[str, int]:
    if not isinstance(fragment, str) or not fragment:
        return fragment, 0

    repaired = 0
    normalized_fragment = fragment
    previous_tail = state.get("markdown_tail", "")
    stripped = normalized_fragment.lstrip()
    leading = normalized_fragment[: len(normalized_fragment) - len(stripped)]
    previous_in_table = bool(state.get("markdown_in_table"))
    previous_column_count = int(state.get("markdown_table_columns") or 0)

    if previous_tail and not previous_tail.endswith("\n"):
        if re.match(r"^\|\s*#\s*\|", stripped):
            normalized_fragment = f"{leading}\n\n{stripped}"
            repaired += 1
        elif (
            re.match(r"^\|\s*:?-{3,}\s*\|", stripped)
            or re.match(r"^\|\s*\d+\s*\|", stripped)
            or (previous_in_table and starts_with_markdown_table_row(stripped))
        ):
            normalized_fragment = f"{leading}\n{stripped}"
            repaired += 1

    normalized_fragment, normalized_repairs, current_in_table, current_column_count = repair_markdown_table_layout(
        normalized_fragment,
        initial_in_table=previous_in_table,
        initial_column_count=previous_column_count,
    )
    repaired += normalized_repairs
    normalized_fragment, changed = re.subn(
        r"(\|[^\n]*\|)\n\s*\n(\|\s*:?-{3,}[^\n]*\|)",
        r"\1\n\2",
        normalized_fragment,
    )
    repaired += changed
    normalized_fragment, changed = re.subn(
        r"(\|\s*:?-{3,}[^\n]*\|)\n\s*\n(\|[^\n]*\|)",
        r"\1\n\2",
        normalized_fragment,
    )
    repaired += changed
    state["markdown_tail"] = f"{previous_tail}{normalized_fragment}"[-240:]
    state["markdown_in_table"] = current_in_table
    state["markdown_table_columns"] = current_column_count
    return normalized_fragment, repaired


def canonicalize_name(name: str | None) -> str:
    if not isinstance(name, str):
        return ""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def is_bash_like_tool_name(tool_name: str | None) -> bool:
    bash_like_canonicals = {
        canonicalize_name(item)
        for item in BASH_LIKE_TOOL_NAMES | {"execute_command"}
    }
    return canonicalize_name(tool_name) in bash_like_canonicals


def flatten_instruction_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        text_parts = []
        for block in value:
            if not isinstance(block, dict):
                continue
            block_text = block.get("text")
            if isinstance(block_text, str):
                text_parts.append(block_text)
        return "".join(text_parts)
    return ""


def extract_openai_text_from_blocks(content_blocks) -> tuple[str | list, list[dict], bool]:
    if not isinstance(content_blocks, list):
        return content_blocks, [], False

    text_parts = []
    tool_calls = []
    recognized_any = False

    for block in content_blocks:
        if not isinstance(block, dict):
            return content_blocks, [], False

        block_type = block.get("type")
        if block_type in {"text", "input_text", "output_text"}:
            recognized_any = True
            text_parts.append(block.get("text", ""))
            continue

        if block_type == "tool_use":
            recognized_any = True
            tool_calls.append(
                {
                    "id": block.get("id") or f"call_{uuid.uuid4().hex[:24]}",
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                    },
                }
            )
            continue

        return content_blocks, [], False

    if not recognized_any:
        return content_blocks, [], False

    normalized_text = "".join(text_parts)
    if tool_calls and not normalized_text:
        normalized_text = None

    return normalized_text, tool_calls, True


def build_text_tool_label_candidates(tool_schemas: dict) -> list[tuple[str, str]]:
    if not isinstance(tool_schemas, dict) or not tool_schemas:
        return []

    candidates = {}
    for schema_name in tool_schemas:
        if not isinstance(schema_name, str) or not schema_name.strip():
            continue
        variants = {
            schema_name,
            schema_name.replace("_", " "),
            schema_name.replace("-", " "),
        }
        for variant in variants:
            normalized_variant = " ".join(variant.split()).strip().lower()
            if normalized_variant:
                candidates[normalized_variant] = schema_name

    for group in TOOL_NAME_ALIAS_GROUPS:
        resolved_name = None
        for candidate in group:
            resolved_name = resolve_tool_name(candidate, tool_schemas)
            if resolved_name in tool_schemas:
                break
        if resolved_name not in tool_schemas:
            continue

        for alias in group:
            variants = {
                alias,
                alias.replace("_", " "),
                alias.replace("-", " "),
            }
            for variant in variants:
                normalized_variant = " ".join(str(variant).split()).strip().lower()
                if normalized_variant:
                    candidates[normalized_variant] = resolved_name

    return sorted(candidates.items(), key=lambda item: len(item[0]), reverse=True)


def match_text_tool_invocation_header(line: str, tool_schemas: dict) -> tuple[str | None, str]:
    stripped = (line or "").strip()
    if not stripped:
        return None, ""

    for label, resolved_name in build_text_tool_label_candidates(tool_schemas):
        match = re.match(rf"(?i)^{re.escape(label)}(?:\s*[:：-]\s*|\s+)?(.*)?$", stripped)
        if not match:
            continue
        return resolved_name, (match.group(1) or "").strip()

    return None, ""


def looks_like_textual_tool_payload(tool_name: str | None, payload_text: str, tool_schemas: dict) -> bool:
    stripped = (payload_text or "").strip()
    if not stripped:
        return False

    if stripped.startswith("{") or stripped.startswith("["):
        return True

    resolved_tool_name = resolve_tool_name(tool_name, tool_schemas) or tool_name or ""
    tool_canonical = canonicalize_name(resolved_tool_name)
    schema = tool_schemas.get(resolved_tool_name, {})
    required = list(schema.get("required") or [])

    if is_bash_like_tool_name(resolved_tool_name):
        return any(token in stripped for token in (" ", "/", "\\", ":", "-", "|", "&", ";", "=", ">", "<", ".")) or len(stripped) <= 64

    if any(marker in tool_canonical for marker in ("read", "file", "path", "dir", "list", "glob", "search")):
        return (
            any(token in stripped for token in ("/", "\\", ":", ".", "*", "?", '"', "'"))
            or stripped.lower() in {"readme", "license", "makefile", "dockerfile"}
            or (
                bool(SIMPLE_FILEISH_TOKEN_PATTERN.fullmatch(stripped))
                and any(token in stripped for token in (".", "/", "\\", ":", "_", "-"))
            )
        )

    if required == ["query"]:
        return len(stripped) <= 200

    return False


def is_effectively_empty_tool_payload(payload_text: str) -> bool:
    stripped = (payload_text or "").strip()
    if stripped in {"", "{}", "[]", "null", "None", '""', "''"}:
        return True
    return False


def looks_like_failed_tool_transcript(tool_name: str | None, payload_text: str, transcript_text: str) -> bool:
    transcript = (transcript_text or "").lower()
    if "tool_use_error" not in transcript and "inputvalidationerror" not in transcript:
        return False

    if "required parameter" in transcript or "command is missing" in transcript or "expected 'function' type" in transcript:
        return True

    if "unexpected parameter" in transcript or "provided" in transcript:
        return True

    if is_effectively_empty_tool_payload(payload_text):
        return True

    if is_bash_like_tool_name(tool_name):
        return "bash failed" in transcript

    return False


def is_failed_tool_status_line(tool_name: str | None, current_line: str, candidate_line: str) -> bool:
    current = (current_line or "").strip()
    candidate = (candidate_line or "").strip().lower()
    if not candidate or "failed" not in candidate:
        return False

    current_canonical = canonicalize_name(current)
    tool_canonical = canonicalize_name(tool_name)
    candidate_without_failed = canonicalize_name(
        re.sub(r"(?i)\b(?:write|read|glob|bash|tool)?\s*failed\b", "", candidate_line or "")
    )

    if candidate in {"failed", "write failed", "read failed", "glob failed", "bash failed"}:
        return True

    if current_canonical and current_canonical in canonicalize_name(candidate_line):
        return True
    if tool_canonical and tool_canonical in canonicalize_name(candidate_line):
        return True
    if candidate_without_failed and (
        candidate_without_failed in current_canonical
        or candidate_without_failed in tool_canonical
        or current_canonical in candidate_without_failed
        or tool_canonical in candidate_without_failed
    ):
        return True

    return False


def collect_out_error_transcript(
    lines: list[str],
    start_index: int,
    tool_schemas: dict,
) -> tuple[str, int]:
    transcript_lines = []
    scan_index = start_index

    while scan_index < len(lines):
        current_line = lines[scan_index]
        prospective_tool_name, _ = match_text_tool_invocation_header(current_line, tool_schemas)
        if scan_index > start_index and prospective_tool_name:
            break
        transcript_lines.append(current_line)
        scan_index += 1

    return "\n".join(transcript_lines), max(start_index, scan_index - 1)


def extract_plain_text_tool_calls_from_text(text: str, tool_schemas: dict) -> tuple[str, list[dict], int]:
    if not isinstance(text, str) or not tool_schemas:
        return text, [], 0

    normalized_text = text.replace("\r", "")
    lines = normalized_text.split("\n")
    cleaned_lines = []
    tool_calls = []
    repaired = 0
    index = 0

    while index < len(lines):
        current_line = lines[index]
        tool_name, inline_payload = match_text_tool_invocation_header(current_line, tool_schemas)
        if not tool_name:
            cleaned_lines.append(current_line)
            index += 1
            continue

        next_non_empty = index + 1
        while next_non_empty < len(lines) and not lines[next_non_empty].strip():
            next_non_empty += 1

        payload_text = None
        transcript_text = current_line
        consume_until = index
        used_in_block = False

        if next_non_empty < len(lines) and lines[next_non_empty].strip().upper() == "IN":
            used_in_block = True
            payload_lines = []
            transcript_lines = [current_line, lines[next_non_empty]]
            scan_index = next_non_empty + 1
            while scan_index < len(lines):
                stripped_line = lines[scan_index].strip()
                if stripped_line.upper() == "OUT":
                    transcript_lines.append(lines[scan_index])
                    scan_index += 1
                    while scan_index < len(lines):
                        transcript_lines.append(lines[scan_index])
                        prospective_tool_name, _ = match_text_tool_invocation_header(lines[scan_index], tool_schemas)
                        if prospective_tool_name:
                            transcript_lines.pop()
                            break
                        scan_index += 1
                    break
                payload_lines.append(lines[scan_index])
                transcript_lines.append(lines[scan_index])
                scan_index += 1
            payload_text = "\n".join(payload_lines).strip()
            consume_until = max(index, scan_index - 1)
            transcript_text = "\n".join(transcript_lines)
        elif inline_payload and looks_like_textual_tool_payload(tool_name, inline_payload, tool_schemas):
            payload_text = inline_payload
            transcript_text = current_line
        elif next_non_empty < len(lines):
            candidate_line = lines[next_non_empty].strip()
            candidate_tool_name, _ = match_text_tool_invocation_header(lines[next_non_empty], tool_schemas)
            if candidate_tool_name and not inline_payload:
                repaired += 1
                index += 1
                continue
            if candidate_line.upper() == "OUT":
                transcript_text, consume_until = collect_out_error_transcript(lines, index, tool_schemas)
                if looks_like_failed_tool_transcript(tool_name, "", transcript_text):
                    repaired += 1
                    index = consume_until + 1
                    continue
            if is_failed_tool_status_line(tool_name, current_line, candidate_line):
                repaired += 1
                index = next_non_empty + 1
                continue
            if (
                candidate_line
                and candidate_line.upper() != "OUT"
                and not candidate_tool_name
                and looks_like_textual_tool_payload(tool_name, candidate_line, tool_schemas)
            ):
                payload_text = candidate_line
                consume_until = next_non_empty
                transcript_text = f"{current_line}\n{lines[next_non_empty]}"

        if payload_text is None and not used_in_block:
            cleaned_lines.append(current_line)
            index += 1
            continue

        if looks_like_failed_tool_transcript(tool_name, payload_text or "", transcript_text):
            repaired += 1
            index = consume_until + 1
            continue

        schema = tool_schemas.get(resolve_tool_name(tool_name, tool_schemas) or tool_name or "", {})
        if is_effectively_empty_tool_payload(payload_text or "") and list(schema.get("required") or []):
            repaired += 1
            index = consume_until + 1
            continue

        parsed_payload = payload_text or ""
        if isinstance(parsed_payload, str):
            stripped_payload = parsed_payload.strip()
            if stripped_payload.startswith("{") or stripped_payload.startswith("["):
                try:
                    parsed_payload = json.loads(stripped_payload)
                except json.JSONDecodeError:
                    parsed_payload = payload_text or ""

        resolved_tool_name = resolve_tool_name(tool_name, tool_schemas) or tool_name
        normalized_payload, modified = normalize_tool_arguments_payload(
            resolved_tool_name,
            parsed_payload,
            tool_schemas,
        )
        resolved_tool_name = infer_tool_name_from_payload(resolved_tool_name, normalized_payload, tool_schemas) or resolved_tool_name
        if should_suppress_tool_call(resolved_tool_name, normalized_payload, tool_schemas):
            repaired += 1 + (1 if modified else 0)
            index = consume_until + 1
            continue
        tool_calls.append(
            {
                "id": f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {
                    "name": resolved_tool_name,
                    "arguments": json.dumps(normalized_payload, ensure_ascii=False, separators=(",", ":")),
                },
            }
        )
        repaired += 1 + (1 if modified else 0)
        index = consume_until + 1

    return "\n".join(cleaned_lines), tool_calls, repaired


def normalize_assistant_text_tool_calls(content: str, tool_schemas: dict) -> tuple[str | None, list[dict], int]:
    if not isinstance(content, str):
        return content, [], 0

    if not tool_schemas:
        cleaned_content = content
        repaired = 0

        cleaned_content, removed = strip_all_dsml_tags(cleaned_content)
        repaired += removed
        cleaned_content, removed = strip_tool_use_error_blocks(cleaned_content)
        repaired += removed
        cleaned_content, removed = strip_validation_noise_lines(cleaned_content)
        repaired += removed
        cleaned_content, removed = sanitize_dsml_text(cleaned_content)
        repaired += removed
        cleaned_content, removed = normalize_markdown_output_text(cleaned_content)
        repaired += removed

        normalized_content = cleaned_content if cleaned_content and cleaned_content.strip() else None
        return normalized_content, [], repaired

    cleaned_content = content
    synthetic_tool_calls = []
    repaired = 0

    cleaned_content, dsml_tool_calls, _, removed, repaired_count = extract_dsml_tool_calls_from_text(
        cleaned_content,
        tool_schemas,
        finalizing=True,
    )
    if removed:
        repaired += removed
    if dsml_tool_calls:
        synthetic_tool_calls.extend(dsml_tool_calls)
        repaired += repaired_count + len(dsml_tool_calls)

    cleaned_content, plain_tool_calls, plain_repaired = extract_plain_text_tool_calls_from_text(
        cleaned_content,
        tool_schemas,
    )
    if plain_repaired:
        repaired += plain_repaired
    if plain_tool_calls:
        synthetic_tool_calls.extend(plain_tool_calls)

    cleaned_content, removed = strip_tool_use_error_blocks(cleaned_content)
    if removed:
        repaired += removed

    cleaned_content, removed = strip_validation_noise_lines(cleaned_content)
    if removed:
        repaired += removed

    cleaned_content, removed = sanitize_dsml_text(cleaned_content)
    if removed:
        repaired += removed

    cleaned_content, removed = normalize_markdown_output_text(cleaned_content)
    if removed:
        repaired += removed

    normalized_content = cleaned_content if cleaned_content and cleaned_content.strip() else None
    return normalized_content, synthetic_tool_calls, repaired


def convert_input_to_messages(input_payload) -> list[dict] | None:
    if isinstance(input_payload, str):
        return [{"role": "user", "content": input_payload}]

    if isinstance(input_payload, dict) and input_payload.get("role"):
        return [dict(input_payload)]

    if not isinstance(input_payload, list) or not input_payload:
        return None

    if all(isinstance(item, dict) and item.get("role") for item in input_payload):
        return [dict(item) for item in input_payload]

    if all(isinstance(item, dict) and item.get("type") in {"input_text", "text"} for item in input_payload):
        text = "".join(str(item.get("text", "")) for item in input_payload)
        return [{"role": "user", "content": text}]

    return None


def extract_tool_schemas(request_payload: dict | None) -> dict:
    if not isinstance(request_payload, dict):
        return {}

    schemas = {}
    for tool in request_payload.get("tools") or []:
        if not isinstance(tool, dict):
            continue

        function_meta = tool.get("function") or {}
        tool_name = function_meta.get("name") or tool.get("name")

        if tool.get("type") == "function" and isinstance(function_meta, dict) and tool_name:
            parameters = function_meta.get("parameters") or {}
        elif tool_name:
            # Anthropic / non-standard format: name + parameters/input_schema at top level
            parameters = tool.get("parameters") or tool.get("input_schema") or {}
        else:
            continue

        if not tool_name or tool_name in schemas:
            continue

        schemas[tool_name] = {
            "required": list(parameters.get("required") or []),
            "properties": list((parameters.get("properties") or {}).keys()),
            "additional_properties": parameters.get("additionalProperties"),
            "property_types": {
                key: (value or {}).get("type")
                for key, value in (parameters.get("properties") or {}).items()
                if isinstance(value, dict)
            },
        }

    return schemas


def resolve_tool_name(tool_name: str | None, tool_schemas: dict) -> str | None:
    if not tool_name:
        return tool_name
    if tool_name in tool_schemas:
        return tool_name

    requested_by_canonical = {
        canonicalize_name(schema_name): schema_name
        for schema_name in tool_schemas
    }
    tool_canonical = canonicalize_name(tool_name)
    if tool_canonical in requested_by_canonical:
        return requested_by_canonical[tool_canonical]

    for group in TOOL_NAME_ALIAS_GROUPS:
        group_canonical = {canonicalize_name(item) for item in group}
        if tool_canonical not in group_canonical:
            continue
        for schema_name in tool_schemas:
            if canonicalize_name(schema_name) in group_canonical:
                return schema_name

    for schema_name in tool_schemas:
        schema_canonical = canonicalize_name(schema_name)
        if tool_canonical and (tool_canonical in schema_canonical or schema_canonical in tool_canonical):
            return schema_name

    return tool_name


def build_auto_explanation(tool_name: str | None, payload: dict) -> str:
    summary_value = None
    for key in ("command", "query", "filePath", "path", "target_directory", "targetDirectory", "pattern"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            summary_value = value.strip()
            break

    if summary_value:
        compact = " ".join(summary_value.split())
        return f"中文执行说明：{compact[:80]}"

    return f"中文执行说明：执行工具 {tool_name or 'unknown_tool'}"


def already_has_proxy_system_prompt(messages) -> bool:
    if not isinstance(messages, list):
        return False

    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") != "system":
            continue
        content = message.get("content")
        if isinstance(content, str) and "[ProxyZHRules]" in content:
            return True

    return False


def inject_proxy_system_prompt(messages) -> tuple[list, int]:
    if not INJECT_ZH_SYSTEM_PROMPT:
        return list(messages or []), 0

    normalized_messages = list(messages or [])
    if already_has_proxy_system_prompt(normalized_messages):
        return normalized_messages, 0

    for index, message in enumerate(normalized_messages):
        if not isinstance(message, dict):
            continue
        if message.get("role") != "system":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            normalized_messages[index] = {
                **message,
                "content": PROXY_SYSTEM_PROMPT_ZH + "\n\n" + content,
            }
            return normalized_messages, 1

    normalized_messages.insert(
        0,
        {
            "role": "system",
            "content": PROXY_SYSTEM_PROMPT_ZH,
        },
    )
    return normalized_messages, 1


def apply_common_field_aliases(normalized: dict, properties: list, required: list) -> bool:
    modified = False
    schema_fields = set(properties) | set(required)

    for field_name in list(schema_fields):
        if field_name in normalized:
            continue
        canonical_field = canonicalize_name(field_name)
        for existing_key in list(normalized.keys()):
            if existing_key == field_name:
                continue
            if canonicalize_name(existing_key) != canonical_field:
                continue
            normalized[field_name] = normalized.pop(existing_key)
            modified = True
            break

    for target_field, aliases in COMMON_FIELD_ALIASES.items():
        if target_field not in schema_fields or target_field in normalized:
            continue

        for alias in aliases:
            alias_value = normalized.get(alias)
            if alias_value is None:
                continue
            if isinstance(alias_value, str) and not alias_value.strip():
                continue
            normalized[target_field] = alias_value
            if alias != target_field:
                normalized.pop(alias, None)
            modified = True
            break

    return modified


def drop_alias_keys_outside_schema(normalized: dict, properties: list, required: list) -> bool:
    schema_fields = set(properties) | set(required)
    if not schema_fields:
        return False

    canonical_fields = {
        canonicalize_name(field_name): field_name
        for field_name in schema_fields
    }
    alias_targets = {}
    for target_field, aliases in COMMON_FIELD_ALIASES.items():
        if target_field not in schema_fields:
            continue
        for alias in aliases:
            alias_targets[canonicalize_name(alias)] = target_field

    modified = False
    for existing_key in list(normalized.keys()):
        if existing_key in schema_fields:
            continue

        canonical_key = canonicalize_name(existing_key)
        target_field = alias_targets.get(canonical_key) or canonical_fields.get(canonical_key)
        if not target_field:
            continue

        if target_field not in normalized:
            normalized[target_field] = normalized[existing_key]
        normalized.pop(existing_key, None)
        modified = True

    return modified


def drop_unexpected_keys_by_schema(normalized: dict, tool_name: str | None, tool_schemas: dict) -> bool:
    schema = tool_schemas.get(tool_name or "", {})
    schema_fields = set(schema.get("properties") or []) | set(schema.get("required") or [])
    if not schema_fields:
        return False

    additional_properties = schema.get("additional_properties")
    should_strip_unknown = additional_properties is False or bool(schema_fields)
    if not should_strip_unknown:
        return False

    modified = False
    for existing_key in list(normalized.keys()):
        if existing_key in schema_fields:
            continue
        if field_is_run_in_background(existing_key):
            continue
        normalized.pop(existing_key, None)
        modified = True

    return modified


def unwrap_nested_arguments_container(payload, tool_name: str | None, tool_schemas: dict) -> tuple[object, bool]:
    if not isinstance(payload, dict):
        return payload, False

    container_keys = ("arguments", "input", "parameters", "kwargs")
    passthrough_items = {
        key: value
        for key, value in payload.items()
        if key not in container_keys
    }
    schema = tool_schemas.get(tool_name or "", {})
    schema_fields = set(schema.get("properties") or []) | set(schema.get("required") or [])

    for container_key in container_keys:
        if container_key not in payload:
            continue

        nested_value = payload.get(container_key)
        if isinstance(nested_value, str):
            stripped = nested_value.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    nested_value = json.loads(stripped)
                except json.JSONDecodeError:
                    pass

        if isinstance(nested_value, dict):
            merged = dict(nested_value)
            for key, value in passthrough_items.items():
                if key not in merged:
                    merged[key] = value
            return merged, True

        if isinstance(nested_value, list):
            return nested_value, True

        if nested_value == {} and not passthrough_items:
            return {}, True

        if nested_value is not None and len(schema_fields) == 1 and not passthrough_items:
            return nested_value, True

    return payload, False


def coerce_value_by_declared_type(value, declared_type: str | None):
    if declared_type is None:
        return value, False

    if declared_type == "string":
        if isinstance(value, str):
            return value, False
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False), True
        return str(value), True

    if declared_type == "boolean":
        if isinstance(value, bool):
            return value, False
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value in {0, 1}:
                return bool(value), True
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "y", "on", "enabled", "enable", "parallel", "async", "background", "并行", "后台", "是", "开"}:
                return True, True
            if lowered in {"false", "0", "no", "n", "off", "disabled", "disable", "sync", "foreground", "同步", "否", "关"}:
                return False, True
        return value, False

    if declared_type in {"integer", "number"}:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value, False
        if isinstance(value, str):
            stripped = value.strip()
            try:
                return (int(stripped) if declared_type == "integer" else float(stripped)), True
            except ValueError:
                return value, False
        return value, False

    if declared_type in {"object", "array"}:
        expected_python_type = dict if declared_type == "object" else list
        if isinstance(value, expected_python_type):
            return value, False
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    return value, False
                if isinstance(parsed, expected_python_type):
                    return parsed, True
        return value, False

    return value, False


def extract_meaningful_string_from_mapping(value_map: dict, preferred_field: str | None) -> str | None:
    if preferred_field:
        for candidate in (preferred_field, *COMMON_FIELD_ALIASES.get(preferred_field, ())):
            candidate_value = value_map.get(candidate)
            if isinstance(candidate_value, str) and candidate_value.strip():
                return candidate_value

        preferred_canonical = canonicalize_name(preferred_field)
        for candidate_key, candidate_value in value_map.items():
            if canonicalize_name(candidate_key) == preferred_canonical and isinstance(candidate_value, str) and candidate_value.strip():
                return candidate_value

    string_values = [item for item in value_map.values() if isinstance(item, str) and item.strip()]
    if len(string_values) == 1:
        return string_values[0]

    return None


def normalize_string_like_value(field_name: str, value):
    if not isinstance(value, str):
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False), True
        return str(value), True

    stripped = value.strip()
    if stripped in {"{}", "[]", "null", "None", '""', "''"}:
        return "", True

    if stripped.startswith("{") or stripped.startswith("[") or (
        len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}
    ):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return value, False

        if isinstance(parsed, str):
            reparsed_value, changed = normalize_string_like_value(field_name, parsed)
            return reparsed_value, True or changed

        if isinstance(parsed, dict):
            meaningful = extract_meaningful_string_from_mapping(parsed, field_name)
            if meaningful is not None:
                return meaningful, True
            if not parsed:
                return "", True
            return json.dumps(parsed, ensure_ascii=False), True

        if isinstance(parsed, list):
            if not parsed:
                return "", True
            return json.dumps(parsed, ensure_ascii=False), True

    return value, False


def normalize_array_like_value(field_name: str, value):
    if isinstance(value, list):
        return value, False

    if isinstance(value, dict):
        direct_value = value.get(field_name)
        if isinstance(direct_value, list):
            return direct_value, True
        return [], True

    if isinstance(value, str):
        stripped = value.strip()
        if stripped in {"", "{}", "[]", "null", "None"}:
            return [], True
        if stripped.startswith("{") or stripped.startswith("[") or (
            len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}
        ):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return value, False

            if isinstance(parsed, str):
                reparsed_value, changed = normalize_array_like_value(field_name, parsed)
                return reparsed_value, True or changed

            if isinstance(parsed, list):
                return parsed, True

            if isinstance(parsed, dict):
                nested_value = parsed.get(field_name)
                if isinstance(nested_value, list):
                    return nested_value, True
                return [], True

    return value, False


def normalize_object_like_value(field_name: str, value):
    if isinstance(value, dict):
        return value, False

    if isinstance(value, str):
        stripped = value.strip()
        if stripped in {"", "{}", "null", "None"}:
            return {}, True
        if stripped.startswith("{") or stripped.startswith("[") or (
            len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}
        ):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return value, False

            if isinstance(parsed, str):
                reparsed_value, changed = normalize_object_like_value(field_name, parsed)
                return reparsed_value, True or changed

            if isinstance(parsed, dict):
                return parsed, True

            if isinstance(parsed, list):
                if not parsed:
                    return {}, True
                return {"items": parsed}, True

    return value, False


def field_is_run_in_background(field_name: str | None) -> bool:
    return canonicalize_name(field_name) == RUN_IN_BACKGROUND_FIELD_CANONICAL


def schema_supports_run_in_background(schema: dict) -> str | None:
    schema_fields = list(schema.get("required") or []) + list(schema.get("properties") or [])
    for field_name in schema_fields:
        if field_is_run_in_background(field_name):
            return field_name
    return None


def payload_text_for_background_inference(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    text_parts = []
    for key, value in payload.items():
        if field_is_run_in_background(key):
            continue
        if isinstance(value, str):
            text_parts.append(value)
        elif isinstance(value, (dict, list)):
            text_parts.append(json.dumps(value, ensure_ascii=False))
    return " ".join(text_parts).lower()


def infer_run_in_background_value(tool_name: str | None, payload: dict) -> bool:
    searchable = payload_text_for_background_inference(payload)
    if any(marker in searchable for marker in RUN_IN_BACKGROUND_FALSE_MARKERS):
        return False
    if any(marker in searchable for marker in RUN_IN_BACKGROUND_TRUE_MARKERS):
        return True

    tool_key = canonicalize_name(tool_name)
    if any(canonicalize_name(marker) in tool_key for marker in TASK_LIKE_TOOL_NAME_MARKERS):
        if any(marker in searchable for marker in ("parallel", "concurrent", "background", "explore", "research", "并行", "探索", "调研")):
            return True
    return False


def is_task_control_tool_name(tool_name: str | None) -> bool:
    tool_key = canonicalize_name(tool_name)
    if not tool_key:
        return False
    return any(marker == tool_key or marker in tool_key for marker in TASK_CONTROL_TOOL_NAME_MARKERS)


def should_infer_run_in_background_without_schema(tool_name: str | None, tool_schemas: dict) -> bool:
    resolved = resolve_tool_name(tool_name, tool_schemas) or tool_name or ""
    if is_task_control_tool_name(resolved):
        return False
    resolved_key = canonicalize_name(resolved)
    if not resolved_key:
        return False
    return any(
        canonicalize_name(marker) == resolved_key
        for marker in TASK_LIKE_TOOL_NAME_MARKERS
    )


def ensure_run_in_background_argument(tool_name: str | None, normalized: dict, tool_schemas: dict) -> bool:
    schema = tool_schemas.get(tool_name or "", {})
    field_name = schema_supports_run_in_background(schema)

    if not field_name:
        if should_infer_run_in_background_without_schema(tool_name, tool_schemas):
            for existing_key in list(normalized):
                if field_is_run_in_background(existing_key):
                    if existing_key != "run_in_background":
                        normalized["run_in_background"] = normalized.pop(existing_key)
                        return True
                    return False
            normalized["run_in_background"] = infer_run_in_background_value(tool_name, normalized)
            return True
        return False

    for existing_key in list(normalized):
        if field_is_run_in_background(existing_key):
            if existing_key != field_name:
                normalized[field_name] = normalized.pop(existing_key)
                return True
            return False

    normalized[field_name] = infer_run_in_background_value(tool_name, normalized)
    return True


def coerce_payload_values_by_schema(normalized: dict, tool_name: str | None, tool_schemas: dict) -> bool:
    schema = tool_schemas.get(tool_name or "", {})
    property_types = dict(schema.get("property_types") or {})
    modified = False

    for field_name, field_type in property_types.items():
        if field_name not in normalized:
            continue
        current_value = normalized.get(field_name)
        if field_type == "string":
            coerced_value, changed = normalize_string_like_value(field_name, current_value)
        elif field_type == "array":
            coerced_value, changed = normalize_array_like_value(field_name, current_value)
        elif field_type == "object":
            coerced_value, changed = normalize_object_like_value(field_name, current_value)
        else:
            coerced_value, changed = coerce_value_by_declared_type(current_value, field_type)
        if changed:
            normalized[field_name] = coerced_value
            modified = True

    return modified


def fill_missing_required_fields(tool_name: str | None, normalized: dict, tool_schemas: dict) -> bool:
    schema = tool_schemas.get(tool_name or "", {})
    required = list(schema.get("required") or [])
    property_types = dict(schema.get("property_types") or {})
    modified = ensure_run_in_background_argument(tool_name, normalized, tool_schemas)

    for field_name in required:
        if field_name in normalized:
            continue

        if field_is_run_in_background(field_name):
            normalized[field_name] = infer_run_in_background_value(tool_name, normalized)
            modified = True
            continue

        if field_name in {"explanation", "justification"}:
            normalized[field_name] = build_auto_explanation(tool_name, normalized)
            modified = True
            continue

        field_type = property_types.get(field_name)
        if field_type == "boolean":
            normalized[field_name] = False
            modified = True
            continue
        if field_type in {"integer", "number"}:
            normalized[field_name] = 0
            modified = True
            continue
        if field_type == "array":
            normalized[field_name] = []
            modified = True
            continue
        if field_type == "object":
            normalized[field_name] = {}
            modified = True
            continue

        if field_name in {"command", "pattern", "query", "filePath", "path", "target_directory", "targetDirectory"}:
            normalized[field_name] = ""
            modified = True
            continue

        normalized[field_name] = ""
        modified = True

    return modified


def parse_tool_arguments_object(arguments_value):
    if isinstance(arguments_value, dict):
        return arguments_value

    if isinstance(arguments_value, list):
        return arguments_value

    if isinstance(arguments_value, str):
        stripped = arguments_value.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return arguments_value

    return None


def get_field_name_canonicals(field_name: str) -> set[str]:
    canonicals = {canonicalize_name(field_name)}
    for alias in COMMON_FIELD_ALIASES.get(field_name, ()):
        canonicals.add(canonicalize_name(alias))
    return {item for item in canonicals if item}


def extract_tool_field_value(payload_object: dict, field_name: str):
    if not isinstance(payload_object, dict):
        return None

    field_canonicals = get_field_name_canonicals(field_name)
    for key, value in payload_object.items():
        if canonicalize_name(key) in field_canonicals:
            return value

    return None


def is_search_like_tool(tool_name: str | None, tool_schemas: dict) -> bool:
    resolved_name = resolve_tool_name(tool_name, tool_schemas) or tool_name or ""
    schema = tool_schemas.get(resolved_name, {})
    schema_fields = {
        canonicalize_name(field_name)
        for field_name in list(schema.get("properties") or []) + list(schema.get("required") or [])
    }
    tool_canonical = canonicalize_name(resolved_name)
    return bool(schema_fields & SEARCH_INPUT_FIELD_CANONICALS) or any(
        marker in tool_canonical
        for marker in ("search", "grep", "glob", "find")
    )


def tool_requires_arguments_before_stream_header(tool_name: str | None, tool_schemas: dict) -> bool:
    resolved_name = resolve_tool_name(tool_name, tool_schemas) or tool_name or ""
    if is_bash_like_tool_name(resolved_name):
        return True

    schema = tool_schemas.get(resolved_name, {})
    required = list(schema.get("required") or [])
    if not required:
        return False

    for field_name in required:
        if field_is_run_in_background(field_name):
            continue
        if canonicalize_name(field_name) in EMPTY_TOOL_META_FIELD_CANONICALS:
            continue
        return True

    return False


def infer_tool_name_from_payload(tool_name: str | None, payload, tool_schemas: dict) -> str | None:
    resolved_name = resolve_tool_name(tool_name, tool_schemas) or (tool_name.strip() if isinstance(tool_name, str) else "")
    if resolved_name:
        return resolved_name

    payload_object = parse_tool_arguments_object(payload)
    if isinstance(payload_object, str):
        if not payload_object.strip():
            return None
        bash_candidates = []
        for schema_name, schema in tool_schemas.items():
            schema_fields = list(dict.fromkeys(list(schema.get("required") or []) + list(schema.get("properties") or [])))
            if not schema_fields:
                continue
            accepted = set()
            for field_name in schema_fields:
                accepted.update(get_field_name_canonicals(field_name))
            if "command" in accepted:
                bash_candidates.append(schema_name)
        return bash_candidates[0] if len(bash_candidates) == 1 else None

    if not isinstance(payload_object, dict) or not payload_object:
        return None

    meaningful_items = [
        (key, value)
        for key, value in payload_object.items()
        if tool_payload_has_meaningful_value(value)
    ]
    if not meaningful_items:
        return None

    ranked_candidates = []
    for schema_name, schema in tool_schemas.items():
        required = list(schema.get("required") or [])
        schema_fields = list(dict.fromkeys(required + list(schema.get("properties") or [])))
        if not schema_fields:
            continue

        matched_fields = set()
        matched_required_fields = set()
        unmatched_field = False

        for key, value in meaningful_items:
            key_canonical = canonicalize_name(key)
            matched_field_name = None
            for field_name in schema_fields:
                if key_canonical in get_field_name_canonicals(field_name):
                    matched_field_name = field_name
                    break
            if not matched_field_name:
                unmatched_field = True
                break
            matched_fields.add(matched_field_name)
            if matched_field_name in required:
                matched_required_fields.add(matched_field_name)

        if unmatched_field or not matched_fields:
            continue

        score = (
            len(matched_required_fields),
            len(matched_fields),
            -max(len(required) - len(matched_required_fields), 0),
            -len(schema_fields),
        )
        ranked_candidates.append((score, schema_name))

    if not ranked_candidates:
        return None

    ranked_candidates.sort(reverse=True)
    best_score = ranked_candidates[0][0]
    best_names = [schema_name for score, schema_name in ranked_candidates if score == best_score]
    return best_names[0] if len(best_names) == 1 else None


def required_field_has_meaningful_value(field_type: str | None, value) -> bool:
    if field_type == "boolean":
        return value is not None
    if field_type in {"integer", "number"}:
        return value is not None
    if field_type == "array":
        return isinstance(value, list) and any(tool_payload_has_meaningful_value(item) for item in value)
    if field_type == "object":
        return isinstance(value, dict) and any(tool_payload_has_meaningful_value(item) for item in value.values())
    return tool_payload_has_meaningful_value(value)


def tool_call_lacks_required_input_signal(tool_name: str | None, payload, tool_schemas: dict) -> bool:
    resolved_name = resolve_tool_name(tool_name, tool_schemas) or tool_name or ""
    schema = tool_schemas.get(resolved_name, {})
    required = list(schema.get("required") or [])
    property_types = dict(schema.get("property_types") or {})
    payload_object = parse_tool_arguments_object(payload)

    if is_bash_like_tool_name(resolved_name):
        if isinstance(payload_object, str):
            return not tool_payload_has_meaningful_value(payload_object)
        if isinstance(payload_object, dict):
            command_value = extract_tool_field_value(payload_object, "command")
            return not required_field_has_meaningful_value("string", command_value)
        return True

    if isinstance(payload_object, str):
        return not tool_payload_has_meaningful_value(payload_object)
    if not isinstance(payload_object, dict):
        return not tool_payload_has_meaningful_value(payload)

    checked_any_required = False
    for field_name in required:
        if canonicalize_name(field_name) in EMPTY_TOOL_META_FIELD_CANONICALS:
            continue
        checked_any_required = True
        field_value = extract_tool_field_value(payload_object, field_name)
        if not required_field_has_meaningful_value(property_types.get(field_name), field_value):
            return True

    return False if checked_any_required else False


def tool_call_has_empty_search_signal(tool_name: str | None, payload, tool_schemas: dict) -> bool:
    if not is_search_like_tool(tool_name, tool_schemas):
        return False

    payload_object = parse_tool_arguments_object(payload)
    if not isinstance(payload_object, dict):
        return False

    saw_search_field = False
    has_search_value = False
    for key, value in payload_object.items():
        canonical_key = canonicalize_name(key)
        if canonical_key not in SEARCH_INPUT_FIELD_CANONICALS:
            continue
        saw_search_field = True
        if tool_payload_has_meaningful_value(value):
            has_search_value = True
            break

    return saw_search_field and not has_search_value


def should_suppress_tool_call(tool_name: str | None, payload, tool_schemas: dict) -> bool:
    resolved_name = infer_tool_name_from_payload(tool_name, payload, tool_schemas)
    if not resolved_name:
        return True
    if should_suppress_empty_tool_call(resolved_name, payload, tool_schemas):
        return True
    if tool_call_lacks_required_input_signal(resolved_name, payload, tool_schemas):
        return True
    if tool_call_has_empty_search_signal(resolved_name, payload, tool_schemas):
        return True
    return False


def tool_payload_has_meaningful_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip() not in {"", "{}", "[]", "null", "None", '""', "''"}
    if isinstance(value, list):
        return any(tool_payload_has_meaningful_value(item) for item in value)
    if isinstance(value, dict):
        return any(tool_payload_has_meaningful_value(item) for item in value.values())
    return True


def clean_preview_fragment(text: str | None) -> str:
    if not isinstance(text, str) or not text:
        return ""
    cleaned = text
    cleaned = ENGLISH_TOOL_LEADIN_PATTERN.sub("", cleaned)
    cleaned, _ = strip_tool_use_error_blocks(cleaned)
    cleaned, _ = strip_validation_noise_lines(cleaned)
    cleaned, _ = sanitize_dsml_text(cleaned)
    cleaned = cleaned.replace("\r", " ").replace("\n", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" |")
    if not cleaned:
        return ""
    if DSML_ORPHAN_FRAGMENT_LINE_PATTERN.match(cleaned):
        return ""
    return cleaned


def merge_preview_text_fragments(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if re.search(r"[A-Za-z0-9]$", left) and re.match(r"^[A-Za-z0-9]", right):
        return f"{left} {right}"
    return f"{left}{right}"


def append_preview_text(preview_parts: list[str], fragment: str | None) -> None:
    cleaned = clean_preview_fragment(fragment)
    if not cleaned:
        return
    if preview_parts and not preview_parts[-1].startswith("工具:"):
        preview_parts[-1] = merge_preview_text_fragments(preview_parts[-1], cleaned)
        return
    preview_parts.append(cleaned)


def compact_preview_payload_value(value) -> str:
    if isinstance(value, str):
        return clean_preview_fragment(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        compact_items = [compact_preview_payload_value(item) for item in value[:3]]
        compact_items = [item for item in compact_items if item]
        return ", ".join(compact_items)
    if isinstance(value, dict):
        for field_name in PREVIEW_TOOL_ARGUMENT_PRIORITY:
            nested_value = extract_tool_field_value(value, field_name)
            if tool_payload_has_meaningful_value(nested_value):
                compact = compact_preview_payload_value(nested_value)
                if compact:
                    return compact
        serialized = clean_preview_fragment(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        return serialized[:140]
    return ""


def build_preview_tool_summary(tool_name: str | None, payload, tool_schemas: dict) -> str:
    resolved_name = infer_tool_name_from_payload(tool_name, payload, tool_schemas)
    if not resolved_name:
        return ""

    normalized_payload, _ = normalize_tool_arguments_payload(resolved_name, payload, tool_schemas)
    if should_suppress_tool_call(resolved_name, normalized_payload, tool_schemas):
        return ""

    compact_payload = compact_preview_payload_value(parse_tool_arguments_object(normalized_payload) or normalized_payload)
    summary = f"工具:{resolved_name}"
    if compact_payload:
        summary = f"{summary} {compact_payload[:140]}"
    return summary.strip()


def append_preview_tool(preview_parts: list[str], tool_name: str | None, payload, tool_schemas: dict) -> None:
    summary = build_preview_tool_summary(tool_name, payload, tool_schemas)
    if not summary:
        return
    preview_parts.append(summary)


def build_preview_summary(preview_parts: list[str]) -> str | None:
    if not preview_parts:
        return None
    summary = " | ".join(part for part in preview_parts if part)
    summary = clean_preview_fragment(summary)
    if not summary:
        return None
    return summary[:280]


def is_edit_like_tool(tool_name: str | None, tool_schemas: dict) -> bool:
    resolved_name = resolve_tool_name(tool_name, tool_schemas) or tool_name or ""
    tool_canonical = canonicalize_name(resolved_name)
    edit_alias_canonicals = {canonicalize_name(item) for item in TOOL_NAME_ALIAS_GROUPS[3]}
    if tool_canonical in edit_alias_canonicals:
        return True

    schema = tool_schemas.get(resolved_name, {})
    schema_fields = {
        canonicalize_name(field_name)
        for field_name in list(schema.get("properties") or []) + list(schema.get("required") or [])
    }
    has_path_field = bool(schema_fields & EDIT_PATH_FIELD_CANONICALS)
    has_old_field = bool(schema_fields & EDIT_OLD_FIELD_CANONICALS)
    has_new_field = bool(schema_fields & EDIT_NEW_FIELD_CANONICALS)
    return has_path_field and (has_old_field or has_new_field)


def should_suppress_empty_tool_call(tool_name: str | None, payload, tool_schemas: dict) -> bool:
    if not is_edit_like_tool(tool_name, tool_schemas):
        return False

    if isinstance(payload, str) and is_effectively_empty_tool_payload(payload):
        return True

    payload_object = parse_tool_arguments_object(payload)
    if not isinstance(payload_object, dict):
        return not tool_payload_has_meaningful_value(payload)

    core_canonicals = (
        EDIT_PATH_FIELD_CANONICALS
        | EDIT_OLD_FIELD_CANONICALS
        | EDIT_NEW_FIELD_CANONICALS
    )
    recognized_core_present = False
    core_has_meaningful_value = False
    other_has_meaningful_value = False

    for key, value in payload_object.items():
        canonical_key = canonicalize_name(key)
        if canonical_key in core_canonicals:
            recognized_core_present = True
            if tool_payload_has_meaningful_value(value):
                core_has_meaningful_value = True
            continue
        if canonical_key in EMPTY_TOOL_META_FIELD_CANONICALS:
            continue
        if tool_payload_has_meaningful_value(value):
            other_has_meaningful_value = True

    if recognized_core_present:
        return not core_has_meaningful_value and not other_has_meaningful_value

    return not any(
        tool_payload_has_meaningful_value(value)
        for key, value in payload_object.items()
        if canonicalize_name(key) not in EMPTY_TOOL_META_FIELD_CANONICALS
    )


def normalize_tool_arguments_payload(tool_name: str | None, payload, tool_schemas: dict) -> tuple[object, bool]:
    modified = False
    resolved_name = resolve_tool_name(tool_name, tool_schemas) or tool_name
    schema = tool_schemas.get(resolved_name or "", {})
    required = list(schema.get("required") or [])
    properties = list(schema.get("properties") or [])
    bash_like = is_bash_like_tool_name(resolved_name)
    search_like = is_search_like_tool(resolved_name, tool_schemas)

    payload, unwrapped = unwrap_nested_arguments_container(payload, resolved_name, tool_schemas)
    modified = unwrapped or modified

    if isinstance(payload, str):
        stripped = payload.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                reparsed = json.loads(stripped)
            except json.JSONDecodeError:
                reparsed = None
            if reparsed is not None:
                normalized_payload, _ = normalize_tool_arguments_payload(resolved_name, reparsed, tool_schemas)
                return normalized_payload, True
        if bash_like:
            command_value, command_modified = normalize_bash_command_text(payload)
            return {"command": command_value}, True or command_modified
        if len(required) == 1:
            return {required[0]: payload}, True
        return payload, False

    if not isinstance(payload, dict):
        return payload, False

    normalized = dict(payload)
    modified = apply_common_field_aliases(normalized, properties, required) or modified
    modified = drop_alias_keys_outside_schema(normalized, properties, required) or modified
    modified = drop_unexpected_keys_by_schema(normalized, resolved_name, tool_schemas) or modified
    target_field = None
    if bash_like or "command" in required or "command" in properties:
        target_field = "command"
    elif len(required) == 1:
        target_field = required[0]

    if target_field and target_field not in normalized:
        for alias in COMMAND_ALIASES:
            alias_value = normalized.get(alias)
            if isinstance(alias_value, str) and alias_value.strip():
                normalized[target_field] = alias_value
                if alias != target_field:
                    normalized.pop(alias, None)
                modified = True
                break

    if (
        target_field
        and target_field not in normalized
        and (len(required) == 1 or bash_like)
        and not (search_like and canonicalize_name(target_field) in SEARCH_INPUT_FIELD_CANONICALS)
    ):
        string_entries = [
            (key, value)
            for key, value in normalized.items()
            if isinstance(value, str)
            and value.strip()
            and canonicalize_name(key) not in EMPTY_TOOL_META_FIELD_CANONICALS
        ]
        if len(string_entries) == 1:
            only_key, only_value = string_entries[0]
            normalized[target_field] = only_value
            if only_key != target_field:
                normalized.pop(only_key, None)
            modified = True

    if bash_like and isinstance(normalized.get("command"), str):
        normalized["command"], command_modified = normalize_bash_command_text(normalized.get("command"))
        modified = command_modified or modified

    modified = coerce_payload_values_by_schema(normalized, resolved_name, tool_schemas) or modified
    modified = fill_missing_required_fields(resolved_name, normalized, tool_schemas) or modified
    modified = drop_alias_keys_outside_schema(normalized, properties, required) or modified
    modified = drop_unexpected_keys_by_schema(normalized, resolved_name, tool_schemas) or modified
    modified = coerce_payload_values_by_schema(normalized, resolved_name, tool_schemas) or modified

    resolved_check = resolve_tool_name(resolved_name or tool_name, tool_schemas) or resolved_name or tool_name or ""
    if any(
        canonicalize_name(marker) in canonicalize_name(resolved_check)
        for marker in TASK_LIKE_TOOL_NAME_MARKERS
    ):
        rb_present = any(field_is_run_in_background(k) for k in normalized)
        logging.getLogger("local_proxy").info(
            "[DIAG-FINAL] tool=%s rb_present=%s rb_val=%s modified=%s args=%s",
            resolved_check,
            rb_present,
            normalized.get("run_in_background"),
            modified,
            json.dumps(normalized, ensure_ascii=False)[:300],
        )

    return normalized, modified


def normalize_bash_command_text(command_text: str | None) -> tuple[str, bool]:
    if not isinstance(command_text, str):
        return str(command_text or ""), False
    command = command_text.strip()
    if not command:
        return command_text, False

    modified = False

    def replace_cd(match):
        nonlocal modified
        prefix, cd_token, drive, path_part = match.groups()
        normalized_tail = path_part.replace("\\", "/").strip("/")
        replacement = f'{prefix}{cd_token} "{drive.lower()}:/{normalized_tail}"'
        modified = True
        return replacement

    command = WINDOWS_DRIVE_CD_PATTERN.sub(replace_cd, command)
    return command, modified


def normalize_tool_arguments_text(
    tool_name: str | None,
    arguments_text: str,
    tool_schemas: dict,
    *,
    final_only: bool,
) -> tuple[str | None, bool, bool]:
    raw = arguments_text.strip()
    if raw == "":
        return None, False, False

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        if final_only:
            if raw.startswith("{") or raw.startswith("["):
                return None, False, False
            normalized_payload, modified = normalize_tool_arguments_payload(tool_name, raw, tool_schemas)
            if isinstance(normalized_payload, str):
                return json.dumps(normalized_payload, ensure_ascii=False), modified, True
            return json.dumps(normalized_payload, ensure_ascii=False, separators=(",", ":")), modified, True
        return None, False, False

    normalized_payload, modified = normalize_tool_arguments_payload(tool_name, parsed, tool_schemas)
    return json.dumps(normalized_payload, ensure_ascii=False, separators=(",", ":")), modified, True


def normalize_tool_call_list(tool_calls, tool_schemas: dict) -> tuple[list, int]:
    if not isinstance(tool_calls, list):
        return tool_calls, 0

    normalized_calls = []
    repaired = 0

    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            normalized_calls.append(tool_call)
            continue

        normalized_call = dict(tool_call)
        original_function = normalized_call.get("function")
        function_data = original_function
        changed = False

        if not isinstance(function_data, dict):
            function_data = {}
            changed = True
        else:
            function_data = dict(function_data)

        raw_name = (
            function_data.get("name")
            or (original_function if isinstance(original_function, str) else "")
            or normalized_call.get("name")
            or normalized_call.get("tool_name")
            or ""
        )
        resolved_name = resolve_tool_name(raw_name, tool_schemas) or raw_name
        if resolved_name and function_data.get("name") != resolved_name:
            function_data["name"] = resolved_name
            changed = True

        raw_arguments = function_data.get("arguments")
        if raw_arguments is None:
            if "arguments" in normalized_call:
                raw_arguments = normalized_call.get("arguments")
                changed = True
            elif "input" in normalized_call:
                raw_arguments = normalized_call.get("input")
                changed = True
        if raw_arguments is None and "input" in function_data:
            raw_arguments = function_data.get("input")
            changed = True

        inferred_name = infer_tool_name_from_payload(resolved_name, raw_arguments, tool_schemas)
        if inferred_name and inferred_name != resolved_name:
            resolved_name = inferred_name
            function_data["name"] = resolved_name
            changed = True

        if raw_arguments is None and resolved_name:
            normalized_payload, modified = normalize_tool_arguments_payload(
                resolved_name,
                {},
                tool_schemas,
            )
            normalized_text = json.dumps(
                normalized_payload,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            function_data["arguments"] = normalized_text
            changed = True
            if modified:
                changed = True
        elif raw_arguments is not None:
            if isinstance(raw_arguments, str):
                normalized_text, modified, complete = normalize_tool_arguments_text(
                    resolved_name,
                    raw_arguments,
                    tool_schemas,
                    final_only=True,
                )
                if complete and normalized_text is not None:
                    if function_data.get("arguments") != normalized_text:
                        function_data["arguments"] = normalized_text
                        changed = True
                    if modified:
                        changed = True
            else:
                normalized_payload, modified = normalize_tool_arguments_payload(
                    resolved_name,
                    raw_arguments,
                    tool_schemas,
                )
                normalized_text = json.dumps(
                    normalized_payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                if function_data.get("arguments") != normalized_text:
                    function_data["arguments"] = normalized_text
                    changed = True
                if modified:
                    changed = True

        normalized_arguments = function_data.get("arguments")
        inferred_name = infer_tool_name_from_payload(resolved_name, normalized_arguments, tool_schemas)
        if inferred_name and inferred_name != resolved_name:
            resolved_name = inferred_name
            function_data["name"] = resolved_name
            changed = True

        if should_suppress_tool_call(resolved_name, normalized_arguments, tool_schemas):
            repaired += 1 + (1 if changed else 0)
            continue

        if normalized_call.get("type") != "function" and (
            function_data.get("name") or function_data.get("arguments") is not None
        ):
            normalized_call["type"] = "function"
            changed = True

        for redundant_key in ("name", "arguments", "input", "tool_name"):
            if redundant_key in normalized_call:
                normalized_call.pop(redundant_key, None)
                changed = True
        if "input" in function_data:
            function_data.pop("input", None)
            changed = True

        normalized_call["function"] = function_data
        normalized_calls.append(normalized_call)
        if changed:
            repaired += 1

    return normalized_calls, repaired


def normalize_chat_completion_tool_calls(response_body: dict, tool_schemas: dict) -> int:
    repaired = 0
    for choice in response_body.get("choices") or []:
        message = choice.get("message") or {}
        normalized_tool_calls, repaired_count = normalize_tool_call_list(
            message.get("tool_calls") or [],
            tool_schemas,
        )
        if repaired_count:
            message["tool_calls"] = normalized_tool_calls
            repaired += repaired_count

    return repaired


def normalize_chat_completion_finish_reasons(response_body: dict) -> int:
    normalized = 0
    for choice in response_body.get("choices") or []:
        message = choice.get("message") or {}
        finish_reason = choice.get("finish_reason")
        finish_reason_text = str(finish_reason or "").strip()
        has_tool_calls = bool(message.get("tool_calls"))
        content_value = message.get("content")
        has_text_content = False
        if isinstance(content_value, str):
            has_text_content = bool(content_value.strip())
        elif isinstance(content_value, list):
            has_text_content = any(
                isinstance(item, dict) and str(item.get("text") or "").strip()
                for item in content_value
            )
        if has_tool_calls and finish_reason in {None, "stop"}:
            choice["finish_reason"] = "tool_calls"
            normalized += 1
            continue
        if not has_tool_calls and finish_reason == "tool_calls":
            choice["finish_reason"] = "stop"
            normalized += 1
            continue
        if finish_reason_text and any(marker in finish_reason_text.lower() for marker in ("error", "failure", "failed", "exception")):
            choice["finish_reason"] = "stop"
            normalized += 1

    return normalized


def normalize_chat_completion_text_tool_calls(response_body: dict, tool_schemas: dict) -> int:
    repaired = 0
    for choice in response_body.get("choices") or []:
        message = choice.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            continue

        normalized_content, synthetic_tool_calls, repaired_count = normalize_assistant_text_tool_calls(
            content,
            tool_schemas,
        )
        if normalized_content != content:
            if normalized_content is None and message.get("reasoning"):
                message["content"] = ""
            else:
                message["content"] = normalized_content
        if synthetic_tool_calls:
            existing_tool_calls = list(message.get("tool_calls") or [])
            existing_tool_calls.extend(synthetic_tool_calls)
            message["tool_calls"] = existing_tool_calls
        repaired += repaired_count

    return repaired


def normalize_openai_tool_definition(tool) -> tuple[object, bool]:
    if not isinstance(tool, dict):
        return tool, False

    changed = False
    normalized_tool = dict(tool)
    function_meta = normalized_tool.get("function")

    if isinstance(function_meta, dict):
        normalized_function = dict(function_meta)
        if "parameters" not in normalized_function and normalized_function.get("input_schema") is not None:
            normalized_function["parameters"] = normalized_function.pop("input_schema")
            changed = True
        if normalized_tool.get("type") != "function":
            normalized_tool["type"] = "function"
            changed = True
        normalized_tool["function"] = normalized_function
        return normalized_tool, changed

    if normalized_tool.get("name"):
        parameters = (
            normalized_tool.get("parameters")
            or normalized_tool.get("input_schema")
            or {"type": "object", "properties": {}}
        )
        return (
            {
                "type": "function",
                "function": {
                    "name": normalized_tool.get("name"),
                    "description": normalized_tool.get("description", ""),
                    "parameters": parameters,
                },
            },
            True,
        )

    return tool, False


def normalize_openai_tool_choice(tool_choice):
    if tool_choice is None:
        return None, False

    if isinstance(tool_choice, str):
        if tool_choice == "any":
            return "required", True
        return tool_choice, False

    if not isinstance(tool_choice, dict):
        return tool_choice, False

    choice_type = tool_choice.get("type")
    if choice_type == "any":
        return "required", True
    if choice_type == "tool" and tool_choice.get("name"):
        return {
            "type": "function",
            "function": {
                "name": tool_choice["name"],
            },
        }, True
    if tool_choice.get("name") and not tool_choice.get("function"):
        return {
            "type": "function",
            "function": {
                "name": tool_choice["name"],
            },
        }, True
    if choice_type == "function" and isinstance(tool_choice.get("function"), str):
        return {
            "type": "function",
            "function": {
                "name": tool_choice["function"],
            },
        }, True

    return tool_choice, False


def normalize_openai_messages(messages, tool_schemas: dict | None = None) -> tuple[object, int]:
    if not isinstance(messages, list):
        return messages, 0

    repairs = 0
    normalized_messages = []
    tool_schemas = tool_schemas or {}

    for message in messages:
        if not isinstance(message, dict):
            normalized_messages.append(message)
            continue

        normalized_message = dict(message)
        role = normalized_message.get("role")
        if role == "developer":
            normalized_message["role"] = "system"
            repairs += 1

        content = normalized_message.get("content")
        normalized_content, synthetic_tool_calls, changed = extract_openai_text_from_blocks(content)
        if changed:
            normalized_message["content"] = normalized_content
            if synthetic_tool_calls and normalized_message.get("role") == "assistant":
                merged_tool_calls = list(normalized_message.get("tool_calls") or [])
                merged_tool_calls.extend(synthetic_tool_calls)
                normalized_message["tool_calls"] = merged_tool_calls
            repairs += 1

        if normalized_message.get("role") == "assistant" and isinstance(normalized_message.get("content"), str):
            normalized_content, synthetic_tool_calls, repaired_count = normalize_assistant_text_tool_calls(
                normalized_message.get("content"),
                tool_schemas,
            )
            if normalized_content != normalized_message.get("content"):
                normalized_message["content"] = normalized_content
            if synthetic_tool_calls:
                merged_tool_calls = list(normalized_message.get("tool_calls") or [])
                merged_tool_calls.extend(synthetic_tool_calls)
                normalized_message["tool_calls"] = merged_tool_calls
            repairs += repaired_count

        if normalized_message.get("role") == "assistant" and normalized_message.get("tool_calls"):
            normalized_tool_calls, repaired_count = normalize_tool_call_list(
                normalized_message.get("tool_calls") or [],
                tool_schemas,
            )
            if repaired_count:
                normalized_message["tool_calls"] = normalized_tool_calls
                repairs += repaired_count

        normalized_messages.append(normalized_message)

    return normalized_messages, repairs


def normalize_openai_request_payload(request_payload: dict | None) -> tuple[dict | None, int]:
    if not ENABLE_REQUEST_NORMALIZATION or not isinstance(request_payload, dict):
        return request_payload, 0

    normalized_payload = dict(request_payload)
    repairs = 0

    if normalized_payload.get("max_output_tokens") is not None and normalized_payload.get("max_tokens") is None:
        normalized_payload["max_tokens"] = normalized_payload.pop("max_output_tokens")
        repairs += 1

    repairs += normalize_completion_token_limits(normalized_payload)

    if normalized_payload.get("stop_sequences") is not None and normalized_payload.get("stop") is None:
        normalized_payload["stop"] = normalized_payload.pop("stop_sequences")
        repairs += 1

    if not normalized_payload.get("messages") and normalized_payload.get("input") is not None:
        converted_messages = convert_input_to_messages(normalized_payload.get("input"))
        if converted_messages:
            normalized_payload["messages"] = converted_messages
            normalized_payload.pop("input", None)
            repairs += 1

    if normalized_payload.get("instructions"):
        instructions_text = flatten_instruction_text(normalized_payload.get("instructions"))
        if instructions_text:
            messages = normalized_payload.setdefault("messages", [])
            if not any(isinstance(item, dict) and item.get("role") == "system" for item in messages):
                messages.insert(0, {"role": "system", "content": instructions_text})
                repairs += 1
        normalized_payload.pop("instructions", None)

    tools = normalized_payload.get("tools")
    normalized_tools = tools
    if isinstance(tools, list):
        normalized_tools = []
        tool_repairs = 0
        for tool in tools:
            normalized_tool, changed = normalize_openai_tool_definition(tool)
            normalized_tools.append(normalized_tool)
            if changed:
                tool_repairs += 1
        normalized_payload["tools"] = normalized_tools
        if tool_repairs:
            repairs += tool_repairs

    tool_schemas = extract_tool_schemas(normalized_payload)

    messages, message_repairs = normalize_openai_messages(normalized_payload.get("messages"), tool_schemas)
    if message_repairs:
        normalized_payload["messages"] = messages
        repairs += message_repairs
    else:
        normalized_payload["messages"] = messages

    normalized_messages, prompt_repairs = inject_proxy_system_prompt(normalized_payload.get("messages"))
    if prompt_repairs:
        normalized_payload["messages"] = normalized_messages
        repairs += prompt_repairs

    normalized_tool_choice, changed = normalize_openai_tool_choice(normalized_payload.get("tool_choice"))
    if changed:
        normalized_payload["tool_choice"] = normalized_tool_choice
        repairs += 1

    return normalized_payload, repairs


def parse_xml_attributes(attrs_text: str) -> dict:
    return {
        match.group(1): match.group(2)
        for match in XML_ATTR_PATTERN.finditer(attrs_text or "")
    }


def clean_dsml_parameter_text(value: str) -> str:
    cleaned = (value or "").replace("\r", "")
    non_empty_lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if non_empty_lines:
        single_char_lines = sum(1 for line in non_empty_lines if len(line) == 1)
        if single_char_lines >= max(6, int(len(non_empty_lines) * 0.6)):
            cleaned = "".join(non_empty_lines)
        else:
            cleaned = "\n".join(non_empty_lines)
    return cleaned.strip()


def coerce_dsml_parameter_value(value: str, attrs: dict):
    cleaned = clean_dsml_parameter_text(value)
    if cleaned == "":
        return ""

    if str(attrs.get("string", "")).lower() == "true":
        return cleaned

    lowered = cleaned.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if re.fullmatch(r"-?\d+", cleaned):
        try:
            return int(cleaned)
        except ValueError:
            return cleaned
    if re.fullmatch(r"-?\d+\.\d+", cleaned):
        try:
            return float(cleaned)
        except ValueError:
            return cleaned
    if cleaned.startswith("{") or cleaned.startswith("["):
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return cleaned

    return cleaned


def build_dsml_tool_call(invoke_text: str, tool_schemas: dict) -> tuple[dict | None, int]:
    invoke_match = DSML_INVOKE_PATTERN.search(invoke_text or "")
    if not invoke_match:
        return None, 0

    invoke_attrs = parse_xml_attributes(invoke_match.group("attrs"))
    raw_tool_name = invoke_attrs.get("name") or ""
    resolved_tool_name = resolve_tool_name(raw_tool_name, tool_schemas) or raw_tool_name
    repaired = 1 if resolved_tool_name != raw_tool_name else 0
    arguments_payload = {}

    for parameter_match in DSML_PARAMETER_PATTERN.finditer(invoke_match.group("body") or ""):
        parameter_attrs = parse_xml_attributes(parameter_match.group("attrs"))
        parameter_name = parameter_attrs.get("name")
        if not parameter_name:
            continue
        arguments_payload[parameter_name] = coerce_dsml_parameter_value(
            parameter_match.group("body") or "",
            parameter_attrs,
        )

    arguments_payload, unwrapped = unwrap_nested_arguments_container(
        arguments_payload,
        resolved_tool_name,
        tool_schemas,
    )
    if unwrapped:
        repaired += 1

    inferred_tool_name = infer_tool_name_from_payload(resolved_tool_name, arguments_payload, tool_schemas)
    if inferred_tool_name and inferred_tool_name != resolved_tool_name:
        resolved_tool_name = inferred_tool_name
        repaired += 1

    normalized_payload, modified = normalize_tool_arguments_payload(
        resolved_tool_name,
        arguments_payload,
        tool_schemas,
    )
    if modified:
        repaired += 1

    if should_suppress_tool_call(resolved_tool_name, normalized_payload, tool_schemas):
        return None, repaired + 1

    return (
        {
            "id": f"call_{uuid.uuid4().hex[:24]}",
            "type": "function",
            "function": {
                "name": resolved_tool_name,
                "arguments": json.dumps(
                    normalized_payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        },
        repaired,
    )


def extract_dsml_tool_calls_from_text(
    text: str,
    tool_schemas: dict,
    *,
    finalizing: bool,
) -> tuple[str, list[dict], str, int, int]:
    raw_text = text or ""
    tag_match = DSML_TAG_START_PATTERN.search(raw_text)
    if not tag_match:
        return raw_text, [], "", 0, 0

    prefix = raw_text[:tag_match.start()]
    candidate = raw_text[tag_match.start():]
    tool_calls = []
    cleaned_parts = []
    cursor = 0
    repaired = 0
    removed_markers = 0
    saw_invoke = False

    while True:
        invoke_match = DSML_INVOKE_PATTERN.search(candidate, cursor)
        if not invoke_match:
            remainder = candidate[cursor:]
            if saw_invoke:
                sanitized_remainder, removed = strip_all_dsml_tags(remainder)
                removed_markers += removed
                cleaned_parts.append(sanitized_remainder)
                return prefix + "".join(cleaned_parts), tool_calls, "", removed_markers, repaired

            if finalizing:
                sanitized_remainder, removed = strip_all_dsml_tags(candidate)
                removed_markers += removed
                return prefix + sanitized_remainder, tool_calls, "", removed_markers, repaired

            return prefix, [], candidate, removed_markers, repaired

        saw_invoke = True
        before_invoke = candidate[cursor:invoke_match.start()]
        if before_invoke:
            sanitized_before, removed = strip_all_dsml_tags(before_invoke)
            removed_markers += removed
            cleaned_parts.append(sanitized_before)

        tool_call, repaired_count = build_dsml_tool_call(invoke_match.group(0), tool_schemas)
        if tool_call:
            tool_calls.append(tool_call)
            repaired += repaired_count

        removed_markers += len(DSML_ANY_TAG_PATTERN.findall(invoke_match.group(0)))
        cursor = invoke_match.end()


def normalize_dsml_content_tool_calls(
    content: str,
    state: dict,
    tool_schemas: dict,
    *,
    finalizing: bool,
) -> tuple[str | None, list[dict], int, int]:
    source_text = f"{state.get('dsml_buffer', '')}{content}"
    cleaned_text, synthetic_tool_calls, incomplete_tail, removed, repaired = extract_dsml_tool_calls_from_text(
        source_text,
        tool_schemas,
        finalizing=finalizing,
    )

    if incomplete_tail and not finalizing:
        state["dsml_buffer"] = incomplete_tail
    else:
        state["dsml_buffer"] = ""

    if finalizing and incomplete_tail:
        sanitized_tail, tail_removed = strip_all_dsml_tags(incomplete_tail)
        removed += tail_removed
        cleaned_text = f"{cleaned_text}{sanitized_tail}"

    content_value = cleaned_text if cleaned_text and cleaned_text.strip() else None
    return content_value, synthetic_tool_calls, removed, repaired


def normalize_chat_completion_dsml_tool_calls(response_body: dict, tool_schemas: dict) -> int:
    repaired = 0
    for choice in response_body.get("choices") or []:
        message = choice.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or "DSML" not in content.upper():
            continue

        cleaned_content, synthetic_tool_calls, _, _, repaired_count = extract_dsml_tool_calls_from_text(
            content,
            tool_schemas,
            finalizing=True,
        )
        if not synthetic_tool_calls:
            if cleaned_content != content:
                message["content"] = cleaned_content if cleaned_content and cleaned_content.strip() else None
            continue

        existing_tool_calls = message.setdefault("tool_calls", [])
        existing_tool_calls.extend(synthetic_tool_calls)
        message["content"] = cleaned_content if cleaned_content and cleaned_content.strip() else None
        repaired += repaired_count + len(synthetic_tool_calls)

    return repaired


def get_choice_stream_state(choice_states: dict, choice_index: int) -> dict:
    return choice_states.setdefault(
        choice_index,
        {
            "pending_marker": "",
            "content_emitted": False,
            "text_content_seen": False,
            "tool_calls": {},
            "tool_call_seen": False,
            "dsml_buffer": "",
            "synthetic_tool_call_index": 0,
            "markdown_tail": "",
            "reasoning_text": "",
            "last_reasoning_delta": "",
        },
    )


def consume_dsml_content_fragment(fragment: str, state: dict) -> tuple[str | None, int]:
    if fragment == "":
        return "", 0

    combined = f"{state['pending_marker']}{fragment}"
    if not state["content_emitted"]:
        stripped = combined.lstrip()
        if stripped == "":
            state["pending_marker"] = combined
            return None, 0

        if looks_like_dsml_marker_prefix(stripped):
            state["pending_marker"] = combined
            return None, 0

        remainder, removed = strip_leading_dsml_marker(stripped)
        if removed:
            state["pending_marker"] = ""
            if remainder:
                state["content_emitted"] = state["content_emitted"] or bool(remainder.strip())
                return remainder, removed
            return None, removed

    state["pending_marker"] = ""
    state["content_emitted"] = state["content_emitted"] or bool(combined.strip())
    return combined, 0


def flush_pending_dsml_fragment(state: dict, *, for_tool_call: bool) -> tuple[str | None, int]:
    pending = state.get("pending_marker", "")
    if not pending:
        return None, 0

    state["pending_marker"] = ""
    stripped = pending.lstrip()
    if stripped and looks_like_dsml_marker_prefix(stripped):
        return None, 1 if for_tool_call else 0

    stripped_pending, removed = strip_leading_dsml_marker(stripped)
    if removed:
        if stripped_pending.strip():
            state["content_emitted"] = state["content_emitted"] or bool(stripped_pending.strip())
            return stripped_pending, removed
        return None, removed

    state["content_emitted"] = state["content_emitted"] or bool(pending.strip())
    return pending, 0


def canonicalize_dsml_marker_fragment(text: str) -> str:
    return canonicalize_dsml_marker_seed(text)


def looks_like_dsml_marker_prefix(text: str) -> bool:
    canonical_fragment = canonicalize_dsml_marker_fragment(text)
    if not canonical_fragment:
        return False
    # Require at least 3 characters to avoid false positives on bare "<" or "<d"
    if len(canonical_fragment) < 3:
        return False
    return any(
        marker.startswith(canonical_fragment)
        for marker in CANONICAL_DSML_MARKER_VARIANTS
    )


def strip_leading_dsml_marker(text: str) -> tuple[str, int]:
    if not isinstance(text, str) or not text:
        return text, 0

    match = DSML_LEADING_FRAGMENT_PATTERN.match(text)
    if not match:
        return text, 0
    return text[match.end():], 1


def get_tool_call_stream_state(choice_state: dict, tool_index: int) -> dict:
    return choice_state["tool_calls"].setdefault(
        tool_index,
        {
            "id": "",
            "type": "function",
            "name": "",
            "arguments_buffer": "",
            "header_emitted": False,
            "arguments_emitted": False,
            "last_arguments": "",
            "suppressed": False,
        },
    )


def normalize_stream_tool_calls(
    tool_calls: list,
    choice_state: dict,
    tool_schemas: dict,
    *,
    finalizing: bool,
) -> tuple[list, int]:
    emitted_tool_calls = []
    repaired = 0

    for tool_call in tool_calls:
        tool_index = tool_call.get("index", 0)
        tool_state = get_tool_call_stream_state(choice_state, tool_index)
        function_delta = dict(tool_call.get("function") or {})
        emit_tool_call = {"index": tool_index}
        emit_function = {}

        if tool_call.get("id"):
            tool_state["id"] = tool_call["id"]
        if tool_call.get("type"):
            tool_state["type"] = tool_call["type"]
        if function_delta.get("name"):
            tool_state["name"] = function_delta["name"]

        edit_like_tool = bool(tool_state["name"]) and is_edit_like_tool(tool_state["name"], tool_schemas)

        def emit_header() -> None:
            if tool_state["header_emitted"] or not tool_state["name"]:
                return
            if tool_state["id"]:
                emit_tool_call["id"] = tool_state["id"]
            emit_tool_call["type"] = tool_state["type"] or "function"
            emit_function["name"] = tool_state["name"]
            tool_state["header_emitted"] = True

        if (not tool_state["name"] or edit_like_tool) and function_delta.get("name"):
            edit_like_tool = bool(tool_state["name"]) and is_edit_like_tool(tool_state["name"], tool_schemas)

        defer_header_until_arguments = tool_requires_arguments_before_stream_header(tool_state["name"], tool_schemas)

        if tool_state["name"] and not edit_like_tool and not defer_header_until_arguments and function_delta.get("name"):
            emit_header()
        elif function_delta.get("name") and tool_state["header_emitted"]:
            emit_function["name"] = tool_state["name"]

        arguments_fragment = function_delta.get("arguments")
        if isinstance(arguments_fragment, str):
            tool_state["arguments_buffer"] = f"{tool_state['arguments_buffer']}{arguments_fragment}"
            normalized_text, modified, complete = normalize_tool_arguments_text(
                tool_state["name"],
                tool_state["arguments_buffer"],
                tool_schemas,
                final_only=False,
            )
            if complete and normalized_text is not None and normalized_text != tool_state["last_arguments"]:
                inferred_name = infer_tool_name_from_payload(tool_state["name"], normalized_text, tool_schemas)
                if inferred_name and inferred_name != tool_state["name"]:
                    tool_state["name"] = inferred_name
                    edit_like_tool = is_edit_like_tool(tool_state["name"], tool_schemas)
                    repaired += 1
                if should_suppress_tool_call(tool_state["name"], normalized_text, tool_schemas):
                    tool_state["suppressed"] = True
                    repaired += 1 + (1 if modified else 0)
                else:
                    emit_header()
                    emit_function["arguments"] = normalized_text
                    tool_state["arguments_emitted"] = True
                    tool_state["last_arguments"] = normalized_text
                    if modified:
                        repaired += 1

        if finalizing and not tool_state["arguments_emitted"] and not tool_state["suppressed"]:
            normalized_text, modified, complete = normalize_tool_arguments_text(
                tool_state["name"],
                tool_state["arguments_buffer"],
                tool_schemas,
                final_only=True,
            )
            if complete and normalized_text is not None:
                inferred_name = infer_tool_name_from_payload(tool_state["name"], normalized_text, tool_schemas)
                if inferred_name and inferred_name != tool_state["name"]:
                    tool_state["name"] = inferred_name
                    edit_like_tool = is_edit_like_tool(tool_state["name"], tool_schemas)
                    repaired += 1
                if should_suppress_tool_call(tool_state["name"], normalized_text, tool_schemas):
                    tool_state["suppressed"] = True
                    repaired += 1 + (1 if modified else 0)
                else:
                    emit_header()
                    emit_function["arguments"] = normalized_text
                    tool_state["arguments_emitted"] = True
                    tool_state["last_arguments"] = normalized_text
                    if modified:
                        repaired += 1
            elif tool_state["name"]:
                fallback_payload, fallback_modified = normalize_tool_arguments_payload(
                    tool_state["name"],
                    {},
                    tool_schemas,
                )
                inferred_name = infer_tool_name_from_payload(tool_state["name"], fallback_payload, tool_schemas)
                if inferred_name and inferred_name != tool_state["name"]:
                    tool_state["name"] = inferred_name
                    edit_like_tool = is_edit_like_tool(tool_state["name"], tool_schemas)
                    repaired += 1
                if should_suppress_tool_call(tool_state["name"], fallback_payload, tool_schemas):
                    tool_state["suppressed"] = True
                    repaired += 1 + (1 if fallback_modified else 0)
                else:
                    fallback_text = json.dumps(
                        fallback_payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    emit_header()
                    emit_function["arguments"] = fallback_text
                    tool_state["arguments_emitted"] = True
                    tool_state["last_arguments"] = fallback_text
                    repaired += 1 + (1 if fallback_modified else 0)

        if emit_function:
            if "name" not in emit_function:
                inferred_name = infer_tool_name_from_payload(
                    tool_state["name"],
                    emit_function.get("arguments"),
                    tool_schemas,
                )
                if inferred_name:
                    tool_state["name"] = inferred_name
                    emit_function["name"] = inferred_name
                    repaired += 1
                else:
                    tool_state["suppressed"] = True
                    repaired += 1
                    continue
            if tool_state["id"] and "id" not in emit_tool_call:
                emit_tool_call["id"] = tool_state["id"]
            emit_tool_call["type"] = tool_state["type"] or "function"
            emit_tool_call["function"] = emit_function
        if len(emit_tool_call) > 1:
            emitted_tool_calls.append(emit_tool_call)
            choice_state["tool_call_seen"] = True

    return emitted_tool_calls, repaired


def finalize_pending_stream_tool_calls(choice_state: dict, tool_schemas: dict) -> tuple[list, int]:
    pending_tool_calls = []
    for tool_index in sorted((choice_state.get("tool_calls") or {}).keys()):
        tool_state = choice_state["tool_calls"].get(tool_index) or {}
        if tool_state.get("arguments_emitted") or tool_state.get("suppressed"):
            continue
        pending_tool_calls.append(
            {
                "index": tool_index,
                "id": tool_state.get("id"),
                "type": tool_state.get("type") or "function",
                "function": {},
            }
        )

    if not pending_tool_calls:
        return [], 0

    return normalize_stream_tool_calls(
        pending_tool_calls,
        choice_state,
        tool_schemas,
        finalizing=True,
    )


def normalize_stream_choice(choice: dict, choice_states: dict, tool_schemas: dict) -> tuple[dict | None, int, int]:
    normalized_choice = dict(choice)
    choice_index = normalized_choice.get("index", 0)
    state = get_choice_stream_state(choice_states, choice_index)
    delta = dict(normalized_choice.get("delta") or {})
    message_payload = normalized_choice.get("message") or {}
    message_tool_calls = []
    if isinstance(message_payload, dict):
        message_tool_calls = list(message_payload.get("tool_calls") or [])
    if "tool_calls" not in delta and isinstance(message_payload, dict):
        if isinstance(message_tool_calls, list) and message_tool_calls:
            delta["tool_calls"] = message_tool_calls
    had_upstream_tool_calls = "tool_calls" in delta
    sanitized_markers = 0
    repaired_tool_args = 0

    if "tool_calls" in delta:
        _, removed = flush_pending_dsml_fragment(state, for_tool_call=True)
        sanitized_markers += removed
        normalized_tool_calls, repaired_count = normalize_stream_tool_calls(
            delta.get("tool_calls") or [],
            state,
            tool_schemas,
            finalizing=False,
        )
        repaired_tool_args += repaired_count
        if normalized_tool_calls:
            delta["tool_calls"] = normalized_tool_calls
        else:
            delta.pop("tool_calls", None)

    content = delta.get("content")
    if isinstance(content, str):
        normalized_content, synthetic_tool_calls, removed, repaired_count = normalize_dsml_content_tool_calls(
            content,
            state,
            tool_schemas,
            finalizing=False,
        )
        sanitized_markers += removed
        repaired_tool_args += repaired_count

        if synthetic_tool_calls:
            synthetic_with_index = []
            next_index = max(state["synthetic_tool_call_index"], len(state["tool_calls"]))
            for tool_call in synthetic_tool_calls:
                tool_call_payload = dict(tool_call)
                tool_call_payload["index"] = next_index
                synthetic_with_index.append(tool_call_payload)
                next_index += 1
            state["synthetic_tool_call_index"] = next_index
            normalized_tool_calls, repaired_count = normalize_stream_tool_calls(
                synthetic_with_index,
                state,
                tool_schemas,
                finalizing=True,
            )
            repaired_tool_args += repaired_count
            if normalized_tool_calls:
                merged_tool_calls = list(delta.get("tool_calls") or [])
                merged_tool_calls.extend(normalized_tool_calls)
                delta["tool_calls"] = merged_tool_calls

        if normalized_content is None:
            delta.pop("content", None)
        else:
            normalized_content, removed = strip_tool_use_error_blocks(normalized_content)
            sanitized_markers += removed
            normalized_content, removed = sanitize_dsml_text(normalized_content)
            sanitized_markers += removed
            normalized_content, removed = consume_dsml_content_fragment(normalized_content, state)
            sanitized_markers += removed
            if normalized_content is None:
                delta.pop("content", None)
            else:
                normalized_content, formatting_repairs = normalize_markdown_output_fragment(normalized_content, state)
                repaired_tool_args += formatting_repairs
                delta["content"] = normalized_content
                if isinstance(normalized_content, str) and normalized_content.strip():
                    state["text_content_seen"] = True

    reasoning_content = (
        delta.get("reasoning")
        or delta.get("reasoning_content")
        or delta.get("thinking")
        or delta.get("thinking_content")
    )
    reasoning_delta_text = ""
    if isinstance(reasoning_content, str) and reasoning_content:
        state["reasoning_text"] = f"{state.get('reasoning_text', '')}{reasoning_content}"
        reasoning_delta_text = reasoning_content
    elif isinstance(reasoning_content, list):
        joined_reasoning = "".join(
            str(item.get("text", ""))
            for item in reasoning_content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
        if joined_reasoning:
            state["reasoning_text"] = f"{state.get('reasoning_text', '')}{joined_reasoning}"
            reasoning_delta_text = joined_reasoning

    finish_reason = normalized_choice.get("finish_reason")
    finish_reason_text = str(finish_reason or "").strip().lower()
    if finish_reason_text and any(marker in finish_reason_text for marker in ("error", "failure", "failed", "exception")):
        normalized_choice["finish_reason"] = "stop"
        finish_reason = "stop"
    if state["tool_call_seen"] and finish_reason in {None, "stop"}:
        normalized_choice["finish_reason"] = "tool_calls"
        finish_reason = "tool_calls"

    if finish_reason and finish_reason != "tool_calls":
        if state.get("dsml_buffer"):
            pending_content, synthetic_tool_calls, removed, repaired_count = normalize_dsml_content_tool_calls(
                "",
                state,
                tool_schemas,
                finalizing=True,
            )
            sanitized_markers += removed
            repaired_tool_args += repaired_count
            if synthetic_tool_calls:
                synthetic_with_index = []
                next_index = max(state["synthetic_tool_call_index"], len(state["tool_calls"]))
                for tool_call in synthetic_tool_calls:
                    tool_call_payload = dict(tool_call)
                    tool_call_payload["index"] = next_index
                    synthetic_with_index.append(tool_call_payload)
                    next_index += 1
                state["synthetic_tool_call_index"] = next_index
                normalized_tool_calls, repaired_count = normalize_stream_tool_calls(
                    synthetic_with_index,
                    state,
                    tool_schemas,
                    finalizing=True,
                )
                repaired_tool_args += repaired_count
                if normalized_tool_calls:
                    merged_tool_calls = list(delta.get("tool_calls") or [])
                    merged_tool_calls.extend(normalized_tool_calls)
                    delta["tool_calls"] = merged_tool_calls
                    normalized_choice["finish_reason"] = "tool_calls"
                    finish_reason = "tool_calls"
            if pending_content:
                pending_content, formatting_repairs = normalize_markdown_output_fragment(pending_content, state)
                repaired_tool_args += formatting_repairs
                current_content = delta.get("content", "")
                delta["content"] = f"{current_content}{pending_content}" if current_content else pending_content

        pending_text, removed = flush_pending_dsml_fragment(state, for_tool_call=False)
        sanitized_markers += removed
        if pending_text:
            pending_text, formatting_repairs = normalize_markdown_output_fragment(pending_text, state)
            repaired_tool_args += formatting_repairs
            current_content = delta.get("content", "")
            delta["content"] = f"{current_content}{pending_text}" if current_content else pending_text
    elif finish_reason == "tool_calls":
        if state.get("dsml_buffer"):
            _, synthetic_tool_calls, removed, repaired_count = normalize_dsml_content_tool_calls(
                "",
                state,
                tool_schemas,
                finalizing=True,
            )
            sanitized_markers += removed
            repaired_tool_args += repaired_count
            if synthetic_tool_calls:
                synthetic_with_index = []
                next_index = max(state["synthetic_tool_call_index"], len(state["tool_calls"]))
                for tool_call in synthetic_tool_calls:
                    tool_call_payload = dict(tool_call)
                    tool_call_payload["index"] = next_index
                    synthetic_with_index.append(tool_call_payload)
                    next_index += 1
                state["synthetic_tool_call_index"] = next_index
                normalized_tool_calls, repaired_count = normalize_stream_tool_calls(
                    synthetic_with_index,
                    state,
                    tool_schemas,
                    finalizing=True,
                )
                repaired_tool_args += repaired_count
                if normalized_tool_calls:
                    merged_tool_calls = list(delta.get("tool_calls") or [])
                    merged_tool_calls.extend(normalized_tool_calls)
                    delta["tool_calls"] = merged_tool_calls

        _, removed = flush_pending_dsml_fragment(state, for_tool_call=True)
        sanitized_markers += removed
        if had_upstream_tool_calls:
            pending_tool_calls, repaired_count = finalize_pending_stream_tool_calls(
                state,
                tool_schemas,
            )
            repaired_tool_args += repaired_count
            if pending_tool_calls:
                delta["tool_calls"] = pending_tool_calls
        if "tool_calls" not in delta and message_tool_calls:
            fallback_tool_calls, repaired_count = normalize_tool_call_list(message_tool_calls, tool_schemas)
            repaired_tool_args += repaired_count
            if fallback_tool_calls:
                delta["tool_calls"] = fallback_tool_calls
                state["tool_call_seen"] = True

    if normalized_choice.get("finish_reason") == "tool_calls" and not state["tool_call_seen"]:
        normalized_choice["finish_reason"] = "stop"
        finish_reason = "stop"
    null_delta_keys = [key for key, value in delta.items() if value is None]
    for key in null_delta_keys:
        delta.pop(key, None)
    has_meaningful_delta = any(
        key in delta
        for key in ("role", "tool_calls", "content", "reasoning_content", "reasoning", "thinking", "thinking_content")
    ) or bool(reasoning_delta_text)
    if "content" in delta and delta["content"] == "":
        delta.pop("content", None)
        has_meaningful_delta = any(key in delta for key in ("role", "tool_calls"))

    if delta:
        normalized_choice["delta"] = delta
    else:
        normalized_choice.pop("delta", None)
    normalized_choice.pop("message", None)

    if state.get("reasoning_text"):
        normalized_choice["reasoning"] = state["reasoning_text"]
        if "delta" in normalized_choice and reasoning_delta_text:
            normalized_choice["delta"]["reasoning_content"] = reasoning_delta_text

    if not has_meaningful_delta and finish_reason is None:
        return None, sanitized_markers, repaired_tool_args

    return normalized_choice, sanitized_markers, repaired_tool_args


def _normalize_sse_payload_text(
    payload: str,
    choice_states: dict,
    tool_schemas: dict,
    *,
    original_line: str,
) -> tuple[str | None, int, int, dict | None]:
    if payload == "[DONE]":
        return "data: [DONE]", 0, 0, None

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        sanitized_line, removed = sanitize_dsml_text(original_line)
        return sanitized_line, removed, 0, None
    if not isinstance(event, dict):
        sanitized_line, removed = sanitize_dsml_text(original_line)
        return sanitized_line, removed, 0, None

    sanitized_markers = 0
    repaired_tool_args = 0
    if isinstance(event.get("usage"), dict):
        event["usage"] = normalize_openai_usage_payload(event.get("usage"))
    choices = event.get("choices")
    if isinstance(choices, list):
        normalized_choices = []
        for choice in choices:
            normalized_choice, removed, repaired_count = normalize_stream_choice(choice, choice_states, tool_schemas)
            sanitized_markers += removed
            repaired_tool_args += repaired_count
            if normalized_choice is not None:
                normalized_choices.append(normalized_choice)
        event["choices"] = normalized_choices
        if not normalized_choices and "usage" not in event:
            return None, sanitized_markers, repaired_tool_args, event

    return (
        f"data: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}",
        sanitized_markers,
        repaired_tool_args,
        event,
    )


def normalize_sse_line(line: str, choice_states: dict, tool_schemas: dict) -> tuple[str | None, int, int, dict | None]:
    if not line:
        return "", 0, 0, None

    if line.startswith("data:"):
        return _normalize_sse_payload_text(
            line[5:].strip(),
            choice_states,
            tool_schemas,
            original_line=line,
        )

    stripped_line = line.strip()
    if stripped_line == "[DONE]" or stripped_line.startswith("{") or stripped_line.startswith("["):
        return _normalize_sse_payload_text(
            stripped_line,
            choice_states,
            tool_schemas,
            original_line=line,
        )

    sanitized_line, removed = sanitize_dsml_text(line)
    return sanitized_line, removed, 0, None


def merge_tool_call_delta(message: dict, tool_call_delta: dict) -> None:
    tool_calls = message.setdefault("tool_calls", [])
    call_index = tool_call_delta.get("index", 0)
    while len(tool_calls) <= call_index:
        tool_calls.append(
            {
                "id": "",
                "type": "function",
                "function": {
                    "name": "",
                    "arguments": "",
                },
            }
        )

    tool_call = tool_calls[call_index]
    if tool_call_delta.get("id"):
        tool_call["id"] = tool_call_delta["id"]
    if tool_call_delta.get("type"):
        tool_call["type"] = tool_call_delta["type"]

    function_delta = tool_call_delta.get("function") or {}
    function_payload = tool_call.setdefault("function", {"name": "", "arguments": ""})
    if function_delta.get("name"):
        function_payload["name"] = function_delta["name"]
    if function_delta.get("arguments"):
        function_payload["arguments"] = f"{function_payload.get('arguments', '')}{function_delta['arguments']}"


def build_chat_completion_from_sse(events: list[dict]) -> dict:
    first_event = next((event for event in events if event.get("choices") is not None), {})
    aggregated_choices = {}
    usage = None

    for event in events:
        if "usage" in event:
            usage = event["usage"]

        for choice in event.get("choices", []):
            choice_index = choice.get("index", 0)
            aggregate = aggregated_choices.setdefault(
                choice_index,
                {
                    "index": choice_index,
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "reasoning": "",
                    },
                    "finish_reason": None,
                },
            )

            delta = choice.get("delta") or {}
            if delta.get("role"):
                aggregate["message"]["role"] = delta["role"]
            if isinstance(delta.get("content"), str):
                aggregate["message"]["content"] = f"{aggregate['message'].get('content', '')}{delta['content']}"
            if isinstance(choice.get("reasoning"), str):
                aggregate["message"]["reasoning"] = f"{aggregate['message'].get('reasoning', '')}{choice['reasoning']}"
            reasoning_delta = delta.get("reasoning_content")
            if isinstance(reasoning_delta, str):
                aggregate["message"]["reasoning"] = f"{aggregate['message'].get('reasoning', '')}{reasoning_delta}"
            for tool_call_delta in delta.get("tool_calls") or []:
                merge_tool_call_delta(aggregate["message"], tool_call_delta)

            if choice.get("finish_reason") is not None:
                aggregate["finish_reason"] = choice["finish_reason"]

    choices = []
    for choice_index in sorted(aggregated_choices):
        aggregate = aggregated_choices[choice_index]
        message = aggregate["message"]
        if message.get("tool_calls") and not message.get("content"):
            message["content"] = None
        if not message.get("reasoning"):
            message.pop("reasoning", None)
        choices.append(
            {
                "index": choice_index,
                "message": message,
                "finish_reason": aggregate.get("finish_reason") or "stop",
            }
        )

    if not choices:
        choices.append(
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                },
                "finish_reason": "stop",
            }
        )

    return {
        "id": first_event.get("id", f"chatcmpl-{uuid.uuid4().hex[:16]}"),
        "object": "chat.completion",
        "created": first_event.get("created", int(time.time())),
        "model": first_event.get("model"),
        "choices": choices,
        "usage": usage,
    }
