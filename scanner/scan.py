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
MIN_BET = 500  # only show a capper's pick when their stake on that side is $500+
MAX_ENTRY = 0.90
WINDOW_SECS = 24 * 3600
DECIDED_PX = 0.97
KFINAL = ("finalized", "determined", "settled")  # result is in
KSOFT_CLOSED = ("closed", "deactivated", "inactive")  # not enough alone if the game is still live or not started
FINISH_GRACE_SECS = 30 * 60  # short OT window past typical duration, if the market is still mid-price
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


def _mid_price(info):
    ya, na, px = info.get("yes_ask"), info.get("no_ask"), info.get("price")
    def mid(v):
        return v is not None and (1 - DECIDED_PX) < float(v) < DECIDED_PX
    if mid(ya) or mid(na) or mid(px):
        return True
    if ya is not None and na is not None:
        return float(ya) < DECIDED_PX and float(na) < DECIDED_PX
    return False

def game_finished(info, now, league):
    """True when the Kalshi market is done or the event has clearly ended.

    Live in-progress games stay up: a still-active mid-price market gets a short
    grace window past typical duration (overtime). After that, or once Kalshi
    settles/closes the market or the result is in, the pick is dropped.
    """
    status = (info.get("status") or info.get("state") or "").lower()
    result = (info.get("result") or "")
    if isinstance(result, str):
        result = result.lower()
    if result in ("yes", "no"):
        return True, "kalshi " + str(result)
    if status in KFINAL:
        return True, "kalshi " + status
    start = info.get("start_ts") or 0
    close = info.get("close_ts") or 0
    # "inactive" / "closed" / "deactivated" are not treated as settled on their
    # own — Kalshi often uses them before tip or while a live market is halted.
    # Those picks stay up until the result is in, the price is decided after
    # start, or the typical game length (plus a short OT grace) has passed.
    if close and now >= close:
        return True, "past close"
    ya, na, px = info.get("yes_ask"), info.get("no_ask"), info.get("price")
    started = bool(start and now >= start)
    if started:
        kind = bet_type(info.get("ticker") or "", info.get("title") or "")
        if (league or "").upper() not in ("UFC", "MMA", "BOXING"):
            if kind == "Moneyline" and ((ya is not None and ya >= DECIDED_PX) or (na is not None and na >= DECIDED_PX)):
                return True, "decided at %s/%s" % (ya, na)
            if px is not None and (px >= DECIDED_PX or px <= 1 - DECIDED_PX):
                return True, "decided at %s" % px
    if start and now >= start + live_secs(league):
        active = status in ("", "active", "open", "initialized", "unopened")
        if active and _mid_price(info) and now < start + live_secs(league) + FINISH_GRACE_SECS:
            return False, ""
        return True, "past max duration"
    return False, ""


def rec_line(nick, graded, pnl, age, extra="", best_at=None):
    parts = [nick]
    if graded and graded.get("n"):
        parts.append("%d-%d" % (graded.get("w") or 0, graded.get("l") or 0))
        if graded.get("roi") is not None:
            parts.append("%s%.0f%%" % ("+" if graded["roi"] >= 0 else "", graded["roi"]))
    if best_at:
        parts.append("Best at " + str(best_at))
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
PINNED_TAG = "Best Cappers"
PINNED_TAGS = {PINNED_TAG, "My 40", "Top 10", "Following"}  # accept older badge labels

def is_pin_tag(v):
    return (v or "") in PINNED_TAGS

TARGET_FOLLOW = 50  # rotating top 50 on each full scan; manuals stay pinned
# Best Cappers is a rotating top 50 of official-leaderboard cappers whose public
# trades are visible and trackable. Official all-time profit must be positive; a
# losing reconstructed record is out. Names with no public trades go to Watching.
# Noel's manual pins (falcon999, BWmarkets) stay unless he says otherwise.
MIN_FOLLOW_SAMPLE = 1
MIN_FOLLOW_PNL = 0.01  # any official profit > 0
MIN_FOLLOW_PNL_EARNER = 100000.0  # unused for follows; no-trade earners are Watching
FOLLOW_HORIZON_DAYS = 30  # Best Cappers keeps near-term sports only, not months-out futures
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
        "Best Cappers is a rotating top %d of official Kalshi projected-PnL "
        "leaderboard cappers whose public trades can be tracked, official "
        "all-time profit is positive, and they have no losing reconstructed "
        "record. Each full scan reranks by performance (veteran Wilson record, "
        "recent form, then official PnL) and keeps the top of the list. Manual "
        "pins stay. If a board fetch fails, the last list is kept. Leaderboard "
        "earners with no public trades go to Watching. doNotPin names, including "
        "80Mill, never re-enter."
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


STICKY_MANUAL = {"falcon999", "bwmarkets"}


def is_manual_pin(row, nick=None):
    """Noel's manual Best Cappers (falcon999, BWmarkets) stay unless he says otherwise.

    doNotPin still wins. Other auto members rotate on each full scan.
    """
    name = nick_key(nick or ((row.get("nickname") if isinstance(row, dict) else row) or ""))
    if name.lower() in STICKY_MANUAL:
        return True
    if not isinstance(row, dict):
        return False
    src = (row.get("source") or "").strip().lower()
    return bool(row.get("manual")) or src in ("manual", "user")


def wilson_lower(w, n, z=1.96):
    if not n or n <= 0:
        return 0.0
    z2 = z * z
    p = float(w) / float(n)
    denom = 1.0 + z2 / n
    center = p + z2 / (2.0 * n)
    spread = z * ((p * (1.0 - p) + z2 / (4.0 * n)) / n) ** 0.5
    return max(0.0, (center - spread) / denom)


