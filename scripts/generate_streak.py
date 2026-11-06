#!/usr/bin/env python3
"""Generate assets/streak.svg from the GitHub contributions calendar.

Reads the token from GITHUB_TOKEN. Uses only the standard library so the
scheduled workflow needs no install step.
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from itertools import groupby
from pathlib import Path
from typing import NamedTuple, Optional

LOGIN = "mohammedareebalishivji"
OUTPUT = Path(__file__).resolve().parent.parent / "assets" / "streak.svg"
# The calendar's last day follows the timezone of the query, so this decides when "today" starts.
IST = timezone(timedelta(hours=5, minutes=30))

CREATED_QUERY = "query($login: String!) { user(login: $login) { createdAt } }"
CALENDAR_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


class Streak(NamedTuple):
    length: int = 0
    start: Optional[date] = None
    end: Optional[date] = None


def graphql(token, query, variables):
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "profile-streak-card"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


def fetch_days(token):
    """Return every day since the account was created as sorted (date, count) pairs."""
    data = graphql(token, CREATED_QUERY, {"login": LOGIN})
    start = datetime.fromisoformat(data["user"]["createdAt"].replace("Z", "+00:00"))
    now = datetime.now(IST)
    counts = {}
    # The API accepts at most one year per request.
    while start < now:
        end = min(start + timedelta(days=365), now)
        variables = {"login": LOGIN, "from": start.isoformat(), "to": end.isoformat()}
        collection = graphql(token, CALENDAR_QUERY, variables)["user"]["contributionsCollection"]
        for week in collection["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                counts[date.fromisoformat(day["date"])] = day["contributionCount"]
        start = end
    return sorted(counts.items())


def summarize(days):
    """Return (total contributions, current Streak, longest Streak)."""
    total = sum(count for _, count in days)
    active = [day for day, count in days if count > 0]
    # Consecutive dates share the same value of ordinal minus position.
    runs = []
    for _, group in groupby(enumerate(active), key=lambda pair: pair[1].toordinal() - pair[0]):
        run = [day for _, day in group]
        runs.append(Streak(len(run), run[0], run[-1]))
    longest = max(runs, default=Streak())
    # Today is not over yet, so a streak that ended yesterday is still alive.
    current = runs[-1] if runs and (days[-1][0] - runs[-1].end).days <= 1 else Streak()
    return total, current, longest


def format_day(day, today):
    text = f"{day:%b} {day.day}"
    return text if day.year == today.year else f"{text}, {day.year}"


def format_range(streak, today, empty):
    if streak.length == 0:
        return empty
    if streak.start == streak.end:
        return format_day(streak.end, today)
    return f"{streak.start:%b} {streak.start.day} – {format_day(streak.end, today)}"


def render(days):
    total, current, longest = summarize(days)
    first, today = days[0][0], days[-1][0]
    title = (
        f"GitHub streak: {total:,} contributions, current streak {current.length} days, "
        f"longest streak {longest.length} days"
    )
    return f"""<svg width="360" height="140" viewBox="0 0 360 140" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="streakTitle">
  <title id="streakTitle">{title}</title>
  <style>
    text {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; text-anchor: middle; }}
    .num {{ font-size: 24px; font-weight: 700; }}
    .label {{ font-size: 11px; font-weight: 600; }}
    .dates {{ font-size: 9.5px; fill: #a9fef7; }}
  </style>
  <rect width="360" height="140" rx="10" fill="#0d1117"/>
  <path d="M120 28V112M240 28V112" stroke="#00f2fe" stroke-opacity="0.45"/>

  <text x="60" y="62" class="num" fill="#fe428e">{total:,}</text>
  <text x="60" y="88" class="label" fill="#fe428e">Contributions</text>
  <text x="60" y="106" class="dates">Since {first:%b %Y}</text>

  <circle cx="180" cy="54" r="29" stroke="#00f2fe" stroke-width="3"/>
  <circle cx="180" cy="25" r="11" fill="#0d1117"/>
  <path transform="translate(180 27)" d="M0-13C5-7 8-3 8 2A8 8 0 0 1-8 2C-8-2-5-4-4-8-3-5-2-4-1-4-1-7-1-10 0-13Z" fill="#00f2fe"/>
  <text x="180" y="63" class="num" fill="#f8d847">{current.length}</text>
  <text x="180" y="102" class="label" fill="#00f2fe">Current Streak</text>
  <text x="180" y="120" class="dates">{format_range(current, today, "No active streak")}</text>

  <text x="300" y="62" class="num" fill="#fe428e">{longest.length}</text>
  <text x="300" y="88" class="label" fill="#fe428e">Longest Streak</text>
  <text x="300" y="106" class="dates">{format_range(longest, today, "None yet")}</text>
</svg>
"""


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    days = fetch_days(token)
    if not days:
        sys.exit("The contributions calendar came back empty; keeping the existing card")
    OUTPUT.write_text(render(days), encoding="utf-8")


if __name__ == "__main__":
    main()
