import json
import re
import time
import uuid
from collections import deque

from local_proxy.compat.tools import (
    infer_tool_name_from_payload,
    inject_proxy_system_prompt,
    normalize_openai_request_payload,
    normalize_tool_arguments_payload,
    parse_tool_arguments_object,
    should_suppress_tool_call,
)
from local_proxy.upstream.capabilities import estimate_payload_tokens


GEMINI_GENERATE_SUBPATH_PATTERN = re.compile(
    r"^(?P<resource>models|tunedModels)/(?P<model>.+):(?P<method>generateContent|streamGenerateContent)$",
    re.IGNORECASE,
)
GEMINI_SCHEMA_TYPE_MAP = {
    "STRING": "string",
    "NUMBER": "number",
    "INTEGER": "integer",
    "BOOLEAN": "boolean",
    "ARRAY": "array",
    "OBJECT": "object",
}


def coerce_non_negative_int(value) -> int:
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    try:
        return max(0, int(float(str(value).strip())))
    except Exception:
        return 0


def estimate_text_tokens(text: str | None) -> int:
    if not isinstance(text, str) or not text:
        return 0
    char_count = len(text)
    ascii_count = sum(1 for ch in text if ord(ch) < 128)
    non_ascii_count = max(0, char_count - ascii_count)
    estimated = (ascii_count / 4.0) + (non_ascii_count / 1.6)
    return max(1, int(estimated))


def estimate_openai_response_completion_tokens(response_body: dict | None) -> int:
    if not isinstance(response_body, dict):
        return 0

    fragments: list[str] = []
    for choice in response_body.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message") or {}
        if not isinstance(message, dict):
            continue

        content = message.get("content")
        if isinstance(content, str):
            fragments.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    fragments.append(item.get("text") or "")

        reasoning = message.get("reasoning") or message.get("reasoning_content")
        if isinstance(reasoning, str):
            fragments.append(reasoning)

        for tool_call in message.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            function_data = tool_call.get("function") or {}
            if isinstance(function_data.get("name"), str):
                fragments.append(function_data.get("name") or "")
            if isinstance(function_data.get("arguments"), str):
                fragments.append(function_data.get("arguments") or "")

    return estimate_text_tokens("".join(fragments))


def build_anthropic_usage_from_openai(response_body: dict | None, request_payload: dict | None = None) -> dict:
    usage = response_body.get("usage") if isinstance(response_body, dict) else {}
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = coerce_non_negative_int(usage.get("prompt_tokens") or usage.get("input_tokens"))
    output_tokens = coerce_non_negative_int(usage.get("completion_tokens") or usage.get("output_tokens"))
    cache_read_input_tokens = coerce_non_negative_int(
        usage.get("cache_read_input_tokens")
        or ((usage.get("prompt_tokens_details") or {}).get("cached_tokens") if isinstance(usage.get("prompt_tokens_details"), dict) else 0)
    )
    cache_creation_input_tokens = coerce_non_negative_int(
        usage.get("cache_creation_input_tokens")
        or ((usage.get("prompt_tokens_details") or {}).get("cache_creation_tokens") if isinstance(usage.get("prompt_tokens_details"), dict) else 0)
    )

    if input_tokens <= 0 and isinstance(request_payload, dict):
        input_tokens = estimate_payload_tokens(request_payload)
    if output_tokens <= 0:
        output_tokens = estimate_openai_response_completion_tokens(response_body)

    result = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    if cache_read_input_tokens > 0:
        result["cache_read_input_tokens"] = cache_read_input_tokens
    if cache_creation_input_tokens > 0:
        result["cache_creation_input_tokens"] = cache_creation_input_tokens
    return result