def rotation_score(cap):
    """Veterans first (Wilson record x experience), then recent form, then official PnL."""
    g = follow_record(cap) or {}
    w, l, n = graded_wl(g)
    rec = wilson_lower(w, n) * (n / (n + 40.0))
    veteran = 1 if (n >= 10 and w > l) else 0
    form = 0.0
    if cap.get("tape7d") is not None:
        form = float(cap.get("tape7d") or 0)
    elif cap.get("weeklyPnl") is not None:
        form = float(cap.get("weeklyPnl") or 0)
    elif cap.get("tape30d") is not None:
        form = float(cap.get("tape30d") or 0)
    pnl = official_pnl(cap) or 0.0
    return (veteran, rec, form, pnl, n, w - l)


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
    """Do not shrink Best Cappers versus the last good list unless a name failed a real gate.

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


def reconcile_follow_list(active, pinned, cappers, people, now, log=print, rotate=None):
    """Keep Best Cappers as a rotating top TARGET_FOLLOW, plus Noel's manual pins.

    Auto members come only from official projected-PnL leaderboards, must be
    publicly trackable, have a winning (or ungraded) record, and positive
    official profit. doNotPin names never enter. On each successful full scan
    the list is reranked by performance (veteran Wilson/experience, then recent
    form, then official PnL) and trimmed to the top 50. Manual pins stay even
    if they would rank below the cut. Ranking-based drops are allowed; if the
    board fetch fails or this is a follow-check (incomplete pool), the last
    list is kept. Negative official profit still unpins non-manual names and
    adds them to doNotPin.
    """
    if rotate is None:
        rotate = SCAN_MODE not in ("follow", "follow-check", "follow_check")
    previous_names = list(dict.fromkeys(
        pinned_names(pinned) + [nick_key(n) for n in (pinned.get("lastGoodFollows") or []) if nick_key(n)]
    ))
    skip = do_not_pin_set(pinned)
    by = {nick_key(c.get("nickname")).lower(): c for c in cappers if c.get("nickname")}
    prev_rows = {}
    for row in list(pinned.get("cappers") or []):
        nick = nick_key(row.get("nickname") if isinstance(row, dict) else row)
        if nick:
            prev_rows[nick.lower()] = row if isinstance(row, dict) else {"nickname": nick, "tag": PINNED_TAG}

    def keep_row(nick, cap, source, row=None):
        base = dict(row) if isinstance(row, dict) else {}
        base["nickname"] = nick
        base["tag"] = PINNED_TAG
        if source:
            base["source"] = source
        if source == "manual" or is_manual_pin(base, nick):
            base["source"] = "manual"
            base["manual"] = True
        base.setdefault("addedAt", today_pt(now))
        if cap:
            cap["pinned"] = True
            cap["tag"] = PINNED_TAG
            cap["tier"] = PINNED_TAG
        return base

    still, dropped = [], []
    have = set()

    def drop_name(nick, cap, why):
        pnl = official_pnl(cap)
        if cap and is_negative_profit(pnl) and not is_manual_pin(prev_rows.get(nick.lower()) or {}, nick):
            add_do_not_pin(pinned, nick, "negative profit", now)
            why = "negative profit %s" % signed_k(pnl)
        dropped.append("%s (%s)" % (nick, why))
        if cap:
            clear_follow_flags(cap, people)

    # Always honor doNotPin. Manual pins stay through rotation and failed fetches.
    for nick in previous_names:
        k = nick.lower()
        if not k or k in have:
            continue
        cap = by.get(k)
        row = prev_rows.get(k)
        if k in skip:
            drop_name(nick, cap, "doNotPin")
            continue
        if is_manual_pin(row or {}, nick):
            still.append(keep_row(nick, cap, "manual", row))
            have.add(k)
            continue
        if not rotate:
            # Incomplete run or failed board fetch: keep the last list.
            # Only drop a non-manual we re-evaluated this run who now has negative official profit.
            if cap and is_negative_profit(official_pnl(cap)):
                drop_name(nick, cap, "negative profit")
                continue
            still.append(keep_row(nick, cap, (row or {}).get("source") if row else "safeguard", row))
            have.add(k)

    if rotate:
        skip = do_not_pin_set(pinned)
        scored = []
        for cap in cappers:
            k = nick_key(cap.get("nickname")).lower()
            if not k or k in have or k in skip:
                continue
            if can_follow(cap):
                scored.append((rotation_score(cap), cap))
        scored.sort(key=lambda x: (-x[0][0], -x[0][1], -x[0][2], -x[0][3], -x[0][4], -x[0][5], nick_key(x[1].get("nickname")).lower()))
        added = []
        for _sc, cap in scored:
            if len(still) >= TARGET_FOLLOW:
                break
            nick = cap["nickname"]
            k = nick_key(nick).lower()
            g = cap.get("graded") or {}
            pnl = official_pnl(cap)
            still.append(keep_row(nick, cap, "auto-winning", prev_rows.get(k)))
            have.add(k)
            added.append("%s %d-%d %s" % (nick, g.get("w") or 0, g.get("l") or 0, signed_k(pnl) if pnl is not None else ""))
        # Anyone previously followed who did not make this cut rotates off.
        for nick in previous_names:
            k = nick.lower()
            if k and k not in have and k not in skip:
                cap = by.get(k)
                if is_manual_pin(prev_rows.get(k) or {}, nick):
                    continue
                dropped.append("%s (rotated)" % nick)
                if cap:
                    clear_follow_flags(cap, people)
        if added:
            log("follow: rotated in %d (target %d): %s" % (len(added), TARGET_FOLLOW, ", ".join(added)))

    pinned["cappers"] = still
    if dropped:
        log("follow: unpinned: " + ", ".join(dropped))
    if rotate or not pinned.get("lastGoodFollows"):
        current = pinned_names(pinned)
        if current:
            pinned["lastGoodFollows"] = current
    log("follow: %d/%d pinned%s; discovery continues every hour" % (
        len(pinned["cappers"]), TARGET_FOLLOW, "" if rotate else " (list held)"))
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
            start_ts = info.get("start_ts") or ticker_date_ts(tk) or 0
            if window_secs and start_ts and start_ts > now + window_secs:
                continue
            inv = inv_map.get(tk) if inv_map else None
            entry, cost = lib.pick_entry_and_cost(inv, signed)
            side = "yes" if signed > 0 else "no"
            ask = info.get("yes_ask") if side == "yes" else info.get("no_ask")
            if entry is None and ask is not None:
                entry = ask
                cost = abs(signed) * (entry or 0)
            if entry is None or cost is None:
                # Public positions can lack a quote or tape entry; estimate so
                # large viewable books (e.g. BWmarkets) are not silently dropped.
                entry = 0.5 if entry is None else entry
                cost = abs(signed) * entry
            if max_entry is not None and entry is not None and entry >= max_entry:
                continue
            if min_bet and (cost is None or cost < min_bet):
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
            px = ask if ask is not None else entry
            picks.append({
                "ticker": tk,
                "eventTicker": info.get("event_ticker") or ev_tk,
                "marketTitle": info.get("event_title") or info.get("title") or "",
                "contractTitle": info.get("title") or "",
                "backing": backing,
                "yesNo": "Yes" if side == "yes" else "No",
                "label": backing,
                "entry": round(entry, 4) if entry is not None else None,
                "price": round(px, 4) if px is not None else None,
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


def _grade_n(g):
    if not g:
        return 0
    return int(g.get("n") or 0) or (int(g.get("w") or 0) + int(g.get("l") or 0))


def follow_record(cap):
    """Prefer the fuller public W-L. A short follow-check tape must not beat a longer grade."""
    all_g = (cap or {}).get("gradedAll")
    sports = (cap or {}).get("graded")
    if _grade_n(all_g) >= _grade_n(sports) and _grade_n(all_g) > 0:
        return all_g
    return sports or all_g


def merge_preserved_record(new_cap, old_cap):
    """Keep the longer W-L / sports tape when a short inspect would clobber it."""
    if not old_cap or not new_cap:
        return new_cap
    replaced_graded = False
    for key in ("graded", "gradedAll"):
        if _grade_n(old_cap.get(key)) > _grade_n(new_cap.get(key)):
            new_cap[key] = old_cap.get(key)
            if key == "graded":
                replaced_graded = True
    old_sports, new_sports = old_cap.get("sports") or {}, new_cap.get("sports") or {}
    old_sn = sum(_grade_n(v) if isinstance(v, dict) else 0 for v in old_sports.values())
    new_sn = sum(_grade_n(v) if isinstance(v, dict) else 0 for v in new_sports.values())
    if old_sn > new_sn:
        new_cap["sports"] = old_sports
        if old_cap.get("bestAt"):
            new_cap["bestAt"] = old_cap.get("bestAt")
    if replaced_graded and old_cap.get("recordLine"):
        new_cap["recordLine"] = old_cap.get("recordLine")
    for key in ("tape7d", "tape30d", "volumeUsd", "ageDays", "recordLine", "pnl", "pnlSource"):
        if old_cap.get(key) is not None and new_cap.get(key) is None:
            new_cap[key] = old_cap.get(key)
    return new_cap


def stake_ok(p, floor=None):
    """True when this capper's stake on that side of the market meets the $500 minimum."""
    if floor is None:
        floor = MIN_BET
    try:
        return float((p or {}).get("cost") or 0) >= float(floor)
    except (TypeError, ValueError):
        return False


