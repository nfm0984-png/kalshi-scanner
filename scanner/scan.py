#!/usr/bin/env python3
"""Kalshi Scanner: Sports leaderboard cappers with public books, grouped into game cards.

Source: Kalshi's public social + trade APIs (api.elections.kalshi.com).
Kalshi has no 30-day leaderboard period; the closest is 'monthly'.
Capper DB: data/cappers_active.json, data/cappers_queue.json, data/cappers_rejected.json.
Scan order: refresh active, review the queue (active vs rejected), then enqueue 10 new names.
Reject = hidden book, market-maker, or no sports activity at all — never rechecked.
A visible sports trader with no open picks today stays in the active db.
W-L is reconstructed from the public sports trade tape — never fabricated.
"""
from __future__ import annotations

import json, os, re, sys, time, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import lib_cappers as lib

PT = lib.PT
MIN_BET = 100  # lower than the whale site so more public books show
MAX_ENTRY = 0.90
WINDOW_SECS = 24 * 3600
DECIDED_PX = 0.97
KFINAL = ("finalized", "determined", "settled", "closed", "deactivated", "inactive")
LIVE_HOURS = {
    "NFL": 4, "CFB": 4, "NCAAF": 4, "MLB": 3.5, "ATP": 3.5, "WTA": 3.5, "TENNIS": 3.5,
    "UFC": 6, "MMA": 6, "BOXING": 6, "CBB": 2.75, "NCAAB": 2.75, "NCAAMB": 2.75,
    "NBA": 3, "NHL": 3, "CS2": 3.5, "DOTA2": 3.5, "LOL": 3.5, "VAL": 3.5, "ESPORTS": 3.5,
}


def live_secs(league):
    return int(3600 * LIVE_HOURS.get((league or "").upper(), 3))


def pt(ts):
    return lib.pt(ts) if ts else ""


def bet_type(ticker, label=""):
    ser = ((ticker or "").split("-")[0] or "").upper()
    if re.search(r"SPREAD", ser):
        return "Spread"
    if re.search(r"TOTAL", ser):
        return "Totals"
    if re.search(r"BTTS", ser):
        return "Both teams to score"
    if re.search(r"(GAME|FIGHT|MATCH|WINNER)$", ser):
        return "Moneyline"
    if re.search(r"(PTS|PASS|RSH|RUSH|REC|YDS|REB|AST|TD|3PT|SOG|SAVE|STRIKE|HIT|GOAL)", ser):
        return "Player props"
    lab = label or ""
    if re.search(r"spread|\+\d|-\d+\.5", lab, re.I):
        return "Spread"
    if re.search(r"^(over|under)\b", lab, re.I):
        return "Totals"
    return "Other"


def board_set(boards, period, n):
    out = set()
    for nick, rec in boards.items():
        r = (rec.get("ranks") or {}).get(period)
        if r and r <= n:
            out.add(nick)
    return out


def capper_tier(nick, at50, mo50, at100, mo100):
    if nick in at50 and nick in mo50:
        return "Core"
    if nick in at50 or nick in mo50:
        return "Top 50"
    if nick in at100 or nick in mo100:
        return "Board"
    return "Weekly"


def game_finished(info, now, league):
    status = (info.get("status") or "").lower()
    if status in KFINAL or info.get("result") in ("yes", "no"):
        return True, "kalshi " + (status or str(info.get("result")))
    start = info.get("start_ts") or 0
    close = info.get("close_ts") or 0
    if close and now >= close:
        return True, "past close"
    if start and now >= start + live_secs(league):
        return True, "past max duration"
    if start and now >= start and (league or "").upper() not in ("UFC", "MMA", "BOXING"):
        ya, na = info.get("yes_ask"), info.get("no_ask")
        kind = bet_type(info.get("ticker") or "", info.get("title") or "")
        if kind == "Moneyline" and ((ya is not None and ya >= DECIDED_PX) or (na is not None and na >= DECIDED_PX)):
            return True, "decided at %s/%s" % (ya, na)
    return False, ""


def rec_line(nick, graded, pnl, age, extra=""):
    parts = [nick]
    if graded and graded.get("n"):
        parts.append("%d-%d" % (graded.get("w") or 0, graded.get("l") or 0))
        if graded.get("roi") is not None:
            parts.append("%s%.0f%%" % ("+" if graded["roi"] >= 0 else "", graded["roi"]))
    if pnl is not None:
        parts.append(signed_k(pnl) + " all")
    if extra:
        parts.append(extra)
    return " · ".join(parts)


