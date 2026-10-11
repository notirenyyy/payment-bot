# Instant "I've paid" with a Cloudflare Worker

Telegram sends each button tap straight to a free Cloudflare Worker. The
Worker marks the person paid, saves `ledger.json` to this repo, and updates
the Telegram message within about a second. The Sunday reminder and Monday
nudge stay on GitHub Actions.

All of the setup happens in your browser; you don't need to install anything.

## Before you start

Push the latest code to GitHub first. The GitHub job needs to know to stop
collecting taps itself once the Worker takes over.

## 1. GitHub token for the Worker (2 min)

1. Open https://github.com/settings/personal-access-tokens/new
2. **Name:** `payment-bot worker`. **Expiration:** the longest available, or no expiration.
3. **Repository access:** *Only select repositories* → `payment-bot`
4. **Permissions → Repository permissions → Contents:** *Read and write*
5. **Generate token** and copy the `github_pat_…` value.

The token can only read and write files in this one repo.

## 2. Create the Worker (5 min)

1. Sign up or log in at https://dash.cloudflare.com (the free plan is enough).
2. Go to **Workers & Pages** → **Create** → **Create Worker** (the "Hello World" starter).
3. Name it `payment-bot` and click **Deploy**.
4. Click **Edit code**. Delete everything in the editor, paste in the whole of
   [`worker.js`](worker.js), then click **Deploy**.
5. Note the Worker's URL, for example `https://payment-bot.<you>.workers.dev`.

## 3. Add the settings (3 min)

In the Worker, open **Settings** → **Variables and secrets** → **Add**:

| Type   | Name                | Value |
|--------|---------------------|-------|
| Secret | `BOT_TOKEN`         | the bot token from @BotFather (same as the GitHub secret) |
| Secret | `GITHUB_TOKEN`      | the `github_pat_…` token from step 1 |
| Secret | `WEBHOOK_SECRET`    | a random password, letters and numbers only |
| Text   | `REPO`              | `notirenyyy/payment-bot` |
| Text   | `USERNAMES`         | `@limmxy,@notirenyyy,@mienions_ra,@ilyisabel` |
| Text   | `AMOUNT_PER_PERSON` | `$10` |
| Text   | `AMOUNT_TOTAL`      | `$40` |

Click **Deploy** (or **Save and deploy**) when you're done.

## 4. Connect Telegram to the Worker (1 min)

Open this in your browser, replacing the two placeholders:

```
https://payment-bot.<you>.workers.dev/setup?key=<WEBHOOK_SECRET>
```

You should see `"ok": true` and `"Webhook was set"`.

To check it later, open `/status?key=<WEBHOOK_SECRET>`. If it shows
`"pending_update_count"` above 0 or a `"last_error_message"`, something is wrong.

## 5. Test it

Tap **I've paid** on the latest reminder. The ⏳ should turn ✅ within about a
second, and a commit named `chore: @you paid for … [skip ci]` should appear in
the repo.

## Turning it off

To go back to GitHub Actions collecting the taps (slower), open:

```
https://api.telegram.org/bot<BOT_TOKEN>/deleteWebhook
```

## Troubleshooting

- **The button spins and nothing happens:** open `/status`. If
  `last_error_message` is set, the Worker URL or secret is wrong. Run `/setup` again.
- **"Couldn't save that" popup:** the GitHub token is wrong, has expired, or is
  missing *Contents: Read and write*. In Cloudflare, open the Worker →
  **Logs** to see the exact error.
- **Message updates but no commit appears:** check `REPO` is spelled exactly
  `notirenyyy/payment-bot`.
