from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_WRITE_LOCK = threading.Lock()


def write_stock_data_api_log(
    event: str,
    payload: Any,
    ok: bool = True,
    error: Any = None,
) -> Path | None:
    now = datetime.now(SHANGHAI_TZ)
    line = {
        "timestamp": now.isoformat(),
        "event": event,
        "ok": bool(ok),
        "payload": _jsonable(payload),
        "error": _format_error(error),
    }
    path = stock_data_api_log_dir() / f"{now.date().isoformat()}.log"
    try:
        with _WRITE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, ensure_ascii=False, default=repr))
                handle.write("\n")
    except OSError:
        return None
    return path


def stock_data_api_log_dir() -> Path:
    root = Path(os.getenv("AUTOSTOCK_STOCK_DATA_API_LOG_ROOT", "logs"))
    if not root.is_absolute():
        root = repo_root() / root
    return root / "stock_data_api"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _format_error(error: Any) -> Any:
    if error is None:
        return None
    if isinstance(error, BaseException):
        return {"type": type(error).__name__, "message": str(error)}
    return _jsonable(error)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)
