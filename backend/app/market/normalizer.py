from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_symbol(value: Any) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6)


def normalize_history_rows(
    rows: Any,
    symbol: str,
    interval: str,
    adjust: str,
    name: str | None = None,
    source: str = "akshare.stock_zh_a_hist",
    fetch_time: str | None = None,
) -> list[dict[str, Any]]:
    fetched_at = fetch_time or utc_now()
    normalized_symbol = normalize_symbol(symbol)
    result: list[dict[str, Any]] = []
    for row in _records(rows):
        bar = {
            "symbol": normalized_symbol,
            "name": name,
            "interval": interval,
            "datetime": _date_string(row.get("日期") or row.get("date")),
            "open": _number(row.get("开盘") or row.get("open")),
            "high": _number(row.get("最高") or row.get("high")),
            "low": _number(row.get("最低") or row.get("low")),
            "close": _number(row.get("收盘") or row.get("close")),
            "volume": _number(row.get("成交量") or row.get("volume")),
            "amount": _number(row.get("成交额") or row.get("amount")),
            "adjust": adjust or "",
            "source": source,
            "fetch_time": fetched_at,
        }
        bar["raw_hash"] = raw_hash(bar)
        result.append(bar)
    return result


def normalize_spot_rows(
    rows: Any,
    source: str = "akshare.stock_zh_a_spot_em",
    fetch_time: str | None = None,
) -> list[dict[str, Any]]:
    fetched_at = fetch_time or utc_now()
    result: list[dict[str, Any]] = []
    for row in _records(rows):
        quote = {
            "symbol": normalize_symbol(row.get("代码") or row.get("symbol")),
            "name": _text(row.get("名称") or row.get("name")),
            "price": _number(row.get("最新价") or row.get("price")),
            "open": _number(row.get("今开") or row.get("open")),
            "high": _number(row.get("最高") or row.get("high")),
            "low": _number(row.get("最低") or row.get("low")),
            "previous_close": _number(row.get("昨收") or row.get("previous_close")),
            "volume": _number(row.get("成交量") or row.get("volume")),
            "amount": _number(row.get("成交额") or row.get("amount")),
            "source": source,
            "fetch_time": fetched_at,
        }
        quote["raw_hash"] = raw_hash(quote)
        result.append(quote)
    return result


def raw_hash(payload: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in payload.items()
        if key not in {"fetch_time", "raw_hash"}
    }
    content = json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _records(rows: Any) -> list[dict[str, Any]]:
    if rows is None:
        return []
    if hasattr(rows, "to_dict"):
        return rows.to_dict(orient="records")
    return list(rows)


def _date_string(value: Any) -> str:
    if value is None:
        raise ValueError("Market bar row is missing datetime/date.")
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in {"", "-", "--", "None", "nan", "NaN"}:
        return None
    try:
        number = float(text.replace(",", ""))
    except ValueError:
        return None
    if number != number:
        return None
    return number


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
