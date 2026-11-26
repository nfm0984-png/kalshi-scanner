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



def _payout(px):
    if isinstance(px, (int, float)) and 0 < px < 1:
        return 1.0 / px
    return None


def _bucket_stats(rows):
    w = l = pending = 0
    pnl = 0.0
    for r in rows:
        res = r.get("result")
        if res == "W":
            w += 1
        elif res == "L":
            l += 1
        elif res == "pending":
            pending += 1
        u = r.get("pnl")
        if isinstance(u, (int, float)):
            pnl += u
    return {"w": w, "l": l, "pending": pending, "pnl": round(pnl, 2), "n": len(rows)}


def signal_breakdown(picks):
    agree, single, singles, combos, dogs, favs = [], [], [], [], [], []
    for p in picks:
        if (p.get("agree") or 1) >= 2:
            agree.append(p)
        else:
            single.append(p)
        if p.get("combo"):
            combos.append(p)
        else:
            singles.append(p)
        pay = p.get("payout")
        if pay is None:
            pay = _payout(p.get("price"))
        if isinstance(pay, (int, float)):
            (dogs if pay >= 2.0 else favs).append(p)
    out = []
    for label, rows in (
        ("2+ agree", agree),
        ("Single capper", single),
        ("Singles", singles),
        ("Combos", combos),
        ("Underdogs (≥2.0x)", dogs),
        ("Favorites (<2.0x)", favs),
    ):
        if not rows:
            continue
        st = _bucket_stats(rows)
        st["label"] = label
        out.append(st)
    return out



def yes_no(side):
    u = (side or "").strip().upper()
    if u in ("Y", "YES") or u.endswith(" YES") or "BUY YES" in u:
        return "YES"
    if u in ("N", "NO") or u.endswith(" NO") or "BUY NO" in u:
        return "NO"
    return u


def _dedupe_key(p):
    tk = (p.get("ticker") or "").strip().upper()
    yn = yes_no(p.get("yesNo") or p.get("side"))
    if tk and yn:
        return ("t", tk, yn)
    return ("q", (p.get("q") or p.get("label") or "").strip().lower(), yn, p.get("start") or p.get("startTs") or 0)


def dedupe_picks(raw):
    groups, order = {}, []
    for p in raw:
        k = _dedupe_key(p)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(p)
    out = []
    for k in order:
        rows = groups[k]
        names = []
        for r in rows:
            n = (r.get("capper") or "").strip()
            if n and n not in names:
                names.append(n)
        agree = max(len(names) or 0, max((r.get("agree") or 1) for r in rows), len(rows))
        results = [r.get("result") for r in rows]
        if "W" in results and "L" not in results:
            res = "W"
        elif "L" in results and "W" not in results:
            res = "L"
        else:
            res = rows[0].get("result") or "pending"
        proto = dict(rows[0])
        yn = yes_no(proto.get("yesNo") or proto.get("side"))
        proto["yesNo"] = yn
        proto["side"] = yn
        proto["result"] = res
        proto["agree"] = agree
        proto["cappers"] = names
        proto["capper"] = names[0] if len(names) == 1 else proto.get("capper") or ""
        proto["capperNote"] = names[0] if len(names) == 1 else ("%d capper%s" % (agree, "" if agree == 1 else "s"))
        # One flat-unit PnL: keep the first row that matches the consensus result
        pnl = None
        price = proto.get("price")
        for r in rows:
            if r.get("result") == res:
                if r.get("pnl") is not None and pnl is None:
                    pnl = r.get("pnl")
                if r.get("price") is not None and price is None:
                    price = r.get("price")
        proto["price"] = price
        proto["payout"] = None if _payout(price) is None else round(_payout(price), 2)
        proto["pnl"] = None if pnl is None or abs(pnl) < 0.005 else round(pnl, 2)
        out.append(proto)
    return out


