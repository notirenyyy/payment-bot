#!/usr/bin/env python3
"""Poll Telegram for button presses on the weekly reminders, update the
ledger, and edit the original message to reflect who has paid.

Designed to be run on a recurring schedule (e.g. hourly). Uses getUpdates
with an offset so the same callback is never processed twice.

Run modes:
    python3 process_callbacks.py             # poll and apply updates
    python3 process_callbacks.py --dry-run   # poll but don't apply changes
"""
import sys

from lib import (
    load_config,
    load_ledger,
    mark_paid,
    reply_markup_for,
    save_ledger,
    status_message,
    tg_call,
    write_ledger_md,
)


def main() -> None:
    cfg = load_config()
    ledger = load_ledger()
    dry_run = "--dry-run" in sys.argv

    token = cfg.get("bot_token", "")
    chat_id = cfg.get("chat_id", "")
    if not token or token.startswith("PASTE_"):
        sys.exit("bot_token is not set in config.json")

    offset = ledger.get("last_update_id", 0) + 1
    result = tg_call(token, "getUpdates", {
        "offset": offset,
        "timeout": 0,
        "allowed_updates": ["callback_query"],
    })
    if not result.get("ok"):
        sys.exit(f"getUpdates failed: {result}")

    updates = result["result"]
    print(f"Fetched {len(updates)} update(s) since offset {offset}.")

    touched_weeks = {}  # date -> week dict

    for upd in updates:
        update_id = upd["update_id"]
        if update_id > ledger.get("last_update_id", 0):
            ledger["last_update_id"] = update_id

        cb = upd.get("callback_query")
        if not cb:
            continue

        data = cb.get("data", "")
        if not data.startswith("paid:"):
            continue
        date = data.split(":", 1)[1]

        # Identify the clicker.
        user = cb.get("from", {})
        handle = "@" + user["username"] if user.get("username") else (
            user.get("first_name") or f"id:{user.get('id')}"
        )

        # Find or create the week.
        week = None
        for w in ledger["weeks"]:
            if w["date"] == date:
                week = w
                break
        if week is None:
            print(f"  ! callback for unknown week {date}, skipping")
            # Still answer the callback so the spinner clears.
            tg_call(token, "answerCallbackQuery", {
                "callback_query_id": cb["id"],
                "text": "That week isn't tracked.",
            })
            continue

        was_new = mark_paid(week, handle)
        touched_weeks[date] = week
        ack = "Recorded — thanks!" if was_new else "Already marked as paid ✅"
        print(f"  {handle} → {date} ({'new' if was_new else 'duplicate'})")

        if not dry_run:
            tg_call(token, "answerCallbackQuery", {
                "callback_query_id": cb["id"],
                "text": ack,
            })

    # Edit each touched message with refreshed status.
    if not dry_run:
        for date, week in touched_weeks.items():
            if not week.get("message_id"):
                print(f"  - no message_id for {date}; skipping edit")
                continue
            edit_result = tg_call(token, "editMessageText", {
                "chat_id": chat_id,
                "message_id": week["message_id"],
                "text": status_message(week, cfg),
                "reply_markup": reply_markup_for(week),
            })
            if not edit_result.get("ok"):
                # "message is not modified" is harmless.
                desc = edit_result.get("description", "")
                if "not modified" not in desc:
                    print(f"  ! edit failed for {date}: {edit_result}")

        save_ledger(ledger)
        write_ledger_md(ledger, cfg)
    else:
        print("[dry-run] Not saving ledger or editing messages.")

    if not updates:
        # Still refresh the markdown view so the file's "Last updated" stays current.
        if not dry_run:
            write_ledger_md(ledger, cfg)


if __name__ == "__main__":
    main()
