import re
import time
from urllib.parse import urlparse, urlsplit, urlunsplit


OPENAI_IMAGE_SUBPATH = "images/generations"
GOOGLE_IMAGEN_DEFAULT_MODEL = "imagen-4.0-generate-001"
GOOGLE_GEMINI_IMAGE_DEFAULT_MODEL = "gemini-3.1-flash-image-preview"
OPENAI_IMAGE_DEFAULT_MODEL = "gpt-image-1"
DASHSCOPE_IMAGE_DEFAULT_MODEL = "qwen-image-2.0-pro"
DASHSCOPE_MULTIMODAL_PATH = "/api/v1/services/aigc/multimodal-generation/generation"
DASHSCOPE_TEXT2IMAGE_PATH = "/api/v1/services/aigc/text2image/image-synthesis"
DASHSCOPE_WAN_IMAGE_PATH = "/api/v1/services/aigc/image-generation/generation"

GOOGLE_PREDICT_PATTERN = re.compile(
    r"^models/(?P<model>[^:]+):(?P<method>predict)$",
    re.IGNORECASE,
)
GOOGLE_GENERATE_PATTERN = re.compile(
    r"^models/(?P<model>[^:]+):(?P<method>generateContent|streamGenerateContent)$",
    re.IGNORECASE,
)


def strip_slashes(value: str | None) -> str:
    return str(value or "").strip("/")


def lower_model(model: str | None) -> str:
    return str(model or "").strip().lower().removeprefix("models/")


def parse_model_from_subpath(subpath: str | None) -> str:
    normalized = strip_slashes(subpath)
    for pattern in (GOOGLE_PREDICT_PATTERN, GOOGLE_GENERATE_PATTERN):
        match = pattern.match(normalized)
        if match:
            return match.group("model").strip()
    return ""


def detect_downstream_image_protocol(subpath: str | None, payload: dict | None) -> str | None:
    normalized = strip_slashes(subpath)
    if normalized == OPENAI_IMAGE_SUBPATH:
        return "openai_images"

    if GOOGLE_PREDICT_PATTERN.match(normalized):
        return "google_imagen_predict"

    if GOOGLE_GENERATE_PATTERN.match(normalized):
        model = parse_model_from_subpath(normalized)
        if gemini_payload_requests_image(payload) or model_looks_image_capable(model):
            return "gemini_image_generate_content"

    if "services/aigc/" in normalized and normalized.endswith(("generation", "image-synthesis")):
        return "dashscope_image"

    return None


def model_looks_image_capable(model: str | None) -> bool:
    model_name = lower_model(model)
    return any(
        marker in model_name
        for marker in (
            "gpt-image",
            "dall-e",
            "imagen",
            "image-preview",
            "flash-image",
            "qwen-image",
            "wanx",
            "wan2",
            "wan-",
        )
    )


