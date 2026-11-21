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
HISTORY_PATH = os.path.join(DATA_DIR, "scan_history.json")
CARRY_SEED_PATH = os.path.join(DATA_DIR, "carry_seed.json")
DATA_JSON_PATH = os.path.join(ROOT, "data.json")
HISTORY_KEEP = 48
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
# Graded winners need official all-time profit of at least $10,000.
# Leaderboard names with no public W-L can still follow at $100,000 official profit.
MIN_FOLLOW_SAMPLE = 1
MIN_FOLLOW_PNL = 10000.0
MIN_FOLLOW_PNL_EARNER = 100000.0
FOLLOW_HORIZON_DAYS = 30  # My 40 keeps near-term sports only, not months-out futures
FOLLOW_HORIZON_SECS = FOLLOW_HORIZON_DAYS * 86400
NEW_PER_SCAN_DEFAULT = 30  # hourly cron; stay under Actions time with 0 429s


def _env_int(name, default, lo=0, hi=200):
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return max(lo, min(hi, int(float(str(raw).strip()))))
    except Exception:
        return default


NEW_PER_SCAN = _env_int("NEW_PER_SCAN", _env_int("NEW_NAMES", NEW_PER_SCAN_DEFAULT))
REVIEW_NEW = os.environ.get("REVIEW_NEW", "").strip().lower() in ("1", "true", "yes")
SCAN_MODE = os.environ.get("KALSHI_SCAN_MODE", "scan").strip().lower()  # "scan" | "follow"

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
# Extra sport-specific board names; empty API results are ignored.
SPORT_BOARD_CATS = [
    "NFL", "NBA", "MLB", "NHL", "NCAAF", "NCAAB", "CFB", "CBB", "WNBA",
    "Soccer", "Football", "Basketball", "Tennis", "MMA", "UFC", "Golf",
    "MLS", "EPL", "NCAAMB", "College Football", "College Basketball",
]
BOARD_PERIODS = ["all_time", "monthly", "weekly", "yearly"]
BOARD_METRICS = ["projected_pnl", "volume"]
ALL_BOARD_CATS = BOARD_CATS + [c for c in SPORT_BOARD_CATS if c not in BOARD_CATS]


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
    payload["target"] = TARGET_FOLLOW
    payload["note"] = (
        "Followed cappers for My 40, taken from official Kalshi projected-PnL "
        "leaderboards. A name is followed if (graded W > L and official all-time "
        "profit of at least $10,000) or (no public graded record and official "
        "all-time profit of at least $100,000). A losing reconstructed record is "
        "out. doNotPin names, including 80Mill, never re-enter, including via the "
        "never-shrink guard. Up to %d. A scan will not shrink the follow list "
        "unless each dropped name actually failed a gate or is on doNotPin."
        % TARGET_FOLLOW
    )
    if now:
        payload["updatedAt"] = pt(now)
    save_json(PINNED_PATH, payload)


def do_not_pin_entries(pinned=None):
    """Normalize doNotPin to {nickname, reason, at} dicts. Older files stored bare names."""
    pinned = pinned if pinned is not None else load_pinned_file()
    out = []
    seen = set()
    for n in (pinned.get("doNotPin") or []):
        if isinstance(n, dict):
            nick = nick_key(n.get("nickname") or n.get("name"))
            reason = (n.get("reason") or "excluded").strip() or "excluded"
            at = n.get("at") or n.get("updatedAt") or ""
        else:
            nick = nick_key(n)
            reason, at = "reviewed", ""
        k = nick.lower()
        if not nick or k in seen:
            continue
        seen.add(k)
        out.append({"nickname": nick, "reason": reason, "at": at})
    return out


def do_not_pin_set(pinned=None):
    return {e["nickname"].lower() for e in do_not_pin_entries(pinned)}


def add_do_not_pin(pinned, nick, reason, now=None):
    """Exclude a nickname from auto-follow / drop-in seeding, with a reason."""
    entries = do_not_pin_entries(pinned)
    k = nick_key(nick).lower()
    at = pt(now) if now else today_pt()
    for e in entries:
        if e["nickname"].lower() == k:
            e["reason"] = reason
            e["at"] = e.get("at") or at
            pinned["doNotPin"] = entries
            return entries
    entries.append({"nickname": nick_key(nick), "reason": reason, "at": at})
    pinned["doNotPin"] = entries
    return entries


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
                clear_follow_flags(row)
    return moved


def apply_follow_safeguard(pinned, previous_names, cappers, now, log=print):
    """Do not shrink My 40 versus the last good list unless a name failed a real gate.

    If this run did not re-evaluate a previously followed capper, keep them.
    """
    skip = do_not_pin_set(pinned)
    have = {n.lower() for n in pinned_names(pinned)}
    by = {nick_key(c.get("nickname")).lower(): c for c in cappers if c.get("nickname")}
    restored = []
    for nick in previous_names or []:
        k = nick_key(nick).lower()
        if not k or k in have or k in skip:
            continue
        cap = by.get(k)
        why = follow_fail_reason(cap) if cap else None
        if cap and why:
            log("safeguard: not restoring %s (%s)" % (nick, why))
            continue
        if not cap:
            log("safeguard: keeping %s (not re-evaluated this run)" % nick)
        pinned.setdefault("cappers", []).append({
            "nickname": nick_key(nick),
            "tag": PINNED_TAG,
            "source": "safeguard",
            "addedAt": today_pt(now),
        })
        have.add(k)
        if cap:
            cap["pinned"] = True
            cap["tag"] = PINNED_TAG
            cap["tier"] = PINNED_TAG
        restored.append(nick_key(nick))
    if restored:
        log("safeguard: restored %d previously followed: %s" % (len(restored), ", ".join(restored)))
    return restored