def follow_fail_reason(cap):
    """Why this capper must not be (or stay) in Best Cappers. None means every gate passed.

    Gates: must appear on an official Kalshi projected-PnL leaderboard
    (weekly, monthly, yearly, or all-time, including sport-specific boards).
    A name passes if they are on an official profit leaderboard, official
    all-time profit is positive, they have no losing reconstructed record,
    and their public trades or open sports picks can be found and tracked.
    Leaderboard earners with no public trades go to Watching — their picks
    cannot be copied. doNotPin is handled by the caller and never re-enters
    (the never-shrink guard also honors it).
    """
    if not is_trackable(cap):
        return "no public positions or posts to track"
    pnl = official_pnl(cap)
    if is_negative_profit(pnl):
        return "negative profit %s" % signed_k(pnl)
    # Viewable positions or profile posts are enough to stay on the list.
    # Closed-position grade (veterans first) does the ranking; a losing
    # reconstructed tape no longer auto-drops a book we can actually copy.
    return None


def is_trackable(cap):
    """True when public positions or profile posts let us copy this capper's book."""
    if not cap:
        return False
    if cap.get("positionsVisible") or cap.get("postsVisible"):
        return True
    w, l, n = graded_wl(follow_record(cap) or cap.get("graded") or cap.get("gradedAll"))
    if n > 0:
        return True
    if cap.get("picks") or cap.get("followingPicks"):
        return True
    if (cap.get("pickCount") or 0) > 0 or (cap.get("followCount") or 0) > 0:
        return True
    return False


def can_follow(cap):
    return follow_fail_reason(cap) is None


def is_near_term_pick(p, now, horizon_secs=FOLLOW_HORIZON_SECS):
    """True for live or soon-starting sports; false for undated / months-out futures or finished markets."""
    if not p:
        return False
    start = p.get("startTs") or 0
    close = p.get("closeTs") or 0
    view = p.get("view") or {}
    info = {
        "status": p.get("status") or p.get("state") or "",
        "result": p.get("result") or "",
        "start_ts": start,
        "close_ts": close,
        "yes_ask": p.get("yesAsk") if p.get("yesAsk") is not None else view.get("yesAsk"),
        "no_ask": p.get("noAsk") if p.get("noAsk") is not None else view.get("noAsk"),
        "price": p.get("price") if p.get("price") is not None else view.get("price"),
        "ticker": p.get("ticker") or view.get("ticker"),
        "title": p.get("label") or p.get("backing") or p.get("big") or p.get("game") or "",
        "state": p.get("state") or "",
    }
    done, _why = game_finished(info, now, p.get("league") or "")
    if done:
        return False
    when = start or close or ticker_date_ts(p.get("ticker") or info.get("ticker") or "") or 0
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
    sports_map, best_at = lib.grade_sports(lib.closed_cycles(trades, nick, sports_only=True))
    tier = capper_tier(nick, people)
    pin = is_pinned(nick)
    if pin:
        tier = PINNED_TAG  # show as Best Cappers; board rank still lives in ranks{}
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
        "sports": sports_map or {},
        "bestAt": best_at,
        "recordLine": rec_line(nick, use, all_time_pnl, age, tier, best_at),
        "picks": picks,
        "addedAt": today_pt(now),
    }




_TICKER_DATE_RE = re.compile(r"(?:^|-)(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})(?=[A-Z-]|\b)", re.I)
_MONTH_NUM = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,"JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}

def ticker_date(tk):
    """Calendar date encoded in a YYMONDD ticker, or None."""
    m = _TICKER_DATE_RE.search(tk or "")
    if not m:
        return None
    try:
        return dt.date(2000 + int(m.group(1)), _MONTH_NUM[m.group(2).upper()], int(m.group(3)))
    except (ValueError, KeyError):
        return None

def ticker_date_ts(tk, hour=13):
    """PT timestamp for a dated ticker when Kalshi omits occurrence_datetime.

    1pm PT is a last-resort slate time (typical NFL window) so $500+ today
    positions are not dropped as undated. Do not invent a start in the past
    morning, which would let decided-price logic hide a pre-kickoff favorite.
    """
    day = ticker_date(tk)
    if not day:
        return None
    return int(dt.datetime(day.year, day.month, day.day, hour, 0, tzinfo=PT).timestamp())

