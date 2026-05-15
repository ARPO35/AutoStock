from __future__ import annotations

from http.client import RemoteDisconnected
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.market.names import StockNameResolver
from app.market.normalizer import (
    normalize_bid_ask_quote,
    normalize_history_rows,
    normalize_sina_quote_response,
    normalize_spot_rows,
    normalize_symbol,
    raw_hash,
)


class AKShareMarketProvider:
    source = "akshare"

    def __init__(self, name_resolver: StockNameResolver | None = None) -> None:
        self.name_resolver = name_resolver or StockNameResolver()

    async def quote(self, symbol: str) -> dict[str, Any]:
        return await run_in_threadpool(self.quote_sync, symbol)

    def quote_sync(self, symbol: str) -> dict[str, Any]:
        ak = self._akshare()
        normalized_symbol = normalize_symbol(symbol)
        try:
            name = self.name_resolver.resolve(normalized_symbol, ak)
            frame = ak.stock_bid_ask_em(symbol=normalized_symbol)
            quote = normalize_bid_ask_quote(frame, symbol=normalized_symbol, name=name)
            if quote["price"] is None:
                raise LookupError(f"AKShare quote data has no price: {normalized_symbol}")
            if not quote.get("name"):
                quote = self._enrich_missing_name_from_sina(quote)
            return quote
        except Exception as exc:
            if not isinstance(exc, LookupError) and not self._should_fallback_request_error(exc):
                raise
            return self._sina_quote_sync(normalized_symbol)

    async def quotes_batch(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        return await run_in_threadpool(self.quotes_batch_sync, symbols)

    def quotes_batch_sync(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        unique_symbols = list(dict.fromkeys(normalize_symbol(symbol) for symbol in symbols))
        if not unique_symbols:
            return {}

        try:
            quotes = self._sina_quotes_sync(unique_symbols)
        except Exception:
            quotes = {}

        for symbol in unique_symbols:
            if symbol in quotes:
                continue
            try:
                quotes[symbol] = self.quote_sync(symbol)
            except Exception:
                continue
        return {symbol: quotes[symbol] for symbol in unique_symbols if symbol in quotes}

    async def all_a_quotes(self) -> list[dict[str, Any]]:
        return await run_in_threadpool(self.all_a_quotes_sync)

    def all_a_quotes_sync(self) -> list[dict[str, Any]]:
        ak = self._akshare()
        frame = ak.stock_zh_a_spot_em()
        return normalize_spot_rows(frame)

    async def history(
        self,
        symbol: str,
        start: str,
        end: str,
        interval: str = "daily",
        adjust: str = "",
    ) -> list[dict[str, Any]]:
        return await run_in_threadpool(self.history_sync, symbol, start, end, interval, adjust)

    def history_sync(
        self,
        symbol: str,
        start: str,
        end: str,
        interval: str = "daily",
        adjust: str = "",
    ) -> list[dict[str, Any]]:
        if interval != "daily":
            raise NotImplementedError("Only daily history is implemented for AKShare MVP.")

        ak = self._akshare()
        normalized_symbol = normalize_symbol(symbol)
        name = self.name_resolver.resolve(normalized_symbol, ak)
        try:
            frame = ak.stock_zh_a_hist(
                symbol=normalized_symbol,
                period="daily",
                start_date=self._ak_date(start),
                end_date=self._ak_date(end),
                adjust=adjust or "",
            )
            source = "akshare.stock_zh_a_hist"
        except Exception as exc:
            if not self._should_fallback_request_error(exc):
                raise
            frame = self._sina_history_frame(ak, normalized_symbol, start, end, adjust or "")
            source = "akshare.stock_zh_a_daily"
        return normalize_history_rows(
            frame,
            symbol=normalized_symbol,
            interval=interval,
            adjust=adjust or "",
            name=name,
            source=source,
        )

    _MINUTE_PERIODS = {"1", "5", "15", "30", "60"}

    async def minute(
        self,
        symbol: str,
        start: str,
        end: str,
        period: str = "1",
        adjust: str = "",
    ) -> list[dict[str, Any]]:
        from app.market.normalizer import normalize_minute_rows

        return await run_in_threadpool(self._minute_sync, symbol, start, end, period, adjust, normalize_minute_rows)

    def _minute_sync(
        self,
        symbol: str,
        start: str,
        end: str,
        period: str,
        adjust: str,
        normalizer_func: Any,
    ) -> list[dict[str, Any]]:
        period = str(period).strip()
        if period not in self._MINUTE_PERIODS:
            raise ValueError(
                f"Unsupported minute period: {period!r}. Choose from {sorted(self._MINUTE_PERIODS)}."
            )

        ak = self._akshare()
        normalized_symbol = normalize_symbol(symbol)
        name = self.name_resolver.resolve(normalized_symbol, ak)

        start_dt = self._minute_datetime(start)
        end_dt = self._minute_datetime(end)

        frame = ak.stock_zh_a_hist_min_em(
            symbol=normalized_symbol,
            start_date=start_dt,
            end_date=end_dt,
            period=period,
            adjust=adjust or "",
        )
        return normalizer_func(
            frame,
            symbol=normalized_symbol,
            period=period,
            adjust=adjust or "",
            name=name,
        )

    async def announcement(
        self,
        symbol: str,
        start: str,
        end: str,
    ) -> list[dict[str, Any]]:
        from app.market.normalizer import normalize_announcement_rows

        return await run_in_threadpool(self._announcement_sync, symbol, start, end, normalize_announcement_rows)

    def _announcement_sync(
        self,
        symbol: str,
        start: str,
        end: str,
        normalizer_func: Any,
    ) -> list[dict[str, Any]]:
        ak = self._akshare()
        normalized_symbol = normalize_symbol(symbol)

        frame = ak.stock_individual_notice_report(
            security=normalized_symbol,
            symbol="全部",
            begin_date=self._ak_date(start),
            end_date=self._ak_date(end),
        )
        return normalizer_func(frame, symbol=normalized_symbol)

    @staticmethod
    def _minute_datetime(value: str) -> str:
        text = value.strip()
        if " " in text:
            return text
        return f"{text} 09:30:00"

    def _akshare(self) -> Any:
        try:
            import akshare as ak
        except ModuleNotFoundError as exc:
            raise RuntimeError("The akshare package is required for live market provider calls.") from exc
        return ak

    def _ak_date(self, value: str) -> str:
        return value.replace("-", "")

    def _sina_quote_sync(self, symbol: str) -> dict[str, Any]:
        normalized_symbol = normalize_symbol(symbol)
        quote = self._sina_quotes_sync([normalized_symbol]).get(normalized_symbol)
        if quote is None or quote["price"] is None:
            raise LookupError(f"Symbol not found in Sina quote data: {normalized_symbol}")
        return quote

    def _enrich_missing_name_from_sina(self, quote: dict[str, Any]) -> dict[str, Any]:
        symbol = normalize_symbol(quote["symbol"])
        try:
            sina_quote = self._sina_quotes_sync([symbol]).get(symbol)
        except Exception:
            return quote
        name = (sina_quote or {}).get("name")
        if not name:
            return quote
        enriched = {**quote, "name": name}
        enriched["raw_hash"] = raw_hash(enriched)
        return enriched

    def _sina_quotes_sync(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        normalized_symbols = list(dict.fromkeys(normalize_symbol(symbol) for symbol in symbols))
        if not normalized_symbols:
            return {}
        payload = self._sina_response(normalized_symbols)
        quotes = normalize_sina_quote_response(payload)
        return {
            quote["symbol"]: quote
            for quote in quotes
            if quote.get("symbol") in normalized_symbols and quote.get("price") is not None
        }

    def _sina_history_frame(
        self,
        ak: Any,
        symbol: str,
        start: str,
        end: str,
        adjust: str,
    ) -> list[dict[str, Any]]:
        frame = ak.stock_zh_a_daily(
            symbol=self._sina_code(symbol),
            start_date=self._ak_date(start),
            end_date=self._ak_date(end),
            adjust=adjust,
        )
        return self._sina_history_rows(frame)

    @staticmethod
    def _sina_history_rows(rows: Any) -> list[dict[str, Any]]:
        if rows is None:
            return []
        if hasattr(rows, "to_dict"):
            records = rows.to_dict(orient="records")
        else:
            records = list(rows)

        result: list[dict[str, Any]] = []
        for row in records:
            item = dict(row)
            volume = item.get("volume")
            if volume is not None:
                try:
                    item["volume"] = float(volume) / 100
                except (TypeError, ValueError):
                    pass
            result.append(item)
        return result

    def _sina_response(self, symbols: list[str]) -> str:
        import requests

        codes = ",".join(self._sina_code(symbol) for symbol in symbols)
        response = requests.get(
            "https://hq.sinajs.cn/list=" + codes,
            headers={
                "Referer": "https://finance.sina.com.cn/",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=5,
        )
        response.raise_for_status()
        if response.content:
            return response.content.decode("gbk", errors="replace")
        return response.text

    @staticmethod
    def _sina_code(symbol: str) -> str:
        normalized_symbol = normalize_symbol(symbol)
        if normalized_symbol.startswith(("4", "8")):
            return "bj" + normalized_symbol
        if normalized_symbol.startswith(("0", "2", "3")):
            return "sz" + normalized_symbol
        return "sh" + normalized_symbol

    @staticmethod
    def _should_fallback_request_error(exc: Exception) -> bool:
        if isinstance(exc, (ConnectionError, TimeoutError, RemoteDisconnected)):
            return True
        try:
            import requests
        except ModuleNotFoundError:
            return False
        return isinstance(exc, requests.exceptions.RequestException)