def gemini_payload_requests_image(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False

    generation_config = payload.get("generationConfig") or payload.get("generation_config") or {}
    if isinstance(generation_config, dict):
        modalities = (
            generation_config.get("responseModalities")
            or generation_config.get("response_modalities")
            or []
        )
        if isinstance(modalities, str):
            modalities = [modalities]
        if any(str(item).strip().lower() == "image" for item in modalities):
            return True
        image_config = generation_config.get("imageConfig") or generation_config.get("image_config")
        if isinstance(image_config, dict) and image_config:
            return True

    return False


def detect_upstream_provider(base_url: str, model: str | None, override: str = "auto") -> str:
    selected = str(override or "auto").strip().lower()
    if selected in {"openai", "google", "dashscope"}:
        return selected

    parsed = urlparse(str(base_url or ""))
    host = parsed.netloc.lower()
    path = parsed.path.lower()

    if "dashscope" in host or "aliyuncs.com" in host or "/services/aigc/" in path:
        return "dashscope"
    if "generativelanguage.googleapis.com" in host or "aiplatform.googleapis.com" in host:
        return "google"
    if "api.openai.com" in host or "openai" in host or "/images/generations" in path:
        return "openai"

    return "openai"


def first_text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [first_text(item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("text", "prompt", "content"):
            text = first_text(value.get(key))
            if text:
                return text
    return ""


def collect_gemini_text_and_images(payload: dict | None) -> tuple[str, list[str]]:
    if not isinstance(payload, dict):
        return "", []

    texts = []
    images = []
    contents = payload.get("contents") or []
    if isinstance(contents, dict):
        contents = [contents]
    if isinstance(contents, str):
        return contents.strip(), []

    for content in contents if isinstance(contents, list) else []:
        if isinstance(content, str):
            texts.append(content)
            continue
        if not isinstance(content, dict):
            continue
        parts = content.get("parts") or []
        if isinstance(parts, dict):
            parts = [parts]
        for part in parts if isinstance(parts, list) else []:
            if isinstance(part, str):
                texts.append(part)
                continue
            if not isinstance(part, dict):
                continue
            if part.get("text"):
                texts.append(str(part.get("text")))
            inline_data = part.get("inlineData") or part.get("inline_data") or {}
            if isinstance(inline_data, dict) and inline_data.get("data"):
                mime = inline_data.get("mimeType") or inline_data.get("mime_type") or "image/png"
                images.append(f"data:{mime};base64,{inline_data.get('data')}")
            file_data = part.get("fileData") or part.get("file_data") or {}
            if isinstance(file_data, dict) and file_data.get("fileUri"):
                images.append(str(file_data.get("fileUri")))
            if isinstance(file_data, dict) and file_data.get("file_uri"):
                images.append(str(file_data.get("file_uri")))

    return "\n".join(text.strip() for text in texts if text and text.strip()), images


def collect_dashscope_text_and_images(payload: dict | None) -> tuple[str, list[str]]:
    if not isinstance(payload, dict):
        return "", []

    input_payload = payload.get("input") or {}
    if isinstance(input_payload, dict):
        prompt = first_text(input_payload.get("prompt"))
        images = []
        for key in ("image", "image_url", "ref_image"):
            if input_payload.get(key):
                images.append(str(input_payload.get(key)))
        messages = input_payload.get("messages") or []
        for message in messages if isinstance(messages, list) else []:
            content_items = message.get("content") if isinstance(message, dict) else None
            if isinstance(content_items, str):
                prompt = prompt or content_items
                continue
            for item in content_items if isinstance(content_items, list) else []:
                if isinstance(item, dict):
                    if item.get("text"):
                        prompt = prompt or str(item.get("text"))
                    for key in ("image", "image_url", "ref_image"):
                        if item.get(key):
                            images.append(str(item.get(key)))
        return prompt, images

    return "", []


def extract_image_request(subpath: str, payload: dict | None, downstream_protocol: str) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    model = str(payload.get("model") or parse_model_from_subpath(subpath) or "").removeprefix("models/")
    prompt = first_text(payload.get("prompt"))
    input_images = []
    n = payload.get("n") or payload.get("num_images") or payload.get("sampleCount") or 1
    size = str(payload.get("size") or "").replace("*", "x")
    response_format = payload.get("response_format") or payload.get("responseFormat")
    quality = payload.get("quality")
    style = payload.get("style")

    if downstream_protocol == "google_imagen_predict":
        instances = payload.get("instances") or []
        parameters = payload.get("parameters") or {}
        first_instance = instances[0] if isinstance(instances, list) and instances else {}
        if isinstance(first_instance, dict):
            prompt = prompt or first_text(first_instance.get("prompt"))
        if isinstance(parameters, dict):
            n = parameters.get("sampleCount") or parameters.get("numberOfImages") or n
            size = size or aspect_ratio_to_size(parameters.get("aspectRatio"))
            quality = quality or parameters.get("imageSize")

    elif downstream_protocol == "gemini_image_generate_content":
        prompt, input_images = collect_gemini_text_and_images(payload)
        generation_config = payload.get("generationConfig") or payload.get("generation_config") or {}
        if isinstance(generation_config, dict):
            image_config = generation_config.get("imageConfig") or generation_config.get("image_config") or {}
            if isinstance(image_config, dict):
                size = size or aspect_ratio_to_size(image_config.get("aspectRatio") or image_config.get("aspect_ratio"))
                quality = quality or image_config.get("imageSize") or image_config.get("image_size")

    elif downstream_protocol == "dashscope_image":
        prompt, input_images = collect_dashscope_text_and_images(payload)
        parameters = payload.get("parameters") or {}
        if isinstance(parameters, dict):
            n = parameters.get("n") or n
            size = size or str(parameters.get("size") or "").replace("*", "x")

    return {
        "model": model,
        "prompt": prompt,
        "input_images": input_images,
        "n": coerce_positive_int(n, default=1),
        "size": size or "1024x1024",
        "response_format": response_format,
        "quality": quality,
        "style": style,
        "negative_prompt": payload.get("negative_prompt") or payload.get("negativePrompt"),
        "raw": payload,
    }


def coerce_positive_int(value, default: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def aspect_ratio_to_size(aspect_ratio: str | None) -> str:
    ratio = str(aspect_ratio or "").strip()
    mapping = {
        "1:1": "1024x1024",
        "16:9": "1792x1024",
        "9:16": "1024x1792",
        "4:3": "1024x768",
        "3:4": "768x1024",
        "3:2": "1536x1024",
        "2:3": "1024x1536",
    }
    return mapping.get(ratio, "")


def size_to_aspect_ratio(size: str | None) -> str:
    normalized = str(size or "").lower().replace("*", "x")
    parts = normalized.split("x")
    if len(parts) != 2:
        return "1:1"
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError:
        return "1:1"
    if width <= 0 or height <= 0:
        return "1:1"
    if abs(width / height - 16 / 9) < 0.12:
        return "16:9"
    if abs(width / height - 9 / 16) < 0.12:
        return "9:16"
    if abs(width / height - 4 / 3) < 0.12:
        return "4:3"
    if abs(width / height - 3 / 4) < 0.12:
        return "3:4"
    return "1:1"


def size_to_dashscope(size: str | None) -> str:
    return str(size or "1024x1024").replace("x", "*")


def build_openai_payload(image_request: dict) -> dict:
    payload = {
        "model": image_request.get("model") or OPENAI_IMAGE_DEFAULT_MODEL,
        "prompt": image_request.get("prompt") or "",
        "n": image_request.get("n") or 1,
        "size": image_request.get("size") or "1024x1024",
    }
    for key in ("response_format", "quality", "style"):
        if image_request.get(key):
            payload[key] = image_request[key]
    return payload


def build_google_payload(image_request: dict, model: str) -> tuple[str, dict]:
    model_name = lower_model(model or image_request.get("model"))
    if model_name.startswith("gemini") or "image-preview" in model_name or "flash-image" in model_name:
        generation_config = {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {
                "aspectRatio": size_to_aspect_ratio(image_request.get("size")),
            },
        }
        if image_request.get("quality"):
            generation_config["imageConfig"]["imageSize"] = str(image_request["quality"])
        return "generate_content", {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": image_request.get("prompt") or ""}],
                }
            ],
            "generationConfig": generation_config,
        }

    return "predict", {
        "instances": [{"prompt": image_request.get("prompt") or ""}],
        "parameters": {
            "sampleCount": min(max(image_request.get("n") or 1, 1), 4),
            "aspectRatio": size_to_aspect_ratio(image_request.get("size")),
        },
    }


def dashscope_uses_async_text2image(model: str | None) -> bool:
    model_name = lower_model(model)
    return (
        model_name in {"qwen-image", "qwen-image-plus", "wanx-v1"}
        or model_name.startswith("wanx-")
        or model_name.startswith("wanx_")
    )


def dashscope_uses_wan_image_generation(model: str | None) -> bool:
    model_name = lower_model(model)
    return model_name.startswith("wan2") or model_name.startswith("wan-")


def build_dashscope_payload(image_request: dict, model: str) -> tuple[str, dict]:
    model_name = model or image_request.get("model") or DASHSCOPE_IMAGE_DEFAULT_MODEL
    parameters = {
        "size": size_to_dashscope(image_request.get("size")),
        "n": image_request.get("n") or 1,
    }
    if image_request.get("negative_prompt"):
        parameters["negative_prompt"] = image_request["negative_prompt"]

    if dashscope_uses_async_text2image(model_name):
        return "text2image_async", {
            "model": model_name,
            "input": {
                "prompt": image_request.get("prompt") or "",
            },
            "parameters": parameters,
        }

    content = [{"text": image_request.get("prompt") or ""}]
    for image_url in image_request.get("input_images") or []:
        content.append({"image": image_url})
    if dashscope_uses_wan_image_generation(model_name):
        if parameters.get("size") in {"1024*1024", "1024x1024"}:
            parameters["size"] = "1K"
        parameters.setdefault("prompt_extend", True)
        parameters.setdefault("watermark", False)
        return "wan_image_async", {
            "model": model_name,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": content,
                    }
                ]
            },
            "parameters": parameters,
        }
    return "multimodal", {
        "model": model_name,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ]
        },
        "parameters": parameters,
    }


