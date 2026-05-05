from __future__ import annotations

import asyncio
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.market.normalizer import normalize_bid_ask_quote, normalize_history_rows, normalize_symbol


class AKShareMarketProvider:
    source = "akshare"

    async def quote(self, symbol: str) -> dict[str, Any]:
        return await run_in_threadpool(self.quote_sync, symbol)

    def quote_sync(self, symbol: str) -> dict[str, Any]:
        ak = self._akshare()
        normalized_symbol = normalize_symbol(symbol)
        frame = ak.stock_bid_ask_em(symbol=normalized_symbol)
        quote = normalize_bid_ask_quote(frame, symbol=normalized_symbol)
        if quote["price"] is None:
            raise LookupError(f"Symbol not found in AKShare quote data: {normalized_symbol}")
        return quote

    async def quotes_batch(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        unique_symbols = list(dict.fromkeys(normalize_symbol(symbol) for symbol in symbols))
        results = await asyncio.gather(
            *(self.quote(symbol) for symbol in unique_symbols),
            return_exceptions=True,
        )
        return {
            symbol: quote
            for symbol, quote in zip(unique_symbols, results, strict=False)
            if isinstance(quote, dict)
        }

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
        frame = ak.stock_zh_a_hist(
            symbol=normalized_symbol,
            period="daily",
            start_date=self._ak_date(start),
            end_date=self._ak_date(end),
            adjust=adjust or "",
        )
        return normalize_history_rows(
            frame,
            symbol=normalized_symbol,
            interval=interval,
            adjust=adjust or "",
        )

    async def minute(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise NotImplementedError("Minute history is reserved for a later phase.")

    async def announcement(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise NotImplementedError("Announcement data is reserved for a later phase.")

    def _akshare(self) -> Any:
        try:
            import akshare as ak
        except ModuleNotFoundError as exc:
            raise RuntimeError("The akshare package is required for live market provider calls.") from exc
        return ak

    def _ak_date(self, value: str) -> str:
        return value.replace("-", "")
