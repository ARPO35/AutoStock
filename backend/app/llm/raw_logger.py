from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RawLogContext = dict[str, Any]

_WRITE_LOCK = threading.Lock()
_DISABLED_VALUES = {"0", "false", "no", "off"}


def write_raw_llm_log(
    *,
    context: RawLogContext | None,
    direction: str,
    event: str,
    payload: Any,
) -> Path | None:
    if not raw_logging_enabled():
        return None

    log_dir = raw_log_dir()
    now = datetime.now(timezone.utc)
    line = {
        "timestamp": now.isoformat(),
        "session_id": None,
        "run_id": None,
        "call_index": None,
        "round_index": None,
        "provider_type": None,
        "provider_name": None,
        "provider_id": None,
        "model": None,
        "direction": direction,
        "event": event,
        "payload": _jsonable(payload),
    }
    if context:
        for key in (
            "session_id",
            "run_id",
            "call_index",
            "round_index",
            "provider_type",
            "provider_name",
            "provider_id",
            "model",
        ):
            if key in context:
                line[key] = context[key]

    path = log_dir / f"llm-api-{now.date().isoformat()}.jsonl"
    try:
        with _WRITE_LOCK:
            log_dir.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, ensure_ascii=False, default=repr))
                handle.write("\n")
    except OSError:
        return None
    return path


def raw_logging_enabled() -> bool:
    value = os.getenv("AUTOSTOCK_LLM_RAW_LOG_ENABLED", "1").strip().lower()
    return value not in _DISABLED_VALUES


def raw_log_dir() -> Path:
    configured = os.getenv("AUTOSTOCK_LLM_RAW_LOG_DIR", "logs")
    path = Path(configured)
    if path.is_absolute():
        return path
    return repo_root() / path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)