def reconcile_follow_list(active, pinned, cappers, people, now, log=print):
    """Keep My 40 as pinned follows that pass every gate, up to TARGET_FOLLOW.

    My 40 is sourced only from official projected-PnL leaderboards (weekly,
    monthly, yearly, all-time). Tape-discovered names are never auto-followed.
    Every currently followed capper is re-checked each scan. A name is followed
    if (graded W > L and official all-time profit of at least $10,000) or
    (no public graded record and official all-time profit of at least $100,000).
    Failures are unpinned; leaderboard names stay in Watching. A losing
    reconstructed record is out. Negative official all-time profit is also
    added to doNotPin and can never re-enter. doNotPin names, including 80Mill,
    never re-enter. New auto-follows must pass the same gates and come from
    the leaderboard. Rank by record first, profit second.
    """
    previous_names = list(dict.fromkeys(
        pinned_names(pinned) + [nick_key(n) for n in (pinned.get("lastGoodFollows") or []) if nick_key(n)]
    ))
    skip = do_not_pin_set(pinned)
    by = {nick_key(c.get("nickname")).lower(): c for c in cappers if c.get("nickname")}
    still, dropped = [], []
    for row in list(pinned.get("cappers") or []):
        nick = nick_key(row.get("nickname") if isinstance(row, dict) else row)
        k = nick.lower()
        cap = by.get(k)
        why = None
        if k in skip:
            why = "doNotPin"
        else:
            why = follow_fail_reason(cap)
        if why:
            pnl = official_pnl(cap)
            if is_negative_profit(pnl):
                add_do_not_pin(pinned, nick, "negative profit", now)
                why = "negative profit %s" % signed_k(pnl)
            dropped.append("%s (%s)" % (nick, why))
            if cap:
                clear_follow_flags(cap, people)
            continue
        still.append(row if isinstance(row, dict) else {"nickname": nick, "tag": PINNED_TAG, "addedAt": today_pt(now)})
        if cap:
            cap["pinned"] = True
            cap["tag"] = PINNED_TAG
            cap["tier"] = PINNED_TAG
    pinned["cappers"] = still
    skip = do_not_pin_set(pinned)
    have = {nick_key(r.get("nickname") if isinstance(r, dict) else r).lower() for r in still}
    cands = []
    for cap in cappers:
        k = nick_key(cap.get("nickname")).lower()
        if not k or k in have or k in skip:
            continue
        if can_follow(cap):
            g = follow_record(cap) or {}
            w, l, n = graded_wl(g)
            pnl = official_pnl(cap) or 0
            cands.append((-(w - l), -w, -(w / n if n else 0), -pnl, cap))
    cands.sort(key=lambda x: (x[0], x[1], x[2], x[3], nick_key(x[4].get("nickname")).lower()))
    added = []
    for _s, _w, _r, _p, cap in cands:
        if len(pinned["cappers"]) >= TARGET_FOLLOW:
            break
        nick = cap["nickname"]
        g = cap.get("graded") or {}
        pnl = official_pnl(cap)
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
        added.append("%s %d-%d %s" % (nick, g.get("w") or 0, g.get("l") or 0, signed_k(pnl) if pnl is not None else ""))
    if dropped:
        log("follow: unpinned (failed My 40 gates or excluded): " + ", ".join(dropped))
    if added:
        log("follow: auto-pinned %d (target %d): %s" % (len(added), TARGET_FOLLOW, ", ".join(added)))
    apply_follow_safeguard(pinned, previous_names, cappers, now, log)
    # lastGood is the last published passing list only. doNotPin and names that
    # failed a gate are not remembered, so the never-shrink guard cannot revive them.
    current = pinned_names(pinned)
    if current:
        pinned["lastGoodFollows"] = current
    log("follow: %d/%d pinned; discovery continues every hour" % (len(pinned["cappers"]), TARGET_FOLLOW))
    save_pinned_file(pinned, now)
    pinset = {nick_key(r.get("nickname") if isinstance(r, dict) else r).lower() for r in (pinned.get("cappers") or [])}
    for row in active.get("cappers") or []:
        k = nick_key(row.get("nickname")).lower()
        if k in pinset:
            row["pinned"] = True
            row["tag"] = PINNED_TAG
            row["tier"] = PINNED_TAG
        else:
            clear_follow_flags(row, people)
    return pinned


def fetch_all_boards(http, log=print):
    """Every official profit/volume board window, plus sport-specific categories.

    Kalshi rejects limit 200, so we use 100 and follow cursors until a list is
    exhausted so the follow pool is not just the first page.
    """
    people = {}
    coverage = {}
    for cat in ALL_BOARD_CATS:
        for period in BOARD_PERIODS:
            for metric in BOARD_METRICS:
                key = "%s:%s:%s" % (cat, period, metric)
                cursor = None
                rows_all = []
                for _page in range(10):
                    params = {
                        "metric_name": metric,
                        "category": cat,
                        "time_period": period,
                        "limit": 100,
                    }
                    if cursor:
                        params["cursor"] = cursor
                    data = http.get(f"{lib.SOCIAL}/leaderboard", params) or {}
                    rows = data.get("rank_list") or []
                    if not rows:
                        break
                    rows_all.extend(rows)
                    cursor = data.get("cursor")
                    if not cursor:
                        break
                coverage[key] = len(rows_all)
                if not rows_all and cat not in BOARD_CATS:
                    continue
                for row in rows_all:
                    nick = nick_key(row.get("nickname") or "")
                    if not nick:
                        continue
                    rec = people.setdefault(nick, {"nickname": nick, "ranks": {}, "pnl": {}, "profitRanks": {}, "sources": []})
                    rec["ranks"].setdefault(cat, {})
                    if rec["ranks"][cat].get(period) is None or (row.get("rank") or 9999) < rec["ranks"][cat][period]:
                        rec["ranks"][cat][period] = row.get("rank")
                    if metric == "projected_pnl":
                        pr = rec.setdefault("profitRanks", {})
                        pr.setdefault(cat, {})
                        if pr[cat].get(period) is None or (row.get("rank") or 9999) < pr[cat][period]:
                            pr[cat][period] = row.get("rank")
                        if cat == "Sports":
                            rec["pnl"][period] = row.get("value")
                    rec["sources"].append("%s %s #%s" % (cat, period, row.get("rank")))
                    rec["is_anonymous"] = bool(row.get("is_anonymous"))
    nonempty = sum(1 for n in coverage.values() if n)
    log("boards: %d unique names across %d lists (%d nonempty)" % (len(people), len(coverage), nonempty))
    return people, coverage


# High-traffic traditional-sports series used to find traders on live books.
# series_ticker is a supported social-trades filter; a bare "ticker" param is ignored.
TAPE_SERIES = [
    "KXNFLGAME", "KXNFLSPREAD", "KXNFLTOTAL",
    "KXNBAGAME", "KXNBASPREAD", "KXNBATOTAL",
    "KXNCAAFGAME", "KXNCAAFSPREAD", "KXNCAAFTOTAL",
    "KXNCAABGAME", "KXNHLGAME", "KXMLBGAME",
    "KXATPMATCH", "KXWTAMATCH", "KXUFCFIGHT",
    "KXEPLGAME", "KXUCLGAME", "KXMLSGAME",
]