def build_openai_usage_from_response(response_body: dict | None, request_payload: dict | None = None) -> dict:
    usage = response_body.get("usage") if isinstance(response_body, dict) else {}
    usage = dict(usage) if isinstance(usage, dict) else {}
    prompt_tokens = coerce_non_negative_int(usage.get("prompt_tokens") or usage.get("input_tokens"))
    completion_tokens = coerce_non_negative_int(usage.get("completion_tokens") or usage.get("output_tokens"))
    total_tokens = coerce_non_negative_int(usage.get("total_tokens"))

    if prompt_tokens <= 0 and isinstance(request_payload, dict):
        prompt_tokens = estimate_payload_tokens(request_payload)
    if completion_tokens <= 0:
        completion_tokens = estimate_openai_response_completion_tokens(response_body)
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens

    prompt_tokens_details = usage.get("prompt_tokens_details")
    if not isinstance(prompt_tokens_details, dict):
        prompt_tokens_details = {}
    cached_tokens = coerce_non_negative_int(
        prompt_tokens_details.get("cached_tokens")
        or usage.get("cache_read_input_tokens")
    )
    cache_creation_tokens = coerce_non_negative_int(
        prompt_tokens_details.get("cache_creation_tokens")
        or usage.get("cache_creation_input_tokens")
    )
    if cached_tokens > 0:
        prompt_tokens_details["cached_tokens"] = cached_tokens
    if cache_creation_tokens > 0:
        prompt_tokens_details["cache_creation_tokens"] = cache_creation_tokens

    usage["prompt_tokens"] = prompt_tokens
    usage["completion_tokens"] = completion_tokens
    usage["total_tokens"] = total_tokens
    if prompt_tokens_details:
        usage["prompt_tokens_details"] = prompt_tokens_details
    if cached_tokens > 0:
        usage["cache_read_input_tokens"] = cached_tokens
    if cache_creation_tokens > 0:
        usage["cache_creation_input_tokens"] = cache_creation_tokens
    return usage


def ensure_openai_response_usage(response_body: dict | None, request_payload: dict | None = None) -> dict:
    if not isinstance(response_body, dict):
        return {}
    usage = build_openai_usage_from_response(response_body, request_payload)
    response_body["usage"] = usage
    return usage


def openai_usage_has_billable_tokens(usage: dict | None) -> bool:
    if not isinstance(usage, dict):
        return False
    return (
        coerce_non_negative_int(usage.get("prompt_tokens") or usage.get("input_tokens")) > 0
        and coerce_non_negative_int(usage.get("completion_tokens") or usage.get("output_tokens")) > 0
    )


def flatten_anthropic_text_content(content) -> str:
    if isinstance(content, str):
        return content

    texts = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
            elif block.get("type") == "tool_result":
                tool_content = block.get("content")
                if isinstance(tool_content, str):
                    texts.append(tool_content)
                elif isinstance(tool_content, list):
                    texts.append(flatten_anthropic_text_content(tool_content))

    return "".join(texts)


def parse_tool_call_input(
    arguments_text: str,
    tool_name: str | None = None,
    tool_schemas: dict | None = None,
):
    tool_schemas = tool_schemas or {}

    try:
        parsed = json.loads(arguments_text)
    except Exception:
        parsed = arguments_text

    normalized_payload, _ = normalize_tool_arguments_payload(tool_name, parsed, tool_schemas)
    if isinstance(normalized_payload, dict):
        return normalized_payload

    if isinstance(parsed, dict):
        return parsed

    return {}


def map_anthropic_tool_choice(tool_choice):
    if tool_choice is None:
        return "auto"
    if isinstance(tool_choice, str):
        return tool_choice
    if not isinstance(tool_choice, dict):
        return "auto"

    choice_type = tool_choice.get("type")
    if choice_type == "auto":
        return "auto"
    if choice_type == "any":
        return "required"
    if choice_type == "tool" and tool_choice.get("name"):
        return {
            "type": "function",
            "function": {
                "name": tool_choice["name"],
            },
        }
    if choice_type == "none":
        return "none"
    return "auto"


