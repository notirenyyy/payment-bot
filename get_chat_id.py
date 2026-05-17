#!/usr/bin/env python3
"""Run this once to find the correct chat_id for your group.

Steps:
  1. Make sure your bot is in the group.
  2. Send any message in the group (so Telegram has a recent update).
  3. Run:  python3 get_chat_id.py
"""
import json, urllib.request
from pathlib import Path

cfg = json.loads((Path(__file__).parent / "config.json").read_text())
token = cfg["bot_token"]

url = f"https://api.telegram.org/bot{token}/getUpdates"
with urllib.request.urlopen(url, timeout=15) as r:
    data = json.loads(r.read())

if not data.get("result"):
    print("No updates found.")
    print("→ Send a message in your group, then run this script again.")
else:
    seen = {}
    for upd in data["result"]:
        chat = (upd.get("message") or upd.get("my_chat_member", {}).get("chat", {}))
        if isinstance(chat, dict):
            cid  = chat.get("id")
            kind = chat.get("type")
            title = chat.get("title") or chat.get("username") or "(no title)"
            if cid and cid not in seen:
                seen[cid] = (kind, title)
    if seen:
        print("Chats visible to your bot:\n")
        for cid, (kind, title) in seen.items():
            marker = " ← update this in config.json" if str(cid) != str(cfg.get("chat_id")) else " ✅ (current)"
            print(f"  id: {cid}   type: {kind}   title: {title}{marker}")
    else:
        print("Could not parse any chat IDs from updates.")
        print("Raw result:", json.dumps(data["result"], indent=2))
