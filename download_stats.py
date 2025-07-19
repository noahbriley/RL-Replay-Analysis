#!/usr/bin/env python3
"""
Download every replay in a Ballchasing group, save raw JSON into stats/,
and build summary.csv with win/loss metrics for one player.
"""

# ── Imports ───────────────────────────────────────────────────────────
import os
import json
import time
from pathlib import Path

import requests
import pandas as pd
from requests.exceptions import ReadTimeout, ConnectionError

print(">>> script started")

# ── Config from environment variables ────────────────────────────────
TOKEN   = os.getenv("BC_TOKEN")          # 40‑char personal API token
GROUP   = os.getenv("BC_GROUP_ID")       # e.g. replay-analysis-j2e0c8rw06
PLAYER  = os.getenv("BC_PLAYER_NAME")    # in‑game name, e.g. 'n o a h'

if not all([TOKEN, GROUP, PLAYER]):
    raise RuntimeError("BC_TOKEN, BC_GROUP_ID, BC_PLAYER_NAME must be set.")

HEADERS   = {"Authorization": TOKEN}
OUT_DIR   = Path("stats");  OUT_DIR.mkdir(exist_ok=True)
TIMEOUT   = 90   # seconds per request
MAX_RETRY = 4

# ── Helper: GET with retry + back‑off ────────────────────────────────
def get_with_retry(url: str, **kwargs) -> requests.Response:
    for attempt in range(1, MAX_RETRY + 1):
        try:
            return requests.get(url, timeout=TIMEOUT, **kwargs)
        except (ReadTimeout, ConnectionError) as e:
            if attempt == MAX_RETRY:
                raise
            print(f"⚠  {e} – retry {attempt}/{MAX_RETRY}")
            time.sleep(2 * attempt)  # simple back‑off

# ── Helper: list all replay IDs in a group (handles pagination) ──────
def list_replays(group_id: str) -> list[str]:
    url    = "https://ballchasing.com/api/replays"
    params = {"group": group_id, "count": 200}
    ids: list[str] = []

    while True:
        r = get_with_retry(url, headers=HEADERS, params=params)
        r.raise_for_status()
        data = r.json()

        ids.extend(item["id"] for item in data["list"])

        next_url = data.get("next")
        if not next_url:
            break
        url, params = next_url, None   # follow next page

    return ids

# ── Helper: download full replay JSON ────────────────────────────────
def fetch_replay(replay_id: str) -> dict:
    url = f"https://ballchasing.com/api/replays/{replay_id}"
    r   = get_with_retry(url, headers=HEADERS)
    r.raise_for_status()
    return r.json()

# ── Helper: extract stats for the specified player ───────────────────
def extract_player_stats(js: dict) -> dict:
    blue, orange = js["blue"], js["orange"]

    def team_goals(team):
        return sum(p["stats"]["core"]["goals"] for p in team["players"])

    me_on_blue = any(p["name"] == PLAYER for p in blue["players"])
    your_team, other_team = (blue, orange) if me_on_blue else (orange, blue)
    outcome = "win" if team_goals(your_team) > team_goals(other_team) else "loss"

    you  = next(p for p in your_team["players"] if p["name"] == PLAYER)
    s    = you["stats"]; b, m, d = s["boost"], s["movement"], s["demo"]

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

# ── Main routine ─────────────────────────────────────────────────────
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
        print("No replays downloaded – group empty?")

# ── Entrypoint ───────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