def message_content_looks_anthropic(content) -> bool:
    if not isinstance(content, list):
        return False

    for block in content:
        if isinstance(block, dict) and block.get("type") in {"tool_use", "tool_result"}:
            return True

    return False


def tools_look_anthropic(tools) -> bool:
    if not isinstance(tools, list):
        return False

    for tool in tools:
        if isinstance(tool, dict) and "input_schema" in tool:
            return True

    return False


def payload_looks_anthropic(request_payload: dict | None) -> bool:
    if not isinstance(request_payload, dict):
        return False

    if tools_look_anthropic(request_payload.get("tools")):
        return True

    tool_choice = request_payload.get("tool_choice")
    if isinstance(tool_choice, dict) and tool_choice.get("type") in {"tool", "any"}:
        return True

    if request_payload.get("stop_sequences"):
        return True

    if isinstance(request_payload.get("system"), (list, dict)):
        return True

    for message in request_payload.get("messages") or []:
        if isinstance(message, dict) and message_content_looks_anthropic(message.get("content")):
            return True

    return False


def parse_gemini_generate_subpath(subpath: str | None) -> dict | None:
    match = GEMINI_GENERATE_SUBPATH_PATTERN.match(str(subpath or "").strip("/"))
    if not match:
        return None
    resource = match.group("resource")
    model = match.group("model").strip("/")
    method = match.group("method")
    if not model:
        return None
    return {
        "resource": resource,
        "model": model,
        "method": method,
        "stream": method.lower() == "streamgeneratecontent",
    }


def get_first_present(mapping: dict | None, *keys, default=None):
    if not isinstance(mapping, dict):
        return default
    for key in keys:
        if key in mapping:
            return mapping.get(key)
    return default


def as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def normalize_gemini_schema_for_openai(schema):
    if isinstance(schema, list):
        return [normalize_gemini_schema_for_openai(item) for item in schema]
    if not isinstance(schema, dict):
        return schema

    normalized = {}
    for key, value in schema.items():
        normalized_key = key
        if key == "propertyOrdering":
            continue
        if key == "nullable":
            normalized_key = "nullable"
        if key in {"properties", "defs", "$defs"} and isinstance(value, dict):
            normalized[normalized_key] = {
                prop_key: normalize_gemini_schema_for_openai(prop_value)
                for prop_key, prop_value in value.items()
            }
            continue
        if key in {"items", "additionalProperties"}:
            normalized[normalized_key] = normalize_gemini_schema_for_openai(value)
            continue
        if key == "type" and isinstance(value, str):
            normalized[normalized_key] = GEMINI_SCHEMA_TYPE_MAP.get(value.upper(), value.lower())
            continue
        normalized[normalized_key] = normalize_gemini_schema_for_openai(value)
    return normalized


def flatten_gemini_parts_text(parts) -> str:
    text_parts = []
    for part in as_list(parts):
        if not isinstance(part, dict):
            if part is not None:
                text_parts.append(str(part))
            continue
        text = get_first_present(part, "text")
        if text is not None:
            text_parts.append(str(text))
    return "".join(text_parts)


def extract_gemini_content_parts(content) -> list:
    if isinstance(content, str):
        return [{"text": content}]
    if isinstance(content, dict):
        if "parts" not in content and any(
            key in content
            for key in (
                "text",
                "inlineData",
                "inline_data",
                "fileData",
                "file_data",
                "functionCall",
                "function_call",
                "functionResponse",
                "function_response",
            )
        ):
            return [content]
        parts = get_first_present(content, "parts", default=[])
        return as_list(parts)
    if isinstance(content, list):
        return content
    return []


