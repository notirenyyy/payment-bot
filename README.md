# Weekly Payment Fund Reminder Bot

A Telegram bot that:

1. Posts a reminder in your group every **Sunday at 12:00 SGT** asking everyone to chip in $10.
2. Shows an **"✅ I've paid"** inline button. When a friend taps it, the bot marks them as paid and edits the message in real time so everyone can see who's still pending.
3. **Mondays at 12:00 SGT** (24h after the reminder), the bot tags anyone who still hasn't paid — but stays quiet if everyone already has.
4. Keeps a running ledger (`ledger.md`) you can open anytime to see history.

## Files

- `send_reminder.py` — posts the Sunday reminder with the inline button
- `process_callbacks.py` — polls Telegram hourly for button taps, updates the ledger, refreshes the message
- `nag_unpaid.py` — Monday-noon follow-up that tags anyone still unpaid (skips if everyone's paid)
- `render_ledger.py` — regenerates `ledger.md` from `ledger.json` (run manually if you hand-edit)
- `lib.py` — shared helpers
- `config.json` — bot token, group chat ID, $10 amount, friend handles
- `ledger.json` — the source of truth: every week's paid list
- `ledger.md` — auto-generated, human-readable ledger

## Scheduled tasks (already set up)

- `weekly-payment-reminder` — fires every Sunday at 12:00 SGT, runs `send_reminder.py`
- `payment-callback-poller` — fires hourly, runs `process_callbacks.py`
- `payment-24h-nag` — fires every Monday at 12:00 SGT, runs `nag_unpaid.py`

You can pause, edit, or trigger them manually from the **Scheduled** section in the Claude sidebar.

## One-time setup

### 1. Add your bot to the group chat

Telegram → your group → **Add member** → search your bot's username → add it.

By default, Telegram bots in groups only see messages directed at them, which is fine here — we only need callback queries from button presses.

### 2. Get the group chat ID

1. Have anyone send a message in the group (e.g. "hello").
2. Open this URL in a browser, replacing `<TOKEN>` with your bot token:

   `https://api.telegram.org/bot<TOKEN>/getUpdates`

3. Find `"chat":{"id":-1001234567890,...}`. That negative number is your group chat ID.

### 3. Fill in `config.json`

```json
{
  "bot_token": "123456789:ABC-DEF...",
  "chat_id": "-1001234567890",
  "amount_per_person": "$10",
  "amount_total": "$40",
  "usernames": [
    "@limmxy",
    "@notirenyyy",
    "@mienions_ra",
    "@ilyisabel"
  ]
}
```

The button only credits people whose Telegram has a public `@username`. If a friend doesn't have one, ask them to set one in **Telegram → Settings → Username**, otherwise they'll be recorded by their first name instead of their @handle.

### 4. Test it

```bash
cd "/Users/irene.xu/Documents/Claude/Projects/payment bot reminder"
python3 send_reminder.py --dry-run    # preview without sending
python3 send_reminder.py              # send a test reminder right now
```

If the test reminder lands in your group with an "I've paid" button, you're set. Tap the button yourself, then wait an hour (or trigger `payment-callback-poller` manually from the sidebar) and watch the message update.

## How a typical week works

- **Sun 12:00** — bot posts: "💸 Weekly fund reminder — 17 May 2026 / Please send $10 each ..." with ⏳ next to all 4 names and an "I've paid" button.
- **Through the day** — each friend taps the button after sending their share. Within the hour, the bot edits the message so their ⏳ becomes ✅.
- **Mon 12:00 (24h later)** — if anyone's still ⏳, the bot replies to the original reminder with a follow-up that tags only the holdouts ("⏰ Gentle nudge ... @notirenyyy @mienions_ra"). If everyone paid, the bot stays quiet.
- **Whenever** — once all 4 are ✅, the original message updates to "🎉 Everyone's paid — thanks!"
- **`ledger.md`** — updated every poll. Open it anytime to see the full running history.

## Common tweaks

- **Change the amount** → edit `amount_per_person` (and optionally `amount_total`) in `config.json`. Next Sunday will use the new amount.
- **Add or remove a friend** → edit `usernames` in `config.json`.
- **Re-send this week's reminder** → run `python3 send_reminder.py` manually. It updates the existing week entry rather than duplicating it.
- **Fix a mistake** → edit `ledger.json` directly, then run `python3 render_ledger.py` to refresh the markdown view.
- **Change the day/time** → ask Claude to update the `weekly-payment-reminder` scheduled task.
- **Poll more often** → ask Claude to bump `payment-callback-poller` to, say, every 15 min. (Hourly is the default to keep the work light.)
- **Disable the Monday nag** → in the Scheduled sidebar, toggle off `payment-24h-nag`. Or ask Claude to change it to, e.g., daily until everyone pays.

## Historical data (seeded)

The ledger starts from **11 Jan 2026** with 19 weeks pre-loaded, including 29 Mar and 5 Apr as partial weeks (only @limmxy and @ilyisabel paid those two). Open `ledger.md` to view.

## Troubleshooting

- *"chat not found"* — bot isn't in the group, or `chat_id` is wrong (must include the leading minus sign for groups).
- *"Forbidden: bot was kicked"* — re-add the bot.
- *"bot_token is not set"* — you haven't pasted your token into `config.json` yet.
- *Button tap doesn't update the message* — the poller runs hourly; either wait, or run `python3 process_callbacks.py` manually to apply changes immediately.
- *Someone tapped the button but wasn't credited* — check `ledger.json`. If they were recorded under their first name instead of @handle, ask them to set a Telegram username.
