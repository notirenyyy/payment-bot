#!/usr/bin/env python3
"""Merge two versions of ledger.json so no one's changes are lost.

Used by the GitHub Actions push step when the Cloudflare Worker committed a
tap while the Action was running.

    python3 merge_ledger.py OURS.json THEIRS.json > ledger.json

Rules per week (matched by date):
  - paid:        union, keeping their order then appending ours
  - *_sent flags: True if either side says True
  - message_id / sent_at: ours if set (only Actions sends reminders), else theirs
  - last_update_id: max
"""
import json
import sys


def merge(ours: dict, theirs: dict) -> dict:
    out = {
        "last_update_id": max(ours.get("last_update_id", 0), theirs.get("last_update_id", 0)),
        "weeks": [],
    }
    by_date = {w["date"]: dict(w) for w in theirs.get("weeks", [])}
    for o in ours.get("weeks", []):
        t = by_date.get(o["date"])
        if t is None:
            by_date[o["date"]] = dict(o)
            continue
        paid = list(t.get("paid", []))
        paid += [h for h in o.get("paid", []) if h not in paid]
        t["paid"] = paid
        for flag in ("nudge_sent", "summary_sent"):
            t[flag] = bool(t.get(flag)) or bool(o.get(flag))
        for field in ("message_id", "sent_at"):
            if o.get(field):
                t[field] = o[field]
    out["weeks"] = sorted(by_date.values(), key=lambda w: w["date"])
    # Keep any other top-level keys
    for k, v in {**theirs, **ours}.items():
        out.setdefault(k, v)
    return out


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        ours = json.load(f)
    with open(sys.argv[2]) as f:
        theirs = json.load(f)
    json.dump(merge(ours, theirs), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
