from __future__ import annotations

import threading
from typing import Any

from app.market.normalizer import normalize_symbol


class StockNameResolver:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._names: dict[str, str] | None = None

    def resolve(self, symbol: str, akshare_module: Any) -> str | None:
        names = self._load_names(akshare_module)
        return names.get(normalize_symbol(symbol))

    def _load_names(self, akshare_module: Any) -> dict[str, str]:
        if self._names is not None:
            return self._names
        with self._lock:
            if self._names is not None:
                return self._names
            try:
                rows = akshare_module.stock_info_a_code_name()
                self._names = _parse_code_names(rows)
            except Exception:
                self._names = {}
            return self._names


def _parse_code_names(rows: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in _records(rows):
        code = _first_text(row, ("code", "symbol", "\u4ee3\u7801", "\u80a1\u7968\u4ee3\u7801"))
        name = _first_text(row, ("name", "\u540d\u79f0", "\u80a1\u7968\u7b80\u79f0"))
        if code and name:
            result[normalize_symbol(code)] = name
    return result


def _records(rows: Any) -> list[dict[str, Any]]:
    if rows is None:
        return []
    if hasattr(rows, "to_dict"):
        return rows.to_dict(orient="records")
    return list(rows)


def _first_text(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in {"None", "nan", "NaN"}:
            return text
    return None
