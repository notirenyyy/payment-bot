#!/usr/bin/env python3
"""Send this Sunday's payment reminder to the Telegram group with an
"I've paid" inline keyboard button.

Run modes:
    python3 send_reminder.py             # send the reminder for the current week
    python3 send_reminder.py --dry-run   # print the message without sending
"""
import sys
from datetime import datetime, timezone

from lib import (
    get_or_create_week,
    load_config,
    load_ledger,
    reply_markup_for,
    save_ledger,
    status_message,
    tg_call,
    this_sunday,
    write_ledger_md,
)


def main() -> None:
    cfg = load_config()
    ledger = load_ledger()
    dry_run = "--dry-run" in sys.argv

    date = this_sunday()
    week = get_or_create_week(ledger, date)
    text = status_message(week, cfg)
    markup = reply_markup_for(week)

    print(f"--- Week {date} ---")
    print(text)
    print("------------------")

    if dry_run:
        print("[dry-run] Not sending.")
        write_ledger_md(ledger, cfg)
        return

    token = cfg.get("bot_token", "")
    chat_id = cfg.get("chat_id", "")
    if not token or token.startswith("PASTE_"):
        sys.exit("bot_token is not set in config.json")
    if not chat_id or str(chat_id).startswith("PASTE_"):
        sys.exit("chat_id is not set in config.json")

    result = tg_call(token, "sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": markup,
    })
    if not result.get("ok"):
        sys.exit(f"Telegram API error: {result}")

    week["message_id"] = result["result"]["message_id"]
    week["sent_at"] = datetime.now(timezone.utc).isoformat()
    week["nudge_sent"] = False
    week["summary_sent"] = False
    save_ledger(ledger)
    write_ledger_md(ledger, cfg)
    print("Sent! message_id =", week["message_id"])


if __name__ == "__main__":
    main()