def gemini_part_to_openai_content_item(part):
    if not isinstance(part, dict):
        return {"type": "text", "text": str(part)}

    if part.get("text") is not None:
        return {"type": "text", "text": str(part.get("text"))}

    inline_data = get_first_present(part, "inlineData", "inline_data")
    if isinstance(inline_data, dict):
        mime_type = get_first_present(inline_data, "mimeType", "mime_type", default="application/octet-stream")
        data = inline_data.get("data")
        if data and str(mime_type).startswith("image/"):
            return {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{data}",
                },
            }
        if data and str(mime_type).startswith("audio/"):
            audio_format = str(mime_type).split("/", 1)[-1].split(";", 1)[0] or "wav"
            return {
                "type": "input_audio",
                "input_audio": {
                    "data": data,
                    "format": audio_format,
                },
            }
        return {"type": "text", "text": f"[inline_data mime_type={mime_type}]"}

    file_data = get_first_present(part, "fileData", "file_data")
    if isinstance(file_data, dict):
        mime_type = get_first_present(file_data, "mimeType", "mime_type", default="application/octet-stream")
        uri = get_first_present(file_data, "fileUri", "file_uri", default="")
        if uri and str(mime_type).startswith("image/"):
            return {"type": "image_url", "image_url": {"url": uri}}
        return {"type": "text", "text": f"[file_data mime_type={mime_type} uri={uri}]"}

    executable_code = get_first_present(part, "executableCode", "executable_code")
    if isinstance(executable_code, dict):
        language = get_first_present(executable_code, "language", default="")
        code = get_first_present(executable_code, "code", default="")
        return {"type": "text", "text": f"```{language}\n{code}\n```"}

    code_result = get_first_present(part, "codeExecutionResult", "code_execution_result")
    if isinstance(code_result, dict):
        return {
            "type": "text",
            "text": json.dumps(code_result, ensure_ascii=False, separators=(",", ":")),
        }

    return {"type": "text", "text": json.dumps(part, ensure_ascii=False, separators=(",", ":"))}


def gemini_parts_to_openai_content(parts):
    content_items = []
    text_only = True
    for part in as_list(parts):
        if not isinstance(part, dict) or part.get("text") is not None:
            content_items.append(gemini_part_to_openai_content_item(part))
            continue

        if get_first_present(part, "functionCall", "function_call") is not None:
            continue
        if get_first_present(part, "functionResponse", "function_response") is not None:
            continue

        item = gemini_part_to_openai_content_item(part)
        if item.get("type") != "text":
            text_only = False
        content_items.append(item)

    if not content_items:
        return ""
    if text_only and all(item.get("type") == "text" for item in content_items):
        return "".join(str(item.get("text", "")) for item in content_items)
    return content_items


def convert_gemini_messages_to_openai(contents) -> list[dict]:
    openai_messages = []
    pending_tool_call_ids_by_name: dict[str, deque] = {}

    for content in as_list(contents):
        if isinstance(content, str):
            openai_messages.append({"role": "user", "content": content})
            continue
        if not isinstance(content, dict):
            continue

        role = str(content.get("role") or "user").lower()
        parts = extract_gemini_content_parts(content)
        function_response_parts = []
        function_call_parts = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            function_response = get_first_present(part, "functionResponse", "function_response")
            if function_response is not None:
                function_response_parts.append(function_response)
            function_call = get_first_present(part, "functionCall", "function_call")
            if function_call is not None:
                function_call_parts.append(function_call)

        if role in {"model", "assistant"}:
            assistant_message = {"role": "assistant"}
            content_value = gemini_parts_to_openai_content(parts)
            if content_value:
                assistant_message["content"] = content_value
            elif function_call_parts:
                assistant_message["content"] = None
            else:
                assistant_message["content"] = ""

            tool_calls = []
            for function_call in function_call_parts:
                if not isinstance(function_call, dict):
                    continue
                name = str(function_call.get("name") or "")
                args = get_first_present(function_call, "args", "arguments", default={})
                call_id = f"call_gemini_{uuid.uuid4().hex[:24]}"
                if name:
                    pending_tool_call_ids_by_name.setdefault(name, deque()).append(call_id)
                tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(args if args is not None else {}, ensure_ascii=False),
                        },
                    }
                )
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            openai_messages.append(assistant_message)
            continue

        if function_response_parts:
            for function_response in function_response_parts:
                if not isinstance(function_response, dict):
                    continue
                name = str(function_response.get("name") or "")
                response_payload = get_first_present(function_response, "response", default={})
                response_text = (
                    response_payload
                    if isinstance(response_payload, str)
                    else json.dumps(response_payload, ensure_ascii=False, separators=(",", ":"))
                )
                call_queue = pending_tool_call_ids_by_name.get(name)
                if call_queue:
                    openai_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_queue.popleft(),
                            "content": response_text,
                        }
                    )
                else:
                    openai_messages.append(
                        {
                            "role": "user",
                            "content": f"工具 {name or 'unknown'} 返回：{response_text}",
                        }
                    )

        content_value = gemini_parts_to_openai_content(parts)
        if content_value:
            openai_messages.append({"role": "user", "content": content_value})

    return openai_messages