def fetch_sports_tape_names(http, people, log=print, pages_per_series=1):
    """Add nicknames seen as maker/taker on public sports series tapes."""
    added = 0
    pages = 0
    for series in TAPE_SERIES:
        cursor = None
        for _ in range(max(1, pages_per_series)):
            params = {"limit": 100, "series_ticker": series}
            if cursor:
                params["cursor"] = cursor
            data = http.get(f"{lib.SOCIAL}/trades", params) or {}
            pages += 1
            rows = data.get("trades") or []
            for tr in rows:
                tk = tr.get("ticker") or ""
                if tk and not lib.is_sports_ticker(tk):
                    continue
                for key in ("maker_nickname", "taker_nickname"):
                    nick = nick_key(tr.get(key) or "")
                    if not nick:
                        continue
                    rec = people.setdefault(nick, {"nickname": nick, "ranks": {}, "pnl": {}, "sources": []})
                    was_new = not rec.get("sources")
                    src = "sports tape %s" % series
                    if src not in (rec.get("sources") or []):
                        rec.setdefault("sources", []).append(src)
                    if was_new:
                        added += 1
            cursor = data.get("cursor")
            if not cursor or not rows:
                break
    log("sports tape: %d new names from %d pages across %d series (pool now %d)" % (
        added, pages, len(TAPE_SERIES), len(people)))
    return added


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


def grade_from_trades(trades, nick, sports_only=True):
    """W-L from every settled public cycle (no dollar floor).

    sports_only=True is the display sports tape. Follow gates use sports_only=False
    so leaderboard names are graded across every category, not sports trades only.
    """
    cycles = lib.closed_cycles(trades, nick, sports_only=sports_only)
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


def official_pnl(cap):
    """Kalshi profile all-time P&L in dollars, or None if the API did not return it."""
    if not cap:
        return None
    v = cap.get("pnl")
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def is_positive_profit(pnl):
    return pnl is not None and pnl > 0


def is_negative_profit(pnl):
    return pnl is not None and pnl < 0


def graded_wl(g):
    if not g:
        return 0, 0, 0
    w, l = g.get("w") or 0, g.get("l") or 0
    n = g.get("n") or (w + l)
    return w, l, n


def on_profit_leaderboard(cap, people=None):
    """True when this nickname is on an official projected-PnL leaderboard."""
    if not cap and not people:
        return False
    nick = nick_key((cap or {}).get("nickname") if isinstance(cap, dict) else cap)
    rec = (people or {}).get(nick) or {}
    raw = {}
    if isinstance(cap, dict):
        if cap.get("onProfitBoard"):
            return True
        raw = cap.get("profitRanks") or {}
        if any(cap.get(k) is not None for k in ("weeklyPnl", "monthlyPnl", "yearlyPnl")):
            return True
    raw = raw or rec.get("profitRanks") or {}
    if raw:
        # {category: {period: rank}} or a flat {period: rank}
        for v in raw.values():
            if isinstance(v, dict):
                if any(rank for rank in v.values() if rank):
                    return True
            elif v:
                return True
    if isinstance(rec.get("pnl"), dict) and any(v is not None for v in rec.get("pnl").values()):
        return True
    return False


def follow_record(cap):
    """Prefer all-category public W-L for follow gates; fall back to the sports tape."""
    return (cap or {}).get("gradedAll") or (cap or {}).get("graded")


def follow_fail_reason(cap):
    """Why this capper must not be (or stay) in My 40. None means every gate passed.

    Gates: must appear on an official Kalshi projected-PnL leaderboard
    (weekly, monthly, yearly, or all-time, including sport-specific boards).
    A name passes if (graded W > L and official all-time profit of at least
    $10,000) or (no public graded record and official all-time profit of at
    least $100,000). A reconstructed losing record is a fail. doNotPin is
    handled by the caller and never re-enters (the never-shrink guard also
    honors it). W-L is graded from settled public trades across every
    category when available.
    """
    if not on_profit_leaderboard(cap):
        return "not on official profit leaderboard"
    pnl = official_pnl(cap)
    if is_negative_profit(pnl):
        return "negative profit %s" % signed_k(pnl)
    if pnl is None:
        return "no official all-time profit"
    w, l, n = graded_wl(follow_record(cap))
    if n > 0:
        if w <= l:
            return "%d-%d" % (w, l)
        if pnl < MIN_FOLLOW_PNL:
            return "profit %s below $10,000" % signed_k(pnl)
        return None
    if pnl >= MIN_FOLLOW_PNL_EARNER:
        return None
    return "no graded W-L (need $100,000 official profit)"


def can_follow(cap):
    return follow_fail_reason(cap) is None


def is_near_term_pick(p, now, horizon_secs=FOLLOW_HORIZON_SECS):
    """True for live or soon-starting sports; false for undated / months-out futures."""
    if not p:
        return False
    start = p.get("startTs") or 0
    close = p.get("closeTs") or 0
    when = start or close
    if not when:
        return False
    if when <= now:
        return True
    return when <= now + horizon_secs


def board_tier_for(cap, people=None):
    """Non-follow badge after an unpin, using stored ranks when the board map is empty."""
    people = dict(people or {})
    nick = nick_key((cap or {}).get("nickname") if isinstance(cap, dict) else cap)
    if isinstance(cap, dict) and nick and nick not in people:
        ranks = cap.get("ranks") or {}
        if ranks.get("Sports"):
            people[nick] = {"ranks": ranks}
        elif ranks:
            people[nick] = {"ranks": {"Sports": ranks}}
    return capper_tier(nick, people)


def clear_follow_flags(row, people=None):
    if not row:
        return row
    row["pinned"] = False
    if is_pin_tag(row.get("tag")):
        row["tag"] = ""
    if is_pin_tag(row.get("tier")):
        row["tier"] = board_tier_for(row, people)
    line = row.get("recordLine") or ""
    if line:
        row["recordLine"] = line.replace(" · My 40", "").replace(" · Top 10", "").replace(" · Following", "")
    return row


def tape_profit_since(trades, nick, now, days):
    """Realized sports-tape profit over a window, from settled public trades only. None if no cycles."""
    cycles = lib.closed_cycles(trades, nick)
    cutoff = int(now) - int(days) * 86400
    use = [c for c in cycles if (c.get("end") or c.get("ts") or 0) >= cutoff]
    if not use:
        return None
    return round(sum(c.get("profit") or 0 for c in use), 2)


def _board_pnl_dollars(rec, period):
    """Sports leaderboard projected_pnl values are already in dollars (not metrics 1/10000 units)."""
    v = (rec.get("pnl") or {}).get(period)
    if v is None:
        return None
    try:
        return round(float(v), 2)
    except Exception:
        return None


