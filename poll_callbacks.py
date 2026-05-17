#!/usr/bin/env python3
"""Poll Telegram for "I've paid" button taps, send nudges, and post the all-paid summary.

Designed to be run every 5 minutes via GitHub Actions (or locally).
Each run:
  1. Fetches new callback_query updates from Telegram
  2. Marks payers, edits the reminder message in real time
  3. If everyone just paid → posts the all-paid summary
  4. If 24h have passed and someone hasn't paid → sends a nudge
"""
import sys
from datetime import datetime, timedelta, timezone

from lib import (
    all_paid,
    all_paid_message,
    get_or_create_week,
    load_config,
    load_ledger,
    mark_paid,
    nudge_message,
    reply_markup_for,
    save_ledger,
    status_message,
    tg_call,
    this_sunday,
    write_ledger_md,
)

NUDGE_HOURS = 24


def main() -> None:
    cfg = load_config()
    token = cfg.get("bot_token", "")
    chat_id = str(cfg.get("chat_id", ""))
    if not token or token.startswith("PASTE_"):
        sys.exit("bot_token is not set")
    if not chat_id or chat_id.startswith("PASTE_"):
        sys.exit("chat_id is not set")

    ledger = load_ledger()
    offset = ledger.get("last_update_id", 0)
    if offset:
        offset += 1

    dirty = False

    # ── 1. Fetch new callback updates ────────────────────────────────────────
    result = tg_call(token, "getUpdates", {"offset": offset, "timeout": 0})
    if not result.get("ok"):
        sys.exit(f"getUpdates failed: {result}")

    updates = result.get("result", [])
    for upd in updates:
        upd_id = upd["update_id"]
        ledger["last_update_id"] = max(ledger.get("last_update_id", 0), upd_id)

        cb = upd.get("callback_query")
        if not cb:
            continue
        data = cb.get("data", "")
        if not data.startswith("paid:"):
            continue

        date     = data[len("paid:"):]
        user     = cb["from"]
        username = f"@{user['username']}" if user.get("username") else str(user["id"])
        cb_id    = cb["id"]
        msg      = cb.get("message", {})
        msg_id   = msg.get("message_id")
        cb_chat  = msg.get("chat", {}).get("id")

        week   = get_or_create_week(ledger, date)
        is_new = mark_paid(week, username)

        tg_call(token, "answerCallbackQuery", {
            "callback_query_id": cb_id,
            "text": "✅ Marked as paid!" if is_new else "Already marked as paid.",
            "show_alert": False,
        })

        if is_new:
            print(f"💰 {username} paid for week {date}")
            if msg_id and cb_chat:
                edit = tg_call(token, "editMessageText", {
                    "chat_id":      cb_chat,
                    "message_id":   msg_id,
                    "text":         status_message(week, cfg),
                    "reply_markup": reply_markup_for(week),
                })
                if edit.get("ok"):
                    print(f"  ✏️  Message updated.")
                else:
                    print(f"  ⚠️  Edit failed: {edit.get('description')}")
            dirty = True
        else:
            print(f"ℹ️  {username} already paid for week {date}.")

    # ── 2. Check nudge + all-paid summary for current week ───────────────────
    date = this_sunday()
    week = get_or_create_week(ledger, date)

    # All-paid summary
    if all_paid(week, cfg) and not week.get("summary_sent"):
        msg = all_paid_message(week, cfg)
        res = tg_call(token, "sendMessage", {"chat_id": chat_id, "text": msg})
        if res.get("ok"):
            week["summary_sent"] = True
            print("🎉 Everyone paid! Summary sent.")
            dirty = True
        else:
            print(f"⚠️  Summary failed: {res.get('description')}")

    # 24h nudge
    sent_at = week.get("sent_at")
    if sent_at and not week.get("nudge_sent") and not all_paid(week, cfg):
        sent_dt  = datetime.fromisoformat(sent_at)
        deadline = sent_dt + timedelta(hours=NUDGE_HOURS)
        if datetime.now(timezone.utc) >= deadline:
            msg = nudge_message(week, cfg)
            res = tg_call(token, "sendMessage", {"chat_id": chat_id, "text": msg})
            if res.get("ok"):
                week["nudge_sent"] = True
                unpaid = [h for h in cfg["usernames"] if h not in week["paid"]]
                print(f"⏰ Nudge sent for: {', '.join(unpaid)}")
                dirty = True
            else:
                print(f"⚠️  Nudge failed: {res.get('description')}")

    if dirty:
        save_ledger(ledger)
        write_ledger_md(ledger, cfg)
        print("Ledger saved.")
    else:
        print("No changes.")


if __name__ == "__main__":
    main()
