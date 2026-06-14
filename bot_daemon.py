#!/usr/bin/env python3
"""Real-time payment bot daemon.

Flow:
  1. Reminder sent every Sunday 12pm (via send_reminder.py / scheduled task)
  2. Someone taps "I've paid" → message updates instantly ✅
  3. Everyone paid → bot posts a celebratory ledger summary to the group
  4. 24 hours after reminder, anyone still unpaid → bot sends a nudge

Run while the reminder is active (Sunday → Monday):
    python3 bot_daemon.py

Press Ctrl-C to stop.
"""
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from lib import (
    all_paid,
    all_paid_message,
    get_or_create_week,
    ledger_summary_message,
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

POLL_TIMEOUT  = 30   # seconds Telegram holds the connection open

# ── Health-check server (keeps Render free tier alive) ────────────────────────
class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *_): pass  # silence request logs

def _start_health_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(("0.0.0.0", port), _Health).serve_forever()
# ─────────────────────────────────────────────────────────────────────────────
RETRY_DELAY   = 5    # seconds to wait after a network error
NUDGE_HOURS   = 24   # hours after reminder before sending nudge
CHECK_INTERVAL = 60  # seconds between nudge/summary checks


def send_all_paid_summary(
    week: dict, cfg: dict, ledger: dict, token: str, chat_id: str
) -> None:
    msg = all_paid_message(week, cfg)
    result = tg_call(token, "sendMessage", {
        "chat_id": chat_id,
        "text": msg,
    })
    if result.get("ok"):
        week["summary_sent"] = True
        print("🎉 Everyone paid! Summary sent to group.")
    else:
        print(f"⚠️  Could not send summary: {result.get('description')}")
        return

    # Post the running ledger right after the celebration so the group always
    # sees the up-to-date weekly history in chat.
    ledger_msg = ledger_summary_message(ledger, cfg)
    ledger_result = tg_call(token, "sendMessage", {
        "chat_id": chat_id,
        "text": ledger_msg,
    })
    if ledger_result.get("ok"):
        print("📒 Ledger summary sent.")
    else:
        print(f"⚠️  Could not send ledger summary: {ledger_result.get('description')}")


def send_nudge(week: dict, cfg: dict, token: str, chat_id: str) -> None:
    msg = nudge_message(week, cfg)
    result = tg_call(token, "sendMessage", {
        "chat_id": chat_id,
        "text": msg,
    })
    if result.get("ok"):
        week["nudge_sent"] = True
        unpaid = [h for h in cfg["usernames"] if h not in week["paid"]]
        print(f"⏰ 24h nudge sent for: {', '.join(unpaid)}")
    else:
        print(f"⚠️  Could not send nudge: {result.get('description')}")


def check_scheduled_actions(cfg: dict, ledger: dict, token: str, chat_id: str) -> bool:
    """Check if a nudge or all-paid summary needs to be sent. Returns True if ledger was mutated."""
    date  = this_sunday()
    week  = get_or_create_week(ledger, date)
    dirty = False

    # --- All-paid summary (step 3) ---
    if all_paid(week, cfg) and not week.get("summary_sent"):
        send_all_paid_summary(week, cfg, ledger, token, chat_id)
        dirty = True

    # --- 24h nudge (step 4) ---
    sent_at = week.get("sent_at")
    if (
        sent_at
        and not week.get("nudge_sent")
        and not all_paid(week, cfg)
    ):
        sent_dt  = datetime.fromisoformat(sent_at)
        deadline = sent_dt + timedelta(hours=NUDGE_HOURS)
        if datetime.now(timezone.utc) >= deadline:
            send_nudge(week, cfg, token, chat_id)
            dirty = True

    return dirty


def process_callback(cb: dict, cfg: dict, ledger: dict, token: str, chat_id: str) -> bool:
    """Handle an I've-paid button tap. Returns True if ledger was mutated."""
    data = cb.get("data", "")
    if not data.startswith("paid:"):
        return False

    date     = data[len("paid:"):]
    user     = cb["from"]
    username = f"@{user['username']}" if user.get("username") else str(user["id"])
    cb_id    = cb["id"]
    msg      = cb.get("message", {})
    msg_id   = msg.get("message_id")
    cb_chat  = msg.get("chat", {}).get("id")

    week   = get_or_create_week(ledger, date)
    is_new = mark_paid(week, username)

    # Dismiss spinner on the button
    tg_call(token, "answerCallbackQuery", {
        "callback_query_id": cb_id,
        "text": "✅ Marked as paid!" if is_new else "Already marked as paid.",
        "show_alert": False,
    })

    if not is_new:
        print(f"  ℹ️  {username} already paid for week {date}.")
        return False

    print(f"  💰 {username} paid for week {date}")

    # Edit the original reminder message with updated ✅/⏳ status
    if msg_id and cb_chat:
        new_text   = status_message(week, cfg)
        new_markup = reply_markup_for(week)
        result = tg_call(token, "editMessageText", {
            "chat_id":      cb_chat,
            "message_id":   msg_id,
            "text":         new_text,
            "reply_markup": new_markup,
        })
        if result.get("ok"):
            print(f"  ✏️  Message updated.")
        else:
            print(f"  ⚠️  Could not edit message: {result.get('description')}")

    # Immediately check if everyone just paid → send summary
    if all_paid(week, cfg) and not week.get("summary_sent"):
        send_all_paid_summary(week, cfg, ledger, token, chat_id)

    return True


def main() -> None:
    cfg     = load_config()
    token   = cfg.get("bot_token", "")
    chat_id = cfg.get("chat_id", "")
    if not token or token.startswith("PASTE_"):
        sys.exit("bot_token is not set in config.json")
    if not chat_id or str(chat_id).startswith("PASTE_"):
        sys.exit("chat_id is not set in config.json")

    ledger = load_ledger()
    offset = ledger.get("last_update_id", 0)
    if offset:
        offset += 1

    threading.Thread(target=_start_health_server, daemon=True).start()
    print("🤖 Payment bot running — Ctrl-C to stop.\n")
    print("  Listening for payments and monitoring 24h nudge…\n")

    last_check = 0.0

    while True:
        try:
            # ── Long-poll for button taps ──────────────────────────────────
            result = tg_call(token, "getUpdates", {
                "offset":          offset,
                "timeout":         POLL_TIMEOUT,
                "allowed_updates": ["callback_query"],
            })

            if not result.get("ok"):
                print(f"⚠️  getUpdates error: {result.get('description')} — retrying in {RETRY_DELAY}s")
                time.sleep(RETRY_DELAY)
                continue

            dirty = False
            for upd in result.get("result", []):
                upd_id = upd["update_id"]
                offset = upd_id + 1
                ledger["last_update_id"] = upd_id

                cb = upd.get("callback_query")
                if cb and process_callback(cb, cfg, ledger, token, chat_id):
                    dirty = True

            # ── Periodic nudge / summary check ────────────────────────────
            now = time.monotonic()
            if now - last_check >= CHECK_INTERVAL:
                if check_scheduled_actions(cfg, ledger, token, chat_id):
                    dirty = True
                last_check = now

            if dirty:
                save_ledger(ledger)
                write_ledger_md(ledger, cfg)

        except KeyboardInterrupt:
            print("\n👋 Stopped.")
            save_ledger(ledger)
            break
        except Exception as e:
            print(f"⚠️  Error: {e} — retrying in {RETRY_DELAY}s")
            time.sleep(RETRY_DELAY)


if __name__ == "__main__":
    main()
