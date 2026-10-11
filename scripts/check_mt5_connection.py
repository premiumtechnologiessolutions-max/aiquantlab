from __future__ import annotations

import MetaTrader5 as mt5  # type: ignore[import-untyped]

TARGET_PAIRS = (
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "USDCAD",
    "AUDUSD",
    "NZDUSD",
)


def main() -> int:
    """Check the local MetaTrader 5 connection without trading."""

    print("Checking MetaTrader 5 connection...")

    if not mt5.initialize():
        print("Connection failed.")
        print(f"MT5 error: {mt5.last_error()}")
        return 1

    try:
        version = mt5.version()
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        symbols = mt5.symbols_get()

        print()
        print("Connection successful")
        print(f"Python package version: {mt5.__version__}")
        print(f"Terminal version: {version}")

        if terminal is None:
            print("Terminal information: unavailable")
        else:
            print(
                "Terminal connected: "
                f"{getattr(terminal, 'connected', False)}"
            )
            print(
                "Trading permission: "
                f"{getattr(terminal, 'trade_allowed', False)}"
            )

        if account is None:
            print("Account connection: unavailable")
            print(f"MT5 error: {mt5.last_error()}")
            return 2

        print("Account connection: available")

        if symbols is None:
            print("Symbol list: unavailable")
            print(f"MT5 error: {mt5.last_error()}")
            return 3

        available_names = sorted(
            str(symbol.name)
            for symbol in symbols
            if getattr(symbol, "name", None)
        )

        print()
        print("Broker symbol detection:")

        for target_pair in TARGET_PAIRS:
            matches = [
                symbol_name
                for symbol_name in available_names
                if target_pair in symbol_name.upper()
            ]

            if matches:
                print(
                    f"{target_pair}: "
                    + ", ".join(matches[:10])
                )
            else:
                print(f"{target_pair}: NOT FOUND")

        print()
        print("Read-only MT5 diagnostic completed successfully.")

        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())