def build_capper_row(nick, people, prof, metrics, trades, holdings, picks, now, heavy=False):
    rec = people.get(nick) or {}
    metrics = metrics or {}
    pnl_source = None
    all_time_pnl = lib.usd_units(metrics.get("pnl"))
    if all_time_pnl is not None:
        pnl_source = "kalshi_profile_metrics"
    else:
        all_time_pnl = _board_pnl_dollars(rec, "all_time")
        if all_time_pnl is not None:
            pnl_source = "sports_leaderboard_projected"
    use = grade_from_trades(trades, nick, sports_only=True)
    use_all = grade_from_trades(trades, nick, sports_only=False)
    tier = capper_tier(nick, people)
    pin = is_pinned(nick)
    if pin:
        tier = PINNED_TAG  # show as My 40; board rank still lives in ranks{}
    age = lib.age_days((prof or {}).get("joined_at"), now)
    sports_ranks_flat = sports_ranks(people, nick)
    profit_ranks = (rec.get("profitRanks") or {})
    on_board = on_profit_leaderboard({"nickname": nick, "profitRanks": profit_ranks, "weeklyPnl": _board_pnl_dollars(rec, "weekly"), "monthlyPnl": _board_pnl_dollars(rec, "monthly"), "yearlyPnl": _board_pnl_dollars(rec, "yearly")}, people)
    volume_usd = lib.usd_units(metrics.get("dollars_traded"))
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
        "profitRanks": profit_ranks,
        "onProfitBoard": bool(on_board),
        "pnl": None if all_time_pnl is None else round(all_time_pnl, 2),
        "pnlSource": pnl_source,
        "weeklyPnl": _board_pnl_dollars(rec, "weekly"),
        "monthlyPnl": _board_pnl_dollars(rec, "monthly"),
        "yearlyPnl": _board_pnl_dollars(rec, "yearly"),
        "volumeUsd": None if volume_usd is None else round(volume_usd, 2),
        "tape7d": tape_profit_since(trades, nick, now, 7),
        "tape30d": tape_profit_since(trades, nick, now, 30),
        "ageDays": age,
        "graded": {
            "n": use.get("n") or 0,
            "w": use.get("w") or 0,
            "l": use.get("l") or 0,
            "roi": None if use.get("roi") is None else round(use["roi"], 1),
            "profit": round(use.get("profit") or 0, 2),
            "sample": "full" if (use.get("n") or 0) >= 10 else "small",
        } if use else None,
        "gradedAll": {
            "n": use_all.get("n") or 0,
            "w": use_all.get("w") or 0,
            "l": use_all.get("l") or 0,
            "roi": None if use_all.get("roi") is None else round(use_all["roi"], 1),
            "profit": round(use_all.get("profit") or 0, 2),
            "sample": "full" if (use_all.get("n") or 0) >= 10 else "small",
        } if use_all else None,
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
        follow = collect_picks(http, holdings, trades, inv_map, now, mcache, ecache, min_bet=0, window_secs=FOLLOW_HORIZON_SECS, max_entry=None)
        follow = [p for p in follow if is_near_term_pick(p, now)]
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
    pinset = {n.lower() for n in pinned_names(pinned)}
    added = 0
    for p in open_picks:
        if nick_key(p.get("nickname")).lower() not in pinset:
            continue
        if not is_near_term_pick(p, now):
            continue
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
        if nick_key(p.get("nickname")).lower() not in pinset:
            continue
        rec = slot(p.get("nickname"))
        if rec:
            rec["open"] += 1
    # Ledger open rows for a still-followed capper with no current book pick
    # still count as open until graded. Unfollowed names stay in the ledger
    # for history but never re-enter the My 40 capper list.
    open_ids = {trial_id(p.get("nickname"), p.get("ticker"), p.get("yesNo")) for p in open_picks}
    for row in ledger["picks"]:
        if nick_key(row.get("nickname")).lower() not in pinset:
            continue
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
            # Don't count months-out futures as an open My 40 pick.
            if is_near_term_pick(row, now):
                rec["open"] += 1
    out = []
    for rec in stats.values():
        rec["n"] = rec["w"] + rec["l"]
        rec["hitPct"] = None if not rec["n"] else round(100.0 * rec["w"] / rec["n"], 1)
        out.append(rec)
    out = [r for r in out if r["nickname"].lower() in pinset]
    out.sort(key=lambda r: (-(r["n"] or 0), -((r["hitPct"] or -1)), r["nickname"].lower()))
    near = [p for p in open_picks if nick_key(p.get("nickname")).lower() in pinset and is_near_term_pick(p, now)]
    open_sorted = sorted(near, key=lambda p: (0 if (p.get("startTs") and p["startTs"] <= now) else 1, p.get("startTs") or 10**12, p.get("nickname") or "", p.get("ticker") or ""))
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



def load_previous_payload():
    prev = load_json(DATA_JSON_PATH, {})
    games = prev.get("games") or []
    used_seed = False
    if not games and os.path.exists(CARRY_SEED_PATH):
        seed = load_json(CARRY_SEED_PATH, {})
        # Recover picks wiped by a later empty scan. Only if published data is newer than the seed snapshot.
        if (prev.get("ts") or 0) >= (seed.get("ts") or 0) and (seed.get("games") or seed.get("followingPicks")):
            prev = {
                "scannedAt": seed.get("scannedAt") or prev.get("scannedAt") or "",
                "ts": seed.get("ts") or prev.get("ts") or 0,
                "games": seed.get("games") or [],
                "following": {"picks": seed.get("followingPicks") or [], "cappers": (prev.get("following") or {}).get("cappers") or []},
            }
            used_seed = True
    return prev, used_seed


def finish_info_for_pick(p, http=None, mcache=None, ecache=None):
    view = p.get("view") or {}
    ticker = p.get("ticker") or view.get("ticker")
    yes_no = view.get("yesNo") or p.get("yesNo")
    info = {
        "status": p.get("status") or "",
        "result": p.get("result") or "",
        "start_ts": p.get("startTs") or 0,
        "close_ts": p.get("closeTs") or 0,
        "yes_ask": p.get("yesAsk"),
        "no_ask": p.get("noAsk"),
        "ticker": ticker,
        "title": p.get("big") or p.get("backing") or p.get("label") or p.get("game") or view.get("backing") or "",
    }
    if info["yes_ask"] is None and yes_no == "Yes" and view.get("price") is not None:
        info["yes_ask"] = view.get("price")
    if info["no_ask"] is None and yes_no == "No" and view.get("price") is not None:
        info["no_ask"] = view.get("price")
    if http and ticker:
        try:
            fresh = lib.hydrate_market(http, ticker, mcache if mcache is not None else {}, ecache if ecache is not None else {})
        except Exception:
            fresh = None
        if fresh:
            info["status"] = fresh.get("status") or info["status"]
            info["result"] = fresh.get("result") if fresh.get("result") not in (None, "") else info["result"]
            info["start_ts"] = fresh.get("start_ts") or info["start_ts"]
            info["close_ts"] = fresh.get("close_ts") or info["close_ts"]
            if fresh.get("yes_ask") is not None:
                info["yes_ask"] = fresh.get("yes_ask")
            if fresh.get("no_ask") is not None:
                info["no_ask"] = fresh.get("no_ask")
            info["title"] = fresh.get("title") or info["title"]
            info["_fresh"] = fresh
    return info


