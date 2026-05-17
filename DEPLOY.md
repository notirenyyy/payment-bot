# Deploying to Railway

Once deployed, the bot runs 24/7 in the cloud — no laptop needed.

---

## Step 1 — Push code to GitHub

1. Go to https://github.com/new and create a **private** repository (e.g. `payment-bot`)
2. Open Terminal and run:

```bash
cd "/Users/irene.xu/Documents/Claude/Projects/payment bot reminder"
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/payment-bot.git
git push -u origin main
```

> `config.json` and `ledger.json` are in `.gitignore` — they will NOT be uploaded (your token stays safe).

---

## Step 2 — Create a Railway project

1. Go to https://railway.app and sign up (free, no credit card)
2. Click **New Project → Deploy from GitHub repo**
3. Select your `payment-bot` repo
4. Railway will detect the `Procfile` and `railway.toml` automatically

---

## Step 3 — Add environment variables

In Railway → your project → **Variables**, add these:

| Variable | Value |
|---|---|
| `BOT_TOKEN` | Your bot token (from config.json) |
| `CHAT_ID` | `-664163094` |
| `USERNAMES` | `@limmxy,@notirenyyy,@mienions_ra,@ilyisabel` |
| `AMOUNT_PER_PERSON` | `$10` |
| `AMOUNT_TOTAL` | `$40` |
| `LEDGER_PATH` | `/data/ledger.json` |

---

## Step 4 — Add a persistent volume (so the ledger survives redeploys)

1. In Railway → your service → **Volumes**
2. Click **Add Volume**
3. Mount path: `/data`
4. This keeps `ledger.json` safe across restarts and redeploys

---

## Step 5 — Deploy

Click **Deploy**. Railway will:
- Start `bot_daemon.py` as a worker (runs 24/7)
- Schedule `send_reminder.py` every Sunday 4am UTC (= 12pm Singapore time)

Check the **Logs** tab to confirm:
```
🤖 Payment bot running — Ctrl-C to stop.
  Listening for payments and monitoring 24h nudge…
```

---

## Making changes later

1. Edit files in Claude
2. Run in Terminal:
```bash
cd "/Users/irene.xu/Documents/Claude/Projects/payment bot reminder"
git add .
git commit -m "Update bot"
git push
```
Railway auto-redeploys on every push.

---

## Useful Railway links

- Logs: Railway → your project → Logs
- Restart: Railway → your service → Restart
- Stop: Railway → your service → Remove / Pause
