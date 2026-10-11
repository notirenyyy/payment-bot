#!/usr/bin/env python3
"""Send this Sunday's payment reminder to the Telegram group with an
"I've paid" inline keyboard button.

Run modes:
    python3 send_reminder.py             # send this week's reminder (skips if already sent)
    python3 send_reminder.py --force     # send again even if already sent this week
    python3 send_reminder.py --dry-run   # print the message without sending
"""
import sys

from lib import (
    get_or_create_week,
    load_config,
    load_ledger,
    save_ledger,
    send_week_reminder,
    status_message,
    this_sunday,
    write_ledger_md,
)


def main() -> None:
    cfg = load_config()
    ledger = load_ledger()
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv

    date = this_sunday()
    week = get_or_create_week(ledger, date)
    text = status_message(week, cfg)

    print(f"--- Week {date} ---")
    print(text)
    print("------------------")

    if dry_run:
        print("[dry-run] Not sending.")
        write_ledger_md(ledger, cfg)
        return

    if week.get("message_id") and not force:
        # The 5-minute poller may already have sent it as a catch-up.
        print(f"Reminder for {date} already sent (message_id={week['message_id']}). Use --force to resend.")
        return

    token = cfg.get("bot_token", "")
    chat_id = cfg.get("chat_id", "")
    if not token or token.startswith("PASTE_"):
        sys.exit("bot_token is not set in config.json")
    if not chat_id or str(chat_id).startswith("PASTE_"):
        sys.exit("chat_id is not set in config.json")

    result = send_week_reminder(week, cfg, token, chat_id)
    if not result.get("ok"):
        sys.exit(f"Telegram API error: {result}")

    save_ledger(ledger)
    write_ledger_md(ledger, cfg)
    print("Sent! message_id =", week["message_id"])


if __name__ == "__main__":
    main()
