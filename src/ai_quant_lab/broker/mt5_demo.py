from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from numbers import Real
from pathlib import Path
from threading import RLock
from typing import Literal, Protocol, SupportsFloat, SupportsInt, cast

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.models import MarketBar


class DemoTradingBlockedError(RuntimeError):
    """Raised when a connection or order violates demo-only policy."""


class DemoOrderSide(StrEnum):
    """Supported demo market-order directions."""

    BUY = "buy"
    SELL = "sell"


class DemoGatewayConfig(BaseModel):
    """Environment-safe MT5 terminal and demo execution settings."""

    model_config = ConfigDict(frozen=True)

    terminal_path: Path | None = None
    login: int | None = Field(default=None, gt=0)
    password: str | None = Field(default=None, repr=False, exclude=True)
    server: str | None = None
    timeout_ms: int = Field(default=60_000, gt=0, le=300_000)
    portable: bool = False
    symbol_suffix: str = ""
    filling_mode: Literal["ioc", "fok", "return"] = "ioc"
    demo_orders_enabled: bool = False
    maximum_volume_lots: float = Field(default=0.10, gt=0, le=1.0)
    maximum_spread_points: float = Field(default=50.0, gt=0)
    maximum_quote_age_seconds: float = Field(default=30.0, gt=0)
    confirmation_phrase: str = "DEMO ONLY"
    magic_number: int = Field(default=260801, ge=1)
    audit_database: Path = Path("data/demo/audit.sqlite3")

    @classmethod
    def from_environment(cls) -> DemoGatewayConfig:
        """Read credentials from the process environment without persisting them."""

        login_text = os.getenv("AI_QUANT_MT5_LOGIN", "").strip()
        timeout_text = os.getenv("AI_QUANT_MT5_TIMEOUT_MS", "60000").strip()
        maximum_volume_text = os.getenv("AI_QUANT_DEMO_MAX_VOLUME", "0.10").strip()
        maximum_spread_text = os.getenv("AI_QUANT_DEMO_MAX_SPREAD_POINTS", "50").strip()

        try:
            login = int(login_text) if login_text else None
            timeout_ms = int(timeout_text)
            maximum_volume = float(maximum_volume_text)
            maximum_spread = float(maximum_spread_text)
        except ValueError as error:
            raise ValueError("One or more AI Quant MT5 numeric environment values are invalid.") from error

        terminal_text = os.getenv("AI_QUANT_MT5_TERMINAL_PATH", "").strip()

        return cls(
            terminal_path=Path(terminal_text) if terminal_text else None,
            login=login,
            password=os.getenv("AI_QUANT_MT5_PASSWORD") or None,
            server=os.getenv("AI_QUANT_MT5_SERVER") or None,
            timeout_ms=timeout_ms,
            portable=_environment_bool("AI_QUANT_MT5_PORTABLE", default=False),
            symbol_suffix=os.getenv("AI_QUANT_MT5_SYMBOL_SUFFIX", "").strip(),
            filling_mode=cast(
                Literal["ioc", "fok", "return"],
                os.getenv("AI_QUANT_MT5_FILLING_MODE", "ioc").strip().casefold(),
            ),
            demo_orders_enabled=_environment_bool(
                "AI_QUANT_ENABLE_DEMO_ORDERS",
                default=False,
            ),
            maximum_volume_lots=maximum_volume,
            maximum_spread_points=maximum_spread,
            audit_database=Path(
                os.getenv("AI_QUANT_DEMO_AUDIT_DATABASE", "data/demo/audit.sqlite3")
            ),
        )


class DemoAccountSnapshot(BaseModel):
    """Sanitized state of the currently connected demo account."""

    model_config = ConfigDict(frozen=True)

    login_last_four: str
    server: str
    name: str
    currency: str
    balance: float
    equity: float
    margin_free: float
    leverage: int = Field(ge=0)
    trade_allowed: bool
    connected_at: datetime
    account_type: str = "demo"


class DemoConnectionStatus(BaseModel):
    """Connection health returned to the local UI and agents."""

    model_config = ConfigDict(frozen=True)

    available: bool
    connected: bool
    message: str
    account: DemoAccountSnapshot | None = None


class DemoQuoteSnapshot(BaseModel):
    """Validated latest bid/ask quote from a connected demo terminal."""

    model_config = ConfigDict(frozen=True)

    pair: ForexPair
    symbol: str
    timestamp: datetime
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    spread_points: float = Field(ge=0)