def pick_is_finished(p, now, league, http=None, mcache=None, ecache=None):
    info = finish_info_for_pick(p, http, mcache, ecache)
    done, why = game_finished(info, now, league or p.get("league") or "")
    return done, why, info


def _backer_key(name, ticker, yes_no):
    return ((name or "").lower(), ticker or "", yes_no or "")


def _flatten_game_positions(games):
    out = []
    for g in games or []:
        for p in g.get("picks") or []:
            yes_no = (p.get("view") or {}).get("yesNo") or p.get("yesNo") or ""
            ticker = p.get("ticker") or (p.get("view") or {}).get("ticker") or ""
            for b in p.get("backers") or []:
                out.append((g, p, b, _backer_key(b.get("name"), ticker, yes_no)))
    return out


def carry_forward_games(new_games, prev, now, http, mcache, ecache, log=print):
    """Keep still-open picks from the previous (or recovered) data.json.

    Fresh rows from this scan win. Positions no longer visible stay, marked
    Last seen <time> PT, until the usual finished-game rules drop them.
    """
    seen = set()
    for g, p, b, key in _flatten_game_positions(new_games):
        seen.add(key)
    carried = 0
    dropped = []
    by_id = {g.get("id"): g for g in new_games}
    order = [g.get("id") for g in new_games]
    prev_at = prev.get("scannedAt") or ""
    for g, p, b, key in _flatten_game_positions(prev.get("games") or []):
        if key in seen:
            continue
        league = g.get("league") or p.get("league") or ""
        start_ts = p.get("startTs") or g.get("startTs") or 0
        if start_ts and start_ts > now + WINDOW_SECS:
            continue
        done, why, info = pick_is_finished(p, now, league, http, mcache, ecache)
        if done:
            dropped.append("%s / %s (%s)" % (g.get("game") or p.get("ticker"), b.get("name") or "", why))
            continue
        bb = dict(b)
        if not bb.get("lastSeen"):
            bb["lastSeen"] = prev_at or pt(prev.get("ts") or now)
            if prev.get("ts"):
                bb["lastSeenTs"] = prev.get("ts")
        # refresh start/live/price on the pick slot from hydrate when we have it
        pp = dict(p)
        if info.get("start_ts"):
            pp["startTs"] = info["start_ts"]
        if info.get("_fresh") and (pp.get("view") or {}).get("yesNo") == "Yes" and info.get("yes_ask") is not None:
            view = dict(pp.get("view") or {})
            view["price"] = info["yes_ask"]
            pp["view"] = view
        elif info.get("_fresh") and (pp.get("view") or {}).get("yesNo") == "No" and info.get("no_ask") is not None:
            view = dict(pp.get("view") or {})
            view["price"] = info["no_ask"]
            pp["view"] = view
        if start_ts and start_ts <= now:
            pp["state"] = "live"
        gid = g.get("id") or (pp.get("eventTicker") or (g.get("game") + "|" + str(start_ts or 0)))
        if gid not in by_id:
            ng = {
                "id": gid,
                "game": g.get("game") or pp.get("game") or gid,
                "league": league or "Sports",
                "startTs": start_ts or 0,
                "start": g.get("start") or (pt(start_ts) if start_ts else ""),
                "live": bool(start_ts and start_ts <= now),
                "state": "live" if (start_ts and start_ts <= now) else (g.get("state") or "upcoming"),
                "picks": [],
            }
            by_id[gid] = ng
            order.append(gid)
        host = by_id[gid]
        if start_ts and start_ts <= now:
            host["live"] = True
            host["state"] = "live"
        pkey = pp.get("key") or ("%s|%s" % (pp.get("ticker") or "", (pp.get("view") or {}).get("yesNo") or ""))
        slot = None
        for existing in host["picks"]:
            if existing.get("key") == pkey:
                slot = existing
                break
        if slot is None:
            slot = {k: v for k, v in pp.items() if k != "backers"}
            slot["backers"] = []
            slot["key"] = pkey
            host["picks"].append(slot)
        slot["backers"].append(bb)
        slot["total"] = round(sum((x.get("cost") or 0) for x in slot["backers"]), 2)
        tags = []
        for x in slot["backers"]:
            if x.get("tier") and x["tier"] not in tags:
                tags.append(x["tier"])
        slot["tags"] = tags
        seen.add(key)
        carried += 1
    games = [by_id[i] for i in order if i in by_id and (by_id[i].get("picks") or [])]
    games.sort(key=lambda g: (0 if g.get("live") else 1, g.get("startTs") or 10**12, g.get("id") or ""))
    if carried or dropped:
        log("carry-forward: kept %d hidden/prior positions, dropped %d finished%s" % (
            carried, len(dropped), (": " + "; ".join(dropped[:8])) if dropped else ""))
    return games, carried, dropped


