from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from app.simulator.rules import A_SHARE_TIMEZONE
from app.storage.sqlite import SQLiteStore

ClockMode = Literal["live", "replay"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_clock_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = value.strip()
        if not text:
            raise ValueError("replay_time is required.")
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=A_SHARE_TIMEZONE)
    return dt.astimezone(A_SHARE_TIMEZONE)


def iso_seconds(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=A_SHARE_TIMEZONE)
    return dt.isoformat(timespec="seconds")


@dataclass(frozen=True)
class ReplayClockSnapshot:
    account_id: str
    mode: ClockMode
    replay_time: str | None
    speed: float
    effective_time: str
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "mode": self.mode,
            "replay_time": self.replay_time,
            "speed": self.speed,
            "effective_time": self.effective_time,
            "updated_at": self.updated_at,
        }

    def runtime_context(self) -> dict[str, Any]:
        return {
            "time_mode": self.mode,
            "effective_time": self.effective_time,
            "replay_clock": self.as_dict(),
        }


class ReplayClockService:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def get_clock(self, account_id: str) -> ReplayClockSnapshot:
        self._account_or_raise(account_id)
        row = self.store.fetch_one(
            "SELECT * FROM account_replay_clocks WHERE simulator_account_id = ?",
            (account_id,),
        )
        if row is None or row.get("mode") == "live":
            now = utc_now()
            return ReplayClockSnapshot(
                account_id=account_id,
                mode="live",
                replay_time=None,
                speed=1.0,
                effective_time=iso_seconds(now.astimezone(A_SHARE_TIMEZONE)),
                updated_at=str(row["updated_at"]) if row else iso_seconds(now),
            )

        base_replay_time = parse_clock_time(str(row["base_replay_time"]))
        base_real_time = parse_clock_time(str(row["base_real_time"])).astimezone(timezone.utc)
        speed = float(row["speed"])
        now = utc_now()
        effective = base_replay_time + timedelta(seconds=(now - base_real_time).total_seconds() * speed)
        return ReplayClockSnapshot(
            account_id=account_id,
            mode="replay",
            replay_time=iso_seconds(base_replay_time),
            speed=speed,
            effective_time=iso_seconds(effective),
            updated_at=str(row["updated_at"]),
        )

    def set_replay(
        self,
        account_id: str,
        replay_time: str | datetime | None = None,
        speed: float | None = None,
    ) -> ReplayClockSnapshot:
        self._account_or_raise(account_id)
        current = self.get_clock(account_id)
        base_time = parse_clock_time(replay_time) if replay_time is not None else parse_clock_time(current.effective_time)
        next_speed = current.speed if speed is None else float(speed)
        if next_speed < 0:
            raise ValueError("speed must be greater than or equal to 0.")

        now = utc_now()
        updated_at = iso_seconds(now)
        self.store.execute(
            """
            INSERT INTO account_replay_clocks (
                simulator_account_id, mode, base_replay_time, base_real_time,
                speed, updated_at
            )
            VALUES (?, 'replay', ?, ?, ?, ?)
            ON CONFLICT(simulator_account_id) DO UPDATE SET
                mode = excluded.mode,
                base_replay_time = excluded.base_replay_time,
                base_real_time = excluded.base_real_time,
                speed = excluded.speed,
                updated_at = excluded.updated_at
            """,
            (
                account_id,
                iso_seconds(base_time),
                iso_seconds(now),
                next_speed,
                updated_at,
            ),
        )
        return self.get_clock(account_id)

    def set_live(self, account_id: str) -> ReplayClockSnapshot:
        self._account_or_raise(account_id)
        now = utc_now()
        self.store.execute(
            """
            INSERT INTO account_replay_clocks (
                simulator_account_id, mode, base_replay_time, base_real_time,
                speed, updated_at
            )
            VALUES (?, 'live', NULL, ?, 1, ?)
            ON CONFLICT(simulator_account_id) DO UPDATE SET
                mode = excluded.mode,
                base_replay_time = excluded.base_replay_time,
                base_real_time = excluded.base_real_time,
                speed = excluded.speed,
                updated_at = excluded.updated_at
            """,
            (account_id, iso_seconds(now), iso_seconds(now)),
        )
        return self.get_clock(account_id)

    def _account_or_raise(self, account_id: str) -> dict[str, Any]:
        row = self.store.fetch_one("SELECT id FROM simulator_accounts WHERE id = ?", (account_id,))
        if row is None:
            raise LookupError(f"Simulator account not found: {account_id}")
        return row
