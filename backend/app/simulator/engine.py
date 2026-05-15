from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.market.akshare_provider import AKShareMarketProvider
from app.simulator.replay_clock import iso_seconds, parse_clock_time
from app.simulator.rules import A_SHARE_TIMEZONE, TradingRules, TradingRuleError
from app.storage.sqlite import SQLiteStore


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def cn_today() -> str:
    return datetime.now(A_SHARE_TIMEZONE).date().isoformat()


def resolve_runtime_time(value: str | datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(A_SHARE_TIMEZONE)
    return parse_clock_time(value)


class SimulatorEngine:
    def __init__(
        self,
        store: SQLiteStore,
        market_provider: AKShareMarketProvider,
        enforce_trading_hours: bool = True,
    ) -> None:
        self.store = store
        self.market_provider = market_provider
        self.rules = TradingRules(enforce_trading_hours=enforce_trading_hours)

    def create_account(
        self,
        name: str,
        initial_cash: float = 1_000_000,
        commission_rate: float = 0.00025,
        min_commission: float = 5.0,
    ) -> dict[str, object]:
        account_id = uuid4().hex
        now = utc_now()
        self.store.execute(
            """
            INSERT INTO simulator_accounts (
                id, name, initial_cash, cash, frozen_cash, total_asset,
                commission_rate, min_commission, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
            """,
            (account_id, name, initial_cash, initial_cash, initial_cash, commission_rate, min_commission, now, now),
        )
        return self.get_account(account_id)

    def get_account(self, account_id: str) -> dict[str, object]:
        return _get_or_404(self.store, "simulator_accounts", account_id, "模拟账户")

    def get_positions(
        self,
        account_id: str,
        current_time: str | datetime | None = None,
    ) -> list[dict[str, object]]:
        self._rollover_t1_for_account(account_id, current_time=current_time)
        rows = self.store.fetch_all(
            """
            SELECT * FROM positions
            WHERE simulator_account_id = ?
            ORDER BY symbol ASC
            """,
            (account_id,),
        )
        normalized_rows = list(rows)
        for row in normalized_rows:
            row["name"] = _clean_stock_name(row.get("name"))
        return normalized_rows

    async def refresh_account_valuation(
        self,
        account_id: str,
        current_time: str | datetime | None = None,
        force: bool = False,
    ) -> dict[str, object]:
        self.get_account(account_id)
        positions = self.get_positions(account_id, current_time=current_time)
        if positions and (force or any(_needs_position_refresh(pos) for pos in positions)):
            symbols = [str(pos["symbol"]) for pos in positions]
            try:
                quotes = await self.market_provider.quotes_batch(symbols)
            except Exception:
                quotes = {}
            await self._refresh_positions_valuation(
                account_id,
                current_time=current_time,
                quote_overrides=quotes,
            )
            market_value = await self._calc_market_value(
                account_id,
                current_time=current_time,
                quote_overrides=quotes,
            )
        else:
            market_value = round(sum(float(pos.get("market_value") or 0) for pos in positions), 2)
        account = self.get_account(account_id)
        total_asset = round(float(account["cash"]) + market_value, 2)
        now = iso_seconds(resolve_runtime_time(current_time))
        self.store.execute(
            """
            UPDATE simulator_accounts
            SET total_asset = ?, updated_at = ?
            WHERE id = ?
            """,
            (total_asset, now, account_id),
        )
        return self.get_account(account_id)

    def get_orders(
        self, account_id: str, status: str | None = None
    ) -> list[dict[str, object]]:
        if status:
            rows = self.store.fetch_all(
                """
                SELECT * FROM orders
                WHERE simulator_account_id = ? AND status = ?
                ORDER BY created_at DESC
                """,
                (account_id, status),
            )
        else:
            rows = self.store.fetch_all(
                """
                SELECT * FROM orders
                WHERE simulator_account_id = ?
                ORDER BY created_at DESC
                """,
                (account_id,),
            )
        return list(rows)

    def get_trades(self, account_id: str) -> list[dict[str, object]]:
        rows = self.store.fetch_all(
            """
            SELECT * FROM trades
            WHERE simulator_account_id = ?
            ORDER BY traded_at DESC
            """,
            (account_id,),
        )
        return list(rows)

    async def place_buy(
        self,
        session_id: str,
        account_id: str,
        symbol: str,
        quantity: int,
        run_id: str | None = None,
        tool_call_id: str | None = None,
        current_time: str | datetime | None = None,
        quote: dict[str, object] | None = None,
    ) -> dict[str, object]:
        trade_time = resolve_runtime_time(current_time)
        self.rules.check_trading_hours(trade_time)
        self._rollover_t1_for_account(account_id, current_time=trade_time)
        self.rules.check_board_lot(quantity, "buy")

        account = self.get_account(account_id)

        if quote is None:
            quote = await self.market_provider.quote(symbol)
        self.rules.check_suspended(quote)

        price = float(quote["price"])
        prev_close = float(quote.get("previous_close", 0))
        self.rules.check_limit_up_down(price, prev_close, "buy")

        commission, tax, total_fee = self.rules.calculate_fee(
            "buy", price, quantity,
            commission_rate=float(account["commission_rate"]),
            min_commission=float(account["min_commission"]),
        )
        total_cost = price * quantity + total_fee
        cash = float(account["cash"])

        if total_cost > cash:
            raise TradingRuleError(
                f"资金不足：需要 ¥{total_cost:.2f}（含手续费 ¥{total_fee:.2f}），"
                f"可用现金 ¥{cash:.2f}。"
            )

        return await self._execute_trade(
            session_id=session_id,
            account_id=account_id,
            symbol=symbol,
            name=_clean_stock_name(quote.get("name")),
            side="buy",
            price=price,
            quantity=quantity,
            commission=commission,
            tax=tax,
            total_fee=total_fee,
            total_cost=total_cost,
            run_id=run_id,
            tool_call_id=tool_call_id,
            current_time=trade_time,
            quote_overrides={symbol: quote},
        )

    async def place_sell(
        self,
        session_id: str,
        account_id: str,
        symbol: str,
        quantity: int,
        run_id: str | None = None,
        tool_call_id: str | None = None,
        current_time: str | datetime | None = None,
        quote: dict[str, object] | None = None,
    ) -> dict[str, object]:
        trade_time = resolve_runtime_time(current_time)
        self.rules.check_trading_hours(trade_time)
        self._rollover_t1_for_account(account_id, current_time=trade_time)
        self.rules.check_board_lot(quantity, "sell")

        position = self.store.fetch_one(
            """
            SELECT * FROM positions
            WHERE simulator_account_id = ? AND symbol = ?
            """,
            (account_id, symbol),
        )
        if position is None:
            raise TradingRuleError(f"未持有 {symbol}，无法卖出。")

        available = int(position["available_quantity"])
        if available <= 0:
            raise TradingRuleError("T+1：今日买入的股票暂不可卖出（可用数量不足）。")
        if quantity > available:
            raise TradingRuleError(
                f"持仓不足：可卖出 {available} 股，委托 {quantity} 股。"
            )

        if quote is None:
            quote = await self.market_provider.quote(symbol)
        self.rules.check_suspended(quote)

        price = float(quote["price"])
        prev_close = float(quote.get("previous_close", 0))
        self.rules.check_limit_up_down(price, prev_close, "sell")

        account = self.get_account(account_id)
        commission, tax, total_fee = self.rules.calculate_fee(
            "sell", price, quantity,
            commission_rate=float(account["commission_rate"]),
            min_commission=float(account["min_commission"]),
        )
        total_proceeds = price * quantity - total_fee

        return await self._execute_trade(
            session_id=session_id,
            account_id=account_id,
            symbol=symbol,
            name=_clean_stock_name(quote.get("name")),
            side="sell",
            price=price,
            quantity=quantity,
            commission=commission,
            tax=tax,
            total_fee=total_fee,
            total_cost=total_proceeds,
            run_id=run_id,
            tool_call_id=tool_call_id,
            current_time=trade_time,
            quote_overrides={symbol: quote},
        )

    async def _execute_trade(
        self,
        session_id: str,
        account_id: str,
        symbol: str,
        name: str,
        side: str,
        price: float,
        quantity: int,
        commission: float,
        tax: float,
        total_fee: float,
        total_cost: float,
        run_id: str | None,
        tool_call_id: str | None,
        current_time: datetime,
        quote_overrides: dict[str, dict[str, object]] | None = None,
    ) -> dict[str, object]:
        now = iso_seconds(current_time)
        account = self.get_account(account_id)

        order_id = uuid4().hex
        session_id_val = session_id if session_id else None
        self.store.execute(
            """
            INSERT INTO orders (
                id, session_id, simulator_account_id, symbol, name,
                side, order_type, price, quantity, filled_quantity, status,
                run_id, tool_call_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'market', ?, ?, ?, 'filled', ?, ?, ?, ?)
            """,
            (
                order_id,
                session_id_val,
                account_id,
                symbol,
                name,
                side,
                price,
                quantity,
                quantity,
                run_id,
                tool_call_id,
                now,
                now,
            ),
        )

        trade_id = uuid4().hex
        self.store.execute(
            """
            INSERT INTO trades (
                id, order_id, session_id, simulator_account_id,
                symbol, side, price, quantity, fee, tax, run_id, tool_call_id, traded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade_id,
                order_id,
                session_id_val,
                account_id,
                symbol,
                side,
                price,
                quantity,
                commission,
                tax,
                run_id,
                tool_call_id,
                now,
            ),
        )

        if side == "buy":
            new_cash = float(account["cash"]) - total_cost
            self._update_position(account_id, symbol, name, side, price, quantity, commission, tax, current_time)
        else:
            new_cash = float(account["cash"]) + total_cost
            self._update_position(account_id, symbol, name, side, price, quantity, commission, tax, current_time)

        await self._refresh_positions_valuation(account_id, current_time=current_time, quote_overrides=quote_overrides)
        total_asset = new_cash + await self._calc_market_value(
            account_id,
            current_time=current_time,
            quote_overrides=quote_overrides,
        )
        self.store.execute(
            """
            UPDATE simulator_accounts
            SET cash = ?, total_asset = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_cash, total_asset, now, account_id),
        )

        return {
            "ok": True,
            "order": _order_dict(self.store, order_id),
            "trade": self.store.fetch_one("SELECT * FROM trades WHERE id = ?", (trade_id,)),
            "account": self.get_account(account_id),
        }

    def _update_position(
        self,
        account_id: str,
        symbol: str,
        name: str,
        side: str,
        price: float,
        quantity: int,
        commission: float,
        tax: float,
        current_time: datetime | None = None,
    ) -> None:
        now = iso_seconds(resolve_runtime_time(current_time))
        existing = self.store.fetch_one(
            "SELECT * FROM positions WHERE simulator_account_id = ? AND symbol = ?",
            (account_id, symbol),
        )

        if existing is None:
            if side == "buy":
                total_cost_new = quantity * price + commission + tax
                new_avg = round(total_cost_new / quantity, 4) if quantity > 0 else price
                self.store.execute(
                    """
                    INSERT INTO positions (
                        id, simulator_account_id, symbol, name,
                        quantity, available_quantity, avg_cost, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (uuid4().hex, account_id, symbol, name, quantity, 0, new_avg, now),
                )
            return

        old_qty = int(existing["quantity"])
        old_available = int(existing["available_quantity"])
        old_avg = float(existing["avg_cost"])
        old_name = _best_stock_name(existing.get("name"), name)

        if side == "buy":
            new_qty = old_qty + quantity
            total_cost_old = old_qty * old_avg
            total_cost_new = quantity * price + commission + tax
            new_avg = round((total_cost_old + total_cost_new) / new_qty, 4)
            new_available = old_available
        else:
            new_qty = old_qty - quantity
            if new_qty <= 0:
                self.store.execute(
                    "DELETE FROM positions WHERE id = ?",
                    (existing["id"],),
                )
                return
            new_avg = old_avg
            new_available = old_available - quantity

        self.store.execute(
            """
            UPDATE positions
            SET name = ?, quantity = ?, available_quantity = ?, avg_cost = ?, updated_at = ?
            WHERE id = ?
            """,
            (old_name, new_qty, new_available, new_avg, now, existing["id"]),
        )

    async def _calc_market_value(
        self,
        account_id: str,
        current_time: str | datetime | None = None,
        quote_overrides: dict[str, dict[str, object]] | None = None,
    ) -> float:
        positions = self.get_positions(account_id, current_time=current_time)
        if not positions:
            return 0.0

        symbols = [str(p["symbol"]) for p in positions]
        quotes: dict[str, dict[str, object]] | None = quote_overrides
        if quotes is None:
            try:
                quotes = await self.market_provider.quotes_batch(symbols)
            except Exception:
                quotes = None

        total_mv = 0.0
        for pos in positions:
            sym = str(pos["symbol"])
            try:
                if quotes and sym in quotes:
                    price = float(quotes[sym]["price"])
                    mv = price * int(pos["quantity"])
                else:
                    mv = float(pos.get("market_value", 0))
            except Exception:
                mv = float(pos.get("market_value", 0))
            total_mv += mv

        return round(total_mv, 2)

    async def _refresh_positions_valuation(
        self,
        account_id: str,
        current_time: str | datetime | None = None,
        quote_overrides: dict[str, dict[str, object]] | None = None,
    ) -> None:
        positions = self.get_positions(account_id, current_time=current_time)
        if not positions:
            return

        symbols = [str(p["symbol"]) for p in positions]
        quotes = quote_overrides
        if quotes is None:
            quotes = await self.market_provider.quotes_batch(symbols)
        now = iso_seconds(resolve_runtime_time(current_time))
        for pos in positions:
            symbol = str(pos["symbol"])
            quote = quotes.get(symbol) if isinstance(quotes, dict) else None
            if quote is None:
                continue
            price = float(quote["price"])
            quantity = int(pos["quantity"])
            market_value = round(price * quantity, 2)
            unrealized_pnl = round((price - float(pos["avg_cost"])) * quantity, 2)
            self.store.execute(
                """
                UPDATE positions
                SET name = ?, market_value = ?, unrealized_pnl = ?, updated_at = ?
                WHERE id = ?
                """,
                (_best_stock_name(quote.get("name"), pos.get("name")), market_value, unrealized_pnl, now, pos["id"]),
            )

    def _rollover_t1_for_account(
        self,
        account_id: str,
        current_time: str | datetime | None = None,
    ) -> None:
        today = resolve_runtime_time(current_time).date().isoformat() if current_time is not None else cn_today()
        rows = self.store.fetch_all(
            """
            SELECT id, quantity, available_quantity, updated_at
            FROM positions
            WHERE simulator_account_id = ?
            """,
            (account_id,),
        )
        for row in rows:
            quantity = int(row["quantity"])
            available = int(row["available_quantity"])
            if available >= quantity:
                continue
            updated_at = str(row.get("updated_at") or "")
            updated_day = _cn_date_from_iso(updated_at)
            if updated_day and updated_day < today:
                self.store.execute(
                    "UPDATE positions SET available_quantity = ? WHERE id = ?",
                    (quantity, row["id"]),
                )

    def cancel_order(self, order_id: str) -> dict[str, object]:
        order = self.store.fetch_one("SELECT * FROM orders WHERE id = ?", (order_id,))
        if order is None:
            raise LookupError(f"订单不存在: {order_id}")
        if order["status"] != "pending":
            raise TradingRuleError(f"订单状态为 {order['status']}，无法撤单。")

        now = utc_now()
        self.store.execute(
            "UPDATE orders SET status = 'cancelled', updated_at = ? WHERE id = ?",
            (now, order_id),
        )
        return _order_dict(self.store, order_id)

    def reset_account(self, account_id: str) -> dict[str, object]:
        account = self.get_account(account_id)
        now = utc_now()
        initial_cash = float(account["initial_cash"])
        self.store.execute(
            """
            UPDATE simulator_accounts
            SET cash = ?, frozen_cash = 0, total_asset = ?, updated_at = ?
            WHERE id = ?
            """,
            (initial_cash, initial_cash, now, account_id),
        )
        self.store.execute(
            "DELETE FROM trades WHERE simulator_account_id = ?",
            (account_id,),
        )
        self.store.execute(
            "DELETE FROM orders WHERE simulator_account_id = ?",
            (account_id,),
        )
        self.store.execute(
            "DELETE FROM positions WHERE simulator_account_id = ?",
            (account_id,),
        )
        return self.get_account(account_id)

    def delete_account(self, account_id: str) -> None:
        self.get_account(account_id)
        self.store.execute("DELETE FROM simulator_accounts WHERE id = ?", (account_id,))

    def update_account(
        self,
        account_id: str,
        name: str | None = None,
        commission_rate: float | None = None,
        min_commission: float | None = None,
    ) -> dict[str, object]:
        self.get_account(account_id)
        now = utc_now()
        setters: list[str] = []
        params: list[object] = []

        if name is not None:
            setters.append("name = ?")
            params.append(name)
        if commission_rate is not None:
            setters.append("commission_rate = ?")
            params.append(commission_rate)
        if min_commission is not None:
            setters.append("min_commission = ?")
            params.append(min_commission)

        if setters:
            setters.append("updated_at = ?")
            params.append(now)
            params.append(account_id)
            self.store.execute(
                f"UPDATE simulator_accounts SET {', '.join(setters)} WHERE id = ?",
                params,
            )

        return self.get_account(account_id)


def _get_or_404(store: SQLiteStore, table: str, row_id: str, label: str) -> dict[str, object]:
    row = store.fetch_one(f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    if row is None:
        raise LookupError(f"{label} not found: {row_id}")
    return row


def _order_dict(store: SQLiteStore, order_id: str) -> dict[str, object]:
    row = store.fetch_one("SELECT * FROM orders WHERE id = ?", (order_id,))
    if row is None:
        raise LookupError(f"订单不存在: {order_id}")
    return row


def _clean_stock_name(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text in {"", "None", "none", "null", "NULL", "nan", "NaN", "--", "-"}:
        return ""
    return text


def _best_stock_name(*values: object) -> str:
    for value in values:
        name = _clean_stock_name(value)
        if name:
            return name
    return ""


def _needs_position_refresh(position: dict[str, object]) -> bool:
    if not _clean_stock_name(position.get("name")):
        return True
    try:
        return float(position.get("market_value") or 0) <= 0
    except (TypeError, ValueError):
        return True


def _cn_date_from_iso(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).astimezone(A_SHARE_TIMEZONE).date().isoformat()
    except ValueError:
        return value[:10] if len(value) >= 10 else ""
