#!/usr/bin/env python3
"""
Career High Tracker — Update Script
=====================================
Fetches live 2025-26 box scores from the published Google Sheet,
merges with the historical baseline (1947-2025), and generates
an updated career_highs.bin for the Career High Tracker app.

Usage:
    python update_career_highs.py

Requirements:
    - Python 3.7+
    - requests (pip install requests)
    - historical_baseline.bin in the same folder

Output:
    - career_highs.bin (upload this to your GitHub repo)
"""

import csv
import gzip
import io
import json
import os
import sys
from datetime import datetime
from collections import defaultdict

# === CONFIG ===
SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSp9Dyp62wra-_9vCmOlSzuelR8RkigcQsRX8MJs0s9Npabi7r0eVFA6deVdmd19X5DJc5V5Ci2m-nc"
    "/pub?gid=0&single=true&output=csv"
)
BASELINE_FILE = "historical_baseline.bin"
OUTPUT_FILE = "career_highs.bin"
SEASON_START = datetime(2025, 10, 1)


def safe_int(v):
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def load_baseline():
    """Load pre-computed historical data (1947 through 2024-25)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), BASELINE_FILE)
    if not os.path.exists(path):
        print(f"ERROR: {BASELINE_FILE} not found in script directory.")
        print("  This file contains all historical career highs (1947-2025).")
        print("  Place it next to this script and try again.")
        sys.exit(1)

    print(f"Loading {BASELINE_FILE}...")
    with gzip.open(path, "rb") as f:
        data = json.loads(f.read())
    total_players = len(data)
    total_games = sum(d[0] for d in data.values())
    print(f"  {total_players} players, {total_games:,} historical games")
    return data


def fetch_2526_games():
    """Fetch live 2025-26 box scores from the published Google Sheet."""
    try:
        import requests
    except ImportError:
        print("ERROR: 'requests' library not installed.")
        print("  Run: pip install requests")
        sys.exit(1)

    print(f"Fetching 2025-26 box scores from Google Sheets...")
    resp = requests.get(SHEET_CSV_URL, timeout=30)
    resp.raise_for_status()
    text = resp.text
    print(f"  Downloaded {len(text):,} bytes")

    # Parse CSV
    reader = csv.reader(io.StringIO(text))
    # Skip header rows (row 0 = headers, row 1 = blank/sub-header)
    try:
        next(reader)
        next(reader)
    except StopIteration:
        pass

    # Collect team blocks to pair opponents
    blocks = []  # [(date_str, team, [(player, pts, dt)])]
    current_block = None

    for row in reader:
        if len(row) < 23:
            continue
        date_str = row[0].strip()
        player = row[1].strip()
        if not date_str or "/" not in date_str:
            continue
        try:
            dt = datetime.strptime(date_str, "%m/%d/%Y")
        except ValueError:
            continue
        if dt < SEASON_START:
            continue

        team = row[22].strip() if len(row) > 22 else ""
        pts = safe_int(row[20]) if len(row) > 20 else 0

        if player == "TOTALS":
            if current_block:
                blocks.append(current_block)
            current_block = None
            continue
        if player in ("PLAYER", ""):
            continue

        if (current_block is None
                or current_block[0] != date_str
                or current_block[1] != team):
            if current_block:
                blocks.append(current_block)
            current_block = (date_str, team, [])

        current_block[2].append((player, pts, dt))

    if current_block:
        blocks.append(current_block)

    # Pair consecutive blocks on same date as opponents
    games = []
    i = 0
    while i < len(blocks) - 1:
        d1, t1, p1 = blocks[i]
        d2, t2, p2 = blocks[i + 1]
        if d1 == d2:
            for player, pts, dt in p1:
                games.append((player, dt, pts, t1, t2))
            for player, pts, dt in p2:
                games.append((player, dt, pts, t2, t1))
            i += 2
        else:
            i += 1

    print(f"  {len(games):,} player-games parsed (Oct 2025+)")
    return games


def merge_and_build(baseline, games_2526):
    """Merge historical baseline with 2025-26 games and compute career highs."""
    print("Merging data...")

    # Group 2025-26 games by player, sorted by date
    new_games = defaultdict(list)
    for name, dt, pts, team, opp in games_2526:
        new_games[name].append((dt, pts, team, opp))

    for name in new_games:
        new_games[name].sort(key=lambda x: x[0])

    # Start from baseline and extend with 2025-26
    result = {}
    all_player_names = set(baseline.keys()) | set(new_games.keys())

    new_career_highs = []

    for name in sorted(all_player_names):
        # Get historical state
        if name in baseline:
            hist_total, hist_ms = baseline[name]
            career_high = hist_ms[-1][1] if hist_ms else -1
            ms = [m[:] for m in hist_ms]  # deep copy
            game_num = hist_total
        else:
            career_high = -1
            ms = []
            game_num = 0

        # Process 2025-26 games
        if name in new_games:
            for dt, pts, team, opp in new_games[name]:
                game_num += 1
                if pts > career_high:
                    old_high = career_high
                    career_high = pts
                    date_str = dt.strftime("%Y-%m-%d") if dt else ""
                    ms.append([game_num, pts, date_str, team, opp, 2026])
                    if old_high > 0:  # not first career game
                        new_career_highs.append(
                            (name, old_high, pts, pts - old_high, date_str, team, opp)
                        )

        result[name] = [game_num, ms]

    total_players = len(result)
    total_games = sum(d[0] for d in result.values())
    print(f"  {total_players} players, {total_games:,} total games")

    # Show notable new career highs from 2025-26
    if new_career_highs:
        new_career_highs.sort(key=lambda x: -x[3])
        print(f"\n  New career highs set in 2025-26: {len(new_career_highs)}")
        print(f"  {'Player':<28} {'Old':>4} {'New':>4} {'Jump':>5}  Date        Matchup")
        print(f"  {'-'*26}  {'-'*4} {'-'*4} {'-'*5}  {'-'*10}  {'-'*20}")
        for name, old, new, jump, date, team, opp in new_career_highs[:20]:
            print(f"  {name:<28} {old:>4} {new:>4}  +{jump:<4} {date}  {team} vs {opp}")
        if len(new_career_highs) > 20:
            print(f"  ... and {len(new_career_highs) - 20} more")

    return result


def save_output(data):
    """Save career_highs.bin."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), OUTPUT_FILE)
    json_str = json.dumps(data, separators=(",", ":"))
    with gzip.open(path, "wb", compresslevel=9) as f:
        f.write(json_str.encode("utf-8"))
    size_kb = os.path.getsize(path) / 1024
    print(f"\nSaved {OUTPUT_FILE} ({size_kb:.0f} KB)")
    print(f"  → Upload this file to your GitHub repo to update the app")


def main():
    print("=" * 56)
    print("  CAREER HIGH TRACKER — Update Script")
    print("=" * 56)
    print()

    baseline = load_baseline()
    games_2526 = fetch_2526_games()
    result = merge_and_build(baseline, games_2526)
    save_output(result)

    print("\nDone! ✓")


if __name__ == "__main__":
    main()