def signed_k(n):
    sign = "+" if n >= 0 else "-"
    a = abs(n)
    if a >= 1_000_000:
        return sign + "$" + ("%.2f" % (a / 1_000_000)).rstrip("0").rstrip(".") + "M"
    if a >= 10_000:
        return sign + "$" + "%.1fk" % (a / 1000)
    if a >= 1000:
        return sign + "$" + "%.2fk" % (a / 1000) if a % 1000 else sign + "$" + "%dk" % (a // 1000)
    return sign + "$" + ("%d" % round(a) if abs(n - round(n)) < 0.5 else "%.0f" % a)


DATA_DIR = os.path.join(ROOT, "data")
ACTIVE_PATH = os.path.join(DATA_DIR, "cappers_active.json")
QUEUE_PATH = os.path.join(DATA_DIR, "cappers_queue.json")
REJECTED_PATH = os.path.join(DATA_DIR, "cappers_rejected.json")
PINNED_PATH = os.path.join(DATA_DIR, "cappers_pinned.json")
TRIAL_PATH = os.path.join(DATA_DIR, "trial_picks.json")
# Drop-in from another worker: if this appears, names are merged into the pinned list.
PINNED_DROPINS = [
    "/workspace/kalshi-top10-cappers.json",
    os.path.join(ROOT, "kalshi-top10-cappers.json"),
    os.path.join(DATA_DIR, "kalshi-top10-cappers.json"),
]
PINNED_TAG = "My 40"
PINNED_TAGS = {PINNED_TAG, "Top 10", "Following"}  # accept older badge labels

def is_pin_tag(v):
    return (v or "") in PINNED_TAGS

TARGET_FOLLOW = 40  # keep discovering every hour even at 40; swap if a pin goes losing
NEW_PER_SCAN_DEFAULT = 20  # hourly cron stays at 20


def _env_int(name, default, lo=1, hi=200):
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return max(lo, min(hi, int(float(str(raw).strip()))))
    except Exception:
        return default


NEW_PER_SCAN = _env_int("NEW_PER_SCAN", NEW_PER_SCAN_DEFAULT)
REVIEW_NEW = os.environ.get("REVIEW_NEW", "").strip().lower() in ("1", "true", "yes")

# Already reviewed in the first live scan (visible sports traders stay active
# even with no open pick today). Market-makers go to rejected and are never rechecked.
BOOTSTRAP_ACTIVE = [
    "WorkerTrader", "BWmarkets", "reluctant.fox5394", "iluminado", "past.grass",
    "autofade", "breezy.panther", "norrisfan", "devex", "bama0037", "regine",
]
BOOTSTRAP_REJECTED = [
    ("clis41", "market-maker", "MM-like tape and 658 open markets"),
    ("BitcoinTradingChallenge", "market-maker", "MM-like tape and 33 open markets"),
]

BOARD_CATS = ["Sports", "Politics", "Economics", "Crypto", "Mentions"]
BOARD_PERIODS = ["all_time", "monthly", "weekly", "yearly"]
BOARD_METRICS = ["projected_pnl", "volume"]


def today_pt(now=None):
    return dt.datetime.fromtimestamp(int(now or time.time()), PT).strftime("%Y-%m-%d")


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        return json.load(open(path))
    except Exception:
        return default


def save_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    json.dump(payload, open(tmp, "w"), indent=2)
    os.replace(tmp, path)


def nick_key(n):
    return (n or "").strip()


def load_dbs():
    active = load_json(ACTIVE_PATH, {"updatedAt": "", "cappers": []})
    queue = load_json(QUEUE_PATH, {"updatedAt": "", "cappers": []})
    rejected = load_json(REJECTED_PATH, {"updatedAt": "", "cappers": []})
    if not active.get("cappers") and not rejected.get("cappers") and not queue.get("cappers"):
        now_s = today_pt()
        active["cappers"] = [{"nickname": n, "addedAt": now_s, "source": "bootstrap"} for n in BOOTSTRAP_ACTIVE]
        rejected["cappers"] = [
            {"nickname": n, "reason": reason, "date": now_s, "ts": int(time.time()), "detail": detail}
            for n, reason, detail in BOOTSTRAP_REJECTED
        ]
    return active, queue, rejected


def save_dbs(active, queue, rejected, now):
    ts = pt(now)
    active["updatedAt"] = ts
    queue["updatedAt"] = ts
    rejected["updatedAt"] = ts
    save_json(ACTIVE_PATH, active)
    save_json(QUEUE_PATH, queue)
    save_json(REJECTED_PATH, rejected)


def known_nicks(active, queue, rejected):
    s = set()
    for row in active.get("cappers") or []:
        if row.get("nickname"):
            s.add(nick_key(row["nickname"]))
    for row in queue.get("cappers") or []:
        if row.get("nickname"):
            s.add(nick_key(row["nickname"]))
    for row in rejected.get("cappers") or []:
        if row.get("nickname"):
            s.add(nick_key(row["nickname"]))
    return s


def rejected_set(rejected):
    return {nick_key(r["nickname"]) for r in (rejected.get("cappers") or []) if r.get("nickname")}


def reject(rejected, nick, reason, detail="", now=None):
    now = int(now or time.time())
    if is_pinned(nick):
        return
    if nick_key(nick) in rejected_set(rejected):
        return
    rejected.setdefault("cappers", []).append({
        "nickname": nick,
        "reason": reason,
        "date": today_pt(now),
        "ts": now,
        "detail": detail or "",
    })


def parse_capper_names(raw):
    """Accept a list of nicks, {cappers|nicknames|names|top10: [...]}, or newline text."""
    names = []
    if raw is None:
        return names
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = [n.strip() for n in raw.splitlines() if n.strip() and not n.strip().startswith("#")]
    if isinstance(raw, dict):
        raw = raw.get("cappers") or raw.get("nicknames") or raw.get("names") or raw.get("top10") or raw.get("traders") or []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, dict):
                n = item.get("nickname") or item.get("name") or item.get("nick") or item.get("username")
                if n and str(n).strip():
                    names.append(str(n).strip())
    out, seen = [], set()
    for n in names:
        k = nick_key(n).lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(nick_key(n))
    return out


def load_pinned_file():
    return load_json(PINNED_PATH, {"tag": PINNED_TAG, "updatedAt": "", "cappers": []})


def save_pinned_file(payload, now=None):
    payload["tag"] = payload.get("tag") or PINNED_TAG
    if now:
        payload["updatedAt"] = pt(now)
    save_json(PINNED_PATH, payload)


def do_not_pin_set(pinned=None):
    pinned = pinned if pinned is not None else load_pinned_file()
    return {nick_key(n).lower() for n in (pinned.get("doNotPin") or []) if nick_key(n)}


def merge_dropin_pins(pinned, log=print):
    """If a worker dropped kalshi-top10-cappers.json, merge those nicks into the pinned list.
    Names on doNotPin (reviewed, no winning record) are never re-seeded."""
    added = []
    have = {nick_key(r.get("nickname") if isinstance(r, dict) else r).lower() for r in (pinned.get("cappers") or [])}
    skip = do_not_pin_set(pinned)
    # Drop any excluded names already sitting on the pinned list
    pinned["cappers"] = [
        r for r in (pinned.get("cappers") or [])
        if nick_key(r.get("nickname") if isinstance(r, dict) else r).lower() not in skip
    ]
    have = {nick_key(r.get("nickname") if isinstance(r, dict) else r).lower() for r in (pinned.get("cappers") or [])}
    for path in PINNED_DROPINS:
        if not os.path.exists(path):
            continue
        try:
            raw = json.load(open(path))
        except Exception as e:
            log("pinned drop-in unreadable %s: %s" % (path, e))
            continue
        for nick in parse_capper_names(raw):
            k = nick.lower()
            if k in have:
                continue
            if k in skip:
                log("pinned: not re-seeding doNotPin %s from %s" % (nick, path))
                continue
            have.add(k)
            pinned.setdefault("cappers", []).append({
                "nickname": nick,
                "tag": PINNED_TAG,
                "source": path,
                "addedAt": today_pt(),
            })
            added.append(nick)
        if added:
            log("pinned: merged %d from %s: %s" % (len(added), path, ", ".join(added)))
    return added


def pinned_names(pinned=None):
    pinned = pinned if pinned is not None else load_pinned_file()
    names = []
    for r in pinned.get("cappers") or []:
        n = nick_key(r.get("nickname") if isinstance(r, dict) else r)
        if n:
            names.append(n)
    return names


def is_pinned(nick, pinned=None):
    k = nick_key(nick).lower()
    return bool(k) and k in {n.lower() for n in pinned_names(pinned)}


