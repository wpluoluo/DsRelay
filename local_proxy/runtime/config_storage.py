import json
from pathlib import Path


def save_runtime_config(payload: dict, *, config_path: Path, storage, storage_key: str, logger, db_label: str) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if storage is not None:
        try:
            storage.save_app_config(payload, storage_key)
        except Exception as exc:  # pragma: no cover
            logger.warning("save_runtime_config_db_failed label=%s error=%s", db_label, str(exc))


def load_runtime_config_from_db(*, storage, storage_key: str, logger, db_label: str):
    if storage is None:
        return None
    try:
        payload = storage.load_app_config(storage_key)
    except Exception as exc:  # pragma: no cover
        logger.warning("load_runtime_config_db_failed label=%s error=%s", db_label, str(exc))
        return None
    return payload if isinstance(payload, dict) and payload else None


def load_runtime_config_from_file(*, config_path: Path, logger):
    if not config_path.exists():
        return None
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        logger.error("load_runtime_config_failed path=%s error=%s", config_path, str(exc))
        return None
    if not isinstance(payload, dict):
        logger.error("load_runtime_config_failed path=%s error=invalid_payload", config_path)
        return None
    return payload
