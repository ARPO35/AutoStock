from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.simulator.engine import SimulatorEngine
from app.simulator.rules import TradingRuleError
from app.storage.sqlite import SQLiteStore


def make_store() -> SQLiteStore:
    import tempfile, os
    path = os.path.join(tempfile.gettempdir(), f"test_sim_{uuid4().hex}.db")
    store = SQLiteStore(path)
    store.initialize()
    return store


def make_quote(symbol="000001", price=12.50, preclose=12.00, volume=1000000.0, name="平安银行"):
    return {
        "symbol": symbol,
        "name": name,
        "price": price,
        "previous_close": preclose,
        "open": preclose,
        "high": price + 0.50,
        "low": price - 0.50,
        "close": price,
        "volume": volume,
        "amount": volume * price,
        "change": price - preclose,
        "pct_change": (price - preclose) / preclose * 100 if preclose else 0,
    }


def _make_engine(store, enforce_trading_hours=False):
    provider = MagicMock()
    provider.quote = AsyncMock(return_value=make_quote("000001", 12.50))
    provider.quotes_batch = AsyncMock(return_value={"000001": make_quote("000001", 12.50)})
    return SimulatorEngine(store, provider, enforce_trading_hours=enforce_trading_hours)


class TestSimulatorAccount:
    def test_create_and_get_account(self):
        store = make_store()
        engine = _make_engine(store)

        acc = engine.create_account("测试账户", initial_cash=500000, commission_rate=0.0003, min_commission=8.0)
        assert acc["name"] == "测试账户"
        assert float(acc["initial_cash"]) == 500000
        assert float(acc["cash"]) == 500000
        assert float(acc["commission_rate"]) == 0.0003
        assert float(acc["min_commission"]) == 8.0

        fetched = engine.get_account(acc["id"])
        assert fetched["id"] == acc["id"]

    def test_list_accounts(self):
        store = make_store()
        engine = _make_engine(store)

        engine.create_account("账户A")
        engine.create_account("账户B")

        rows = store.fetch_all("SELECT * FROM simulator_accounts ORDER BY created_at DESC")
        assert len(rows) == 2

    def test_update_account(self):
        store = make_store()
        engine = _make_engine(store)

        acc = engine.create_account("测试账户")
        updated = engine.update_account(acc["id"], name="新名称", commission_rate=0.0005)
        assert updated["name"] == "新名称"
        assert float(updated["commission_rate"]) == 0.0005

    def test_reset_account(self):
        store = make_store()
        engine = _make_engine(store)

        acc = engine.create_account("测试账户", initial_cash=1000000)
        asyncio.run(engine.place_buy("", acc["id"], "000001", 1000))
        engine.reset_account(acc["id"])

        acc2 = engine.get_account(acc["id"])
        assert float(acc2["cash"]) == 1000000
        assert engine.get_positions(acc["id"]) == []
        assert engine.get_orders(acc["id"]) == []

    def test_delete_account(self):
        store = make_store()
        engine = _make_engine(store)

        acc = engine.create_account("待删除")
        engine.delete_account(acc["id"])
        try:
            engine.get_account(acc["id"])
            assert False, "should raise"
        except LookupError:
            pass


class TestSimulatorBuy:
    def test_buy_success(self):
        store = make_store()
        engine = _make_engine(store)

        acc = engine.create_account("测试", initial_cash=1000000)
        result = asyncio.run(engine.place_buy("", acc["id"], "000001", 1000))

        assert result["ok"] is True
        order = result["order"]
        assert order["side"] == "buy"
        assert order["symbol"] == "000001"
        assert order["quantity"] == 1000
        assert order["status"] == "filled"

        trade = result["trade"]
        assert trade["side"] == "buy"
        assert float(trade["price"]) == 12.50
        assert int(trade["quantity"]) == 1000

        acc2 = result["account"]
        total_cost = 12.50 * 1000
        commission = max(total_cost * 0.00025, 5.0)
        assert round(float(acc2["cash"]), 2) == round(1000000 - total_cost - commission, 2)

        positions = engine.get_positions(acc["id"])
        assert len(positions) == 1
        assert positions[0]["symbol"] == "000001"
        assert int(positions[0]["quantity"]) == 1000
        assert int(positions[0]["available_quantity"]) == 0

    def test_buy_insufficient_funds(self):
        store = make_store()
        provider = MagicMock()
        provider.quote = AsyncMock(return_value=make_quote("000001", 120.0, preclose=115.0))
        engine = SimulatorEngine(store, provider, enforce_trading_hours=False)

        acc = engine.create_account("测试", initial_cash=10000)

        try:
            asyncio.run(engine.place_buy("", acc["id"], "000001", 100))
            assert False, "should raise"
        except TradingRuleError as e:
            assert "资金不足" in str(e)

    def test_buy_not_board_lot(self):
        store = make_store()
        engine = _make_engine(store)

        acc = engine.create_account("测试")

        try:
            asyncio.run(engine.place_buy("", acc["id"], "000001", 50))
            assert False, "should raise"
        except TradingRuleError as e:
            assert "整数倍" in str(e)

    def test_buy_limit_up(self):
        store = make_store()
        provider = MagicMock()
        provider.quote = AsyncMock(return_value=make_quote("000001", 13.20, preclose=12.00))
        engine = SimulatorEngine(store, provider, enforce_trading_hours=False)

        acc = engine.create_account("测试")

        try:
            asyncio.run(engine.place_buy("", acc["id"], "000001", 100))
            assert False, "should raise"
        except TradingRuleError as e:
            assert "涨停" in str(e)

    def test_buy_suspended(self):
        store = make_store()
        provider = MagicMock()
        provider.quote = AsyncMock(return_value=make_quote("000001", 0.0, preclose=12.00, volume=0))
        engine = SimulatorEngine(store, provider, enforce_trading_hours=False)

        acc = engine.create_account("测试")

        try:
            asyncio.run(engine.place_buy("", acc["id"], "000001", 100))
            assert False, "should raise"
        except TradingRuleError as e:
            assert "停牌" in str(e)

    def test_buy_multiple_average_cost(self):
        store = make_store()
        engine = _make_engine(store)

        acc = engine.create_account("测试")
        asyncio.run(engine.place_buy("", acc["id"], "000001", 1000))
        store.execute(
            "UPDATE positions SET available_quantity = quantity WHERE simulator_account_id = ?",
            (acc["id"],),
        )

        engine.market_provider.quote = AsyncMock(return_value=make_quote("000001", 10.00))
        engine.market_provider.quotes_batch = AsyncMock(return_value={"000001": make_quote("000001", 10.00)})
        asyncio.run(engine.place_buy("", acc["id"], "000001", 500))

        positions = engine.get_positions(acc["id"])
        assert int(positions[0]["quantity"]) == 1500
        expected_avg = (12.50 * 1000 + 5.0 + 10.0 * 500 + 5.0) / 1500
        assert round(float(positions[0]["avg_cost"]), 4) == round(expected_avg, 4)


