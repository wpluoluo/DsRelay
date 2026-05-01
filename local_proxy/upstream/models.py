from __future__ import annotations

import json
import re
from urllib.parse import urlsplit, urlunsplit


DEFAULT_MODEL_ALIASES_TEXT = """
deepseek-v4-flash=deepseek-ai/deepseek-v4-flash
deepseek-v4-pro=deepseek-ai/deepseek-v4-pro
""".strip()


def normalize_model_aliases_text(raw_aliases: str | None) -> str:
    raw_text = str(raw_aliases or "").strip()
    return raw_text or DEFAULT_MODEL_ALIASES_TEXT


def normalize_model_alias_key(model_name: str | None) -> str:
    normalized = str(model_name or "").strip()
    if normalized.lower().startswith("models/"):
        normalized = normalized.split("/", 1)[1]
    return normalized.lower()


def parse_model_aliases(raw_aliases: str | dict | None) -> dict[str, list[str]]:
    if isinstance(raw_aliases, dict):
        items = raw_aliases.items()
    else:
        raw_text = str(raw_aliases or "").strip()
        if not raw_text:
            return {}
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            items = parsed.items()
        else:
            pairs = []
            for raw_line in re.split(r"[\r\n;]+", raw_text):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                for separator in ("=>", "->", "="):
                    if separator in line:
                        alias, target = line.split(separator, 1)
                        pairs.append((alias, target))
                        break
                else:
                    if "," in line:
                        alias, target = line.split(",", 1)
                        pairs.append((alias, target))
            items = pairs

    aliases = {}
    for alias, target in items:
        alias_text = str(alias or "").strip()
        target_candidates = []
        if isinstance(target, list):
            target_candidates = [str(item or "").strip() for item in target]
        else:
            target_candidates = [
                item.strip()
                for item in re.split(r"[,|]+", str(target or ""))
                if item.strip()
            ]
        if not alias_text or not target_candidates:
            continue
        deduped_targets = []
        seen_targets = set()
        for target_text in target_candidates:
            target_key = normalize_model_alias_key(target_text)
            if not target_text or target_key in seen_targets:
                continue
            seen_targets.add(target_key)
            deduped_targets.append(target_text)
        if deduped_targets:
            aliases[normalize_model_alias_key(alias_text)] = deduped_targets
    return aliases


def deepseek_display_case(model_name: str) -> str:
    return re.sub(
        r"(?i)^deepseek-v4-(.+)$",
        lambda match: f"DeepSeek-V4-{match.group(1).lower()}",
        model_name,
    )


def build_related_model_name_candidates(model_name: str | None) -> list[str]:
    original = str(model_name or "").strip()
    if not original:
        return []

    candidates = []
    seen = set()

    def add(candidate: str | None) -> None:
        candidate = str(candidate or "").strip()
        if not candidate or candidate in seen:
            return
        seen.add(candidate)
        candidates.append(candidate)

    add(original)
    no_models_prefix = original.removeprefix("models/")
    add(no_models_prefix)
    namespace = ""
    base = no_models_prefix
    if "/" in no_models_prefix:
        namespace, base = no_models_prefix.rsplit("/", 1)
        add(base)

    base_lower = base.lower()
    add(base_lower)
    display_base = deepseek_display_case(base_lower)
    add(display_base)

    if base_lower.startswith("deepseek-v4-"):
        add(f"deepseek-ai/{base_lower}")
        add(f"deepseek-ai/{display_base}")
    if namespace:
        add(f"{namespace}/{base_lower}")
        add(f"{namespace}/{display_base}")

    return candidates[:12]


def dedupe_model_candidates(candidates: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for candidate in candidates:
        candidate = str(candidate or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


def normalize_model_semantic_key(model_name: str | None) -> str:
    normalized = str(model_name or "").strip().lower().removeprefix("models/")
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return re.sub(r"[^a-z0-9]+", "", normalized)


def tokenize_model_name(model_name: str | None) -> list[str]:
    normalized = str(model_name or "").strip().lower().removeprefix("models/")
    tokens = re.findall(r"[a-z]+|[0-9]+", normalized)
    ignored = {"ai", "model", "models", "provider", "openai", "google", "dashscope"}
    return [token for token in tokens if token not in ignored]


def model_semantic_match_score(reference_model: str | None, candidate_model: str | None) -> int:
    reference_key = normalize_model_semantic_key(reference_model)
    candidate_key = normalize_model_semantic_key(candidate_model)
    if not reference_key or not candidate_key:
        return 0
    if reference_key == candidate_key:
        return 100
    if candidate_key.endswith(reference_key):
        return 94
    if reference_key.endswith(candidate_key) and len(candidate_key) >= max(6, len(reference_key) * 0.72):
        return 88
    if reference_key in candidate_key:
        return 82
    if candidate_key in reference_key and len(candidate_key) >= max(6, len(reference_key) * 0.72):
        return 76

    reference_tokens = tokenize_model_name(reference_model)
    candidate_tokens = set(tokenize_model_name(candidate_model))
    if not reference_tokens or not candidate_tokens:
        return 0
    if all(token in candidate_tokens for token in reference_tokens):
        return 72

    shared = [token for token in reference_tokens if token in candidate_tokens]
    strong_tokens = [token for token in reference_tokens if len(token) > 1 or token.isdigit()]
    if strong_tokens and len(shared) == len(reference_tokens) - 1 and len(shared) >= 3:
        return 66
    return 0


def best_model_semantic_match_score(
    logical_model: str,
    configured_candidates: list[str],
    available_model: str,
) -> int:
    references = [logical_model, *configured_candidates]
    return max(
        (model_semantic_match_score(reference, available_model) for reference in references),
        default=0,
    )


def model_list_url_from_endpoint(route_url: str) -> str:
    parts = urlsplit(route_url)
    path = parts.path.rstrip("/")
    for suffix in ("/chat/completions", "/images/generations", "/completions"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    models_path = f"{path.rstrip('/')}/models" if path else "/models"
    return urlunsplit((parts.scheme, parts.netloc, models_path, "", ""))


def extract_model_ids_from_models_payload(payload) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw_models = payload.get("data") if isinstance(payload.get("data"), list) else payload.get("models")
    if not isinstance(raw_models, list):
        return []

    model_ids = []
    for item in raw_models:
        if isinstance(item, str):
            model_id = item
        elif isinstance(item, dict):
            model_id = str(item.get("id") or item.get("name") or item.get("model") or "").strip()
        else:
            model_id = ""
        if model_id:
            model_ids.append(model_id.removeprefix("models/"))
    return list(dict.fromkeys(model_ids))


def discover_model_candidates_from_models(
    logical_model: str,
    configured_candidates: list[str],
    available_models: list[str],
) -> list[str]:
    configured_keys = {normalize_model_alias_key(item) for item in configured_candidates}
    ranked = []
    for index, model_id in enumerate(available_models):
        if normalize_model_alias_key(model_id) in configured_keys:
            continue
        score = best_model_semantic_match_score(logical_model, configured_candidates, model_id)
        if score >= 72:
            ranked.append((-score, index, model_id))
    ranked.sort()
    return [model_id for _, _, model_id in ranked[:6]]
