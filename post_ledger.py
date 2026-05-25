#!/usr/bin/env python3
"""One-off: post the current running ledger to the Telegram group.

Useful for backfilling a missed ledger update (e.g. when new code was deployed
after the all-paid summary had already been sent for a given week).

Usage:
    python3 post_ledger.py            # send the ledger summary now
    python3 post_ledger.py --dry-run  # print without sending
"""
import sys

from lib import (
    ledger_summary_message,
    load_config,
    load_ledger,
    tg_call,
)


def main() -> None:
    cfg = load_config()
    ledger = load_ledger()
    dry_run = "--dry-run" in sys.argv

    msg = ledger_summary_message(ledger, cfg)
    print("--- Ledger message ---")
    print(msg)
    print("----------------------")

    if dry_run:
        print("[dry-run] Not sending.")
        return

    token = cfg.get("bot_token", "")
    chat_id = cfg.get("chat_id", "")
    if not token or token.startswith("PASTE_"):
        sys.exit("bot_token is not set")
    if not chat_id or str(chat_id).startswith("PASTE_"):
        sys.exit("chat_id is not set")

    result = tg_call(token, "sendMessage", {"chat_id": chat_id, "text": msg})
    if not result.get("ok"):
        sys.exit(f"Telegram API error: {result}")
    print("Sent! message_id =", result["result"]["message_id"])


if __name__ == "__main__":
    main()