def normalize_base_url(base_url: str) -> str:
    text = str(base_url or "").strip()
    if not text:
        return ""
    parts = urlsplit(text)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), parts.query, parts.fragment))


def append_path(base_url: str, path: str) -> str:
    normalized = normalize_base_url(base_url)
    if not normalized:
        return path
    parts = urlsplit(normalized)
    suffix = path if path.startswith("/") else f"/{path}"
    current_path = parts.path.rstrip("/")
    if current_path.endswith(suffix):
        next_path = current_path
    else:
        next_path = f"{current_path}{suffix}" if current_path else suffix
    return urlunsplit((parts.scheme, parts.netloc, next_path, parts.query, parts.fragment))


def openai_image_url(base_url: str) -> str:
    return append_path(base_url, OPENAI_IMAGE_SUBPATH)


def google_endpoint_url(base_url: str, model: str, mode: str) -> str:
    base = normalize_base_url(base_url)
    if ":predict" in base or ":generateContent" in base:
        return base
    parts = urlsplit(base)
    base_path = parts.path.rstrip("/")
    if not re.search(r"/v1(?:beta|alpha)?$", base_path):
        base_path = f"{base_path}/v1beta" if base_path else "/v1beta"
    method = "generateContent" if mode == "generate_content" else "predict"
    final_path = f"{base_path}/models/{model}:{method}"
    return urlunsplit((parts.scheme, parts.netloc, final_path, parts.query, parts.fragment))