def convert_gemini_tools_to_openai(request_payload: dict) -> tuple[list[dict], list[str]]:
    openai_tools = []
    unsupported = []
    for tool in as_list(request_payload.get("tools")):
        if not isinstance(tool, dict):
            continue
        function_declarations = get_first_present(tool, "functionDeclarations", "function_declarations", default=[])
        for declaration in as_list(function_declarations):
            if not isinstance(declaration, dict) or not declaration.get("name"):
                continue
            parameters = get_first_present(declaration, "parameters", default={"type": "object", "properties": {}})
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": declaration.get("name"),
                        "description": declaration.get("description", ""),
                        "parameters": normalize_gemini_schema_for_openai(parameters),
                    },
                }
            )
        for key in ("googleSearch", "google_search", "codeExecution", "code_execution", "retrieval"):
            if key in tool:
                unsupported.append(key)
    return openai_tools, unsupported


def map_gemini_tool_config_to_openai(tool_config, openai_tools: list[dict]):
    if not isinstance(tool_config, dict):
        return None
    function_config = get_first_present(tool_config, "functionCallingConfig", "function_calling_config", default={})
    if not isinstance(function_config, dict):
        return None
    mode = str(function_config.get("mode") or "").upper()
    allowed_names = get_first_present(function_config, "allowedFunctionNames", "allowed_function_names", default=[])
    allowed_names = [str(name) for name in as_list(allowed_names) if str(name or "").strip()]
    declared_names = [
        (((tool.get("function") or {}).get("name")) if isinstance(tool, dict) else "")
        for tool in openai_tools
    ]
    allowed_names = [name for name in allowed_names if name in declared_names]

    if mode == "NONE":
        return "none"
    if allowed_names and len(allowed_names) == 1:
        return {"type": "function", "function": {"name": allowed_names[0]}}
    if mode == "ANY":
        return "required"
    if mode in {"AUTO", "MODE_UNSPECIFIED"}:
        return "auto"
    return None


def map_gemini_generation_config_to_openai(openai_payload: dict, generation_config) -> None:
    if not isinstance(generation_config, dict):
        return

    field_map = {
        "temperature": ("temperature",),
        "top_p": ("topP", "top_p"),
        "max_tokens": ("maxOutputTokens", "max_output_tokens", "maxTokens", "max_tokens"),
        "stop": ("stopSequences", "stop_sequences"),
        "n": ("candidateCount", "candidate_count"),
        "presence_penalty": ("presencePenalty", "presence_penalty"),
        "frequency_penalty": ("frequencyPenalty", "frequency_penalty"),
    }
    for openai_key, gemini_keys in field_map.items():
        value = get_first_present(generation_config, *gemini_keys)
        if value is not None:
            openai_payload[openai_key] = value

    response_mime_type = get_first_present(generation_config, "responseMimeType", "response_mime_type")
    response_schema = get_first_present(generation_config, "responseSchema", "response_schema")
    if response_schema is not None:
        openai_payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "gemini_response_schema",
                "schema": normalize_gemini_schema_for_openai(response_schema),
                "strict": False,
            },
        }
    elif response_mime_type == "application/json":
        openai_payload["response_format"] = {"type": "json_object"}