def apply_pins(active, queue, rejected, pinned, now, log=print):
    """Seed pinned nicks into active, un-reject them, pull them out of the queue. Never reject."""
    moved = []
    have = {nick_key(r.get("nickname")).lower(): r for r in (active.get("cappers") or []) if r.get("nickname")}
    for nick in pinned_names(pinned):
        k = nick.lower()
        # pull out of rejected / queue
        before_r = len(rejected.get("cappers") or [])
        rejected["cappers"] = [r for r in (rejected.get("cappers") or []) if nick_key(r.get("nickname")).lower() != k]
        if len(rejected.get("cappers") or []) != before_r:
            log("pinned: un-rejected %s" % nick)
        queue["cappers"] = [r for r in (queue.get("cappers") or []) if nick_key(r.get("nickname")).lower() != k]
        if k in have:
            row = have[k]
            row["pinned"] = True
            row["tag"] = PINNED_TAG
            continue
        row = {"nickname": nick, "addedAt": today_pt(now), "source": "pinned", "pinned": True, "tag": PINNED_TAG}
        active.setdefault("cappers", []).append(row)
        have[k] = row
        moved.append(nick)
    if moved:
        log("pinned: seeded %d into active: %s" % (len(moved), ", ".join(moved)))
    # Clear follow flags on anyone not on the pinned list (they stay in the active db).
    pinset = {n.lower() for n in pinned_names(pinned)}
    skip = do_not_pin_set(pinned)
    for row in active.get("cappers") or []:
        k = nick_key(row.get("nickname")).lower()
        if k in pinset and k not in skip:
            row["pinned"] = True
            row["tag"] = PINNED_TAG
        else:
            if row.get("pinned") or is_pin_tag(row.get("tag")) or is_pin_tag(row.get("tier")):
                row["pinned"] = False
                row["tag"] = ""
    return moved


def reconcile_follow_list(active, pinned, cappers, people, now, log=print):
    """Keep the follow list as winning records only, up to TARGET_FOLLOW.
    Discovery of new cappers continues every hour even when the list is full.
    If a followed capper's graded record falls to W <= L, unpin them (they stay
    in the active db for Coming Up / Ranked) and swap in a new winner if one is available.
    A capper with no graded record yet is not auto-added and is not dropped for being 'losing'."""
    skip = do_not_pin_set(pinned)
    by = {nick_key(c.get("nickname")).lower(): c for c in cappers if c.get("nickname")}
    still, dropped = [], []
    for row in list(pinned.get("cappers") or []):
        nick = nick_key(row.get("nickname") if isinstance(row, dict) else row)
        k = nick.lower()
        cap = by.get(k)
        g = (cap or {}).get("graded")
        if k in skip or is_losing_grade(g):
            why = "doNotPin" if k in skip else "%d-%d" % (g.get("w") or 0, g.get("l") or 0)
            dropped.append("%s (%s)" % (nick, why))
            if cap:
                cap["pinned"] = False
                cap["tag"] = ""
                if is_pin_tag(cap.get("tier")):
                    cap["tier"] = capper_tier(nick, people)
            continue
        still.append(row if isinstance(row, dict) else {"nickname": nick, "tag": PINNED_TAG, "addedAt": today_pt(now)})
        if cap:
            cap["pinned"] = True
            cap["tag"] = PINNED_TAG
            cap["tier"] = PINNED_TAG
    pinned["cappers"] = still
    have = {nick_key(r.get("nickname") if isinstance(r, dict) else r).lower() for r in still}
    cands = []
    for cap in cappers:
        k = nick_key(cap.get("nickname")).lower()
        if not k or k in have or k in skip:
            continue
        if is_winning_grade(cap.get("graded")):
            g = cap["graded"]
            w, l = g.get("w") or 0, g.get("l") or 0
            n = w + l
            cands.append((-(w - l), -w, -(w / n if n else 0), cap))
    cands.sort(key=lambda x: (x[0], x[1], x[2], nick_key(x[3].get("nickname")).lower()))
    added = []
    for _s, _w, _r, cap in cands:
        if len(pinned["cappers"]) >= TARGET_FOLLOW:
            break
        nick = cap["nickname"]
        g = cap["graded"]
        pinned["cappers"].append({
            "nickname": nick,
            "tag": PINNED_TAG,
            "source": "auto-winning",
            "addedAt": today_pt(now),
        })
        cap["pinned"] = True
        cap["tag"] = PINNED_TAG
        cap["tier"] = PINNED_TAG
        have.add(nick.lower())
        added.append("%s %d-%d" % (nick, g.get("w") or 0, g.get("l") or 0))
    if dropped:
        log("follow: unpinned (losing or excluded): " + ", ".join(dropped))
    if added:
        log("follow: auto-pinned %d (target %d): %s" % (len(added), TARGET_FOLLOW, ", ".join(added)))
    log("follow: %d/%d pinned; discovery continues every hour" % (len(pinned["cappers"]), TARGET_FOLLOW))
    save_pinned_file(pinned, now)
    pinset = {nick_key(r.get("nickname") if isinstance(r, dict) else r).lower() for r in (pinned.get("cappers") or [])}
    for row in active.get("cappers") or []:
        k = nick_key(row.get("nickname")).lower()
        if k in pinset:
            row["pinned"] = True
            row["tag"] = PINNED_TAG
        else:
            row["pinned"] = False
            if is_pin_tag(row.get("tag")):
                row["tag"] = ""
    return pinned


def fetch_all_boards(http, log=print):
    """Sports + other category boards, all periods, pnl and volume. Limit 100 (200 is rejected)."""
    people = {}
    coverage = {}
    for cat in BOARD_CATS:
        for period in BOARD_PERIODS:
            for metric in BOARD_METRICS:
                key = "%s:%s:%s" % (cat, period, metric)
                data = http.get(f"{lib.SOCIAL}/leaderboard", {
                    "metric_name": metric,
                    "category": cat,
                    "time_period": period,
                    "limit": 100,
                }) or {}
                rows = data.get("rank_list") or []
                coverage[key] = len(rows)
                for row in rows:
                    nick = nick_key(row.get("nickname") or "")
                    if not nick:
                        continue
                    rec = people.setdefault(nick, {"nickname": nick, "ranks": {}, "pnl": {}, "sources": []})
                    rec["ranks"].setdefault(cat, {})
                    if rec["ranks"][cat].get(period) is None or (row.get("rank") or 9999) < rec["ranks"][cat][period]:
                        rec["ranks"][cat][period] = row.get("rank")
                    if metric == "projected_pnl" and cat == "Sports":
                        rec["pnl"][period] = row.get("value")
                    rec["sources"].append("%s %s #%s" % (cat, period, row.get("rank")))
                    rec["is_anonymous"] = bool(row.get("is_anonymous"))
    log("boards: %d unique names across %d lists" % (len(people), len(coverage)))
    return people, coverage