class TestSimulatorSell:
    def test_sell_success(self):
        store = make_store()
        engine = _make_engine(store)

        acc = engine.create_account("测试", initial_cash=1000000)
        asyncio.run(engine.place_buy("", acc["id"], "000001", 1000))
        store.execute(
            "UPDATE positions SET available_quantity = quantity WHERE simulator_account_id = ?",
            (acc["id"],),
        )

        engine.market_provider.quote = AsyncMock(return_value=make_quote("000001", 15.00))
        result = asyncio.run(engine.place_sell("", acc["id"], "000001", 500))

        assert result["ok"] is True
        order = result["order"]
        assert order["side"] == "sell"
        assert int(order["quantity"]) == 500

        trade = result["trade"]
        assert trade["side"] == "sell"
        assert float(trade["tax"]) > 0

        positions = engine.get_positions(acc["id"])
        assert int(positions[0]["quantity"]) == 500
        assert int(positions[0]["available_quantity"]) == 500

    def test_sell_full_position(self):
        store = make_store()
        engine = _make_engine(store)

        acc = engine.create_account("测试")
        asyncio.run(engine.place_buy("", acc["id"], "000001", 100))
        store.execute(
            "UPDATE positions SET available_quantity = quantity WHERE simulator_account_id = ?",
            (acc["id"],),
        )
        asyncio.run(engine.place_sell("", acc["id"], "000001", 100))

        positions = engine.get_positions(acc["id"])
        assert positions == []

    def test_sell_no_position(self):
        store = make_store()
        engine = _make_engine(store)

        acc = engine.create_account("测试")

        try:
            asyncio.run(engine.place_sell("", acc["id"], "000001", 100))
            assert False, "should raise"
        except TradingRuleError as e:
            assert "未持有" in str(e)

    def test_sell_over_position(self):
        store = make_store()
        engine = _make_engine(store)

        acc = engine.create_account("测试")
        asyncio.run(engine.place_buy("", acc["id"], "000001", 100))

        try:
            asyncio.run(engine.place_sell("", acc["id"], "000001", 200))
            assert False, "should raise"
        except TradingRuleError as e:
            assert "T+1" in str(e)

    def test_sell_limit_down(self):
        store = make_store()
        engine = _make_engine(store)

        acc = engine.create_account("测试")
        asyncio.run(engine.place_buy("", acc["id"], "000001", 100))
        store.execute(
            "UPDATE positions SET available_quantity = quantity WHERE simulator_account_id = ?",
            (acc["id"],),
        )

        engine.market_provider.quote = AsyncMock(return_value=make_quote("000001", 10.80, preclose=12.00))
        try:
            asyncio.run(engine.place_sell("", acc["id"], "000001", 100))
            assert False, "should raise"
        except TradingRuleError as e:
            assert "跌停" in str(e)


class TestSimulatorFees:
    def test_commission_min(self):
        from app.simulator.rules import TradingRules
        rules = TradingRules(enforce_trading_hours=False)
        commission, tax, total = rules.calculate_fee("buy", 10.0, 100, 0.00025, 5.0)
        assert commission == 5.0
        assert tax == 0.0
        assert total == 5.0

    def test_commission_normal(self):
        from app.simulator.rules import TradingRules
        rules = TradingRules(enforce_trading_hours=False)
        commission, tax, total = rules.calculate_fee("buy", 10.0, 100000, 0.00025, 5.0)
        expected_comm = round(10.0 * 100000 * 0.00025, 2)
        assert commission == expected_comm
        assert tax == 0.0

    def test_stamp_tax_sell(self):
        from app.simulator.rules import TradingRules
        rules = TradingRules(enforce_trading_hours=False)
        commission, tax, total = rules.calculate_fee("sell", 10.0, 10000, 0.00025, 5.0)
        expected_tax = round(10.0 * 10000 * 0.0005, 2)
        assert tax == expected_tax


class TestSimulatorCancel:
    def test_cancel_pending(self):
        pass
