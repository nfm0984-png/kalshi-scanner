#!/usr/bin/env python3
"""Build yesterday's scanner-pick scorecard (W-L and $) from data/scanner_record.json."""
import json, os, re, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REC = os.path.join(ROOT, "data", "scanner_record.json")
TRIAL = os.path.join(ROOT, "data", "trial_picks.json")
OUT = os.path.join(ROOT, "scorecard.json")
PT = ZoneInfo("America/Los_Angeles")
SERIES = {
    "KXATPCHALLENGERMATCH": "ATP Challenger", "KXWTACHALLENGERMATCH": "WTA Challenger",
    "KXATPMATCH": "ATP", "KXWTAMATCH": "WTA", "KXITFMATCH": "ITF tennis",
    "KXNBAGAME": "NBA", "KXNBASPREAD": "NBA spread", "KXNBATOTAL": "NBA total", "KXNBAREB": "NBA rebounds",
    "KXNFLGAME": "NFL", "KXNFLSPREAD": "NFL spread", "KXNFLTOTAL": "NFL total",
    "KXNHLGAME": "NHL", "KXNHLSPREAD": "NHL spread", "KXNHLTOTAL": "NHL total",
    "KXNCAAFGAME": "NCAAF", "KXNCAAFTOTAL": "NCAAF total", "KXNCAAFSPREAD": "NCAAF spread",
    "KXNCAAMBGAME": "NCAAB", "KXNCAAMBTOTAL": "NCAAB total", "KXNCAAMBSPREAD": "NCAAB spread",
    "KXUCLGAME": "UCL", "KXUCLTOTAL": "UCL total", "KXUCLSPREAD": "UCL spread",
    "KXEPLGAME": "EPL", "KXAFCCL": "AFC Champions League", "KXAFCCLTOTAL": "AFC Champions League total",
    "KXMVECROSSCATEGORY": "Combo", "KXSERIEAGAME": "Serie A",
}


def _px_units(status, px):
    if status == "win":
        return (1.0 / px - 1.0) if isinstance(px, (int, float)) and 0 < px < 1 else None
    if status == "loss":
        return -1.0
    return None


def yesterday_date(now=None):
    now = now or datetime.now(PT)
    return (now.astimezone(PT) - timedelta(days=1)).date()


def pretty_ticker(ticker):
    tk = (ticker or "").strip()
    if not tk:
        return ""
    head = tk.split("-", 1)[0]
    return SERIES.get(head) or re.sub(r"^KX", "", head).replace("GAME", "").replace("MATCH", " match").strip() or tk


def load_trial():
    if not os.path.exists(TRIAL):
        return {}
    try:
        data = json.load(open(TRIAL))
    except Exception:
        return {}
    out = {}
    for p in data.get("picks") or []:
        tk = (p.get("ticker") or "").upper()
        side = (p.get("yesNo") or p.get("side") or "").title()
        nick = (p.get("nickname") or "").lower()
        label = " · ".join([x for x in (p.get("backing") or "", p.get("game") or "") if x])
        if not label:
            continue
        if tk and side and nick:
            out[(tk, side, nick)] = label
        if tk and side:
            out.setdefault((tk, side), label)
        if tk:
            out.setdefault((tk,), label)
    return out


def fetch_title(ticker):
    tk = (ticker or "").strip()
    if not tk:
        return ""
    url = "https://api.elections.kalshi.com/trade-api/v2/markets/" + tk
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "kalshi-scorecard/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.load(r)
        m = (d.get("market") or d)
        ev = (d.get("event") or {})
        title = ev.get("title") or m.get("event_title") or m.get("title") or m.get("yes_sub_title") or ""
        return (title or "").strip()
    except Exception:
        return ""


def pick_label(row, trial):
    for key in ("label", "game", "backing"):
        v = (row.get(key) or "").strip()
        if v and not v.upper().startswith("KX"):
            return v
    tk = (row.get("ticker") or "").upper()
    side = (row.get("side") or "").title()
    nick = (row.get("capper") or "").lower()
    for k in ((tk, side, nick), (tk, side), (tk,)):
        if k in trial:
            return trial[k]
    fetched = fetch_title(row.get("ticker"))
    if fetched:
        return fetched
    pretty = pretty_ticker(row.get("ticker"))
    if pretty and side:
        return pretty + " · " + side
    return pretty or (row.get("ticker") or "Pick")


def build(now=None):
    now = now or datetime.now(PT)
    day = yesterday_date(now)
    led = json.load(open(REC)) if os.path.exists(REC) else {"picks": {}}
    trial = load_trial()
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
        label = pick_label(row, trial)
        item = {
            "capper": row.get("capper") or "",
            "ticker": row.get("ticker") or "",
            "side": row.get("side") or "",
            "combo": bool(row.get("combo")),
            "price": row.get("price"),
            "startTs": st,
            "label": label,
            "result": "W" if status == "win" else ("L" if status == "loss" else "pending"),
            "pnl": None if units is None or abs(units) < 0.005 else round(units, 2),
        }
        picks.append(item)
        if status == "win":
            w += 1
            if units is not None:
                pnl += units
        elif status == "loss":
            l += 1
            if units is not None:
                pnl += units
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
