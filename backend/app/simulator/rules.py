from __future__ import annotations

from datetime import datetime, time, timezone, timedelta
from math import floor


A_SHARE_TIMEZONE = timezone(timedelta(hours=8))

MORNING_START = time(9, 30)
MORNING_END = time(11, 30)
AFTERNOON_START = time(13, 0)
AFTERNOON_END = time(15, 0)

BOARD_LOT = 100
LIMIT_UP_DOWN_RATIO = 0.10

COMMISSION_DEFAULT_RATE = 0.00025
MIN_COMMISSION_DEFAULT = 5.0
STAMP_TAX_RATE = 0.0005


class TradingRules:
    def __init__(self, enforce_trading_hours: bool = True) -> None:
        self.enforce_trading_hours = enforce_trading_hours

    def check_trading_hours(self, current_time: datetime | None = None) -> None:
        if not self.enforce_trading_hours:
            return
        current = current_time or datetime.now(A_SHARE_TIMEZONE)
        if current.tzinfo is None:
            current = current.replace(tzinfo=A_SHARE_TIMEZONE)
        current = current.astimezone(A_SHARE_TIMEZONE)
        if current.weekday() >= 5:
            raise TradingRuleError("当前不是A股工作日交易时段。")
        now = current.time()
        if now < MORNING_START:
            raise TradingRuleError("尚未到交易时间（9:30 开盘）。")
        if MORNING_END <= now < AFTERNOON_START:
            raise TradingRuleError("当前为午间休市时间（11:30-13:00）。")
        if now >= AFTERNOON_END:
            raise TradingRuleError("已超过交易时间（15:00 收盘）。")

    def check_board_lot(self, quantity: int, side: str) -> None:
        if quantity <= 0:
            raise TradingRuleError("委托数量必须大于 0。")
        if side == "buy" and quantity % BOARD_LOT != 0:
            raise TradingRuleError(f"买入数量必须为 {BOARD_LOT} 股的整数倍。")

    def check_t1(self, position_available: int, side: str) -> None:
        if side == "sell" and position_available <= 0:
            raise TradingRuleError("T+1：今日买入的股票暂不可卖出（可用数量不足）。")

    def check_limit_up_down(self, quote_price: float, prev_close: float, side: str) -> None:
        if prev_close <= 0:
            return
        limit_up = round(prev_close * (1 + LIMIT_UP_DOWN_RATIO), 2)
        limit_down = round(prev_close * (1 - LIMIT_UP_DOWN_RATIO), 2)
        if side == "buy" and quote_price >= limit_up:
            raise TradingRuleError(f"涨停限制：当前价 {quote_price} 已达涨停价 {limit_up}，无法买入。")
        if side == "sell" and quote_price <= limit_down:
            raise TradingRuleError(f"跌停限制：当前价 {quote_price} 已达跌停价 {limit_down}，无法卖出。")

    def check_suspended(self, quote: dict[str, object] | None) -> None:
        if quote is None:
            raise TradingRuleError("无法获取行情数据，该股票可能停牌。")
        volume = quote.get("volume") if isinstance(quote.get("volume"), (int, float)) else 0
        price = quote.get("price") if isinstance(quote.get("price"), (int, float)) else 0
        if volume == 0 and price == 0:
            raise TradingRuleError("该股票当前处于停牌状态。")

    def calculate_fee(
        self,
        side: str,
        price: float,
        quantity: int,
        commission_rate: float,
        min_commission: float,
    ) -> tuple[float, float, float]:
        turnover = price * quantity
        commission = max(turnover * commission_rate, min_commission)
        commission = round(commission, 2)
        tax = round(turnover * STAMP_TAX_RATE, 2) if side == "sell" else 0.0
        total_fee = commission + tax
        return commission, tax, total_fee


class TradingRuleError(Exception):
    pass