class DemoPositionSnapshot(BaseModel):
    """Sanitized open position visible on the demo account."""

    model_config = ConfigDict(frozen=True)

    ticket: int
    symbol: str
    side: DemoOrderSide
    volume_lots: float = Field(gt=0)
    open_price: float = Field(gt=0)
    current_price: float = Field(gt=0)
    stop_loss: float = Field(ge=0)
    take_profit: float = Field(ge=0)
    profit: float


class DemoOrderIntent(BaseModel):
    """Human-authorized market order permitted only on a demo account."""

    model_config = ConfigDict(frozen=True)

    pair: ForexPair
    side: DemoOrderSide
    volume_lots: float = Field(gt=0)
    stop_loss_points: float = Field(gt=0)
    take_profit_points: float = Field(gt=0)
    deviation_points: int = Field(default=20, ge=0, le=200)
    client_order_id: str = Field(default="manual_demo", min_length=1, max_length=24)


class DemoOrderReceipt(BaseModel):
    """Append-only result returned by MT5 after a guarded demo request."""

    model_config = ConfigDict(frozen=True)

    order_id: int = Field(ge=0)
    deal_id: int = Field(ge=0)
    result_code: int
    message: str
    pair: ForexPair
    symbol: str
    side: DemoOrderSide
    volume_lots: float
    requested_price: float
    filled_price: float
    submitted_at: datetime