def dashscope_endpoint_path(model: str, mode: str) -> str:
    if mode == "text2image_async":
        return DASHSCOPE_TEXT2IMAGE_PATH
    if mode == "wan_image_async" or dashscope_uses_wan_image_generation(model):
        return DASHSCOPE_WAN_IMAGE_PATH
    return DASHSCOPE_MULTIMODAL_PATH


def dashscope_endpoint_url(base_url: str, model: str, mode: str) -> str:
    base = normalize_base_url(base_url)
    if "/services/aigc/" in urlparse(base).path.lower():
        return base
    return append_path(base, dashscope_endpoint_path(model, mode))


def mask_bearer(value: str | None) -> str | None:
    if not value:
        return value
    text = str(value)
    return text if text.lower().startswith("bearer ") else f"Bearer {text}"


def prepare_image_headers(headers: dict, provider: str, api_key: str | None) -> dict:
    prepared = dict(headers or {})
    prepared["Content-Type"] = "application/json"
    explicit_key = api_key

    if provider == "google":
        prepared.pop("Authorization", None)
        prepared.pop("x-api-key", None)
        prepared.pop("X-API-Key", None)
        prepared.pop("x-goog-api-key", None)
        prepared.pop("X-Goog-API-Key", None)
        if explicit_key:
            prepared["x-goog-api-key"] = explicit_key
        return prepared

    prepared.pop("x-api-key", None)
    prepared.pop("X-API-Key", None)
    prepared.pop("x-goog-api-key", None)
    prepared.pop("X-Goog-API-Key", None)
    prepared.pop("Authorization", None)
    if explicit_key:
        prepared["Authorization"] = mask_bearer(explicit_key)
    return prepared