def sports_ranks(people, nick):
    return ((people.get(nick) or {}).get("ranks") or {}).get("Sports") or {}


def capper_tier(nick, people):
    r = sports_ranks(people, nick)
    at, mo = r.get("all_time") or 9999, r.get("monthly") or 9999
    if at <= 50 and mo <= 50:
        return "Core"
    if at <= 50 or mo <= 50:
        return "Top 50"
    if at <= 100 or mo <= 100 or (r.get("weekly") or 9999) <= 100 or (r.get("yearly") or 9999) <= 100:
        return "Board"
    return "Other"


def has_sports_activity(holdings, trades):
    for h in holdings or []:
        for mh in h.get("market_holdings") or []:
            if lib.is_sports_ticker(mh.get("market_ticker") or ""):
                return True
    for tr in trades or []:
        if lib.is_sports_ticker(tr.get("ticker") or ""):
            return True
    return False


def collect_picks(http, holdings, trades, inv_map, now, mcache, ecache, min_bet=MIN_BET, window_secs=WINDOW_SECS, max_entry=MAX_ENTRY):
    picks = []
    for h in holdings or []:
        ev_tk = h.get("event_ticker") or ""
        for mh in h.get("market_holdings") or []:
            tk = mh.get("market_ticker")
            if not tk:
                continue
            try:
                signed = float(mh.get("signed_open_position") or 0)
            except Exception:
                signed = 0.0
            if abs(signed) < 0.5:
                continue
            info = lib.hydrate_market(http, tk, mcache, ecache)
            if not lib.is_sports_market(info, tk):
                continue
            league = lib.league_of(tk, info.get("category")) or "Sports"
            done, _why = game_finished(info, now, league)
            if done:
                continue
            state = lib.open_state(info, now)
            if state == "final":
                continue
            start_ts = info.get("start_ts") or 0
            if window_secs and start_ts and start_ts > now + window_secs:
                continue
            inv = inv_map.get(tk) if inv_map else None
            entry, cost = lib.pick_entry_and_cost(inv, signed)
            side = "yes" if signed > 0 else "no"
            ask = info.get("yes_ask") if side == "yes" else info.get("no_ask")
            if entry is None and ask is not None:
                entry = ask
                cost = abs(signed) * (entry or 0)
            if max_entry is not None and entry is not None and entry >= max_entry:
                continue
            if min_bet and (cost is None or cost < min_bet):
                continue
            if min_bet and ask is None:
                continue
            if cost is None:
                cost = 0.0
            last_ts = (inv or {}).get("last_ts")
            if not last_ts:
                for tr in trades or []:
                    if tr.get("ticker") == tk:
                        tts = lib.iso_ts(tr.get("create_date"))
                        if tts and (not last_ts or tts > last_ts):
                            last_ts = tts
            backing = (info.get("yes_sub_title") if side == "yes" else info.get("no_sub_title")) or info.get("title") or tk
            game = info.get("event_title") or info.get("title") or ev_tk or tk
            slip = round((ask - entry) * 100, 1) if entry is not None and ask is not None else None
            picks.append({
                "ticker": tk,
                "eventTicker": info.get("event_ticker") or ev_tk,
                "marketTitle": info.get("event_title") or info.get("title") or "",
                "contractTitle": info.get("title") or "",
                "backing": backing,
                "yesNo": "Yes" if side == "yes" else "No",
                "label": backing,
                "entry": round(entry, 4) if entry is not None else None,
                "price": round(ask, 4),
                "yesAsk": info.get("yes_ask"),
                "noAsk": info.get("no_ask"),
                "cost": round(cost, 2),
                "contracts": round(abs(signed), 2),
                "lastTs": last_ts,
                "startTs": start_ts or 0,
                "state": "live" if (start_ts and start_ts <= now) else "upcoming",
                "league": league,
                "game": game,
                "bt": bet_type(tk, backing or info.get("title") or ""),
                "slip": slip,
                "status": info.get("status"),
                "result": info.get("result"),
                "closeTs": info.get("close_ts") or 0,
            })
    return picks


def grade_from_trades(trades, nick):
    """Full traditional-sports W-L from every settled cycle (no dollar floor).
    Used for display and for the My 40 winning-record gate (W > L). A high
    size floor would hide a losing overall book behind a few big wins."""
    cycles = lib.closed_cycles(trades, nick)
    use = lib.grade_big_bets(cycles, 0)
    return use if use and use.get("n") else None


def is_winning_grade(g):
    if not g:
        return False
    w, l = g.get("w") or 0, g.get("l") or 0
    n = g.get("n") or (w + l)
    return n > 0 and w > l


def is_losing_grade(g):
    """True only when a graded record exists and is not winning (W <= L). No record is not losing."""
    if not g:
        return False
    w, l = g.get("w") or 0, g.get("l") or 0
    n = g.get("n") or (w + l)
    return n > 0 and w <= l


def build_capper_row(nick, people, prof, metrics, trades, holdings, picks, now, heavy=False):
    rec = people.get(nick) or {}
    all_time_pnl = lib.usd_units((metrics or {}).get("pnl"))
    if all_time_pnl is None:
        all_time_pnl = (rec.get("pnl") or {}).get("all_time")
    use = grade_from_trades(trades, nick)
    tier = capper_tier(nick, people)
    pin = is_pinned(nick)
    if pin:
        tier = PINNED_TAG  # show as My 40; board rank still lives in ranks{}
    age = lib.age_days((prof or {}).get("joined_at"), now)
    sports_ranks_flat = sports_ranks(people, nick)
    return {
        "nickname": nick,
        "profileUrl": "https://kalshi.com/ideas/profiles/" + nick,
        "joinedAt": (prof or {}).get("joined_at") or "",
        "followers": (prof or {}).get("follower_count") or 0,
        "tier": tier,
        "pinned": pin,
        "tag": PINNED_TAG if pin else "",
        "heavy": bool(heavy),
        "ranks": sports_ranks_flat,
        "pnl": None if all_time_pnl is None else round(all_time_pnl, 2),
        "weeklyPnl": (rec.get("pnl") or {}).get("weekly"),
        "monthlyPnl": (rec.get("pnl") or {}).get("monthly"),
        "ageDays": age,
        "graded": {
            "n": use.get("n") or 0,
            "w": use.get("w") or 0,
            "l": use.get("l") or 0,
            "roi": None if use.get("roi") is None else round(use["roi"], 1),
            "profit": round(use.get("profit") or 0, 2),
            "sample": "full" if (use.get("n") or 0) >= 10 else "small",
        } if use else None,
        "recordLine": rec_line(nick, use, all_time_pnl, age, tier),
        "picks": picks,
        "addedAt": today_pt(now),
    }