def post_ticker_in_window(tk, now, slack_days=3, ahead_days=45):
    """Skip clearly stale dated tickers before we hydrate (finished weeks ago)."""
    day = ticker_date(tk)
    if not day:
        return True
    today = dt.datetime.fromtimestamp(int(now), PT).date()
    delta = (day - today).days
    return -slack_days <= delta <= ahead_days


def grade_from_closed_holdings(holdings, open_tickers=None):
    """W-L from public closed positions (PnL sign). ROI unknown without cost."""
    open_tickers = {t.lower() for t in (open_tickers or []) if t}
    w = l = n = 0
    profit = 0.0
    for h in holdings or []:
        for mh in h.get("market_holdings") or []:
            tk = (mh.get("market_ticker") or "").lower()
            if tk and tk in open_tickers:
                continue
            pnl = lib.usd_units(mh.get("pnl"))
            if pnl is None:
                continue
            n += 1
            profit += pnl
            if pnl > 0.5:
                w += 1
            elif pnl < -0.5:
                l += 1
    if not n:
        return None
    return {"n": n, "w": w, "l": l, "roi": None, "profit": round(profit, 2), "sample": "positions"}


def grade_from_posts(posts, now=None, form_days=14):
    """W-L and ROI from settled idea/roi profile posts, one row per ticker|side."""
    best = {}
    for p in posts or []:
        tk = p.get("market_ticker") or ""
        side = (p.get("side") or "").lower()
        if not tk or not lib.post_is_settled(p):
            continue
        if lib.is_esports(tk) or not (lib.is_sports_ticker(tk) or tk.upper().startswith("KXMVE")):
            # Keep traditional sports and sports combos; skip non-sports.
            if not (lib.is_sports_ticker(tk) or "SPORT" in (p.get("series_title") or "").upper()):
                if not lib.is_sports_market({}, tk):
                    continue
        key = tk + "|" + side
        prev = best.get(key)
        if not prev or lib.post_created_ts(p) >= lib.post_created_ts(prev):
            best[key] = p
    w = l = n = 0
    profit = 0.0
    cost_sum = 0.0
    form_w = form_l = 0
    cutoff = (int(now) - form_days * 86400) if now else 0
    for p in best.values():
        cost = lib.post_cost_dollars(p) or 0.0
        paid = p.get("paid_out_cents")
        try:
            paid_d = float(paid) / 100.0 if paid is not None else None
        except (TypeError, ValueError):
            paid_d = None
        pnl = p.get("dollar_roi")
        if pnl is None and paid_d is not None:
            pnl = paid_d - cost
        if pnl is None:
            continue
        n += 1
        profit += float(pnl)
        cost_sum += cost
        win = float(pnl) > 0.5
        loss = float(pnl) < -0.5
        if win:
            w += 1
        elif loss:
            l += 1
        ts = lib.post_created_ts(p)
        if cutoff and ts >= cutoff:
            if win:
                form_w += 1
            elif loss:
                form_l += 1
    if not n:
        return None
    roi = (100.0 * profit / cost_sum) if cost_sum else None
    return {
        "n": n, "w": w, "l": l,
        "roi": round(roi, 1) if roi is not None else None,
        "profit": round(profit, 2),
        "sample": "posts",
        "formW": form_w, "formL": form_l,
    }


def picks_from_posts(http, posts, now, mcache, ecache, min_bet=MIN_BET):
    """Open $500+ sports ideas from profile posts, newest post wins a ticker|side."""
    latest = {}
    for p in posts or []:
        tk = p.get("market_ticker") or ""
        if not tk or lib.post_is_settled(p):
            continue
        if lib.is_esports(tk):
            continue
        cost = lib.post_cost_dollars(p)
        if min_bet and (cost is None or cost < min_bet):
            continue
        if not post_ticker_in_window(tk, now):
            continue
        ts = lib.post_created_ts(p)
        dated = bool(_TICKER_DATE_RE.search(tk or ""))
        if not dated and ts and int(now) - ts > 10 * 86400:
            continue
        side = "Yes" if (p.get("side") or "yes").lower() == "yes" else "No"
        key = tk + "|" + side
        if key not in latest or ts >= lib.post_created_ts(latest[key][0]):
            latest[key] = (p, cost, side)
    out = []
    ordered = sorted(latest.items(), key=lambda kv: -lib.post_created_ts(kv[1][0]))
    for key, (p, cost, side) in ordered[:40]:
        tk = p.get("market_ticker")
        info = lib.hydrate_market(http, tk, mcache, ecache)
        if not lib.is_sports_market(info, tk):
            continue
        league = lib.league_of(tk, info.get("category")) or "Sports"
        done, _why = game_finished(info, now, league)
        if done or lib.open_state(info, now) == "final":
            continue
        start_ts = info.get("start_ts") or ticker_date_ts(tk) or 0
        if not is_near_term_pick({"startTs": start_ts, "closeTs": info.get("close_ts") or 0, "league": league, "ticker": tk, "status": info.get("status")}, now):
            continue
        yes_no = side
        ask = info.get("yes_ask") if yes_no == "Yes" else info.get("no_ask")
        payout = p.get("payout_if_win_cents")
        try:
            contracts = float(payout) / 100.0 if payout else None
        except (TypeError, ValueError):
            contracts = None
        entry = (cost / contracts) if contracts else None
        backing = (info.get("yes_sub_title") if yes_no == "Yes" else info.get("no_sub_title")) or p.get("market_title") or info.get("title") or tk
        game = p.get("event_title") or info.get("event_title") or info.get("title") or p.get("event_ticker") or tk
        out.append({
            "ticker": tk,
            "eventTicker": info.get("event_ticker") or p.get("event_ticker") or "",
            "marketTitle": p.get("event_title") or info.get("event_title") or info.get("title") or "",
            "contractTitle": p.get("market_title") or info.get("title") or "",
            "backing": backing,
            "yesNo": yes_no,
            "label": backing,
            "entry": round(entry, 4) if entry is not None else None,
            "price": round(ask, 4) if ask is not None else (round(entry, 4) if entry is not None else None),
            "yesAsk": info.get("yes_ask"),
            "noAsk": info.get("no_ask"),
            "cost": round(cost or 0, 2),
            "contracts": round(contracts, 2) if contracts is not None else None,
            "lastTs": lib.post_created_ts(p) or None,
            "startTs": start_ts or 0,
            "state": "live" if (start_ts and start_ts <= now) else "upcoming",
            "league": league,
            "game": game,
            "bt": bet_type(tk, backing or p.get("market_title") or ""),
            "slip": None,
            "status": info.get("status"),
            "result": info.get("result"),
            "closeTs": info.get("close_ts") or 0,
            "source": "posts",
            "postId": p.get("id"),
        })
    return out


