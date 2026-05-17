"""Shared helpers for the weekly payment reminder bot."""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

# On Railway, point LEDGER_PATH env var to a persistent volume, e.g. /data/ledger.json
LEDGER_PATH    = Path(os.environ.get("LEDGER_PATH",    str(BASE_DIR / "ledger.json")))
LEDGER_MD_PATH = Path(os.environ.get("LEDGER_MD_PATH", str(BASE_DIR / "ledger.md")))

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


# --- IO ---

def load_config() -> dict:
    """Load config from environment variables (Railway) or config.json (local dev)."""
    if os.environ.get("BOT_TOKEN"):
        usernames_raw = os.environ.get("USERNAMES", "")
        return {
            "bot_token":         os.environ["BOT_TOKEN"],
            "chat_id":           os.environ["CHAT_ID"],
            "usernames":         [u.strip() for u in usernames_raw.split(",") if u.strip()],
            "amount_per_person": os.environ.get("AMOUNT_PER_PERSON", "$10"),
            "amount_total":      os.environ.get("AMOUNT_TOTAL", ""),
        }
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_ledger() -> dict:
    if not LEDGER_PATH.exists():
        return {"last_update_id": 0, "weeks": []}
    with open(LEDGER_PATH) as f:
        return json.load(f)


def save_ledger(ledger: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_PATH, "w") as f:
        json.dump(ledger, f, indent=2, ensure_ascii=False)
        f.write("\n")


# --- Date helpers ---

def this_sunday() -> str:
    """Return the ISO date of the most recent Sunday (today if it's Sunday)."""
    today = datetime.now().date()
    # Python: Monday = 0, Sunday = 6.
    offset = (today.weekday() + 1) % 7
    return (today - timedelta(days=offset)).isoformat()


def pretty_date(iso: str) -> str:
    d = datetime.fromisoformat(iso).date()
    return d.strftime("%d %b %Y")


# --- Ledger helpers ---

def get_or_create_week(ledger: dict, date: str) -> dict:
    for w in ledger["weeks"]:
        if w["date"] == date:
            return w
    new_week = {
        "date": date,
        "message_id": None,
        "paid": [],
        "sent_at": None,       # ISO timestamp when reminder was sent
        "nudge_sent": False,   # True after the 24h nudge is sent
        "summary_sent": False, # True after the all-paid summary is sent
    }
    ledger["weeks"].append(new_week)
    ledger["weeks"].sort(key=lambda w: w["date"])
    return new_week


def all_paid(week: dict, cfg: dict) -> bool:
    return all(h in week["paid"] for h in cfg["usernames"])


def mark_paid(week: dict, username: str) -> bool:
    """Return True if this was a new entry."""
    if username in week["paid"]:
        return False
    week["paid"].append(username)
    return True


# --- Telegram API ---

def tg_call(token: str, method: str, params: dict) -> dict:
    url = TELEGRAM_API.format(token=token, method=method)
    data = json.dumps(params).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        # Read Telegram's JSON error body so we can surface the real description.
        body = e.read().decode(errors="replace")
        try:
            return json.loads(body)  # {"ok": false, "error_code": ..., "description": ...}
        except Exception:
            raise RuntimeError(f"HTTP {e.code}: {body}") from e


# --- Message rendering ---

def status_message(week: dict, cfg: dict) -> str:
    amount = cfg.get("amount_per_person", cfg.get("amount", ""))
    lines = [
        f"💸 Weekly fund reminder — {pretty_date(week['date'])}",
        f"Please send {amount} each 🙏",
        "",
        "Status:",
    ]
    for handle in cfg["usernames"]:
        mark = "✅" if handle in week["paid"] else "⏳"
        lines.append(f"{mark} {handle}")
    # Anyone outside the configured list who tapped the button still gets credit.
    extras = [h for h in week["paid"] if h not in cfg["usernames"]]
    for h in extras:
        lines.append(f"✅ {h} (guest)")
    lines.append("")
    if all(h in week["paid"] for h in cfg["usernames"]):
        lines.append("🎉 Everyone's paid — thanks!")
    else:
        lines.append('Tap "I\'ve paid" below once you\'ve sent yours.')
    return "\n".join(lines)


def reply_markup_for(week: dict) -> dict:
    return {
        "inline_keyboard": [[
            {"text": "✅ I've paid", "callback_data": f"paid:{week['date']}"}
        ]]
    }


# --- Extra message types ---

def all_paid_message(week: dict, cfg: dict) -> str:
    """Celebratory summary sent to the group once everyone has paid."""
    total = cfg.get("amount_total", "")
    lines = [
        f"🎉 All paid for week of {pretty_date(week['date'])}!",
        "",
    ]
    for handle in cfg["usernames"]:
        lines.append(f"✅ {handle}")
    lines.append("")
    lines.append(f"Total collected: {total} 💰 Thanks everyone!")
    return "\n".join(lines)


def nudge_message(week: dict, cfg: dict) -> str:
    """24-hour nudge tagging anyone who hasn't paid yet."""
    unpaid = [h for h in cfg["usernames"] if h not in week["paid"]]
    amount = cfg.get("amount_per_person", cfg.get("amount", ""))
    tags = " ".join(unpaid)
    lines = [
        f"⏰ Friendly nudge — still waiting on:",
        "",
        tags,
        "",
        f"Please send {amount} each 🙏",
    ]
    return "\n".join(lines)


# --- Ledger markdown rendering ---

def render_ledger_md(ledger: dict, cfg: dict) -> str:
    total = cfg.get("amount_total", "")
    per = cfg.get("amount_per_person", cfg.get("amount", ""))
    everyone = set(cfg["usernames"])
    out = ["# Weekly Payment Ledger", ""]
    out.append(f"Weekly amount: **{per} each** ({total} total)")
    out.append("")
    out.append("| Date | Status | Paid by |")
    out.append("|---|---|---|")
    for w in ledger["weeks"]:
        paid_set = set(w["paid"])
        if everyone.issubset(paid_set):
            status = f"✅ Full ({total})"
        elif paid_set:
            status = f"⚠️ Partial ({len(paid_set)}/{len(everyone)})"
        else:
            status = "⏳ Pending"
        paid_str = ", ".join(w["paid"]) if w["paid"] else "—"
        out.append(f"| {pretty_date(w['date'])} | {status} | {paid_str} |")
    out.append("")
    out.append(f"_Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    return "\n".join(out) + "\n"


def write_ledger_md(ledger: dict, cfg: dict) -> None:
    LEDGER_MD_PATH.write_text(render_ledger_md(ledger, cfg))