def carry_forward_following(new_picks, prev, now, http, mcache, ecache, log=print, pinned=None):
    """Same carry rules for My 40 display picks. Does not write the trial ledger.

    Only still-followed, near-term sports picks are kept. Unfollowed books and
    months-out futures are dropped from the display list.
    """
    def fid(p):
        return _backer_key(p.get("nickname"), p.get("ticker"), p.get("yesNo"))
    pinset = {n.lower() for n in pinned_names(pinned)} if pinned is not None else None
    def allowed(p):
        if pinset is not None and nick_key(p.get("nickname")).lower() not in pinset:
            return False
        return is_near_term_pick(p, now)
    seen = {fid(p) for p in (new_picks or []) if allowed(p)}
    out = [p for p in (new_picks or []) if allowed(p)]
    carried = 0
    dropped = 0
    prev_at = prev.get("scannedAt") or ""
    for p in (prev.get("following") or {}).get("picks") or []:
        if fid(p) in seen:
            continue
        if not allowed(p):
            dropped += 1
            continue
        start_ts = p.get("startTs") or 0
        done, why, info = pick_is_finished(p, now, p.get("league") or "", http, mcache, ecache)
        if done:
            dropped += 1
            continue
        if not is_near_term_pick({**p, "startTs": info.get("start_ts") or p.get("startTs") or 0, "closeTs": info.get("close_ts") or p.get("closeTs") or 0}, now):
            dropped += 1
            continue
        pp = dict(p)
        if not pp.get("lastSeen"):
            pp["lastSeen"] = prev_at or pt(prev.get("ts") or now)
            if prev.get("ts"):
                pp["lastSeenTs"] = prev.get("ts")
        if info.get("start_ts"):
            pp["startTs"] = info["start_ts"]
        if info.get("_fresh"):
            if pp.get("yesNo") == "Yes" and info.get("yes_ask") is not None:
                pp["price"] = info["yes_ask"]
                pp["yesAsk"] = info["yes_ask"]
            if pp.get("yesNo") == "No" and info.get("no_ask") is not None:
                pp["price"] = info["no_ask"]
                pp["noAsk"] = info["no_ask"]
        if (pp.get("startTs") or 0) and pp["startTs"] <= now:
            pp["state"] = "live"
        out.append(pp)
        seen.add(fid(pp))
        carried += 1
    out.sort(key=lambda p: (0 if (p.get("startTs") and p["startTs"] <= now) else 1, p.get("startTs") or 10**12, p.get("nickname") or "", p.get("ticker") or ""))
    if carried or dropped:
        log("carry-forward following: kept %d, dropped %d finished" % (carried, dropped))
    return out, carried, dropped


def collect_pick_ids(games, following_picks=None):
    ids, seen = [], set()
    for g in games or []:
        for p in g.get("picks") or []:
            pid = p.get("key") or "%s|%s" % (p.get("ticker") or "", (p.get("view") or {}).get("yesNo") or "")
            if pid and pid not in seen:
                seen.add(pid)
                ids.append(pid)
    for p in following_picks or []:
        gpid = "%s|%s" % (p.get("ticker") or "", p.get("yesNo") or "")
        pid = "%s|%s|%s" % (p.get("nickname") or "", p.get("ticker") or "", p.get("yesNo") or "")
        if gpid in seen or pid in seen:
            continue
        if pid.strip("|"):
            seen.add(pid)
            ids.append(pid)
    return ids


def record_scan_history(now, cov, games, following, prev):
    history = load_json(HISTORY_PATH, {"updatedAt": "", "scans": []})
    scans = list(history.get("scans") or [])
    prev_fol = [c.get("nickname") for c in ((prev.get("following") or {}).get("cappers") or []) if c.get("nickname")]
    # Prefer this scan's follow list (after reconcile), not the carried-display-only names.
    fol = [c.get("nickname") for c in (following.get("cappers") or []) if c.get("nickname")]
    new_follows = [n for n in fol if n not in prev_fol]
    open_picks = sum(len(g.get("picks") or []) for g in (games or []))
    entry = {
        "ts": now,
        "at": pt(now),
        "names": cov.get("namesChecked") or 0,
        "newFollows": new_follows,
        "followed": len(fol),
        "target": TARGET_FOLLOW,
        "openPicks": open_picks,
        "ids": collect_pick_ids(games, following.get("picks") or []),
    }
    # Replace an entry with the same ts if the job retried; otherwise prepend.
    scans = [x for x in scans if (x.get("ts") or 0) != now]
    scans.insert(0, entry)
    scans = scans[:HISTORY_KEEP]
    history = {"updatedAt": entry["at"], "scans": scans}
    save_json(HISTORY_PATH, history)
    return scans


def build(now=None, log=print):
    now = int(now or time.time())
    t0 = time.time()
    prev, used_carry_seed = load_previous_payload()
    http = lib.Http()
    active, queue, rejected = load_dbs()
    pinned = load_pinned_file()
    merge_dropin_pins(pinned, log)
    apply_pins(active, queue, rejected, pinned, now, log)
    save_pinned_file(pinned, now)
    save_dbs(active, queue, rejected, now)
    people, board_cov = fetch_all_boards(http, log)
    tape_new = fetch_sports_tape_names(http, people, log)
    mcache, ecache = {}, {}
    cov = {
        "boards": {k: v for k, v in board_cov.items() if v},
        "leaderboardNames": len(people),
        "tapeNewNames": tape_new,
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
    games, carried_n, carried_dropped = carry_forward_games(games, prev, now, http, mcache, ecache, log)
    dropped = list(dropped) + list(carried_dropped)
    cov["carriedPicks"] = carried_n
    cov["carriedDropped"] = len(carried_dropped)
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
            if not is_near_term_pick(p, now):
                continue
            following_open.append(dict(p, nickname=c.get("nickname"), recordLine=c.get("recordLine") or c.get("nickname"), tier=c.get("tier") or PINNED_TAG))
    following = update_trial_ledger(http, following_open, pinned, pinned_hidden, now, mcache, ecache, log)
    # Carry previous My 40 *display* picks only. The trial ledger is already persisted and was
    # updated solely from this scan's visible followed positions.
    follow_picks, carried_follow, dropped_follow = carry_forward_following(following.get("picks") or [], prev, now, http, mcache, ecache, log, pinned=pinned)
    following["picks"] = follow_picks
    cov["carriedFollowPicks"] = carried_follow
    cov["carriedFollowDropped"] = dropped_follow
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
            "note": "Kalshi public social + trade APIs. No official profit time series and no 30-day leaderboard exist; monthly Sports projected P&L is the stand-in for a 30-day window, weekly for 7 days. All-time profit is the profile metrics PnL (never invented). 7d/30d sports-tape profit is reconstructed only from settled public sports trades. Names come from Sports, Politics, Economics, Crypto and Mentions boards (all-time, monthly, weekly, yearly; projected PnL and volume, top 100) plus traders seen on active traditional-sports series tapes. Picks are traditional sports singles and sports combos only — esports is excluded. Hidden books, market makers, and traders with no traditional-sports activity are rejected and never rechecked, except followed My 40 cappers, who stay in the active db. Visible sports traders stay in the active db even with no open pick today. My 40 is sourced only from official projected-PnL leaderboards (weekly, monthly, yearly, all-time) and copies near-term traditional-sports picks (starting within 30 days; long-dated futures are excluded). A followed capper must be on that leaderboard, have a winning public sports record (W > L), at least 10 settled public sports trades, and official all-time profit of at least $1,000. Tape-discovered names are never followed. No dollar minimum on those trial picks; they are graded from official Kalshi results after settlement. New cappers are still discovered every hour at 40. A followed capper who fails any gate is unpinned and stays on Watching; negative official profit is added to doNotPin and can never re-enter. W-L is reconstructed from the public sports tape and is never invented. Coming Up / Ranked minimum open pick is $%d." % MIN_BET,
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
        "scanHistory": record_scan_history(now, cov, games, following, prev),
    }
    if used_carry_seed and os.path.exists(CARRY_SEED_PATH):
        try:
            os.remove(CARRY_SEED_PATH)
            log("removed one-shot carry_seed.json after recovery")
        except OSError as e:
            log("could not remove carry_seed.json: %s" % e)
    log(
        "scan active {dbActive} queue {dbQueue} rejected {dbRejected} shown {shown} "
        "picks {picks} games {games} follow {followingOpen} trial {trialRecorded} "
        "finished {finishedDropped} calls {calls} 429s {retries429} secs {secs}".format(**cov)
    )
    return payload