def merge_picks(*groups):
    """Dedupe by ticker|side; prefer positions cost when both sources have the pick."""
    by = {}
    for group, source in groups:
        for p in group or []:
            key = "%s|%s" % (p.get("ticker") or "", p.get("yesNo") or "")
            if not key.strip("|"):
                continue
            cur = by.get(key)
            incoming = dict(p)
            incoming.setdefault("source", source)
            if not cur:
                by[key] = incoming
                continue
            # Keep the larger stake; remember both sources.
            if (incoming.get("cost") or 0) > (cur.get("cost") or 0):
                srcs = sorted({cur.get("source"), incoming.get("source")} - {None})
                incoming["source"] = "+".join(srcs) if len(srcs) > 1 else (incoming.get("source") or cur.get("source"))
                by[key] = incoming
            else:
                srcs = sorted({cur.get("source"), incoming.get("source")} - {None})
                if len(srcs) > 1:
                    cur["source"] = "+".join(srcs)
    return list(by.values())


def inspect_visible(http, nick, now, mcache, ecache, people, log, trades_pages=80, old=None, need_tickers=None):
    """Return ('active', row) or ('rejected', reason, detail).

    Positions come from the public holdings endpoint. If that book is hidden,
    profile posts/ideas are used instead (falcon999). Both are used when available.
    """
    vis, _ = lib.holdings_visible(http, nick, limit=5)
    positions_hidden = vis == "hidden"
    if vis not in ("visible", "hidden", None, ""):
        # Empty/failed API response has no visibility_state — do not permanently reject.
        if vis is not None and vis != "":
            raise RuntimeError("holdings visibility unknown (%r)" % (vis,))
    if vis not in ("visible", "hidden"):
        # unknown: try as visible, but don't reject
        positions_hidden = False
    prof = (http.get(f"{lib.SOCIAL}/profile", {"nickname": nick}) or {}).get("social_profile") or {}
    metrics = (http.get(f"{lib.SOCIAL}/profile/metrics", {"nickname": nick}) or {}).get("metrics") or {}
    holdings, trades, closed_holdings = [], [], []
    if not positions_hidden:
        vis2, holdings = lib.paginate_holdings(http, nick)
        if vis2 == "hidden":
            positions_hidden = True
            holdings = []
        else:
            stop_ts = now - lib.RECORD_DAYS * 86400
            auto_need = need_tickers
            if auto_need is None and trades_pages is not None and trades_pages <= 20:
                auto_need = set()
                for h in holdings or []:
                    for mh in h.get("market_holdings") or []:
                        tk = mh.get("market_ticker")
                        try:
                            signed = float(mh.get("signed_open_position") or 0)
                        except Exception:
                            signed = 0.0
                        if tk and abs(signed) >= 0.5:
                            auto_need.add(tk)
                if not auto_need:
                    auto_need = None
            vis3, trades = lib.paginate_trades(http, nick, now, stop_ts, max_pages=trades_pages, need_tickers=auto_need)
            if vis3 == "hidden":
                trades = []
            # Closed positions for W-L / form (cheap extra pages).
            _cv, closed_holdings = lib.paginate_holdings(http, nick, closed=True, max_pages=4)
            if _cv == "hidden":
                closed_holdings = []
    # Profile posts always — this is how hidden books like falcon999 publish picks.
    posts = lib.paginate_timeline(http, nick, max_pages=5 if (trades_pages or 80) <= 20 else 8)
    posts_visible = any((p.get("market_ticker") and (lib.post_cost_dollars(p) or 0) > 0) for p in posts)
    pin = is_pinned(nick)
    if positions_hidden and not posts_visible and not pin:
        return "rejected", "hidden book", "hidden"
    hold_n = sum(len(h.get("market_holdings") or []) for h in holdings or [])
    is_mm, mm_why = lib.mm_flags(trades, nick) if trades else (False, [])
    if is_mm and hold_n >= 25 and not pin:
        return "rejected", "market-maker", "%s; open=%d trades=%d" % (", ".join(mm_why), hold_n, len(trades))
    if (not positions_hidden) and (not has_sports_activity(holdings, trades)) and (not posts_visible) and (not pin):
        return "rejected", "no sports activity", "open=%d trades=%d" % (hold_n, len(trades))
    heavy = bool(is_mm)
    if heavy:
        log("heavy trader kept %s: %s trades=%d open=%d" % (nick, ", ".join(mm_why), len(trades), hold_n))
    inv_map = lib.build_inventory(trades, nick) if trades else {}
    pos_picks = []
    if holdings:
        pos_picks = collect_picks(http, holdings, trades, inv_map, now, mcache, ecache)
        for p in pos_picks:
            p.setdefault("source", "positions")
    post_picks = picks_from_posts(http, posts, now, mcache, ecache, min_bet=MIN_BET) if posts else []
    picks = merge_picks((pos_picks, "positions"), (post_picks, "posts"))
    boardish = pin or on_profit_leaderboard({"nickname": nick, "profitRanks": (people.get(nick) or {}).get("profitRanks"), "pnl": (people.get(nick) or {}).get("pnl")})
    follow = []
    if boardish or pin or posts_visible or (not positions_hidden):
        follow_pos = []
        if holdings:
            follow_pos = collect_picks(http, holdings, trades, inv_map, now, mcache, ecache, min_bet=MIN_BET, window_secs=FOLLOW_HORIZON_SECS, max_entry=None)
            for p in follow_pos:
                p.setdefault("source", "positions")
        follow = merge_picks((follow_pos, "positions"), (post_picks, "posts"))
        follow = [p for p in follow if is_near_term_pick(p, now) and stake_ok(p)]
    row = build_capper_row(nick, people, prof, metrics, trades, holdings, picks, now, heavy=heavy)
    row = merge_preserved_record(row, old)
    # Prefer a fuller closed-position or posts grade when the public tape is thin/hidden.
    open_tks = [mh.get("market_ticker") for h in holdings or [] for mh in (h.get("market_holdings") or [])]
    pos_grade = grade_from_closed_holdings(closed_holdings, open_tks) if closed_holdings else None
    post_grade = grade_from_posts(posts, now=now)
    chosen = None
    if pos_grade and post_grade:
        # Use the larger sample. Do not copy ROI across sources — posts ROI
        # does not belong on a positions W-L (and vice versa).
        chosen = pos_grade if (pos_grade.get("n") or 0) >= (post_grade.get("n") or 0) else post_grade
    else:
        chosen = pos_grade or post_grade
    if chosen and (_grade_n(chosen) >= _grade_n(row.get("graded")) or not row.get("graded")):
        row["graded"] = chosen
        if not row.get("gradedAll") or _grade_n(chosen) >= _grade_n(row.get("gradedAll")):
            row["gradedAll"] = chosen
        extra = ""
        if chosen.get("roi") is not None:
            extra = "%s%.0f%%" % ("+" if chosen["roi"] >= 0 else "", chosen["roi"])
        row["recordLine"] = rec_line(nick, chosen, row.get("pnl"), None, extra, row.get("bestAt"))
    row["followingPicks"] = follow
    row["positionsVisible"] = not positions_hidden
    row["postsVisible"] = bool(posts_visible)
    row["openPositions"] = hold_n
    srcs = []
    if row["positionsVisible"]:
        srcs.append("positions")
    if row["postsVisible"]:
        srcs.append("posts")
    row["pickSource"] = "+".join(srcs) if srcs else ("hidden" if positions_hidden else "")
    if positions_hidden and posts_visible:
        row["rejectNote"] = None
        log("posts used for hidden book %s: %d posts, %d open $%d+ picks" % (nick, len(posts), len(follow), MIN_BET))
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



