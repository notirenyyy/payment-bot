#!/usr/bin/env python3
"""Regenerate ledger.md from ledger.json. Useful if you edit ledger.json
by hand and want the markdown view refreshed."""
from lib import load_config, load_ledger, write_ledger_md


def main() -> None:
    cfg = load_config()
    ledger = load_ledger()
    write_ledger_md(ledger, cfg)
    print("Wrote ledger.md")


if __name__ == "__main__":
    main()
