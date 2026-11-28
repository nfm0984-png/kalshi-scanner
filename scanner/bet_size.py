#!/usr/bin/env python3
"""Capper bet-size confidence labels (display only — never used to filter picks).

Compare each capper's USD stake to their median stake at similar odds.
High confidence = 3x usual or more. Fun bet = 0.5x usual or less.
Need 8 past bets in the odds bucket (fallback to all odds, and say which).
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

MIN_HISTORY = 8
HIGH_MULT = 3.0
FUN_MULT = 0.5

# Odds buckets so longshots are compared to longshots and favorites to favorites.
# [lo, hi)
BUCKETS = (
    ("longshot", 0.01, 0.35),
    ("mid", 0.35, 0.65),
    ("favorite", 0.65, 0.85),
    ("heavy", 0.85, 1.00),
)


def odds_bucket(avg):
    """Return bucket name for an entry price in (0, 1], or None if unusable."""
    try:
        px = float(avg)
    except (TypeError, ValueError):
        return None
    if not (0.01 <= px <= 1.0):
        return None
    if px >= 1.0:
        return "heavy"
    for name, lo, hi in BUCKETS:
        if lo <= px < hi:
            return name
    return None


def _median(xs):
    if not xs:
        return None
    ys = sorted(xs)
    n = len(ys)
    mid = n // 2
    if n % 2:
        return float(ys[mid])
    return (float(ys[mid - 1]) + float(ys[mid])) / 2.0


def _percentile_below(value, xs):
    """Percent of xs strictly smaller than value, rounded to nearest int."""
    if not xs:
        return None
    n = sum(1 for x in xs if x < value)
    return int(round(100.0 * n / len(xs)))


def usd(n):
    try:
        v = int(round(float(n)))
    except (TypeError, ValueError):
        return "$0"
    sign = "-" if v < 0 else ""
    return sign + "$" + "{:,}".format(abs(v))


def format_label(info):
    tag = info.get("tag")
    n = int(info.get("n") or 0)
    if tag == "thin" or tag is None:
        return "❔ Not enough history yet (%d past bet%s)" % (n, "" if n == 1 else "s")
    mult = info.get("mult")
    usual = info.get("usual")
    pct = info.get("pct")
    via = info.get("via")
    if tag == "high":
        head = "🔥 High confidence"
    elif tag == "fun":
        head = "🎈 Fun bet"
    else:
        head = "👍 Normal size"
    bits = [head]
    if mult is not None:
        bits.append("%.1fx their usual bet" % float(mult))
    if usual is not None:
        where = "at similar odds" if via == "similar" else "across all odds"
        bits[-1] = bits[-1] + " (%s %s)" % (usd(usual), where)
    if pct is not None and n:
        bits.append("bigger than %d%% of %d past bets" % (int(pct), n))
    return " · ".join(bits)


def _norm_row(row):
    if not isinstance(row, dict):
        return None
    try:
        cost = float(row.get("cost") or 0)
    except (TypeError, ValueError):
        return None
    if cost <= 0:
        return None
    avg = row.get("avg")
    try:
        avg = float(avg) if avg is not None else None
    except (TypeError, ValueError):
        avg = None
    if avg is not None and not (0 < avg <= 1.0):
        avg = None
    rid = row.get("id")
    if rid is not None:
        rid = str(rid)
    return {"id": rid, "cost": cost, "avg": avg, "ts": row.get("ts") or 0}


def compare_bet(cost, avg, past, exclude_id=None):
    """Compare one USD stake to a capper's past bets.

    past: iterable of {id, cost, avg} (and optional ts).
    Returns a size info dict with tag, label, mult, usual, n, pct, via.
    """
    try:
        cost = float(cost or 0)
    except (TypeError, ValueError):
        cost = 0.0
    try:
        avg = float(avg) if avg is not None else None
    except (TypeError, ValueError):
        avg = None
    if avg is not None and not (0 < avg <= 1.0):
        avg = None

    ex = str(exclude_id) if exclude_id else None
    rows = []
    for raw in past or []:
        row = _norm_row(raw)
        if not row:
            continue
        if ex and row.get("id") and row["id"] == ex:
            continue
        rows.append(row)

    bucket = odds_bucket(avg) if avg is not None else None
    similar = [r for r in rows if r.get("avg") is not None and odds_bucket(r["avg"]) == bucket] if bucket else []
    if len(similar) >= MIN_HISTORY:
        used, via = similar, "similar"
    else:
        used, via = rows, "all"

    n = len(used)
    if n < MIN_HISTORY or cost <= 0:
        info = {"tag": "thin", "mult": None, "usual": None, "n": n, "pct": None, "via": None}
        info["label"] = format_label(info)
        return info

    costs = [r["cost"] for r in used]
    usual = _median(costs)
    if not usual or usual <= 0:
        info = {"tag": "thin", "mult": None, "usual": None, "n": n, "pct": None, "via": via}
        info["label"] = format_label(info)
        return info

    mult = round(cost / usual, 1)
    if cost >= HIGH_MULT * usual - 1e-9:
        tag = "high"
    elif cost <= FUN_MULT * usual + 1e-9:
        tag = "fun"
    else:
        tag = "normal"
    pct = _percentile_below(cost, costs)
    info = {
        "tag": tag,
        "mult": mult,
        "usual": round(usual, 2),
        "n": n,
        "pct": pct,
        "via": via,
    }
    info["label"] = format_label(info)
    return info


def pick_size_tag(backers):
    """Card tag from already-annotated backers: 'big', 'fun', or None.

    Big if at least one High confidence. Fun-size only if every capper
    (and there is at least one) is a Fun bet. Thin / missing never counts as fun.
    """
    tags = []
    for b in backers or []:
        sz = (b or {}).get("size") if isinstance(b, dict) else None
        tag = (sz or {}).get("tag") if isinstance(sz, dict) else None
        tags.append(tag)
    if not tags:
        return None
    if any(t == "high" for t in tags):
        return "big"
    if tags and all(t == "fun" for t in tags):
        return "fun"
    return None


def _add(hist, key, row):
    row = _norm_row(row)
    if not key or not row:
        return
    k = str(key).lower()
    bucket = hist[k]
    rid = row.get("id")
    if rid:
        for i, prev in enumerate(bucket):
            if prev.get("id") == rid:
                # Keep the larger stake if the same pick appears twice.
                if row["cost"] > (prev.get("cost") or 0):
                    bucket[i] = row
                return
    bucket.append(row)


def _load_json(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default



DATA_DIR = os.path.join(ROOT, "data")
HIST_PATH = os.path.join(DATA_DIR, "bet_size_history.json")
MAX_STORED = 400
_REMEMBERED = {}  # nickname -> list of rows, filled during a scan


def remember(nick, rows):
    key = (nick or "").strip().lower()
    if not key or not rows:
        return
    hist = defaultdict(list)
    for row in (_REMEMBERED.get(key) or []):
        _add(hist, key, row)
    for row in rows:
        _add(hist, key, row)
    _REMEMBERED[key] = (hist.get(key) or [])[-MAX_STORED:]


def remembered():
    return _REMEMBERED


def rows_from_trades(trades, nick):
    """Replay already-fetched public trades into (cost, entry) rows. No extra API calls."""
    if not trades or not nick:
        return []
    try:
        import lib_cappers as lib
    except ImportError:
        return []
    by_tk = defaultdict(list)
    for tr in trades:
        tk = tr.get("ticker") or ""
        if not tk:
            continue
        if not lib.is_sports_ticker(tk):
            continue
        if not lib.parse_trade_role(tr, nick):
            continue
        by_tk[tk].append(tr)
    out = []
    for tk, rows in by_tk.items():
        inv = {"pos": 0.0, "cost": 0.0, "last_ts": None}
        cycle_realized = 0.0
        cycle_risked = 0.0
        cycle_ts0 = None
        cycle_entry = None
        open_cyc = False
        for tr in sorted(rows, key=lambda r: lib.iso_ts(r.get("create_date")) or 0):
            role = lib.parse_trade_role(tr, nick)
            if not role:
                continue
            action, side, _ = role
            try:
                px = float(tr.get("price_dollars") or (float(tr.get("price") or 0) / 100.0))
                qty = float(tr.get("count_fp") or tr.get("count") or 0)
            except Exception:
                continue
            if qty <= 0 or px <= 0:
                continue
            ts = lib.iso_ts(tr.get("create_date"))
            before = inv["pos"]
            realized = lib.apply_fill(inv, action, side, px, qty, ts)
            cycle_realized += realized
            if action == "buy" or (abs(before) <= 1e-9 and abs(inv["pos"]) > 1e-9):
                try:
                    cycle_risked += lib.notional(px, qty)
                except Exception:
                    cycle_risked += px * qty
            if cycle_ts0 is None:
                cycle_ts0 = ts
            open_cyc = True
            if abs(inv["pos"]) > 1e-9:
                yes_avg = inv["cost"] / abs(inv["pos"])
                cycle_entry = yes_avg if inv["pos"] > 0 else (1.0 - yes_avg if yes_avg <= 1 else yes_avg)
            if open_cyc and abs(inv["pos"]) <= 1e-6:
                if cycle_risked > 0 and cycle_entry is not None:
                    out.append({"id": tk, "cost": cycle_risked, "avg": cycle_entry, "ts": cycle_ts0 or ts or 0})
                cycle_realized = 0.0
                cycle_risked = 0.0
                cycle_ts0 = None
                cycle_entry = None
                open_cyc = False
        if open_cyc and abs(inv["pos"]) > 1e-6 and inv.get("cost"):
            yes_avg = inv["cost"] / abs(inv["pos"])
            entry = yes_avg if inv["pos"] > 0 else (1.0 - yes_avg if yes_avg <= 1 else yes_avg)
            cost = abs(inv["pos"]) * entry
            if cost > 0 and entry:
                out.append({"id": tk, "cost": cost, "avg": entry, "ts": inv.get("last_ts") or cycle_ts0 or 0})
    return out


def rows_from_picks(picks):
    out = []
    for p in picks or []:
        if not isinstance(p, dict):
            continue
        cost = p.get("cost")
        avg = p.get("entry") if p.get("entry") is not None else p.get("avg")
        tid = p.get("ticker") or p.get("key") or p.get("id")
        side = p.get("yesNo") or p.get("side") or ""
        pid = ("%s|%s" % (tid, side)).strip("|") if tid else None
        row = _norm_row({"id": pid, "cost": cost, "avg": avg, "ts": p.get("lastTs") or p.get("startTs") or 0})
        if row:
            out.append(row)
    return out


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, dict):
        for k in ("dollars", "usd", "value", "amount"):
            if v.get(k) is not None:
                return _num(v.get(k))
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def rows_from_closed_holdings(holdings):
    out = []
    for h in holdings or []:
        for mh in (h.get("market_holdings") or [h] if isinstance(h, dict) and h.get("market_ticker") else (h.get("market_holdings") or [])):
            if not isinstance(mh, dict):
                continue
            tk = mh.get("market_ticker") or mh.get("ticker")
            avg = _num(mh.get("avg_price") or mh.get("average_price") or mh.get("entry") or mh.get("price"))
            if avg is not None and avg > 1:
                avg = avg / 100.0
            cost = _num(mh.get("total_cost") or mh.get("cost") or mh.get("cost_dollars") or mh.get("position_cost") or mh.get("total_cost_dollars"))
            if cost is None:
                qty = _num(mh.get("count_fp") or mh.get("count") or mh.get("position") or mh.get("signed_open_position"))
                if qty is not None and avg is not None:
                    cost = abs(qty) * avg
            row = _norm_row({"id": tk, "cost": cost, "avg": avg, "ts": mh.get("last_traded_ts") or mh.get("close_ts") or 0})
            if row:
                out.append(row)
    return out


def rows_from_posts(posts):
    out = []
    try:
        import lib_cappers as lib
        cost_of = lib.post_cost_dollars
    except Exception:
        def cost_of(p):
            return _num((p or {}).get("cost") or (p or {}).get("cost_dollars") or (p or {}).get("cost_cents") and (float(p.get("cost_cents")) / 100.0))
    for p in posts or []:
        if not isinstance(p, dict):
            continue
        tk = p.get("market_ticker") or p.get("ticker")
        if not tk:
            continue
        try:
            cost = cost_of(p)
        except Exception:
            cost = _num(p.get("cost"))
        contracts = _num(p.get("payout_if_win_cents"))
        if contracts:
            contracts = contracts / 100.0
        entry = None
        if cost and contracts:
            entry = cost / contracts
        if entry is None:
            entry = _num(p.get("entry") or p.get("avg") or p.get("price") or p.get("yes_price"))
        side = p.get("side") or p.get("yesNo") or ""
        pid = "%s|%s" % (tk, side) if side else tk
        row = _norm_row({"id": pid, "cost": cost, "avg": entry, "ts": p.get("created_ts") or 0})
        if row:
            out.append(row)
    return out


def collect_rows(nick=None, trades=None, picks=None, closed=None, posts=None):
    rows = []
    rows.extend(rows_from_trades(trades, nick))
    rows.extend(rows_from_picks(picks))
    rows.extend(rows_from_closed_holdings(closed))
    rows.extend(rows_from_posts(posts))
    return rows


def load_store(path=None):
    data = _load_json(path or HIST_PATH, {})
    caps = data.get("cappers") if isinstance(data, dict) else {}
    hist = defaultdict(list)
    if isinstance(caps, dict):
        for nick, rows in caps.items():
            for row in rows or []:
                _add(hist, nick, row)
    return hist


def save_store(hist, path=None, now=None):
    path = path or HIST_PATH
    caps = {}
    for nick, rows in hist.items():
        cleaned = []
        seen = set()
        for row in sorted(rows or [], key=lambda r: int(r.get("ts") or 0)):
            row = _norm_row(row)
            if not row:
                continue
            rid = row.get("id")
            if rid:
                if rid in seen:
                    # keep latest by replacing
                    for i, prev in enumerate(cleaned):
                        if prev.get("id") == rid:
                            cleaned[i] = row
                            break
                    continue
                seen.add(rid)
            cleaned.append({"id": row.get("id"), "cost": round(row["cost"], 2), "avg": (round(row["avg"], 4) if row.get("avg") is not None else None), "ts": int(row.get("ts") or 0)})
        caps[nick] = cleaned[-MAX_STORED:]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"updatedTs": int(now or 0), "cappers": caps}, f, separators=(",", ":"))
        f.write("\n")
    os.replace(tmp, path)
    return path


def history_from_payload(payload, hist=None):
    hist = hist if hist is not None else defaultdict(list)
    for g in (payload or {}).get("games") or []:
        for p in g.get("picks") or []:
            pid_base = p.get("ticker") or p.get("key") or p.get("mid") or ""
            yesno = ((p.get("view") or {}).get("yesNo") if isinstance(p.get("view"), dict) else None) or p.get("yesNo") or ""
            for b in p.get("backers") or []:
                pid = "%s|%s" % (pid_base, yesno) if pid_base else None
                _add(hist, b.get("name"), {"id": pid, "cost": b.get("cost"), "avg": b.get("avg") if b.get("avg") is not None else b.get("entry"), "ts": b.get("lastTs") or p.get("startTs") or 0})
    for fp in ((payload or {}).get("following") or {}).get("picks") or []:
        pid = "%s|%s" % (fp.get("ticker") or "", fp.get("yesNo") or "")
        _add(hist, fp.get("nickname") or fp.get("name"), {"id": pid.strip("|") or None, "cost": fp.get("cost"), "avg": fp.get("entry") if fp.get("entry") is not None else fp.get("avg"), "ts": fp.get("lastTs") or fp.get("startTs") or 0})
    return hist


def merge_remembered(hist):
    for nick, rows in _REMEMBERED.items():
        for row in rows:
            _add(hist, nick, row)
    return hist


def annotate_backer(b, hist, exclude_id=None):
    if not isinstance(b, dict):
        return b
    key = (b.get("name") or b.get("nickname") or "").lower()
    avg = b.get("avg")
    if avg is None:
        avg = b.get("entry")
    b["size"] = compare_bet(b.get("cost") or 0, avg, hist.get(key) or [], exclude_id=exclude_id)
    return b


def annotate_payload(payload, now=None, persist=True):
    """Attach size fields on game/following capper lines. Merge + save rolling history."""
    if not isinstance(payload, dict):
        return payload
    hist = load_store()
    history_from_payload(payload, hist)
    merge_remembered(hist)
    if persist:
        try:
            save_store(hist, now=now or payload.get("ts"))
        except Exception:
            pass
    for g in payload.get("games") or []:
        for p in g.get("picks") or []:
            pid_base = p.get("ticker") or p.get("key") or p.get("mid") or ""
            yesno = ((p.get("view") or {}).get("yesNo") if isinstance(p.get("view"), dict) else None) or p.get("yesNo") or ""
            pid = ("%s|%s" % (pid_base, yesno)).strip("|") or None
            for b in p.get("backers") or []:
                annotate_backer(b, hist, exclude_id=pid)
            tag = pick_size_tag(p.get("backers"))
            if tag:
                p["sizeTag"] = tag
            elif "sizeTag" in p:
                p.pop("sizeTag", None)
    following = payload.get("following") or {}
    if isinstance(following, dict):
        for fp in following.get("picks") or []:
            pid = ("%s|%s" % (fp.get("ticker") or "", fp.get("yesNo") or "")).strip("|") or None
            annotate_backer(fp, hist, exclude_id=pid)
    return payload
