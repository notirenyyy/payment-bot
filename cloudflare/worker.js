/**
 * payment-bot — instant "I've paid" handler (Cloudflare Worker)
 *
 * Telegram calls this Worker the moment someone taps the button (webhook).
 * The Worker:
 *   1. marks them paid in ledger.json in the GitHub repo (one commit)
 *   2. edits the reminder message so ⏳ → ✅ straight away
 *   3. if that was the last person, posts the 🎉 summary + running ledger
 *
 * The Sunday reminder and Monday nudge still run on GitHub Actions.
 *
 * Settings (Cloudflare → Worker → Settings → Variables and secrets):
 *   Secrets:   BOT_TOKEN, GITHUB_TOKEN, WEBHOOK_SECRET
 *   Variables: REPO (e.g. notirenyyy/payment-bot), BRANCH (main),
 *              USERNAMES (@a,@b,@c,@d), AMOUNT_PER_PERSON ($10), AMOUNT_TOTAL ($40)
 *
 * Endpoints:
 *   POST /                         Telegram webhook (checks the secret header)
 *   GET  /setup?key=WEBHOOK_SECRET  points Telegram's webhook at this Worker
 *   GET  /status?key=WEBHOOK_SECRET shows Telegram's webhook info
 */

const LEDGER_PATH = "ledger.json";
const LEDGER_MD_PATH = "ledger.md";
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/setup") {
      if (url.searchParams.get("key") !== env.WEBHOOK_SECRET) return new Response("forbidden", { status: 403 });
      const res = await tg(env, "setWebhook", {
        url: `${url.origin}/`,
        secret_token: env.WEBHOOK_SECRET,
        allowed_updates: ["callback_query"],
        drop_pending_updates: false,
      });
      return json(res);
    }

    if (request.method === "GET" && url.pathname === "/status") {
      if (url.searchParams.get("key") !== env.WEBHOOK_SECRET) return new Response("forbidden", { status: 403 });
      return json(await tg(env, "getWebhookInfo", {}));
    }

    if (request.method !== "POST") return new Response("payment-bot worker is running");

    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }

    // Always answer 200 so Telegram doesn't retry the same update in a loop.
    try {
      const update = await request.json();
      if (update.callback_query) await handleCallback(update.callback_query, env);
    } catch (err) {
      console.log("handler error:", err && err.stack || err);
    }
    return new Response("ok");
  },
};

// ── Callback handling ────────────────────────────────────────────────────────

async function handleCallback(cb, env) {
  const data = cb.data || "";
  if (!data.startsWith("paid:")) {
    await tg(env, "answerCallbackQuery", { callback_query_id: cb.id });
    return;
  }
  const date = data.slice("paid:".length);
  const user = cb.from || {};
  const handle = user.username ? `@${user.username}` : String(user.id);
  const cfg = config(env);

  let outcome;
  try {
    outcome = await updateLedger(env, (ledger) => {
      const week = getOrCreateWeek(ledger, date);
      if (week.paid.includes(handle)) return { changed: false, week };
      week.paid.push(handle);
      let sendSummary = false;
      // Only the current/most recent week gets the 🎉 summary, same as the poller.
      if (allPaid(week, cfg) && !week.summary_sent) {
        week.summary_sent = true; // claim it in the same commit so nothing else re-sends it
        sendSummary = true;
      }
      return { changed: true, week, sendSummary, ledger };
    }, `chore: ${handle} paid for ${date} [skip ci]`, cfg);
  } catch (err) {
    console.log("ledger update failed:", err && err.stack || err);
    await tg(env, "answerCallbackQuery", {
      callback_query_id: cb.id,
      text: "⚠️ Couldn't save that — please tap again in a minute.",
      show_alert: true,
    });
    return;
  }

  await tg(env, "answerCallbackQuery", {
    callback_query_id: cb.id,
    text: outcome.changed ? "✅ Marked as paid!" : "Already marked as paid ✅",
  });
  if (!outcome.changed) return;

  const msg = cb.message || {};
  if (msg.message_id && msg.chat) {
    const edit = await tg(env, "editMessageText", {
      chat_id: msg.chat.id,
      message_id: msg.message_id,
      text: statusMessage(outcome.week, cfg),
      reply_markup: replyMarkup(outcome.week),
    });
    if (!edit.ok && !String(edit.description || "").includes("not modified")) {
      console.log("edit failed:", JSON.stringify(edit));
    }
  }

  if (outcome.sendSummary && msg.chat) {
    await tg(env, "sendMessage", { chat_id: msg.chat.id, text: allPaidMessage(outcome.week, cfg) });
    await tg(env, "sendMessage", { chat_id: msg.chat.id, text: ledgerSummaryMessage(outcome.ledger, cfg) });
  }
}

// ── GitHub: read-modify-commit ledger.json + ledger.md atomically ───────────

async function updateLedger(env, mutate, message, cfg, attempts = 4) {
  const branch = env.BRANCH || "main";
  for (let i = 0; i < attempts; i++) {
    const ref = await gh(env, `git/ref/heads/${branch}`);
    const headSha = ref.object.sha;
    const commit = await gh(env, `git/commits/${headSha}`);
    const raw = await gh(env, `contents/${LEDGER_PATH}?ref=${headSha}`, { raw: true });
    const ledger = JSON.parse(raw);

    const result = mutate(ledger);
    if (!result.changed) return result;

    const tree = await gh(env, "git/trees", {
      method: "POST",
      body: {
        base_tree: commit.tree.sha,
        tree: [
          { path: LEDGER_PATH, mode: "100644", type: "blob", content: JSON.stringify(ledger, null, 2) + "\n" },
          { path: LEDGER_MD_PATH, mode: "100644", type: "blob", content: renderLedgerMd(ledger, cfg) },
        ],
      },
    });
    const newCommit = await gh(env, "git/commits", {
      method: "POST",
      body: {
        message,
        tree: tree.sha,
        parents: [headSha],
        author: { name: "payment-bot", email: "bot@github-actions" },
      },
    });
    const upd = await gh(env, `git/refs/heads/${branch}`, {
      method: "PATCH",
      body: { sha: newCommit.sha, force: false },
      allowStatus: [422],
    });
    if (upd && upd.__status === 422) {
      // Someone else (GitHub Actions or another tap) committed first — redo on top of theirs.
      await sleep(300 * (i + 1));
      continue;
    }
    return result;
  }
  throw new Error("could not commit ledger after retries");
}