class DemoAuditRecord(BaseModel):
    """Immutable sanitized demo connectivity or order audit event."""

    model_config = ConfigDict(frozen=True)

    record_id: str
    event_type: str
    message: str
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DemoAuditStore:
    """Append-only SQLite audit store that never receives account passwords."""

    def __init__(self, path: str | Path = "data/demo/audit.sqlite3") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    def append(
        self,
        *,
        event_type: str,
        message: str,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> DemoAuditRecord:
        """Append one sanitized event and return the persisted model."""

        record = DemoAuditRecord(
            record_id=self._next_id(),
            event_type=event_type,
            message=message,
            metadata=metadata or {},
        )

        with self._connection() as connection:
            connection.execute(
                "INSERT INTO demo_audit(record_id, payload, created_at) VALUES (?, ?, ?)",
                (record.record_id, record.model_dump_json(), record.created_at.isoformat()),
            )

        return record

    def recent(self, limit: int = 100) -> tuple[DemoAuditRecord, ...]:
        """Return recent events newest first."""

        if limit < 1 or limit > 1_000:
            raise ValueError("Demo audit limit must be between one and one thousand.")

        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM demo_audit ORDER BY created_at DESC, record_id DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return tuple(DemoAuditRecord.model_validate_json(row[0]) for row in rows)

    def _next_id(self) -> str:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) FROM demo_audit").fetchone()

        count = int(row[0]) if row is not None else 0

        return f"demo_audit_{count + 1:09d}"

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS demo_audit (
                    record_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = sqlite3.connect(self.path)

            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()


class MetaTrader5TradingApi(Protocol):
    """Subset of the MT5 Python API required by the guarded demo gateway."""

    ACCOUNT_TRADE_MODE_DEMO: int
    TRADE_ACTION_DEAL: int
    ORDER_TYPE_BUY: int
    ORDER_TYPE_SELL: int
    ORDER_TIME_GTC: int
    ORDER_FILLING_FOK: int
    ORDER_FILLING_IOC: int
    ORDER_FILLING_RETURN: int
    TRADE_RETCODE_DONE: int
    TRADE_RETCODE_DONE_PARTIAL: int
    TRADE_RETCODE_PLACED: int
    TIMEFRAME_M1: int
    TIMEFRAME_M5: int
    TIMEFRAME_M15: int
    TIMEFRAME_H1: int
    TIMEFRAME_H4: int
    TIMEFRAME_D1: int

    def initialize(self, *args: object, **kwargs: object) -> bool: ...

    def shutdown(self) -> None: ...

    def last_error(self) -> tuple[int, str]: ...

    def account_info(self) -> object | None: ...

    def terminal_info(self) -> object | None: ...

    def symbol_select(self, symbol: str, enable: bool) -> bool: ...

    def symbol_info(self, symbol: str) -> object | None: ...

    def symbol_info_tick(self, symbol: str) -> object | None: ...

    def copy_rates_from_pos(
        self,
        symbol: str,
        timeframe: int,
        start_pos: int,
        count: int,
    ) -> object | None: ...

    def positions_get(self, *args: object, **kwargs: object) -> object | None: ...

    def order_check(self, request: Mapping[str, object]) -> object | None: ...

    def order_send(self, request: Mapping[str, object]) -> object | None: ...


class UnavailableTradingApi:
    """Portable placeholder used when MT5 or its Windows terminal is absent."""

    ACCOUNT_TRADE_MODE_DEMO = 0
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_PLACED = 10008
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240
    TIMEFRAME_D1 = 1440

    def initialize(self, *args: object, **kwargs: object) -> bool:
        del args, kwargs
        return False

    def shutdown(self) -> None:
        return None

    def last_error(self) -> tuple[int, str]:
        return (1, "MetaTrader5 Python package or Windows terminal is unavailable")

    def account_info(self) -> None:
        return None

    def terminal_info(self) -> None:
        return None

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        del symbol, enable
        return False

    def symbol_info(self, symbol: str) -> None:
        del symbol

    def symbol_info_tick(self, symbol: str) -> None:
        del symbol

    def copy_rates_from_pos(
        self,
        symbol: str,
        timeframe: int,
        start_pos: int,
        count: int,
    ) -> None:
        del symbol, timeframe, start_pos, count

    def positions_get(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    def order_check(self, request: Mapping[str, object]) -> None:
        del request

    def order_send(self, request: Mapping[str, object]) -> None:
        del request


try:
    import MetaTrader5 as _mt5  # type: ignore[import-not-found]

    DEFAULT_TRADING_API = cast(MetaTrader5TradingApi, _mt5)
except ModuleNotFoundError:
    DEFAULT_TRADING_API = UnavailableTradingApi()


class MT5DemoGateway:
    """Persistent MT5 connection that blocks every non-demo account."""

    def __init__(
        self,
        config: DemoGatewayConfig | None = None,
        *,
        api: MetaTrader5TradingApi | None = None,
        audit: DemoAuditStore | None = None,
    ) -> None:
        self.config = config or DemoGatewayConfig.from_environment()
        self._api = api or DEFAULT_TRADING_API
        self.audit = audit or DemoAuditStore(self.config.audit_database)
        self._lock = RLock()
        self._account: DemoAccountSnapshot | None = None

    def status(self) -> DemoConnectionStatus:
        """Return connection state and re-verify any cached account mode."""

        account = self._account

        if account is None:
            message = "MT5 demo account is not connected."
            available = not isinstance(self._api, UnavailableTradingApi)
            return DemoConnectionStatus(
                available=available,
                connected=False,
                message=message,
            )

        try:
            refreshed = self._require_connection()
        except (DemoTradingBlockedError, RuntimeError) as error:
            return DemoConnectionStatus(
                available=True,
                connected=False,
                message=str(error),
            )

        return DemoConnectionStatus(
            available=True,
            connected=True,
            message="Connected to a verified MT5 demo account.",
            account=refreshed,
        )

    def connect(self) -> DemoAccountSnapshot:
        """Connect and prove the account is demo before exposing market state."""

        with self._lock:
            if self._account is not None:
                return self._account

            options: dict[str, object] = {
                "timeout": self.config.timeout_ms,
                "portable": self.config.portable,
            }

            if self.config.login is not None:
                options["login"] = self.config.login

            if self.config.password is not None:
                options["password"] = self.config.password

            if self.config.server is not None:
                options["server"] = self.config.server

            if self.config.terminal_path is None:
                connected = self._api.initialize(**options)
            else:
                connected = self._api.initialize(str(self.config.terminal_path), **options)

            if not connected:
                raise RuntimeError(f"MT5 initialization failed: {self._last_error_text()}")

            account_info = self._api.account_info()

            if account_info is None:
                self._api.shutdown()
                raise RuntimeError(f"MT5 account information is unavailable: {self._last_error_text()}")

            account = self._verified_account_snapshot(
                account_info,
                connected_at=datetime.now(UTC),
            )
            self._account = account
            self.audit.append(
                event_type="demo_connected",
                message="Connected to a verified MT5 demo account.",
                metadata={"server": account.server, "login_last_four": account.login_last_four},
            )

            return account

    def disconnect(self) -> None:
        """Close the terminal connection without losing the audit history."""

        with self._lock:
            if self._account is None:
                return

            self._api.shutdown()
            self._account = None
            self.audit.append(
                event_type="demo_disconnected",
                message="Disconnected from the MT5 demo account.",
            )

    def latest_quote(self, pair: ForexPair) -> DemoQuoteSnapshot:
        """Return the newest bid/ask quote for a supported pair."""

        self._require_connection()
        symbol = self._symbol(pair)

        if not self._api.symbol_select(symbol, True):
            raise RuntimeError(f"MT5 could not select '{symbol}': {self._last_error_text()}")

        info = self._api.symbol_info(symbol)
        tick = self._api.symbol_info_tick(symbol)

        if info is None or tick is None:
            raise RuntimeError(f"MT5 quote for '{symbol}' is unavailable: {self._last_error_text()}")

        point = _float_field(info, "point")
        bid = _float_field(tick, "bid")
        ask = _float_field(tick, "ask")
        timestamp = datetime.fromtimestamp(_integer_field(tick, "time"), tz=UTC)

        return DemoQuoteSnapshot(
            pair=pair,
            symbol=symbol,
            timestamp=timestamp,
            bid=bid,
            ask=ask,
            spread_points=max(0.0, (ask - bid) / point),
        )

    def recent_bars(
        self,
        pair: ForexPair,
        timeframe: Timeframe,
        *,
        count: int = 300,
    ) -> tuple[MarketBar, ...]:
        """Read completed bars from the connected terminal for live monitoring."""

        if count < 2 or count > 100_000:
            raise ValueError("MT5 recent bar count must be between 2 and 100000.")

        self._require_connection()
        symbol = self._symbol(pair)

        if not self._api.symbol_select(symbol, True):
            raise RuntimeError(f"MT5 could not select '{symbol}': {self._last_error_text()}")

        rates_object = self._api.copy_rates_from_pos(
            symbol,
            self._timeframe(timeframe),
            1,
            count,
        )

        if rates_object is None:
            raise RuntimeError(f"MT5 bars for '{symbol}' are unavailable: {self._last_error_text()}")

        rates = cast(Sequence[object], rates_object)
        bars = tuple(
            MarketBar(
                pair=pair,
                timeframe=timeframe,
                timestamp=datetime.fromtimestamp(_integer_field(rate, "time"), tz=UTC),
                open=_float_field(rate, "open"),
                high=_float_field(rate, "high"),
                low=_float_field(rate, "low"),
                close=_float_field(rate, "close"),
                tick_volume=_integer_field(rate, "tick_volume"),
                real_volume=_float_field(rate, "real_volume"),
                spread_points=_float_field(rate, "spread"),
            )
            for rate in rates
        )

        return tuple(sorted(bars, key=lambda bar: bar.timestamp))

    def positions(self) -> tuple[DemoPositionSnapshot, ...]:
        """Return sanitized currently open demo positions."""

        self._require_connection()
        positions_object = self._api.positions_get()

        if positions_object is None:
            return ()

        positions = cast(Sequence[object], positions_object)

        return tuple(
            DemoPositionSnapshot(
                ticket=_integer_field(position, "ticket"),
                symbol=_text_field(position, "symbol"),
                side=(
                    DemoOrderSide.BUY
                    if _integer_field(position, "type") == self._api.ORDER_TYPE_BUY
                    else DemoOrderSide.SELL
                ),
                volume_lots=_float_field(position, "volume"),
                open_price=_float_field(position, "price_open"),
                current_price=_float_field(position, "price_current"),
                stop_loss=_float_field(position, "sl"),
                take_profit=_float_field(position, "tp"),
                profit=_float_field(position, "profit"),
            )
            for position in positions
        )

    def place_market_order(
        self,
        intent: DemoOrderIntent,
        *,
        confirmation: str,
        observed_at: datetime | None = None,
    ) -> DemoOrderReceipt:
        """Check and send one explicitly armed order to a verified demo account."""

        account = self._require_connection()

        if not self.config.demo_orders_enabled:
            raise DemoTradingBlockedError(
                "Demo order sending is disabled; set AI_QUANT_ENABLE_DEMO_ORDERS=true deliberately."
            )

        if confirmation != self.config.confirmation_phrase:
            raise DemoTradingBlockedError("The explicit demo-only confirmation phrase is missing.")

        if not account.trade_allowed:
            raise DemoTradingBlockedError("The connected demo account does not allow trading.")

        if intent.volume_lots > self.config.maximum_volume_lots:
            raise DemoTradingBlockedError(
                f"Requested volume exceeds the {self.config.maximum_volume_lots:.2f} lot demo limit."
            )

        quote = self.latest_quote(intent.pair)
        now = observed_at or datetime.now(UTC)
        quote_age = (now - quote.timestamp).total_seconds()

        if quote_age < 0 or quote_age > self.config.maximum_quote_age_seconds:
            raise DemoTradingBlockedError(f"The MT5 quote is stale ({quote_age:.3f} seconds old).")

        if quote.spread_points > self.config.maximum_spread_points:
            raise DemoTradingBlockedError(
                f"Spread {quote.spread_points:.2f} exceeds the demo safety limit."
            )

        symbol_info = self._api.symbol_info(quote.symbol)

        if symbol_info is None:
            raise RuntimeError(f"MT5 symbol information is unavailable: {self._last_error_text()}")

        self._validate_volume(intent.volume_lots, symbol_info)
        point = _float_field(symbol_info, "point")
        is_buy = intent.side is DemoOrderSide.BUY
        price = quote.ask if is_buy else quote.bid
        stop_loss = (
            price - intent.stop_loss_points * point
            if is_buy
            else price + intent.stop_loss_points * point
        )
        take_profit = (
            price + intent.take_profit_points * point
            if is_buy
            else price - intent.take_profit_points * point
        )
        request: dict[str, object] = {
            "action": self._api.TRADE_ACTION_DEAL,
            "symbol": quote.symbol,
            "volume": intent.volume_lots,
            "type": self._api.ORDER_TYPE_BUY if is_buy else self._api.ORDER_TYPE_SELL,
            "price": price,
            "sl": stop_loss,
            "tp": take_profit,
            "deviation": intent.deviation_points,
            "magic": self.config.magic_number,
            "comment": f"AIQL-{intent.client_order_id}"[:31],
            "type_time": self._api.ORDER_TIME_GTC,
            "type_filling": self._order_filling_mode(),
        }
        checked = self._api.order_check(request)

        if checked is None:
            raise RuntimeError(f"MT5 order check failed: {self._last_error_text()}")

        check_code = _integer_field(checked, "retcode")

        if check_code != 0:
            raise DemoTradingBlockedError(
                f"MT5 rejected the demo order check ({check_code}): {_text_field(checked, 'comment')}"
            )

        self._require_connection()
        result = self._api.order_send(request)

        if result is None:
            raise RuntimeError(f"MT5 demo order send failed: {self._last_error_text()}")

        result_code = _integer_field(result, "retcode")
        successful_codes = {
            self._api.TRADE_RETCODE_DONE,
            self._api.TRADE_RETCODE_DONE_PARTIAL,
            self._api.TRADE_RETCODE_PLACED,
        }

        if result_code not in successful_codes:
            raise RuntimeError(
                f"MT5 did not accept the demo order ({result_code}): {_text_field(result, 'comment')}"
            )

        receipt = DemoOrderReceipt(
            order_id=_integer_field(result, "order"),
            deal_id=_integer_field(result, "deal"),
            result_code=result_code,
            message=_text_field(result, "comment"),
            pair=intent.pair,
            symbol=quote.symbol,
            side=intent.side,
            volume_lots=intent.volume_lots,
            requested_price=price,
            filled_price=_float_field(result, "price"),
            submitted_at=now,
        )
        self.audit.append(
            event_type="demo_order_sent",
            message="A guarded market order was accepted by the verified demo account.",
            metadata={
                "order_id": receipt.order_id,
                "deal_id": receipt.deal_id,
                "pair": receipt.pair,
                "side": receipt.side,
                "volume_lots": receipt.volume_lots,
            },
        )

        return receipt

    def _require_connection(self) -> DemoAccountSnapshot:
        account = self._account

        if account is None:
            raise RuntimeError("MT5 demo account is not connected.")

        account_info = self._api.account_info()

        if account_info is None:
            self._api.shutdown()
            self._account = None
            raise RuntimeError("The MT5 terminal connection was lost.")

        refreshed = self._verified_account_snapshot(
            account_info,
            connected_at=account.connected_at,
        )
        self._account = refreshed

        return refreshed

    def _verified_account_snapshot(
        self,
        account_info: object,
        *,
        connected_at: datetime,
    ) -> DemoAccountSnapshot:
        """Prove current terminal mode and return sanitized dynamic account values."""

        trade_mode = _integer_field(account_info, "trade_mode")

        if trade_mode != self._api.ACCOUNT_TRADE_MODE_DEMO:
            self._api.shutdown()
            self._account = None
            self.audit.append(
                event_type="real_account_blocked",
                message="A non-demo MT5 account connection was blocked.",
            )
            raise DemoTradingBlockedError(
                "This gateway accepts MT5 demo accounts only; real and contest accounts are blocked."
            )

        login = _integer_field(account_info, "login")

        return DemoAccountSnapshot(
            login_last_four=str(login)[-4:].rjust(4, "*"),
            server=_text_field(account_info, "server"),
            name=_text_field(account_info, "name"),
            currency=_text_field(account_info, "currency"),
            balance=_float_field(account_info, "balance"),
            equity=_float_field(account_info, "equity"),
            margin_free=_float_field(account_info, "margin_free"),
            leverage=_integer_field(account_info, "leverage"),
            trade_allowed=_boolean_field(account_info, "trade_allowed"),
            connected_at=connected_at,
        )

    def _validate_volume(self, volume: float, symbol_info: object) -> None:
        minimum = _float_field(symbol_info, "volume_min")
        maximum = min(
            _float_field(symbol_info, "volume_max"),
            self.config.maximum_volume_lots,
        )
        step = _float_field(symbol_info, "volume_step")

        if volume < minimum or volume > maximum:
            raise DemoTradingBlockedError(
                f"Volume must be between {minimum:.2f} and {maximum:.2f} lots."
            )

        steps = round((volume - minimum) / step)
        normalized = minimum + steps * step

        if abs(normalized - volume) > 1e-9:
            raise DemoTradingBlockedError(f"Volume must follow the broker step of {step:.2f} lots.")

    def _symbol(self, pair: ForexPair) -> str:
        return f"{pair}{self.config.symbol_suffix}"

    def _timeframe(self, timeframe: Timeframe) -> int:
        return {
            "M1": self._api.TIMEFRAME_M1,
            "M5": self._api.TIMEFRAME_M5,
            "M15": self._api.TIMEFRAME_M15,
            "H1": self._api.TIMEFRAME_H1,
            "H4": self._api.TIMEFRAME_H4,
            "D1": self._api.TIMEFRAME_D1,
        }[timeframe]

    def _order_filling_mode(self) -> int:
        return {
            "fok": self._api.ORDER_FILLING_FOK,
            "ioc": self._api.ORDER_FILLING_IOC,
            "return": self._api.ORDER_FILLING_RETURN,
        }[self.config.filling_mode]

    def _last_error_text(self) -> str:
        code, message = self._api.last_error()
        return f"{code}: {message}"


def _environment_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    normalized = value.strip().casefold()

    if normalized in {"1", "true", "yes", "on"}:
        return True

    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ValueError(f"Environment variable {name} must be true or false.")


def _field(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)

        if name in mapping:
            return mapping[name]

    # MetaTrader5 returns historical rates as NumPy structured rows (``numpy.void``).
    # Those rows expose named fields through ``row["time"]`` rather than attributes
    # or the Mapping protocol. Keep this duck-typed so NumPy remains an implementation
    # detail of the API response instead of a runtime dependency of this gateway.
    get_item = getattr(value, "__getitem__", None)

    if callable(get_item):
        try:
            return get_item(name)
        except (IndexError, KeyError, TypeError, ValueError):
            pass

    try:
        return getattr(value, name)
    except AttributeError as error:
        raise RuntimeError(f"MT5 response is missing required field '{name}'.") from error


def _integer_field(value: object, name: str) -> int:
    field = _field(value, name)

    if isinstance(field, bool) or not isinstance(field, Real):
        raise TypeError(f"MT5 field '{name}' must be numeric.")

    return int(cast(SupportsInt, field))


def _float_field(value: object, name: str) -> float:
    field = _field(value, name)

    if isinstance(field, bool) or not isinstance(field, Real):
        raise TypeError(f"MT5 field '{name}' must be numeric.")

    return float(cast(SupportsFloat, field))


def _text_field(value: object, name: str) -> str:
    field = _field(value, name)

    if not isinstance(field, str):
        raise TypeError(f"MT5 field '{name}' must be text.")

    return field


def _boolean_field(value: object, name: str) -> bool:
    field = _field(value, name)

    if not isinstance(field, bool):
        raise TypeError(f"MT5 field '{name}' must be true or false.")

    return field
