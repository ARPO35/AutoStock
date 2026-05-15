from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RawLogContext = dict[str, Any]

_WRITE_LOCK = threading.Lock()
_DISABLED_VALUES = {"0", "false", "no", "off"}
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


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
        "session_created_at": None,
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
            "session_created_at",
        ):
            if key in context:
                line[key] = context[key]

    path = _raw_log_path(log_dir=log_dir, context=context, now=now)
    try:
        with _WRITE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
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


def _raw_log_path(
    *,
    log_dir: Path,
    context: RawLogContext | None,
    now: datetime,
) -> Path:
    session_id = _safe_filename_part((context or {}).get("session_id") or "no-session")
    created_at = (context or {}).get("session_created_at")
    timestamp = _format_log_timestamp(created_at, fallback=now)
    return log_dir / "llm" / f"{session_id}-{timestamp}.jsonl"


def _format_log_timestamp(value: Any, *, fallback: datetime) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        raw = value.strip()
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return _safe_filename_part(raw)
    else:
        parsed = fallback
    return parsed.strftime("%Y-%m-%d--%H-%M-%S")


def _safe_filename_part(value: Any) -> str:
    cleaned = _SAFE_FILENAME_RE.sub("-", str(value).strip()).strip(".-")
    return cleaned or "unknown"


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