def enrich_follow_cappers(following, live_cappers):
    """Attach official profit, closed grade, and pick source to the Best Cappers roster."""
    by = {nick_key(c.get("nickname")): c for c in (live_cappers or []) if c.get("nickname")}
    for rec in following.get("cappers") or []:
        src = by.get(nick_key(rec.get("nickname")))
        if not src:
            continue
        rec["pnl"] = src.get("pnl")
        rec["pnlSource"] = src.get("pnlSource")
        rec["openPositions"] = src.get("openPositions") if src.get("openPositions") is not None else rec.get("open")
        rec["pickSource"] = src.get("pickSource") or ""
        rec["positionsVisible"] = bool(src.get("positionsVisible"))
        rec["postsVisible"] = bool(src.get("postsVisible"))
        g = src.get("graded") or {}
        rec["roi"] = g.get("roi")
        rec["closedW"] = g.get("w")
        rec["closedL"] = g.get("l")
        rec["closedN"] = g.get("n") or ((g.get("w") or 0) + (g.get("l") or 0))
        rec["formW"] = g.get("formW")
        rec["formL"] = g.get("formL")
        rec["recordLine"] = src.get("recordLine") or rec.get("recordLine")
        rec["profileUrl"] = src.get("profileUrl") or rec.get("profileUrl")
        if src.get("postsVisible") or src.get("positionsVisible") or rec.get("open"):
            rec["hidden"] = False
    def rank(r):
        n = r.get("closedN") or 0
        veteran = 0 if n >= 10 else (1 if n >= 5 else (2 if n else 3))
        wr = (r.get("closedW") or 0) / n if n else -1
        roi = r.get("roi")
        return (veteran, -wr, -n, 1e9 if roi is None else -float(roi), -(r.get("pnl") or 0), (r.get("nickname") or "").lower())
    following["cappers"] = sorted(following.get("cappers") or [], key=rank)
    return following


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
    # for history but never re-enter the Best Cappers list.
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
            # Don't count months-out futures as an open Best Cappers pick.
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
        rec = people.get(nick) or {}
        profit = 0 if (rec.get("profitRanks") or rec.get("pnl")) else 1
        r = sports_ranks(people, nick)
        sports = 0 if r else 1
        best = min([r.get(p) or 9999 for p in BOARD_PERIODS] or [9999])
        return (profit, sports, best, nick.lower())
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


def picks_for_slate(c, now=None):
    """Best Cappers public slate uses copyable followed picks ($500+ only) when present.

    Undated and months-out futures are left off — only near-term sports.
    """
    fol = list(c.get("followingPicks") or [])
    use = fol if fol else list(c.get("picks") or [])
    ts = now if now is not None else time.time()
    return [p for p in use if is_near_term_pick(p, ts) and stake_ok(p)]


def followed_slate_cappers(cappers, pinned, now=None):
    pinset = {nick_key(n).lower() for n in pinned_names(pinned)}
    rows = []
    for c in cappers or []:
        nick = nick_key(c.get("nickname"))
        if not nick or nick.lower() not in pinset:
            continue
        rows.append(dict(c, picks=picks_for_slate(c, now=now)))
    return rows