def inspect_visible(http, nick, now, mcache, ecache, people, log, trades_pages=20):
    """Return ('active', row) or ('rejected', reason, detail) for a visible-or-unknown nick."""
    vis, _ = lib.holdings_visible(http, nick, limit=5)
    if vis == "hidden":
        return "rejected", "hidden book", "hidden"
    if vis != "visible":
        # Empty/failed API response has no visibility_state — do not permanently reject.
        raise RuntimeError("holdings visibility unknown (%r)" % (vis,))
    prof = (http.get(f"{lib.SOCIAL}/profile", {"nickname": nick}) or {}).get("social_profile") or {}
    metrics = (http.get(f"{lib.SOCIAL}/profile/metrics", {"nickname": nick}) or {}).get("metrics") or {}
    vis2, holdings = lib.paginate_holdings(http, nick)
    if vis2 == "hidden":
        return "rejected", "hidden book", "holdings hidden"
    stop_ts = now - lib.RECORD_DAYS * 86400
    vis3, trades = lib.paginate_trades(http, nick, now, stop_ts, max_pages=trades_pages)
    if vis3 == "hidden":
        return "rejected", "hidden book", "trades hidden"
    hold_n = sum(len(h.get("market_holdings") or []) for h in holdings or [])
    is_mm, mm_why = lib.mm_flags(trades, nick)
    pin = is_pinned(nick)
    if is_mm and hold_n >= 25 and not pin:
        return "rejected", "market-maker", "%s; open=%d trades=%d" % (", ".join(mm_why), hold_n, len(trades))
    if not has_sports_activity(holdings, trades) and not pin:
        return "rejected", "no sports activity", "open=%d trades=%d" % (hold_n, len(trades))
    heavy = bool(is_mm)
    if heavy:
        log("heavy trader kept %s: %s trades=%d open=%d" % (nick, ", ".join(mm_why), len(trades), hold_n))
    inv_map = lib.build_inventory(trades, nick)
    picks = collect_picks(http, holdings, trades, inv_map, now, mcache, ecache)
    follow = []
    if pin:
        follow = collect_picks(http, holdings, trades, inv_map, now, mcache, ecache, min_bet=0, window_secs=0, max_entry=None)
    row = build_capper_row(nick, people, prof, metrics, trades, holdings, picks, now, heavy=heavy)
    row["followingPicks"] = follow
    return "active", row, ""


def trial_grade(info, yes_no):
    """Grade a copied pick from Kalshi's official market result. None = still open."""
    result = (info.get("result") or "").strip().lower()
    status = (info.get("status") or "").strip().lower()
    if result in ("void", "scalar_void", "cancelled", "canceled", "refund") or status in ("cancelled", "canceled"):
        return "push"
    if result in ("yes", "no"):
        side = (yes_no or "").strip().lower()
        if side == result:
            return "win"
        if side in ("yes", "no"):
            return "loss"
    return None


def trial_id(nick, ticker, yes_no):
    return "%s|%s|%s" % (nick_key(nick), ticker or "", yes_no or "")


def update_trial_ledger(http, open_picks, pinned, hidden, now, mcache, ecache, log=print):
    """Record each followed pick once; grade open ledger rows when Kalshi has a result."""
    ledger = load_json(TRIAL_PATH, {"startedAt": "", "startedTs": 0, "updatedAt": "", "picks": []})
    by_id = {row.get("id"): row for row in (ledger.get("picks") or []) if row.get("id")}
    added = 0
    for p in open_picks:
        pid = trial_id(p.get("nickname"), p.get("ticker"), p.get("yesNo"))
        if not p.get("ticker") or pid in by_id:
            continue
        by_id[pid] = {
            "id": pid,
            "nickname": p.get("nickname"),
            "ticker": p.get("ticker"),
            "eventTicker": p.get("eventTicker") or "",
            "game": p.get("game") or "",
            "backing": p.get("backing") or p.get("label") or "",
            "yesNo": p.get("yesNo"),
            "entry": p.get("entry"),
            "price": p.get("price"),
            "cost": p.get("cost"),
            "contracts": p.get("contracts"),
            "startTs": p.get("startTs") or 0,
            "league": p.get("league") or "",
            "bt": p.get("bt") or "",
            "recordedAt": pt(now),
            "recordedTs": now,
            "status": "open",
            "result": None,
            "settledAt": None,
        }
        added += 1
        if not ledger.get("startedAt"):
            ledger["startedAt"] = pt(now)
            ledger["startedTs"] = now
    graded = 0
    for row in by_id.values():
        if (row.get("status") or "open") != "open":
            continue
        tk = row.get("ticker")
        if not tk:
            continue
        try:
            info = lib.hydrate_market(http, tk, mcache, ecache)
        except Exception as e:
            log("trial grade skip %s: %s" % (tk, e))
            continue
        verdict = trial_grade(info, row.get("yesNo"))
        if not verdict:
            continue
        row["status"] = verdict
        row["result"] = info.get("result") or info.get("status")
        row["settledAt"] = pt(now)
        graded += 1
    ledger["picks"] = sorted(by_id.values(), key=lambda r: (r.get("recordedTs") or 0, r.get("id") or ""))
    ledger["updatedAt"] = pt(now)
    save_json(TRIAL_PATH, ledger)
    log("trial ledger: +%d new, graded %d, total %d" % (added, graded, len(ledger["picks"])))

    stats = {}
    def slot(nick):
        k = nick_key(nick)
        if not k:
            return None
        rec = stats.get(k.lower())
        if rec is None:
            rec = {"nickname": k, "w": 0, "l": 0, "p": 0, "n": 0, "hitPct": None, "open": 0, "hidden": nick_key(nick).lower() in hidden}
            stats[k.lower()] = rec
        return rec
    for nick in pinned_names(pinned):
        slot(nick)
    for p in open_picks:
        rec = slot(p.get("nickname"))
        if rec:
            rec["open"] += 1
    # Ledger open rows for a capper with no current book pick still count as open until graded
    open_ids = {trial_id(p.get("nickname"), p.get("ticker"), p.get("yesNo")) for p in open_picks}
    for row in ledger["picks"]:
        rec = slot(row.get("nickname"))
        if not rec:
            continue
        st = row.get("status") or "open"
        if st == "win":
            rec["w"] += 1
        elif st == "loss":
            rec["l"] += 1
        elif st == "push":
            rec["p"] += 1
        elif st == "open" and row.get("id") not in open_ids:
            rec["open"] += 1
    out = []
    for rec in stats.values():
        rec["n"] = rec["w"] + rec["l"]
        rec["hitPct"] = None if not rec["n"] else round(100.0 * rec["w"] / rec["n"], 1)
        out.append(rec)
    out.sort(key=lambda r: (-(r["n"] or 0), -((r["hitPct"] or -1)), r["nickname"].lower()))
    open_sorted = sorted(open_picks, key=lambda p: (0 if (p.get("startTs") and p["startTs"] <= now) else 1, p.get("startTs") or 10**12, p.get("nickname") or "", p.get("ticker") or ""))
    return {
        "startedAt": ledger.get("startedAt") or "",
        "startedTs": ledger.get("startedTs") or 0,
        "cappers": out,
        "picks": open_sorted,
        "recorded": len(ledger["picks"]),
        "graded": sum(1 for r in ledger["picks"] if (r.get("status") or "open") in ("win", "loss", "push")),
    }