def build_image_generation_plan(
    *,
    subpath: str,
    payload: dict | None,
    upstream_url_pool: list[str],
    inbound_headers: dict,
    inbound_params: list[tuple[str, str]],
    api_key: str | None,
    upstream_protocol_override: str = "auto",
) -> dict:
    downstream_protocol = detect_downstream_image_protocol(subpath, payload) or "openai_images"
    image_request = extract_image_request(subpath, payload, downstream_protocol)
    first_base_url = upstream_url_pool[0] if upstream_url_pool else ""
    provider = detect_upstream_provider(
        first_base_url,
        image_request.get("model"),
        override=upstream_protocol_override,
    )

    if provider == "google":
        requested_model = lower_model(image_request.get("model"))
        model = image_request.get("model") or GOOGLE_IMAGEN_DEFAULT_MODEL
        if requested_model and not (
            requested_model.startswith("imagen")
            or requested_model.startswith("gemini")
            or "image-preview" in requested_model
            or "flash-image" in requested_model
        ):
            model = GOOGLE_IMAGEN_DEFAULT_MODEL
        google_mode, upstream_payload = build_google_payload(image_request, model)
        upstream_urls = [
            google_endpoint_url(base_url, model, google_mode)
            for base_url in upstream_url_pool
        ]
        image_request["model"] = model
        provider_mode = google_mode
    elif provider == "dashscope":
        requested_model = lower_model(image_request.get("model"))
        model = image_request.get("model") or DASHSCOPE_IMAGE_DEFAULT_MODEL
        if requested_model and not (
            requested_model.startswith("qwen-image")
            or requested_model.startswith("wanx")
            or requested_model.startswith("wan2")
            or requested_model.startswith("wan-")
        ):
            model = DASHSCOPE_IMAGE_DEFAULT_MODEL
        provider_mode, upstream_payload = build_dashscope_payload(image_request, model)
        upstream_urls = [
            dashscope_endpoint_url(base_url, model, provider_mode)
            for base_url in upstream_url_pool
        ]
        image_request["model"] = model
    else:
        provider = "openai"
        image_request["model"] = image_request.get("model") or OPENAI_IMAGE_DEFAULT_MODEL
        upstream_payload = build_openai_payload(image_request)
        upstream_urls = [openai_image_url(base_url) for base_url in upstream_url_pool]
        provider_mode = "images_generations"

    headers = prepare_image_headers(inbound_headers, provider, api_key)
    if provider == "dashscope" and provider_mode in {"text2image_async", "wan_image_async"}:
        headers["X-DashScope-Async"] = "enable"

    return {
        "provider": provider,
        "provider_mode": provider_mode,
        "downstream_protocol": downstream_protocol,
        "image_request": image_request,
        "upstream_payload": upstream_payload,
        "upstream_urls": list(dict.fromkeys(upstream_urls)),
        "headers": headers,
        "params": inbound_params,
    }


def extract_images_from_openai(body: dict) -> tuple[list[dict], str | None]:
    data = body.get("data") if isinstance(body, dict) else []
    images = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        image = {}
        if item.get("url"):
            image["url"] = item["url"]
        if item.get("b64_json"):
            image["b64_json"] = item["b64_json"]
        if item.get("revised_prompt"):
            image["revised_prompt"] = item["revised_prompt"]
        if image:
            images.append(image)
    return images, None


def extract_images_from_google(body: dict) -> tuple[list[dict], str | None]:
    images = []
    text_parts = []
    predictions = body.get("predictions") if isinstance(body, dict) else []
    for prediction in predictions if isinstance(predictions, list) else []:
        if not isinstance(prediction, dict):
            continue
        b64 = (
            prediction.get("bytesBase64Encoded")
            or prediction.get("imageBytes")
            or ((prediction.get("image") or {}).get("imageBytes") if isinstance(prediction.get("image"), dict) else None)
        )
        if b64:
            images.append({"b64_json": b64})

    for candidate in body.get("candidates", []) if isinstance(body, dict) else []:
        content = candidate.get("content") if isinstance(candidate, dict) else {}
        for part in (content or {}).get("parts", []) if isinstance(content, dict) else []:
            if not isinstance(part, dict):
                continue
            if part.get("text"):
                text_parts.append(str(part["text"]))
            inline_data = part.get("inlineData") or part.get("inline_data") or {}
            if isinstance(inline_data, dict) and inline_data.get("data"):
                images.append({"b64_json": inline_data["data"]})
            file_data = part.get("fileData") or part.get("file_data") or {}
            if isinstance(file_data, dict) and (file_data.get("fileUri") or file_data.get("file_uri")):
                images.append({"url": file_data.get("fileUri") or file_data.get("file_uri")})
    return images, "\n".join(text_parts) if text_parts else None