def group_games(cappers, now, log=print):
    by, order, dropped = {}, [], []
    for c in cappers:
        rec = c.get("graded")
        for p in c.get("picks") or []:
            if not stake_ok(p):
                continue
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
            sports = c.get("sports") or {}
            fam = lib.sport_family(p.get("league") or g.get("league") or "")
            srec = sports.get(fam) if fam else None
            slot["backers"].append({
                "name": c["nickname"], "cost": p["cost"], "avg": p.get("entry"),
                "line": rec_line(c["nickname"], rec, c.get("pnl"), None, c["tier"], c.get("bestAt")),
                "rec": {"w": rec["w"], "l": rec["l"], "n": rec["n"]} if rec else None,
                "sportRec": {"w": srec["w"], "l": srec["l"], "n": srec["n"]} if srec else None,
                "bestAt": c.get("bestAt"),
                "pnl": c.get("pnl"),
                "pinned": bool(c.get("pinned") or is_pin_tag(c.get("tier")) or is_pin_tag(c.get("tag"))),
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
        kept = []
        for p in picks:
            info = {
                "status": p.get("status") or p.get("state") or "",
                "result": p.get("result") or "",
                "start_ts": p.get("startTs") or g["startTs"] or 0,
                "close_ts": p.get("closeTs") or 0,
                "yes_ask": p.get("yesAsk"),
                "no_ask": p.get("noAsk"),
                "price": (p.get("view") or {}).get("price"),
                "ticker": p.get("ticker"),
                "title": p.get("big") or g["game"],
                "state": p.get("state") or "",
            }
            done, why = game_finished(info, now, g["league"])
            if done:
                dropped.append("%s · %s (%s)" % (g["game"], p.get("big") or "", why))
                continue
            p["backers"] = [b for b in (p.get("backers") or []) if stake_ok({"cost": b.get("cost")})]
            if not p["backers"]:
                continue
            p["backers"].sort(key=lambda b: -(b.get("cost") or 0))
            p["total"] = round(sum(b.get("cost") or 0 for b in p["backers"]), 2)
            kept.append(p)
        if not kept:
            continue
        g["picks"] = kept
        closes = [p.get("closeTs") or 0 for p in kept if p.get("closeTs")]
        g["closeTs"] = min(closes) if closes else 0
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
            verdict = inspect_visible(http, nick, now, mcache, ecache, people, log, trades_pages=80)
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


def carry_forward_games(new_games, prev, now, http, mcache, ecache, log=print, pinned=None):
    """Keep still-open picks from the previous (or recovered) data.json.

    Fresh rows from this scan win. Positions no longer visible stay, marked
    Last seen <time> PT, until the usual finished-game rules drop them.
    When pinned is provided, only Best Cappers backers are carried — tape-only names stay off the slate.
    """
    pinset = {nick_key(n).lower() for n in pinned_names(pinned)} if pinned is not None else None
    seen = set()
    for g, p, b, key in _flatten_game_positions(new_games):
        seen.add(key)
    carried = 0
    dropped = []
    by_id = {g.get("id"): g for g in new_games}
    order = [g.get("id") for g in new_games]
    prev_at = prev.get("scannedAt") or ""
    for g, p, b, key in _flatten_game_positions(prev.get("games") or []):
        if pinset is not None and nick_key(b.get("name") or "").lower() not in pinset:
            continue
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
    """Same carry rules for Best Cappers display picks. Does not write the trial ledger.

    Only still-followed, near-term sports picks are kept. Unfollowed books and
    months-out futures are dropped from the display list.
    """
    def fid(p):
        return _backer_key(p.get("nickname"), p.get("ticker"), p.get("yesNo"))
    pinset = {n.lower() for n in pinned_names(pinned)} if pinned is not None else None
    def allowed(p):
        if pinset is not None and nick_key(p.get("nickname")).lower() not in pinset:
            return False
        if not stake_ok(p):
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
            pages = 80 if is_pinned(nick) else 20
            verdict = inspect_visible(http, nick, now, mcache, ecache, people, log, trades_pages=pages, old=row)
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

    # If Best Cappers is short of 50, keep reviewing official profit-board names
    # in this same run. Hidden books fail on the first holdings call (cheap).
    fill_deadline = t0 + 18 * 60
    fill_rounds = 0
    while time.time() < fill_deadline:
        qualifying = 0
        seen_q = set()
        skip_q = do_not_pin_set(pinned)
        for nick in pinned_names(pinned):
            k = nick.lower()
            if not k or k in skip_q:
                continue
            cap = next((c for c in live_cappers if nick_key(c.get("nickname")).lower() == k), None)
            if is_manual_pin({}, nick) or (cap and can_follow(cap)):
                qualifying += 1
                seen_q.add(k)
        for cap in live_cappers:
            k = nick_key(cap.get("nickname")).lower()
            if not k or k in seen_q or k in skip_q:
                continue
            if can_follow(cap):
                qualifying += 1
                seen_q.add(k)
        cov["qualifyingFollows"] = qualifying
        if qualifying >= TARGET_FOLLOW:
            break
        known = known_nicks(active, queue, rejected)
        if not (queue.get("cappers") or []):
            more = enqueue_new(queue, people, known, 40, now, log)
            cov["queuedNew"] = (cov.get("queuedNew") or 0) + len(more)
            save_dbs(active, queue, rejected, now)
            if not more:
                log("fill: no more official-board names to review (%d/%d qualifying)" % (qualifying, TARGET_FOLLOW))
                break
        before_rev = cov.get("queueReviewed") or 0
        log("fill: %d/%d qualifying; reviewing more leaderboard names" % (qualifying, TARGET_FOLLOW))
        review_queue(http, queue, active, rejected, live_cappers, people, now, mcache, ecache, cov, log)
        save_dbs(active, queue, rejected, now)
        fill_rounds += 1
        if (cov.get("queueReviewed") or 0) == before_rev:
            break
    cov["fillRounds"] = fill_rounds
    cov["namesChecked"] = (cov.get("activeRefreshed") or 0) + (cov.get("queueReviewed") or 0)

    # Dedup live cappers (active refresh + newly activated)
    byn = {}
    for c in live_cappers:
        byn[nick_key(c["nickname"])] = c
    # Any active db member we failed to refresh still appears on the Cappers tab, no invented picks.
    # Keep their last published following picks so a missed refresh cannot wipe $500+ copies.
    live_names = set(byn)
    prev_follow = {}
    for p in ((prev.get("following") or {}).get("picks") or []):
        nk = nick_key(p.get("nickname"))
        if nk:
            prev_follow.setdefault(nk, []).append(p)
    for row in active.get("cappers") or []:
        n = nick_key(row.get("nickname"))
        if n and n not in live_names:
            byn[n] = dict(row, picks=[], followingPicks=list(prev_follow.get(n) or []))
    cappers = list(byn.values())

    # Ranked / Coming Up are built after reconcile so they only include Best Cappers picks.
    games, dropped = [], []
    cov["calls"] = http.calls
    cov["retries429"] = http.retries_429
    cov["secs"] = round(time.time() - t0, 1)
    cov["dbActive"] = len(active.get("cappers") or [])
    cov["dbQueue"] = len(queue.get("cappers") or [])
    cov["dbRejected"] = len(rejected.get("cappers") or [])
    cov["dbPinned"] = sum(1 for r in (active.get("cappers") or []) if r.get("pinned") or is_pin_tag(r.get("tag")) or is_pin_tag(r.get("tier")))

    def cap_key(c):
        pin_n = 0 if (c.get("pinned") or is_pin_tag(c.get("tier"))) else 1
        g = c.get("graded") or {"w": 0, "l": 0, "n": 0}
        n = (g.get("w") or 0) + (g.get("l") or 0) or (g.get("n") or 0)
        wr = (g.get("w") or 0) / n if n else -1
        veteran = 0 if n >= 10 else (1 if n >= 5 else (2 if n else 3))
        roi = g.get("roi")
        roi_n = -(float(roi)) if roi is not None else 1e9
        return (pin_n, veteran, -wr, -n, roi_n, -(c.get("pnl") or 0), (c.get("nickname") or "").lower())
    # Refresh the follow list from this scan's full W-L, then copy their open picks.
    # Discovery (queue + NEW_PER_SCAN new) already ran above and never stops at TARGET_FOLLOW.
    pinned = reconcile_follow_list(active, pinned, cappers, people, now, log, rotate=bool(people))
    save_dbs(active, queue, rejected, now)
    games, dropped = group_games(followed_slate_cappers(cappers, pinned), now, log)
    games, carried_n, carried_dropped = carry_forward_games(games, prev, now, http, mcache, ecache, log, pinned=pinned)
    dropped = list(dropped) + list(carried_dropped)
    cov["carriedPicks"] = carried_n
    cov["carriedDropped"] = len(carried_dropped)
    cov["finishedDropped"] = len(dropped)
    cov["finishedNames"] = dropped
    cov["shown"] = sum(1 for c in followed_slate_cappers(cappers, pinned) if c.get("picks"))
    cov["picks"] = sum(len(g["picks"]) for g in games)
    cov["games"] = len(games)
    following_open = []
    for c in cappers:
        if not (c.get("pinned") or is_pinned(c.get("nickname"), pinned)):
            continue
        for p in c.get("followingPicks") or []:
            if not is_near_term_pick(p, now) or not stake_ok(p):
                continue
            following_open.append(dict(p, nickname=c.get("nickname"), recordLine=c.get("recordLine") or c.get("nickname"), tier=c.get("tier") or PINNED_TAG, source=p.get("source")))
    following = update_trial_ledger(http, following_open, pinned, pinned_hidden, now, mcache, ecache, log)
    following = enrich_follow_cappers(following, cappers)
    # Carry previous Best Cappers *display* picks only. The trial ledger is already persisted and was
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
        if not (c.get("pinned") or is_pinned(c.get("nickname"), pinned) or is_trackable(c)):
            continue
        pub_cappers.append({k: v for k, v in c.items() if k not in ("picks", "followingPicks")} | {"pickCount": len(c.get("picks") or []), "followCount": len(c.get("followingPicks") or [])})
    pub_cappers.sort(key=cap_key)

    payload = {
        "scannedAt": pt(now),
        "ts": now,
        "source": {
            "note": "Kalshi public social + trade APIs. No official profit time series and no 30-day leaderboard exist; monthly Sports projected P&L is the stand-in for a 30-day window, weekly for 7 days. All-time profit is the profile metrics PnL (never invented). 7d/30d sports-tape profit is reconstructed only from settled public sports trades. Names come from Sports, Politics, Economics, Crypto and Mentions boards (all-time, monthly, weekly, yearly; projected PnL and volume, top 100) plus traders seen on active traditional-sports series tapes. Picks are traditional sports singles and sports combos only — esports is excluded. Hidden books, market makers, and traders with no traditional-sports activity are rejected and never rechecked, except followed Best Cappers, who stay in the active db. Visible sports traders stay in the active db even with no open pick today. Open picks come from public positions and, when the book is hidden, from public profile posts/ideas. Closed-position or settled-post W–L, ROI, and official profile-metrics profit are shown. The page lists only cappers whose positions or posts we can actually view — the watching 100+ pool is not displayed. Best Cappers is ranked by closed-position grade, veterans (longer records) above small samples. Near-term traditional-sports picks (starting within 30 days; long-dated futures are excluded) are copied when that capper’s total stake on that side of that market is at least $%d. They are graded from official Kalshi results after settlement. New viewable cappers are still discovered every hour. Negative official profit is added to doNotPin and can never re-enter. W-L is never invented." % MIN_BET,
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
    log("follow-check: refreshing %d pinned cappers (all books, $%d+ stakes)" % (len(names), MIN_BET))
    prev_caps = {nick_key(c.get("nickname")): c for c in (prev.get("cappers") or [])}
    for nick in names:
        try:
            old = prev_caps.get(nick_key(nick)) or next((r for r in (active.get("cappers") or []) if nick_key(r.get("nickname")) == nick_key(nick)), None)
            verdict = inspect_visible(http, nick, now, mcache, ecache, {}, log, trades_pages=20, old=old)
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
            for k in ("profileUrl", "ranks", "profitRanks", "onProfitBoard", "pnl", "weeklyPnl", "monthlyPnl", "yearlyPnl", "tape7d", "tape30d", "volumeUsd", "graded", "gradedAll", "sports", "bestAt", "recordLine", "ageDays"):
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
                if cap.get("gradedAll") is not None:
                    row["gradedAll"] = cap.get("gradedAll")
                if cap.get("sports") is not None:
                    row["sports"] = cap.get("sports")
                if cap.get("bestAt") is not None:
                    row["bestAt"] = cap.get("bestAt")
                if cap.get("pnl") is not None:
                    row["pnl"] = cap.get("pnl")
                for fld in ("positionsVisible", "postsVisible", "pickSource", "openPositions", "recordLine", "pnlSource"):
                    if cap.get(fld) is not None:
                        row[fld] = cap.get(fld)
                break
    # Reconcile follows immediately: drop negative-profit or losing followed names
    # and swap from the previously evaluated pool when a better capper is already known.
    pool = {nick_key(c.get("nickname")): c for c in live_cappers if c.get("nickname")}
    for c in (prev.get("cappers") or []):
        k = nick_key(c.get("nickname"))
        if k and k not in pool:
            pool[k] = dict(c, picks=c.get("picks") or [], followingPicks=c.get("followingPicks") or [])
    pinned = reconcile_follow_list(active, pinned, list(pool.values()), {}, now, log, rotate=False)
    # Keep only still-followed in the live inspect list for Best Cappers picks.
    live_cappers = [
        c for c in live_cappers
        if c.get("pinned") or is_pinned(c.get("nickname"), pinned)
    ]
    save_dbs(active, queue, rejected, now)

    games, dropped = group_games(followed_slate_cappers(live_cappers, pinned), now, log)
    games, carried_n, carried_dropped = carry_forward_games(games, prev, now, http, mcache, ecache, log, pinned=pinned)
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
            if not is_near_term_pick(p, now) or not stake_ok(p):
                continue
            following_open.append(dict(p, nickname=c.get("nickname"), recordLine=c.get("recordLine") or c.get("nickname"), tier=c.get("tier") or PINNED_TAG, source=p.get("source")))
    following = update_trial_ledger(http, following_open, pinned, pinned_hidden, now, mcache, ecache, log)
    following = enrich_follow_cappers(following, live_cappers)
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
    # post-reconcile pin list — never stale pinned=True / "Best Cappers" or "My 40" tiers from prev.
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
    # Display only cappers we can actually track (positions or posts). Do not
    # republish the watching 100+ pool onto the page.

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