def upsert_active(active, row):
    nick = row["nickname"]
    rows = active.setdefault("cappers", [])
    for i, existing in enumerate(rows):
        if nick_key(existing.get("nickname")) == nick_key(nick):
            row["addedAt"] = existing.get("addedAt") or row.get("addedAt")
            # Don't persist bulky picks inside the db; data.json carries them.
            stored = {k: v for k, v in row.items() if k not in ("picks", "followingPicks")}
            stored["pickCount"] = len(row.get("picks") or [])
            stored["followCount"] = len(row.get("followingPicks") or [])
            rows[i] = stored
            return
    stored = {k: v for k, v in row.items() if k not in ("picks", "followingPicks")}
    stored["pickCount"] = len(row.get("picks") or [])
    stored["followCount"] = len(row.get("followingPicks") or [])
    rows.append(stored)


def remove_nick(lst, nick):
    k = nick_key(nick)
    return [r for r in lst if nick_key(r.get("nickname")) != k]


def enqueue_new(queue, people, known, n, now, log=print):
    """Add up to n unseen leaderboard names to the queue. Prefer Sports, then better ranks."""
    def sort_key(nick):
        r = sports_ranks(people, nick)
        sports = 0 if r else 1
        best = min([r.get(p) or 9999 for p in BOARD_PERIODS] or [9999])
        return (sports, best, nick.lower())
    added = []
    for nick in sorted(people.keys(), key=sort_key):
        if len(added) >= n:
            break
        if nick in known:
            continue
        src = ", ".join(((people[nick].get("sources") or [])[:3]) or ["leaderboard"])
        queue.setdefault("cappers", []).append({
            "nickname": nick,
            "addedAt": today_pt(now),
            "source": src,
        })
        known.add(nick)
        added.append(nick)
    log("queued %d new cappers: %s" % (len(added), ", ".join(added) if added else "(none)"))
    return added


def group_games(cappers, now, log=print):
    by, order, dropped = {}, [], []
    for c in cappers:
        rec = c.get("graded")
        for p in c.get("picks") or []:
            gid = p.get("eventTicker") or (p.get("game") + "|" + str(p.get("startTs") or 0))
            if gid not in by:
                by[gid] = {
                    "id": gid, "game": p["game"], "league": p["league"],
                    "startTs": p["startTs"] or 0, "start": pt(p["startTs"]) if p["startTs"] else "",
                    "live": bool(p["startTs"] and p["startTs"] <= now), "state": p["state"], "picks": {},
                }
                order.append(gid)
            g = by[gid]
            if p["startTs"] and (not g["startTs"] or p["startTs"] < g["startTs"]):
                g["startTs"] = p["startTs"]
                g["start"] = pt(p["startTs"])
                g["live"] = p["startTs"] <= now
            key = p["ticker"] + "|" + p["yesNo"]
            slot = g["picks"].setdefault(key, {
                "key": key, "ticker": p["ticker"], "eventTicker": p.get("eventTicker") or gid,
                "mid": p["ticker"], "bt": p["bt"], "big": p["label"],
                "sub": p["game"] if p["label"] != p["game"] else p.get("contractTitle") or "",
                "view": {
                    "backing": p["backing"],
                    "marketTitle": p["marketTitle"] or p.get("contractTitle") or p["game"],
                    "outcome": p["backing"], "yesNo": p["yesNo"], "price": p["price"], "ticker": p["ticker"],
                },
                "backers": [], "total": 0, "tags": [], "slip": p.get("slip"),
                "startTs": p["startTs"], "state": p["state"], "status": p.get("status"),
                "result": p.get("result"), "closeTs": p.get("closeTs") or 0,
                "yesAsk": p.get("yesAsk"), "noAsk": p.get("noAsk"),
            })
            slot["backers"].append({
                "name": c["nickname"], "cost": p["cost"], "avg": p.get("entry"),
                "line": rec_line(c["nickname"], rec, c.get("pnl"), None, c["tier"]),
                "rec": {"w": rec["w"], "l": rec["l"], "n": rec["n"]} if rec else None,
                "lastTs": p.get("lastTs"), "tier": c["tier"],
            })
            slot["total"] = round(sum(b["cost"] for b in slot["backers"]), 2)
            tags = []
            for b in slot["backers"]:
                if b["tier"] not in tags:
                    tags.append(b["tier"])
            slot["tags"] = tags
    games = []
    for gid in order:
        g = by[gid]
        picks = list(g["picks"].values())
        if g["startTs"] and g["startTs"] <= now:
            info = {
                "status": picks[0].get("status"), "result": picks[0].get("result"),
                "start_ts": g["startTs"],
                "close_ts": min((p.get("closeTs") or 0) for p in picks) or 0,
                "yes_ask": next((p.get("yesAsk") for p in picks if p.get("bt") == "Moneyline"), None),
                "no_ask": next((p.get("noAsk") for p in picks if p.get("bt") == "Moneyline"), None),
                "ticker": next((p["ticker"] for p in picks if p.get("bt") == "Moneyline"), picks[0]["ticker"]),
                "title": g["game"],
            }
            done, why = game_finished(info, now, g["league"])
            if done:
                dropped.append("%s (%s)" % (g["game"], why))
                continue
        for p in picks:
            p["backers"].sort(key=lambda b: -(b.get("cost") or 0))
            for k in ("status", "result", "closeTs", "yesAsk", "noAsk"):
                p.pop(k, None)
        g["picks"] = picks
        games.append(g)
    games.sort(key=lambda g: (0 if g["live"] else 1, g["startTs"] or 10**12, g["id"]))
    if dropped:
        log("finished games removed: %d: %s" % (len(dropped), "; ".join(dropped[:12])))
    return games, dropped