def drop_split_picks(picks):
    from collections import defaultdict
    by_tk, by_q = defaultdict(set), defaultdict(set)
    for p in picks:
        yn = yes_no(p.get("yesNo") or p.get("side"))
        tk = (p.get("ticker") or "").strip().upper()
        if tk and yn in ("YES", "NO"):
            by_tk[tk].add(yn)
        qk = ((p.get("q") or p.get("label") or "").strip().lower(), p.get("start") or p.get("startTs") or 0)
        if qk[0] and yn in ("YES", "NO"):
            by_q[qk].add(yn)
    split_tk = {tk for tk, s in by_tk.items() if "YES" in s and "NO" in s}
    split_q = {k for k, s in by_q.items() if "YES" in s and "NO" in s}
    kept, hidden = [], set()
    for p in picks:
        tk = (p.get("ticker") or "").strip().upper()
        qk = ((p.get("q") or p.get("label") or "").strip().lower(), p.get("start") or p.get("startTs") or 0)
        if (tk and tk in split_tk) or (qk[0] and qk in split_q):
            hidden.add(tk or qk[0])
            continue
        kept.append(p)
    return kept, len(hidden)


def totals_of(picks):
    w = l = pending = 0
    pnl = 0.0
    for p in picks:
        res = p.get("result")
        if res == "W":
            w += 1
        elif res == "L":
            l += 1
        elif res == "pending":
            pending += 1
        u = p.get("pnl")
        if isinstance(u, (int, float)):
            pnl += u
    return w, l, pending, round(pnl, 2)


def day_summary(data):
    return {
        "date": data.get("date"),
        "label": data.get("label"),
        "w": data.get("w") or 0,
        "l": data.get("l") or 0,
        "pending": data.get("pending") or 0,
        "pnl": data.get("pnl"),
        "n": len(data.get("picks") or []),
    }


def merge_history(existing, data):
    hist = list((existing or {}).get("history") or [])
    if not hist and existing and existing.get("date") and existing.get("date") != data.get("date"):
        hist.append(day_summary(existing))
    hist = [h for h in hist if h.get("date") != data.get("date")]
    hist.append(day_summary(data))
    hist.sort(key=lambda h: h.get("date") or "")
    return hist[-7:]


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
            "payout": None if _payout(row.get("price")) is None else round(_payout(row.get("price")), 2),
            "startTs": st,
            "label": label,
            "result": "W" if status == "win" else ("L" if status == "loss" else "pending"),
            "pnl": None if units is None or abs(units) < 0.005 else round(units, 2),
        }
        item["yesNo"] = yes_no(item.get("side"))
        picks.append(item)
    picks = dedupe_picks(picks)
    picks, hidden_splits = drop_split_picks(picks)
    picks.sort(key=lambda r: (r.get("startTs") or 0, r.get("capperNote") or r.get("capper") or ""))
    w, l, pending, pnl = totals_of(picks)
    label = datetime(day.year, day.month, day.day, tzinfo=PT).strftime("%a %b %-d, %Y") + " PT"
    return {
        "date": day.isoformat(),
        "label": label,
        "updatedAt": now.astimezone(PT).strftime("%a %b %-d · %-I:%M %p PT"),
        "w": w,
        "l": l,
        "pending": pending,
        "pnl": round(pnl, 2),
        "pnlNote": "Flat $1 at the first shown price · unique contracts only",
        "hiddenSplits": hidden_splits,
        "breakdown": signal_breakdown(picks),
        "picks": picks,
    }


def write(path=OUT, now=None):
    existing = {}
    if os.path.exists(path):
        try:
            existing = json.load(open(path))
        except Exception:
            existing = {}
    data = build(now)
    data["history"] = merge_history(existing, data)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return data


if __name__ == "__main__":
    d = write()
    print("scorecard", d["label"], "%d-%d" % (d["w"], d["l"]), "pending", d["pending"], "pnl", d["pnl"], "n", len(d["picks"]), "hiddenSplits", d.get("hiddenSplits") or 0, "history", len(d.get("history") or []))