def convert_gemini_request_to_openai(request_payload: dict, path_meta: dict) -> tuple[dict, int]:
    request_payload = request_payload if isinstance(request_payload, dict) else {}
    model = request_payload.get("model") or (
        f"{path_meta.get('resource')}/{path_meta.get('model')}"
        if str(path_meta.get("resource", "")).lower() == "tunedmodels"
        else path_meta.get("model")
    )
    openai_payload = {
        "model": model,
        "messages": [],
        "stream": bool(path_meta.get("stream")),
    }
    repairs = 0

    system_instruction = get_first_present(request_payload, "systemInstruction", "system_instruction")
    if system_instruction:
        system_text = flatten_gemini_parts_text(extract_gemini_content_parts(system_instruction))
        if system_text:
            openai_payload["messages"].append({"role": "system", "content": system_text})
            repairs += 1

    contents = request_payload.get("contents")
    if contents is None and request_payload.get("prompt") is not None:
        contents = [{"role": "user", "parts": [{"text": str(request_payload.get("prompt"))}]}]
        repairs += 1
    openai_payload["messages"].extend(convert_gemini_messages_to_openai(contents))

    generation_config = get_first_present(request_payload, "generationConfig", "generation_config")
    map_gemini_generation_config_to_openai(openai_payload, generation_config)

    tools, unsupported_tools = convert_gemini_tools_to_openai(request_payload)
    if tools:
        openai_payload["tools"] = tools
        tool_choice = map_gemini_tool_config_to_openai(
            get_first_present(request_payload, "toolConfig", "tool_config"),
            tools,
        )
        if tool_choice is not None:
            openai_payload["tool_choice"] = tool_choice
        repairs += len(tools)

    if unsupported_tools:
        openai_payload["messages"].insert(
            0,
            {
                "role": "system",
                "content": (
                    "Gemini 原生工具 "
                    + ", ".join(sorted(set(unsupported_tools)))
                    + " 当前会通过 OpenAI 兼容上游转发，无法原样执行；如需外部信息，请在回答中说明限制。"
                ),
            },
        )
        repairs += len(unsupported_tools)

    normalized_payload, request_repairs = normalize_openai_request_payload(openai_payload)
    return normalized_payload or openai_payload, repairs + request_repairs


def map_openai_finish_reason_to_gemini(finish_reason: str | None) -> str:
    reason = str(finish_reason or "").strip().lower()
    if finish_reason == "length":
        return "MAX_TOKENS"
    if finish_reason == "content_filter":
        return "SAFETY"
    if finish_reason in {"stop", "tool_calls", None}:
        return "STOP"
    if any(marker in reason for marker in ("error", "failure", "failed", "exception")):
        return "STOP"
    return "OTHER"


def openai_message_to_gemini_parts(message: dict, tool_schemas: dict | None = None) -> list[dict]:
    tool_schemas = tool_schemas or {}
    parts = []
    content = message.get("content")
    if isinstance(content, str) and content:
        parts.append({"text": content})
    elif isinstance(content, list):
        text = "".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
        if text:
            parts.append({"text": text})

    for tool_call in message.get("tool_calls") or []:
        function_data = tool_call.get("function") or {}
        resolved_name = infer_tool_name_from_payload(function_data.get("name"), function_data.get("arguments", "{}"), tool_schemas)
        if not resolved_name or should_suppress_tool_call(resolved_name, function_data.get("arguments", "{}"), tool_schemas):
            continue
        parts.append(
            {
                "functionCall": {
                    "name": resolved_name,
                    "args": parse_tool_call_input(
                        function_data.get("arguments", "{}"),
                        resolved_name,
                        tool_schemas,
                    ),
                }
            }
        )

    return parts or [{"text": ""}]