def significant_trial():
    """Ledger identity + grades only. Ignore updatedAt, which is rewritten every run."""
    ledger = load_json(TRIAL_PATH, {"picks": []})
    return tuple(sorted(
        (
            r.get("id") or "",
            r.get("status") or "",
            r.get("result") or "",
            r.get("settledAt") or "",
            r.get("recordedTs") or 0,
        )
        for r in (ledger.get("picks") or [])
    ))


def significant_state(data):
    """Compare picks, lastTs, follows, and the trial ledger — ignore live prices and clock fields."""
    rows = []
    for g in data.get("games") or []:
        for p in g.get("picks") or []:
            backs = tuple(sorted(
                (
                    (b.get("name") or ""),
                    b.get("lastTs"),
                    b.get("lastSeen") or "",
                    round(float(b.get("cost") or 0), 2),
                    None if b.get("avg") is None else round(float(b["avg"]), 4),
                )
                for b in (p.get("backers") or [])
            ))
            rows.append((p.get("key") or "", p.get("startTs") or 0, p.get("state") or "", backs))
    fol = tuple(sorted(
        (
            (p.get("nickname") or ""),
            p.get("ticker") or "",
            p.get("yesNo") or "",
            p.get("lastTs"),
            p.get("lastSeen") or "",
            p.get("startTs") or 0,
        )
        for p in ((data.get("following") or {}).get("picks") or [])
    ))
    followed = tuple(sorted((c.get("nickname") or "") for c in ((data.get("following") or {}).get("cappers") or [])))
    rec = ((data.get("following") or {}).get("recorded") or 0, (data.get("following") or {}).get("graded") or 0)
    return (tuple(sorted(rows)), fol, followed, rec)


