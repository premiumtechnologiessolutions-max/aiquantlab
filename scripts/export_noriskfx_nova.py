"""Export one existing Nova hypothesis from AI Quant Lab without DB writes."""
from __future__ import annotations

import argparse
from pathlib import Path

from ai_quant_lab.integrations.noriskfx_export import export_nova_hypothesis


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-db", type=Path, required=True)
    parser.add_argument("--hypothesis-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        export_nova_hypothesis(args.research_db, args.hypothesis_id, args.out)
    except (OSError, ValueError, TypeError):
        # Do not echo path, JSON, account IDs, or private source values.
        parser.exit(2, "Read-only Nova export rejected. No orders or database writes.\n")
    print("Private Nova hypothesis exported; research and trading remain disabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
