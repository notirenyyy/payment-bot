#!/usr/bin/env python3
"""Post a follow-up tag for anyone who hasn't paid 24h after Sunday's
reminder. Designed to run Monday at 12:00 local time.

Run modes:
    python3 nag_unpaid.py             # send the nag if anyone is still unpaid
    python3 nag_unpaid.py --dry-run   # print who would be tagged, don't send
"""
import sys
from datetime import datetime, timedelta

from lib import (
    load_config,
    load_ledger,
    pretty_date,
    tg_call,
)


def last_sunday() -> str:
    """Most recent Sunday strictly in the past (or today if Sunday)."""
    today = datetime.now().date()
    offset = (today.weekday() + 1) % 7
    return (today - timedelta(days=offset)).isoformat()


def main() -> None:
    cfg = load_config()
    ledger = load_ledger()
    dry_run = "--dry-run" in sys.argv

    target_date = last_sunday()
    week = next((w for w in ledger["weeks"] if w["date"] == target_date), None)
    if week is None:
        print(f"No week entry for {target_date} — nothing to nag.")
        return

    unpaid = [h for h in cfg["usernames"] if h not in week["paid"]]
    if not unpaid:
        print(f"Everyone's already paid for {target_date}. No nag needed. 🎉")
        return

    amount = cfg.get("amount_per_person", cfg.get("amount", ""))
    tags = " ".join(unpaid)
    text = (
        f"⏰ Gentle nudge — it's been 24h since the {pretty_date(target_date)} "
        f"reminder. Please send {amount} for this week's fund 🙏\n\n"
        f"{tags}"
    )

    print("--- Nag message ---")
    print(text)
    print("-------------------")

    if dry_run:
        print("[dry-run] Not sending.")
        return

    token = cfg.get("bot_token", "")
    chat_id = cfg.get("chat_id", "")
    if not token or token.startswith("PASTE_"):
        sys.exit("bot_token is not set in config.json")
    if not chat_id or str(chat_id).startswith("PASTE_"):
        sys.exit("chat_id is not set in config.json")

    # Reply to the original Sunday reminder if we have its message_id,
    # otherwise just post a fresh message.
    params = {"chat_id": chat_id, "text": text}
    if week.get("message_id"):
        params["reply_to_message_id"] = week["message_id"]
        params["allow_sending_without_reply"] = True

    result = tg_call(token, "sendMessage", params)
    if not result.get("ok"):
        sys.exit(f"Telegram API error: {result}")
    print("Sent! message_id =", result["result"]["message_id"])


if __name__ == "__main__":
    main()
