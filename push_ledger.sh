#!/usr/bin/env bash
# Commit ledger.json/ledger.md and push. If the Cloudflare Worker committed a
# tap in the meantime, merge both versions instead of failing or overwriting.
# Usage: ./push_ledger.sh "commit message"
set -euo pipefail
MSG="$1"

git config user.name "payment-bot"
git config user.email "bot@github-actions"
git add ledger.json ledger.md
git diff --staged --quiet && { echo "Nothing to save."; exit 0; }
git commit -q -m "$MSG"

for attempt in 1 2 3 4 5; do
  if git push -q origin HEAD:main; then
    echo "Pushed."
    exit 0
  fi
  echo "Push rejected (attempt $attempt) — merging with latest ledger…"
  cp ledger.json "$RUNNER_TEMP/ours.json"
  git fetch -q origin main
  git reset -q --hard origin/main
  python3 merge_ledger.py "$RUNNER_TEMP/ours.json" ledger.json > "$RUNNER_TEMP/merged.json"
  mv "$RUNNER_TEMP/merged.json" ledger.json
  python3 render_ledger.py
  git add ledger.json ledger.md
  git diff --staged --quiet && { echo "Already up to date after merge."; exit 0; }
  git commit -q -m "$MSG"
  sleep $((attempt * 2))
done
echo "Could not push after 5 attempts." >&2
exit 1