def convert_openai_response_to_gemini(response_body: dict, tool_schemas: dict | None = None) -> dict:
    tool_schemas = tool_schemas or {}
    candidates = []
    for choice in response_body.get("choices") or []:
        message = choice.get("message") or {}
        candidate = {
            "index": int(choice.get("index", len(candidates)) or 0),
            "content": {
                "role": "model",
                "parts": openai_message_to_gemini_parts(message, tool_schemas),
            },
            "finishReason": map_openai_finish_reason_to_gemini(choice.get("finish_reason")),
        }
        candidates.append(candidate)

    usage = response_body.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
    completion_tokens = int(usage.get("completion_tokens", 0) or 0)
    return {
        "candidates": candidates,
        "usageMetadata": {
            "promptTokenCount": prompt_tokens,
            "candidatesTokenCount": completion_tokens,
            "totalTokenCount": int(usage.get("total_tokens", prompt_tokens + completion_tokens) or 0),
        },
        "modelVersion": response_body.get("model"),
        "responseId": response_body.get("id"),
    }


def build_gemini_error_payload(*, status_code: int, message: str, retry_count: int, preview: str = "") -> dict:
    if status_code in {400, 422}:
        status = "INVALID_ARGUMENT"
    elif status_code in {401, 403}:
        status = "PERMISSION_DENIED"
    elif status_code == 404:
        status = "NOT_FOUND"
    elif status_code == 429:
        status = "RESOURCE_EXHAUSTED"
    elif status_code in {408, 504, 524}:
        status = "DEADLINE_EXCEEDED"
    elif status_code >= 500:
        status = "UNAVAILABLE"
    else:
        status = "UNKNOWN"
    error = {
        "code": status_code,
        "message": message,
        "status": status,
        "proxyRetries": retry_count,
    }
    if preview:
        error["upstreamPreview"] = preview
    return {"error": error}


def convert_anthropic_messages_to_openai(messages: list) -> list:
    openai_messages = []

    for message in messages or []:
        if not isinstance(message, dict):
            continue

        role = message.get("role")
        content = message.get("content")

        if role == "assistant":
            if isinstance(content, str):
                openai_messages.append({"role": "assistant", "content": content})
                continue

            text_parts = []
            tool_calls = []
            for block in content or []:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "tool_use":
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

            assistant_message = {"role": "assistant"}
            if text_parts:
                assistant_message["content"] = "".join(text_parts)
            elif tool_calls:
                assistant_message["content"] = None
            else:
                assistant_message["content"] = ""

            if tool_calls:
                assistant_message["tool_calls"] = tool_calls

            openai_messages.append(assistant_message)
            continue

        if role == "user":
            if isinstance(content, str):
                openai_messages.append({"role": "user", "content": content})
                continue

            pending_user_text = []
            for block in content or []:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    pending_user_text.append(block.get("text", ""))
                    continue

                if block_type == "tool_result":
                    if pending_user_text:
                        openai_messages.append({"role": "user", "content": "".join(pending_user_text)})
                        pending_user_text = []

                    tool_result_text = flatten_anthropic_text_content(block.get("content"))
                    openai_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": block.get("tool_use_id") or block.get("id") or "",
                            "content": tool_result_text,
                        }
                    )

            if pending_user_text:
                openai_messages.append({"role": "user", "content": "".join(pending_user_text)})

    return openai_messages