async function gh(env, path, { method = "GET", body, raw = false, allowStatus = [] } = {}) {
  const res = await fetch(`https://api.github.com/repos/${env.REPO}/${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: raw ? "application/vnd.github.raw" : "application/vnd.github+json",
      "User-Agent": "payment-bot-worker",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (allowStatus.includes(res.status)) return { __status: res.status };
  if (!res.ok) throw new Error(`GitHub ${method} ${path} → ${res.status}: ${await res.text()}`);
  return raw ? res.text() : res.json();
}

async function tg(env, method, params) {
  const res = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return res.json();
}

// ── Ledger helpers (mirror lib.py) ──────────────────────────────────────────

function config(env) {
  return {
    usernames: (env.USERNAMES || "").split(",").map((s) => s.trim()).filter(Boolean),
    amountPerPerson: env.AMOUNT_PER_PERSON || "$10",
    amountTotal: env.AMOUNT_TOTAL || "",
  };
}

function getOrCreateWeek(ledger, date) {
  let week = ledger.weeks.find((w) => w.date === date);
  if (!week) {
    week = { date, message_id: null, paid: [], sent_at: null, nudge_sent: false, summary_sent: false };
    ledger.weeks.push(week);
    ledger.weeks.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  }
  return week;
}

const allPaid = (week, cfg) => cfg.usernames.every((h) => week.paid.includes(h));

function prettyDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return `${String(d).padStart(2, "0")} ${MONTHS[m - 1]} ${y}`;
}

function statusMessage(week, cfg) {
  const lines = [
    `💸 Weekly fund reminder — ${prettyDate(week.date)}`,
    `Please send ${cfg.amountPerPerson} each 🙏`,
    "",
    "Status:",
  ];
  for (const h of cfg.usernames) lines.push(`${week.paid.includes(h) ? "✅" : "⏳"} ${h}`);
  for (const h of week.paid.filter((h) => !cfg.usernames.includes(h))) lines.push(`✅ ${h} (guest)`);
  lines.push("");
  lines.push(allPaid(week, cfg) ? "🎉 Everyone's paid — thanks!" : `Tap "I've paid" below once you've sent yours.`);
  return lines.join("\n");
}

const replyMarkup = (week) => ({
  inline_keyboard: [[{ text: "✅ I've paid", callback_data: `paid:${week.date}` }]],
});

function allPaidMessage(week, cfg) {
  return [
    `🎉 All paid for week of ${prettyDate(week.date)}!`,
    "",
    ...cfg.usernames.map((h) => `✅ ${h}`),
    "",
    `Total collected: ${cfg.amountTotal} 💰 Thanks everyone!`,
  ].join("\n");
}

function ledgerSummaryMessage(ledger, cfg) {
  const isFull = (w) => cfg.usernames.every((h) => w.paid.includes(h));
  const weeks = [...ledger.weeks].sort((a, b) => (a.date < b.date ? -1 : 1));
  const full = weeks.filter(isFull);
  const perWeek = parseFloat(String(cfg.amountTotal).replace(/[$,]/g, ""));
  const runningTotal = Number.isFinite(perWeek) ? `$${Math.trunc(perWeek * full.length)}` : `${full.length} × ${cfg.amountTotal}`;

  const lines = ["📒 Ledger update", ""];
  for (const w of weeks.slice(-5)) {
    if (isFull(w)) lines.push(`✅ ${prettyDate(w.date)} — paid in full`);
    else if (w.paid.length) lines.push(`⚠️ ${prettyDate(w.date)} — waiting on ${cfg.usernames.filter((h) => !w.paid.includes(h)).join(", ")}`);
    else lines.push(`⏳ ${prettyDate(w.date)} — no payments yet`);
  }
  const olderFull = weeks.slice(0, -5).filter(isFull).length;
  if (olderFull) lines.push(`…plus ${olderFull} earlier weeks ✅`);
  lines.push("", `💰 Running total: ${runningTotal} (${full.length} full weeks)`);
  return lines.join("\n");
}

function renderLedgerMd(ledger, cfg) {
  const everyone = cfg.usernames;
  const out = ["# Weekly Payment Ledger", "", `Weekly amount: **${cfg.amountPerPerson} each** (${cfg.amountTotal} total)`, "", "| Date | Status | Paid by |", "|---|---|---|"];
  for (const w of ledger.weeks) {
    const paidSet = new Set(w.paid);
    let status;
    if (everyone.every((h) => paidSet.has(h))) status = `✅ Full (${cfg.amountTotal})`;
    else if (paidSet.size) status = `⚠️ Partial (${paidSet.size}/${everyone.length})`;
    else status = "⏳ Pending";
    out.push(`| ${prettyDate(w.date)} | ${status} | ${w.paid.length ? w.paid.join(", ") : "—"} |`);
  }
  const sgt = new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 16).replace("T", " ");
  out.push("", `_Last updated: ${sgt} SGT_`);
  return out.join("\n") + "\n";
}

const json = (obj) => new Response(JSON.stringify(obj, null, 2), { headers: { "Content-Type": "application/json" } });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