def build_follow_check(now=None, log=print):
    """Refresh only followed (pinned) cappers' public books. No board crawl, queue, or new names."""
    now = int(now or time.time())
    t0 = time.time()
    prev, _used_seed = load_previous_payload()
    # Previous payload may be AES-wrapped on disk; load_previous_payload reads data.json.
    # If encrypted, games would be missing — decrypt is a workflow concern. When this
    # function runs in Actions, data.json has just been checked out; after the first
    # encrypted commit the runner must decrypt before scan.py. We handle that in main().
    http = lib.Http()
    active, queue, rejected = load_dbs()
    pinned = load_pinned_file()
    mcache, ecache = {}, {}
    cov = {
        "followCheck": True,
        "boards": {},
        "leaderboardNames": 0,
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
        "namesChecked": 0,
    }
    live_cappers = []
    pinned_hidden = set()
    names = pinned_names(pinned)
    log("follow-check: refreshing %d pinned cappers" % len(names))
    prev_caps = {nick_key(c.get("nickname")): c for c in (prev.get("cappers") or [])}
    for nick in names:
        try:
            verdict = inspect_visible(http, nick, now, mcache, ecache, {}, log, trades_pages=20)
        except Exception as e:
            log("follow-check failed %s: %s — keeping previous picks" % (nick, e))
            cov["namesChecked"] += 1
            continue
        cov["namesChecked"] += 1
        if verdict[0] == "rejected":
            _v, reason, detail = verdict
            log("follow-check pinned kept despite %s (%s): %s" % (reason, nick, detail))
            if reason == "hidden book":
                pinned_hidden.add(nick.lower())
            kept = {
                "nickname": nick, "pinned": True, "tag": PINNED_TAG, "tier": PINNED_TAG,
                "rejectNote": "%s: %s" % (reason, detail), "picks": [], "followingPicks": [],
            }
            old = prev_caps.get(nick_key(nick)) or {}
            for k in ("profileUrl", "ranks", "profitRanks", "onProfitBoard", "pnl", "weeklyPnl", "monthlyPnl", "yearlyPnl", "tape7d", "tape30d", "volumeUsd", "graded", "gradedAll", "recordLine", "ageDays"):
                if old.get(k) is not None and not kept.get(k):
                    kept[k] = old[k]
            live_cappers.append(kept)
            continue
        _v, cap, _ = verdict
        old = prev_caps.get(nick_key(nick)) or {}
        if not cap.get("ranks") and old.get("ranks"):
            cap["ranks"] = old.get("ranks")
        if not cap.get("profitRanks") and old.get("profitRanks"):
            cap["profitRanks"] = old.get("profitRanks")
        if cap.get("onProfitBoard") is None and old.get("onProfitBoard") is not None:
            cap["onProfitBoard"] = old.get("onProfitBoard")
        if cap.get("weeklyPnl") is None and old.get("weeklyPnl") is not None:
            cap["weeklyPnl"] = old.get("weeklyPnl")
        if cap.get("monthlyPnl") is None and old.get("monthlyPnl") is not None:
            cap["monthlyPnl"] = old.get("monthlyPnl")
        if cap.get("yearlyPnl") is None and old.get("yearlyPnl") is not None:
            cap["yearlyPnl"] = old.get("yearlyPnl")
        cap["onProfitBoard"] = on_profit_leaderboard(cap)
        cap["addedAt"] = old.get("addedAt") or cap.get("addedAt")
        live_cappers.append(cap)
        cov["activeRefreshed"] += 1
        # Update pick counts on the active db row without dropping other actives.
        for row in (active.get("cappers") or []):
            if nick_key(row.get("nickname")) == nick_key(nick):
                row["pickCount"] = len(cap.get("picks") or [])
                row["followCount"] = len(cap.get("followingPicks") or [])
                if cap.get("graded") is not None:
                    row["graded"] = cap.get("graded")
                if cap.get("pnl") is not None:
                    row["pnl"] = cap.get("pnl")
                break
    # Reconcile follows immediately: drop negative-profit or losing followed names
    # and swap from the previously evaluated pool when a better capper is already known.
    pool = {nick_key(c.get("nickname")): c for c in live_cappers if c.get("nickname")}
    for c in (prev.get("cappers") or []):
        k = nick_key(c.get("nickname"))
        if k and k not in pool:
            pool[k] = dict(c, picks=c.get("picks") or [], followingPicks=c.get("followingPicks") or [])
    pinned = reconcile_follow_list(active, pinned, list(pool.values()), {}, now, log)
    # Keep only still-followed in the live inspect list for My 40 picks.
    live_cappers = [
        c for c in live_cappers
        if c.get("pinned") or is_pinned(c.get("nickname"), pinned)
    ]
    save_dbs(active, queue, rejected, now)

    games, dropped = group_games(live_cappers, now, log)
    games, carried_n, carried_dropped = carry_forward_games(games, prev, now, http, mcache, ecache, log)
    dropped = list(dropped) + list(carried_dropped)
    cov["carriedPicks"] = carried_n
    cov["carriedDropped"] = len(carried_dropped)
    cov["finishedDropped"] = len(dropped)
    cov["finishedNames"] = dropped
    cov["shown"] = sum(1 for c in live_cappers if c.get("picks"))
    cov["picks"] = sum(len(g["picks"]) for g in games)
    cov["games"] = len(games)

    following_open = []
    for c in live_cappers:
        if not (c.get("pinned") or is_pinned(c.get("nickname"), pinned)):
            continue
        for p in c.get("followingPicks") or []:
            if not is_near_term_pick(p, now):
                continue
            following_open.append(dict(p, nickname=c.get("nickname"), recordLine=c.get("recordLine") or c.get("nickname"), tier=c.get("tier") or PINNED_TAG))
    following = update_trial_ledger(http, following_open, pinned, pinned_hidden, now, mcache, ecache, log)
    follow_picks, carried_follow, dropped_follow = carry_forward_following(following.get("picks") or [], prev, now, http, mcache, ecache, log, pinned=pinned)
    following["picks"] = follow_picks
    cov["carriedFollowPicks"] = carried_follow
    cov["carriedFollowDropped"] = dropped_follow
    cov["followingOpen"] = len(following.get("picks") or [])
    cov["followingCappers"] = len(following.get("cappers") or [])
    cov["trialRecorded"] = following.get("recorded") or 0
    cov["trialGraded"] = following.get("graded") or 0
    cov["calls"] = http.calls
    cov["retries429"] = http.retries_429
    cov["secs"] = round(time.time() - t0, 1)
    cov["dbActive"] = len(active.get("cappers") or [])
    cov["dbQueue"] = len(queue.get("cappers") or [])
    cov["dbRejected"] = len(rejected.get("cappers") or [])
    cov["dbPinned"] = sum(1 for r in (active.get("cappers") or []) if r.get("pinned") or is_pin_tag(r.get("tag")) or is_pin_tag(r.get("tier")))

    # Publish every evaluated book, but follow flags always come from the
    # post-reconcile pin list — never stale pinned=True / "My 40" tiers from prev.
    pinset = {n.lower() for n in pinned_names(pinned)}
    pub_cappers = []
    seen = set()
    def publish(c, counts_from_lists=False):
        k = nick_key((c or {}).get("nickname"))
        if not k or k in seen:
            return
        row = {k2: v for k2, v in c.items() if k2 not in ("picks", "followingPicks")}
        if counts_from_lists or "picks" in c:
            row["pickCount"] = len(c.get("picks") or [])
            row["followCount"] = len(c.get("followingPicks") or [])
        else:
            row.setdefault("pickCount", c.get("pickCount") or 0)
            row.setdefault("followCount", c.get("followCount") or 0)
        if k.lower() in pinset:
            row["pinned"] = True
            row["tag"] = PINNED_TAG
            row["tier"] = PINNED_TAG
        else:
            clear_follow_flags(row)
        pub_cappers.append(row)
        seen.add(k)
    for c in live_cappers:
        publish(c, counts_from_lists=True)
    for row in (active.get("cappers") or []):
        publish(row)
    for c in (prev.get("cappers") or []):
        publish(c)

    payload = {
        "scannedAt": prev.get("scannedAt") or pt(now),
        "ts": prev.get("ts") or now,
        "followCheckedAt": pt(now),
        "source": (prev.get("source") or {}) | {
            "coverage": {**((prev.get("source") or {}).get("coverage") or {}), **cov},
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
        "scanHistory": prev.get("scanHistory") or load_json(HISTORY_PATH, {"scans": []}).get("scans") or [],
    }
    log(
        "follow-check refreshed {activeRefreshed}/{namesChecked} carried {carriedPicks} "
        "picks {picks} games {games} follow {followingOpen} trial {trialRecorded} "
        "finished {finishedDropped} calls {calls} 429s {retries429} secs {secs}".format(**cov)
    )
    return payload


def _maybe_decrypt_data_json(log=print):
    """If data.json is AES-wrapped (after the passcode gate landed), unwrap for this process."""
    path = os.path.join(ROOT, "data.json")
    if not os.path.exists(path):
        return
    try:
        obj = json.load(open(path))
    except Exception:
        return
    if not (isinstance(obj, dict) and obj.get("enc") == 1):
        return
    try:
        from gate_crypto import decrypt_obj
        plain = decrypt_obj(obj)
    except Exception as e:
        log("data.json is encrypted but could not be unwrapped: %s" % e)
        raise
    json.dump(plain, open(path, "w"), indent=2)
    open(path, "a").write(chr(10))
    log("unwrapped encrypted data.json for this scan")


def main():
    _maybe_decrypt_data_json()
    follow = SCAN_MODE in ("follow", "follow-check", "follow_check")
    trial_before = significant_trial()
    prev, _ = load_previous_payload()
    data = build_follow_check() if follow else build()
    out = os.path.join(ROOT, "data.json")
    json.dump(data, open(out, "w"), indent=2)
    open(out, "a").write(chr(10))
    print("wrote", out, "games", len(data["games"]), "cappers", len(data["cappers"]),
          "following", len((data.get("following") or {}).get("picks") or []),
          "db", data["source"]["db"])
    if follow:
        trial_after = significant_trial()
        changed = significant_state(data) != significant_state(prev) or trial_before != trial_after
        print("FOLLOW_CHECK_CHANGED=%s" % ("1" if changed else "0"))
        flag = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".follow_changed")
        with open(flag, "w", encoding="utf-8") as f:
            f.write(("1" if changed else "0") + chr(10))


if __name__ == "__main__":
    main()
