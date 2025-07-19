#!/usr/bin/env python3
"""
Download every replay in a Ballchasing group, archive the raw JSON,
and build summary.csv with per‑player stats + win/loss for one player.
"""

# ── Imports ────────────────────────────────────────────────────────────
import os
import json
from pathlib import Path

import requests
import pandas as pd

print(">>> script started")     # simple debug banner

# ── Config from environment variables ──────────────────────────────────
TOKEN   = os.getenv("BC_TOKEN")          # 40‑char personal API token
GROUP   = os.getenv("BC_GROUP_ID")       # e.g. replay-analysis-j2e0c8rw06
PLAYER  = os.getenv("BC_PLAYER_NAME")    # exact in‑game name, e.g. 'n o a h'

if not TOKEN:
    raise RuntimeError("BC_TOKEN env var is missing.")
if not GROUP:
    raise RuntimeError("BC_GROUP_ID env var is missing.")
if not PLAYER:
    raise RuntimeError("BC_PLAYER_NAME env var is missing.")

HEADERS = {"Authorization": TOKEN}
OUT_DIR = Path("stats")
OUT_DIR.mkdir(exist_ok=True)

# ── Helper: list all replay IDs in the group ───────────────────────────
def list_replays(group_id: str) -> list[str]:
    """Return *all* replay IDs inside a group (handles pagination)."""
    url = "https://ballchasing.com/api/replays"
    params = {"group": group_id, "count": 200}   # 200 = max per page
    ids: list[str] = []

    while True:
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()

        # each element in data["list"] is one replay summary
        ids.extend(item["id"] for item in data["list"])

        next_url = data.get("next")
        if not next_url:
            break                # no more pages
        url, params = next_url, None   # follow the `next` link

    return ids

# ── Helper: download full replay stats JSON ────────────────────────────
def fetch_replay(replay_id: str) -> dict:
    url = f"https://ballchasing.com/api/replays/{replay_id}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()

# ── Helper: extract stats for the chosen player ────────────────────────
def extract_player_stats(js: dict) -> dict:
    blue, orange = js["blue"], js["orange"]

    # helper: total goals for a team
    def goals(team):
        return sum(p["stats"]["core"]["goals"] for p in team["players"])

    me_on_blue = any(p["name"] == PLAYER for p in blue["players"])
    your_team, other_team = (blue, orange) if me_on_blue else (orange, blue)

    outcome = "win" if goals(your_team) > goals(other_team) else "loss"

    you = next(p for p in your_team["players"] if p["name"] == PLAYER)
    s   = you["stats"]; b, m, d = s["boost"], s["movement"], s["demo"]

    return {
        "id"        : js["id"],
        "date"      : js["created"],
        "outcome"   : outcome,
        "shots"     : s["core"]["shots"],
        "goals"     : s["core"]["goals"],
        "saves"     : s["core"]["saves"],
        "assists"   : s["core"]["assists"],
        "demos"     : d["inflicted"],
        "boost_bpm" : b["bpm"],
        "avg_speed" : m["avg_speed"],
    }

# ── Main routine ───────────────────────────────────────────────────────
def main() -> None:
    ids = list_replays(GROUP)
    print(f"Found {len(ids)} replay(s) in group {GROUP}")

    rows = []
    for rid in ids:
        js = fetch_replay(rid)
        (OUT_DIR / f"{rid}.json").write_text(json.dumps(js))
        rows.append(extract_player_stats(js))

    if rows:
        pd.DataFrame(rows).to_csv("summary.csv", index=False)
        print(f"✓ {len(rows)} replays → summary.csv")
    else:
        print("No replays downloaded (group empty?).")

# ── Run script ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