def convert_anthropic_request_to_openai(request_payload: dict) -> dict:
    openai_payload = {
        "model": request_payload.get("model"),
        "messages": [],
        "stream": bool(request_payload.get("stream")),
    }

    if request_payload.get("max_tokens") is not None:
        openai_payload["max_tokens"] = request_payload.get("max_tokens")
    if request_payload.get("temperature") is not None:
        openai_payload["temperature"] = request_payload.get("temperature")
    if request_payload.get("top_p") is not None:
        openai_payload["top_p"] = request_payload.get("top_p")
    if request_payload.get("stop_sequences"):
        openai_payload["stop"] = request_payload.get("stop_sequences")

    system_content = request_payload.get("system")
    if system_content:
        openai_payload["messages"].append(
            {
                "role": "system",
                "content": flatten_anthropic_text_content(system_content),
            }
        )

    openai_payload["messages"].extend(
        convert_anthropic_messages_to_openai(request_payload.get("messages") or [])
    )

    tools = []
    for tool in request_payload.get("tools") or []:
        if not isinstance(tool, dict) or not tool.get("name"):
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
                },
            }
        )
    if tools:
        openai_payload["tools"] = tools
        openai_payload["tool_choice"] = map_anthropic_tool_choice(request_payload.get("tool_choice"))

    openai_payload["messages"], _ = inject_proxy_system_prompt(openai_payload.get("messages"))
    normalized_payload, _ = normalize_openai_request_payload(openai_payload)
    return normalized_payload or openai_payload


def map_openai_finish_reason_to_anthropic(finish_reason: str | None) -> str | None:
    reason = str(finish_reason or "").strip().lower()
    if finish_reason == "tool_calls":
        return "tool_use"
    if finish_reason == "length":
        return "max_tokens"
    if finish_reason in {"stop", None}:
        return "end_turn"
    if any(marker in reason for marker in ("error", "failure", "failed", "exception")):
        return "end_turn"
    return finish_reason


def convert_openai_response_to_anthropic(
    response_body: dict,
    tool_schemas: dict | None = None,
    request_payload: dict | None = None,
) -> dict:
    choice = ((response_body.get("choices") or [{}])[0]) if isinstance(response_body, dict) else {}
    message = choice.get("message") or {}
    content_blocks = []
    tool_schemas = tool_schemas or {}

    message_content = message.get("content")
    if isinstance(message_content, str) and message_content:
        content_blocks.append({"type": "text", "text": message_content})

    reasoning_text = message.get("reasoning")
    if isinstance(reasoning_text, str) and reasoning_text:
        content_blocks.append(
            {
                "type": "thinking",
                "thinking": reasoning_text,
                "signature": "proxy-synthetic",
            }
        )

    for tool_call in message.get("tool_calls") or []:
        function_data = tool_call.get("function") or {}
        resolved_name = infer_tool_name_from_payload(function_data.get("name"), function_data.get("arguments", "{}"), tool_schemas)
        if not resolved_name or should_suppress_tool_call(resolved_name, function_data.get("arguments", "{}"), tool_schemas):
            continue
        content_blocks.append(
            {
                "type": "tool_use",
                "id": tool_call.get("id") or f"toolu_{uuid.uuid4().hex[:24]}",
                "name": resolved_name,
                "input": parse_tool_call_input(
                    function_data.get("arguments", "{}"),
                    resolved_name,
                    tool_schemas,
                ),
            }
        )

    stop_reason = map_openai_finish_reason_to_anthropic(choice.get("finish_reason"))
    if any(block.get("type") == "tool_use" for block in content_blocks) and stop_reason in {None, "end_turn"}:
        stop_reason = "tool_use"

    usage = build_anthropic_usage_from_openai(response_body, request_payload)
    return {
        "id": response_body.get("id", f"msg_{uuid.uuid4().hex[:24]}"),
        "type": "message",
        "role": "assistant",
        "model": response_body.get("model"),
        "content": content_blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": usage,
    }


def build_anthropic_error_payload(
    *,
    status_code: int,
    message: str,
    retry_count: int,
    preview: str,
) -> dict:
    if status_code in {408, 504, 524}:
        error_type = "overloaded_error"
    elif status_code == 429:
        error_type = "rate_limit_error"
    else:
        error_type = "api_error"

    payload = {
        "type": "error",
        "error": {
            "type": error_type,
            "message": message,
        },
        "proxy_retries": retry_count,
        "upstream_status": status_code,
    }
    if preview:
        payload["upstream_preview"] = preview
    return payload