def review_queue(http, queue, active, rejected, live_cappers, people, now, mcache, ecache, cov, log=print):
    """Move queued names to active or rejected. Returns how many were reviewed this call."""
    pending = list(queue.get("cappers") or [])
    leftover = []
    reviewed = 0
    for item in pending:
        nick = nick_key(item.get("nickname"))
        if not nick:
            continue
        if nick in rejected_set(rejected) or any(nick_key(r.get("nickname")) == nick for r in active.get("cappers") or []):
            cov["queueReviewed"] += 1
            reviewed += 1
            continue
        try:
            verdict = inspect_visible(http, nick, now, mcache, ecache, people, log, trades_pages=20)
        except Exception as e:
            log("queue review failed %s: %s — leaving in queue" % (nick, e))
            leftover.append(item)
            continue
        cov["queueReviewed"] += 1
        reviewed += 1
        if verdict[0] == "rejected":
            _v, reason, detail = verdict
            if is_pinned(nick):
                log("pinned kept (from queue) despite %s (%s): %s" % (reason, nick, detail))
                kept = {"nickname": nick, "pinned": True, "tag": PINNED_TAG, "tier": PINNED_TAG, "addedAt": today_pt(now), "picks": [], "pickCount": 0, "recordLine": nick + " · " + PINNED_TAG}
                upsert_active(active, kept)
                live_cappers.append(kept)
                continue
            reject(rejected, nick, reason, detail, now)
            cov["queueRejected"] += 1
            if reason == "hidden book":
                cov["hiddenRejected"] += 1
            elif reason == "market-maker":
                cov["mmDropped"] += 1
            elif reason == "no sports activity":
                cov["noSportsRejected"] += 1
            log("queue → rejected %s (%s: %s)" % (nick, reason, detail))
            continue
        _v, cap, _ = verdict
        upsert_active(active, cap)
        live_cappers.append(cap)
        cov["queueToActive"] += 1
        log("queue → active %s picks=%d" % (nick, len(cap.get("picks") or [])))
    queue["cappers"] = leftover
    return reviewed