def extract_images_from_dashscope(body: dict) -> tuple[list[dict], str | None]:
    images = []
    text_parts = []
    output = body.get("output") if isinstance(body, dict) else {}
    if not isinstance(output, dict):
        return images, None

    for result in output.get("results", []) if isinstance(output.get("results"), list) else []:
        if not isinstance(result, dict):
            continue
        url = result.get("url") or result.get("image_url") or result.get("image")
        if url:
            images.append({"url": url})

    for choice in output.get("choices", []) if isinstance(output.get("choices"), list) else []:
        message = choice.get("message") if isinstance(choice, dict) else {}
        content_items = (message or {}).get("content") if isinstance(message, dict) else []
        for item in content_items if isinstance(content_items, list) else []:
            if not isinstance(item, dict):
                continue
            if item.get("text"):
                text_parts.append(str(item["text"]))
            url = item.get("image") or item.get("image_url") or item.get("url")
            if url:
                images.append({"url": url})
            if item.get("b64_json"):
                images.append({"b64_json": item.get("b64_json")})

    task_id = output.get("task_id") or body.get("task_id")
    if task_id and not images:
        return [], f"task_id:{task_id}"
    return images, "\n".join(text_parts) if text_parts else None


def extract_images(provider: str, body: dict) -> tuple[list[dict], str | None]:
    if provider == "google":
        return extract_images_from_google(body)
    if provider == "dashscope":
        return extract_images_from_dashscope(body)
    return extract_images_from_openai(body)


def image_to_gemini_part(image: dict) -> dict:
    if image.get("b64_json"):
        return {
            "inlineData": {
                "mimeType": "image/png",
                "data": image["b64_json"],
            }
        }
    if image.get("url"):
        return {
            "fileData": {
                "mimeType": "image/png",
                "fileUri": image["url"],
            }
        }
    return {"text": ""}


def image_to_dashscope_item(image: dict) -> dict:
    if image.get("url"):
        return {"image": image["url"]}
    if image.get("b64_json"):
        return {"image": f"data:image/png;base64,{image['b64_json']}"}
    return {}


def normalize_image_generation_response(upstream_body: dict, plan: dict, request_id: str) -> dict:
    provider = plan.get("provider") or "openai"
    downstream = plan.get("downstream_protocol") or "openai_images"
    image_request = plan.get("image_request") or {}
    images, text = extract_images(provider, upstream_body if isinstance(upstream_body, dict) else {})
    created = int(time.time())

    if downstream == "gemini_image_generate_content":
        parts = []
        if text and not text.startswith("task_id:"):
            parts.append({"text": text})
        parts.extend(image_to_gemini_part(image) for image in images)
        if not parts and text:
            parts.append({"text": text})
        return {
            "candidates": [
                {
                    "index": 0,
                    "content": {
                        "role": "model",
                        "parts": parts or [{"text": ""}],
                    },
                    "finishReason": "STOP",
                }
            ],
            "modelVersion": image_request.get("model"),
        }

    if downstream == "google_imagen_predict":
        return {
            "predictions": [
                {
                    **({"bytesBase64Encoded": image["b64_json"]} if image.get("b64_json") else {}),
                    **({"imageUri": image["url"], "url": image["url"]} if image.get("url") else {}),
                    "mimeType": "image/png",
                }
                for image in images
            ],
        }

    if downstream == "dashscope_image":
        return {
            "request_id": request_id,
            "output": {
                "choices": [
                    {
                        "message": {
                            "content": [
                                item
                                for item in (image_to_dashscope_item(image) for image in images)
                                if item
                            ]
                        }
                    }
                ],
            },
            "usage": upstream_body.get("usage", {}) if isinstance(upstream_body, dict) else {},
        }

    data = []
    for image in images:
        item = {}
        if image.get("url"):
            item["url"] = image["url"]
        if image.get("b64_json"):
            item["b64_json"] = image["b64_json"]
        if image.get("revised_prompt"):
            item["revised_prompt"] = image["revised_prompt"]
        if item:
            data.append(item)

    body = {
        "created": created,
        "data": data,
    }
    if text and text.startswith("task_id:"):
        body["task_id"] = text.split(":", 1)[1]
        body["status"] = "PENDING"
    if isinstance(upstream_body, dict) and upstream_body.get("usage"):
        body["usage"] = upstream_body["usage"]
    return body


def extract_dashscope_task_id(body: dict) -> str:
    if not isinstance(body, dict):
        return ""
    output = body.get("output") if isinstance(body.get("output"), dict) else {}
    return str(output.get("task_id") or body.get("task_id") or "").strip()


def dashscope_task_status_url(first_upstream_url: str, task_id: str) -> str:
    parsed = urlparse(first_upstream_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    return f"{root}/api/v1/tasks/{task_id}"


def dashscope_body_has_images(body: dict) -> bool:
    images, _ = extract_images_from_dashscope(body if isinstance(body, dict) else {})
    return bool(images)
