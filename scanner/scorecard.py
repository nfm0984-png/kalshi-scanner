#!/usr/bin/env python3
"""Build yesterday's scanner-pick scorecard (W-L and $) from data/scanner_record.json."""
import json, os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REC = os.path.join(ROOT, "data", "scanner_record.json")
OUT = os.path.join(ROOT, "scorecard.json")
PT = ZoneInfo("America/Los_Angeles")


def _px_units(status, px):
    if status == "win":
        return (1.0 / px - 1.0) if isinstance(px, (int, float)) and 0 < px < 1 else 0.0
    if status == "loss":
        return -1.0
    return None


def yesterday_date(now=None):
    now = now or datetime.now(PT)
    return (now.astimezone(PT) - timedelta(days=1)).date()


def build(now=None):
    now = now or datetime.now(PT)
    day = yesterday_date(now)
    led = json.load(open(REC)) if os.path.exists(REC) else {"picks": {}}
    picks = []
    w = l = pending = 0
    pnl = 0.0
    for row in (led.get("picks") or {}).values():
        st = row.get("startTs") or 0
        if not st:
            continue
        if datetime.fromtimestamp(st, PT).date() != day:
            continue
        status = row.get("status") or "open"
        units = _px_units(status, row.get("price"))
        item = {
            "capper": row.get("capper") or "",
            "ticker": row.get("ticker") or "",
            "side": row.get("side") or "",
            "combo": bool(row.get("combo")),
            "price": row.get("price"),
            "startTs": st,
            "result": "W" if status == "win" else ("L" if status == "loss" else "pending"),
            "pnl": None if units is None else round(units, 2),
        }
        picks.append(item)
        if status == "win":
            w += 1
            pnl += units or 0
        elif status == "loss":
            l += 1
            pnl += units or 0
        else:
            pending += 1
    picks.sort(key=lambda r: (r.get("startTs") or 0, r.get("capper") or ""))
    label = datetime(day.year, day.month, day.day, tzinfo=PT).strftime("%a %b %-d, %Y") + " PT"
    return {
        "date": day.isoformat(),
        "label": label,
        "updatedAt": now.astimezone(PT).strftime("%a %b %-d · %-I:%M %p PT"),
        "w": w,
        "l": l,
        "pending": pending,
        "pnl": round(pnl, 2),
        "pnlNote": "Flat $1 at the first shown price",
        "picks": picks,
    }


def write(path=OUT, now=None):
    data = build(now)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return data


if __name__ == "__main__":
    d = write()
    print("scorecard", d["label"], "%d-%d" % (d["w"], d["l"]), "pending", d["pending"], "pnl", d["pnl"], "n", len(d["picks"]))