def build(now=None, log=print):
    now = int(now or time.time())
    t0 = time.time()
    http = lib.Http()
    active, queue, rejected = load_dbs()
    pinned = load_pinned_file()
    merge_dropin_pins(pinned, log)
    apply_pins(active, queue, rejected, pinned, now, log)
    save_pinned_file(pinned, now)
    save_dbs(active, queue, rejected, now)
    people, board_cov = fetch_all_boards(http, log)
    mcache, ecache = {}, {}
    cov = {
        "boards": {k: v for k, v in board_cov.items() if v},
        "leaderboardNames": len(people),
        "activeRefreshed": 0,
        "queueReviewed": 0,
        "queueToActive": 0,
        "queueRejected": 0,
        "queuedNew": 0,
        "mmDropped": 0,
        "hiddenRejected": 0,
        "noSportsRejected": 0,
        "shown": 0,
        "picks": 0,
        "games": 0,
        "finishedDropped": 0,
        "finishedNames": [],
        "calls": 0,
        "retries429": 0,
        "secs": 0,
        "minBet": MIN_BET,
    }
    live_cappers = []
    pinned_hidden = set()

    # 1) Refresh the active db first.
    still_active = []
    for row in list(active.get("cappers") or []):
        nick = nick_key(row.get("nickname"))
        if not nick:
            continue
        if nick in rejected_set(rejected) and not is_pinned(nick):
            continue
        try:
            verdict = inspect_visible(http, nick, now, mcache, ecache, people, log, trades_pages=20)
        except Exception as e:
            log("active refresh failed %s: %s — keeping in active" % (nick, e))
            if is_pinned(nick):
                row = dict(row, pinned=True, tag=PINNED_TAG, tier=row.get("tier") or PINNED_TAG)
            still_active.append(row)
            live_cappers.append(dict(row, picks=row.get("picks") or []))
            continue
        if verdict[0] == "rejected":
            _v, reason, detail = verdict
            if is_pinned(nick):
                log("pinned kept in active despite %s (%s): %s" % (reason, nick, detail))
                if reason == "hidden book":
                    pinned_hidden.add(nick.lower())
                kept = dict(row, pinned=True, tag=PINNED_TAG, tier=PINNED_TAG, rejectNote="%s: %s" % (reason, detail), picks=[], followingPicks=[])
                still_active.append({k: v for k, v in kept.items() if k not in ("picks", "followingPicks")} | {"pickCount": 0, "followCount": 0})
                live_cappers.append(kept)
                continue
            reject(rejected, nick, reason, detail, now)
            if reason == "hidden book":
                cov["hiddenRejected"] += 1
            elif reason == "market-maker":
                cov["mmDropped"] += 1
            elif reason == "no sports activity":
                cov["noSportsRejected"] += 1
            log("active → rejected %s (%s: %s)" % (nick, reason, detail))
            continue
        _v, cap, _ = verdict
        cap["addedAt"] = row.get("addedAt") or cap.get("addedAt")
        stored = {k: v for k, v in cap.items() if k != "picks"}
        stored["pickCount"] = len(cap.get("picks") or [])
        still_active.append(stored)
        live_cappers.append(cap)
        cov["activeRefreshed"] += 1
    active["cappers"] = still_active
    save_dbs(active, queue, rejected, now)
    log("phase 1: refreshed %d active" % cov["activeRefreshed"])

    # If the queue is empty at the start of this cycle (first run), seed 10 so they get reviewed now.
    known = known_nicks(active, queue, rejected)
    seeded = False
    if not (queue.get("cappers") or []):
        enqueue_new(queue, people, known, NEW_PER_SCAN, now, log)
        seeded = True
        save_dbs(active, queue, rejected, now)

    # 2) Review the queue: move each name to active or rejected.
    review_queue(http, queue, active, rejected, live_cappers, people, now, mcache, ecache, cov, log)
    save_dbs(active, queue, rejected, now)
    log("phase 2: reviewed %d queue (%d active, %d rejected)" % (cov["queueReviewed"], cov["queueToActive"], cov["queueRejected"]))

    # 3) Add NEW_PER_SCAN new leaderboard names not already in active/rejected/queue.
    # On a manual big pass (REVIEW_NEW=1), review those names in this same run, then
    # leave the default 20 on the queue for the next hourly cron.
    known = known_nicks(active, queue, rejected)
    added = enqueue_new(queue, people, known, NEW_PER_SCAN, now, log)
    cov["queuedNew"] = len(added)
    save_dbs(active, queue, rejected, now)
    if REVIEW_NEW and added:
        log("phase 3: reviewing %d newly queued names in this run" % len(added))
        review_queue(http, queue, active, rejected, live_cappers, people, now, mcache, ecache, cov, log)
        save_dbs(active, queue, rejected, now)
        log("phase 3: reviewed %d total (%d active, %d rejected)" % (cov["queueReviewed"], cov["queueToActive"], cov["queueRejected"]))
        known = known_nicks(active, queue, rejected)
        leftover = enqueue_new(queue, people, known, NEW_PER_SCAN_DEFAULT, now, log)
        cov["queuedNextHour"] = len(leftover)
        save_dbs(active, queue, rejected, now)
    cov["namesChecked"] = (cov.get("activeRefreshed") or 0) + (cov.get("queueReviewed") or 0)
    cov["newPerScan"] = NEW_PER_SCAN
    cov["reviewNew"] = bool(REVIEW_NEW)

    # Dedup live cappers (active refresh + newly activated)
    byn = {}
    for c in live_cappers:
        byn[nick_key(c["nickname"])] = c
    # Any active db member we failed to refresh still appears on the Cappers tab, no invented picks.
    live_names = set(byn)
    for row in active.get("cappers") or []:
        n = nick_key(row.get("nickname"))
        if n and n not in live_names:
            byn[n] = dict(row, picks=[])
    cappers = list(byn.values())

    games, dropped = group_games(cappers, now, log)
    cov["finishedDropped"] = len(dropped)
    cov["finishedNames"] = dropped
    cov["shown"] = sum(1 for c in cappers if c.get("picks"))
    cov["picks"] = sum(len(g["picks"]) for g in games)
    cov["games"] = len(games)
    cov["calls"] = http.calls
    cov["retries429"] = http.retries_429
    cov["secs"] = round(time.time() - t0, 1)
    cov["dbActive"] = len(active.get("cappers") or [])
    cov["dbQueue"] = len(queue.get("cappers") or [])
    cov["dbRejected"] = len(rejected.get("cappers") or [])
    cov["dbPinned"] = sum(1 for r in (active.get("cappers") or []) if r.get("pinned") or is_pin_tag(r.get("tag")) or is_pin_tag(r.get("tier")))

    def cap_key(c):
        pin_n = 0 if (c.get("pinned") or is_pin_tag(c.get("tier"))) else 1
        tier_n = 0 if is_pin_tag(c.get("tier")) else {"Core": 1, "Top 50": 2, "Board": 3}.get(c.get("tier") or "", 4)
        g = c.get("graded") or {"w": 0, "l": 0, "n": 0}
        n = (g.get("w") or 0) + (g.get("l") or 0)
        wr = (g.get("w") or 0) / n if n else -1
        sample = 0 if n >= 10 else 1
        ungraded = 0 if n else 1
        return (pin_n, ungraded, tier_n, sample, -wr, -(g.get("w") or 0), -(c.get("pnl") or 0))
    # Refresh the follow list from this scan's full W-L, then copy their open picks.
    # Discovery (queue + NEW_PER_SCAN new) already ran above and never stops at TARGET_FOLLOW.
    pinned = reconcile_follow_list(active, pinned, cappers, people, now, log)
    save_dbs(active, queue, rejected, now)
    following_open = []
    for c in cappers:
        if not (c.get("pinned") or is_pinned(c.get("nickname"), pinned)):
            continue
        for p in c.get("followingPicks") or []:
            following_open.append(dict(p, nickname=c.get("nickname"), recordLine=c.get("recordLine") or c.get("nickname"), tier=c.get("tier") or PINNED_TAG))
    following = update_trial_ledger(http, following_open, pinned, pinned_hidden, now, mcache, ecache, log)
    cov["followingOpen"] = len(following.get("picks") or [])
    cov["followingCappers"] = len(following.get("cappers") or [])
    cov["trialRecorded"] = following.get("recorded") or 0
    cov["trialGraded"] = following.get("graded") or 0

    pub_cappers = []
    for c in cappers:
        pub_cappers.append({k: v for k, v in c.items() if k not in ("picks", "followingPicks")} | {"pickCount": len(c.get("picks") or []), "followCount": len(c.get("followingPicks") or [])})
    pub_cappers.sort(key=cap_key)

    payload = {
        "scannedAt": pt(now),
        "ts": now,
        "source": {
            "note": "Kalshi public social + trade APIs. No 30-day leaderboard exists; monthly is the stand-in. Names come from Sports, Politics, Economics, Crypto and Mentions boards (all-time, monthly, weekly, yearly; projected PnL and volume, top 100). Picks are traditional sports singles and sports combos only — esports is excluded. Hidden books, market makers, and traders with no traditional-sports activity are rejected and never rechecked, except followed My 40 cappers, who stay in the active db. Visible sports traders stay in the active db even with no open pick today. My 40 copies every open traditional-sports pick from followed cappers (winning graded record W > L, up to 40) with no dollar minimum and grades them from official Kalshi results after settlement. New cappers are still discovered every hour at 40; a followed capper who falls to a losing record is swapped out (and stays in the general active db). W-L is reconstructed from the public sports tape and is never invented. Coming Up / Ranked minimum open pick is $%d." % MIN_BET,
            "periodUsed": "monthly (no 30-day board exists)",
            "coverage": cov,
            "db": {
                "active": cov["dbActive"],
                "queue": cov["dbQueue"],
                "rejected": cov["dbRejected"],
                "pinned": cov["dbPinned"],
            },
        },
        "cappers": pub_cappers,
        "games": games,
        "following": following,
    }
    log(
        "scan active {dbActive} queue {dbQueue} rejected {dbRejected} shown {shown} "
        "picks {picks} games {games} follow {followingOpen} trial {trialRecorded} "
        "finished {finishedDropped} calls {calls} 429s {retries429} secs {secs}".format(**cov)
    )
    return payload


def main():
    data = build()
    out = os.path.join(ROOT, "data.json")
    json.dump(data, open(out, "w"), indent=2)
    print("wrote", out, "games", len(data["games"]), "cappers", len(data["cappers"]),
          "following", len((data.get("following") or {}).get("picks") or []),
          "db", data["source"]["db"])


if __name__ == "__main__":
    main()
