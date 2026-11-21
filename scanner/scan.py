#!/usr/bin/env python3
"""Kalshi Scanner: Sports leaderboard cappers with public books, grouped into game cards.

Source: Kalshi's public social + trade APIs (api.elections.kalshi.com).
Kalshi has no 30-day leaderboard period; the closest is 'monthly'.
Universe is Sports projected-PnL all-time and monthly boards (top 50 primary,
top 100 used so hidden books don't empty the page), plus weekly for extra
visible traders. Hidden profiles cannot be read. W-L is reconstructed from
each visible capper's public sports trade tape — never fabricated.
"""
from __future__ import annotations

import json, os, re, sys, time, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import lib_cappers as lib

PT = lib.PT
MIN_BET = 500
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


def build(now=None, log=print):
    now = int(now or time.time())
    t0 = time.time()
    http = lib.Http()
    stop_ts = now - lib.RECORD_DAYS * 86400

    boards, board_cov = lib.fetch_leaderboards(http)
    at50, mo50 = board_set(boards, "all_time", 50), board_set(boards, "monthly", 50)
    at100, mo100 = board_set(boards, "all_time", 100), board_set(boards, "monthly", 100)
    wk50 = board_set(boards, "weekly", 50)
    # Primary: all-time top 50 ∪ monthly top 50. Expand to top 100 + weekly 50 so
    # hidden books don't leave an empty page; those extras are tagged "Board"/"Weekly".
    pool = sorted(set(at100) | set(mo100) | set(wk50), key=lambda n: (
        0 if n in at50 and n in mo50 else 1 if n in at50 or n in mo50 else 2,
        (boards[n]["ranks"].get("all_time") or 9999),
        (boards[n]["ranks"].get("monthly") or 9999),
        n.lower(),
    ))

    cov = {
        "leaderboardNames": len(boards),
        "boards": board_cov,
        "intersection50": len(at50 & mo50),
        "union50": len(at50 | mo50),
        "pool": len(pool),
        "visible": 0,
        "hidden": 0,
        "mmDropped": 0,
        "negativePnl": 0,
        "noBook": 0,
        "shown": 0,
        "picks": 0,
        "games": 0,
        "finishedDropped": 0,
        "finishedNames": [],
        "calls": 0,
        "retries429": 0,
        "secs": 0,
    }

    mcache, ecache = {}, {}
    cappers = []

    for nick in pool:
        vis, _hold = lib.holdings_visible(http, nick, limit=5)
        if vis != "visible":
            cov["hidden"] += 1
            continue
        cov["visible"] += 1
        prof = (http.get(f"{lib.SOCIAL}/profile", {"nickname": nick}) or {}).get("social_profile") or {}
        metrics = (http.get(f"{lib.SOCIAL}/profile/metrics", {"nickname": nick}) or {}).get("metrics") or {}
        vis2, holdings = lib.paginate_holdings(http, nick)
        if vis2 == "hidden":
            cov["visible"] -= 1
            cov["hidden"] += 1
            continue
        vis3, trades = lib.paginate_trades(http, nick, now, stop_ts)
        if vis3 == "hidden":
            cov["visible"] -= 1
            cov["hidden"] += 1
            continue
        hold_n = sum(len(h.get("market_holdings") or []) for h in holdings or [])
        is_mm, mm_why = lib.mm_flags(trades, nick)
        # Drop only a quoting book (many open markets + MM-like tape).
        if is_mm and hold_n >= 25:
            cov["mmDropped"] += 1
            log(f"MM drop {nick}: {', '.join(mm_why)} trades={len(trades)} open={hold_n}")
            continue
        heavy = bool(is_mm)
        if heavy:
            log(f"heavy trader kept {nick}: {', '.join(mm_why)} trades={len(trades)} open={hold_n}")

        inv_map = lib.build_inventory(trades, nick)
        all_time_pnl = lib.usd_units(metrics.get("pnl"))
        if all_time_pnl is None:
            all_time_pnl = (boards.get(nick) or {}).get("pnl", {}).get("all_time")
        monthly_pnl = (boards.get(nick) or {}).get("pnl", {}).get("monthly")
        weekly_pnl = (boards.get(nick) or {}).get("pnl", {}).get("weekly")
        if all_time_pnl is not None and all_time_pnl < 0:
            cov["negativePnl"] += 1
            log(f"drop {nick}: negative all-time PnL ${all_time_pnl:,.0f}")
            continue

        cycles = lib.closed_cycles(trades, nick)
        risked = [c["risked"] for c in cycles if c.get("risked")]
        med = lib.median(risked) if risked else None
        floor = MIN_BET if (med is None or len(risked) < 3) else max(MIN_BET, 1.5 * med)
        graded = lib.grade_big_bets(cycles, floor)
        # Also a $500-flat record so small-sample cappers still have a W-L when we have it.
        graded500 = lib.grade_big_bets(cycles, MIN_BET)
        use = graded if (graded.get("n") or 0) >= 10 else (graded500 if graded500.get("n") else graded)
        age = lib.age_days(prof.get("joined_at"), now)
        tier = capper_tier(nick, at50, mo50, at100, mo100)
        ranks = (boards.get(nick) or {}).get("ranks") or {}

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
                done, why = game_finished(info, now, league)
                if done:
                    continue
                state = lib.open_state(info, now)
                if state == "final":
                    continue
                start_ts = info.get("start_ts") or 0
                # 24h window: live or starting within 24h. No start time goes last, still listed if open.
                if start_ts and start_ts > now + WINDOW_SECS:
                    continue
                inv = inv_map.get(tk)
                entry, cost = lib.pick_entry_and_cost(inv, signed)
                side = "yes" if signed > 0 else "no"
                ask = info.get("yes_ask") if side == "yes" else info.get("no_ask")
                if entry is None and ask is not None:
                    entry = ask
                    cost = abs(signed) * entry
                if entry is not None and entry >= MAX_ENTRY:
                    continue
                if cost is None or cost < MIN_BET:
                    continue
                if ask is None:
                    continue
                last_ts = (inv or {}).get("last_ts")
                if not last_ts:
                    for tr in trades:
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
                    "yesSubTitle": info.get("yes_sub_title") or "",
                    "noSubTitle": info.get("no_sub_title") or "",
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

        if not picks:
            cov["noBook"] += 1

        cappers.append({
            "nickname": nick,
            "profileUrl": "https://kalshi.com/ideas/profiles/" + nick,
            "joinedAt": prof.get("joined_at") or "",
            "followers": prof.get("follower_count") or 0,
            "tier": tier, "heavy": heavy,
            "ranks": ranks,
            "pnl": None if all_time_pnl is None else round(all_time_pnl, 2),
            "weeklyPnl": weekly_pnl,
            "monthlyPnl": monthly_pnl,
            "ageDays": age,
            "graded": {
                "n": use.get("n") or 0,
                "w": use.get("w") or 0,
                "l": use.get("l") or 0,
                "roi": None if use.get("roi") is None else round(use["roi"], 1),
                "profit": round(use.get("profit") or 0, 2),
                "sample": "full" if (use.get("n") or 0) >= 10 else "small",
            } if use and use.get("n") else None,
            "recordLine": rec_line(nick, use if use and use.get("n") else None, all_time_pnl, age, tier),
            "picks": picks,
        })

    # Group open picks into one card per game (event).
    by = {}
    order = []
    for c in cappers:
        rec = c.get("graded")
        for p in c["picks"]:
            gid = p.get("eventTicker") or (p.get("game") + "|" + str(p.get("startTs") or 0))
            if gid not in by:
                by[gid] = {
                    "id": gid,
                    "game": p["game"],
                    "league": p["league"],
                    "startTs": p["startTs"] or 0,
                    "start": pt(p["startTs"]) if p["startTs"] else "",
                    "live": bool(p["startTs"] and p["startTs"] <= now),
                    "state": p["state"],
                    "picks": {},
                }
                order.append(gid)
            g = by[gid]
            if p["startTs"] and (not g["startTs"] or p["startTs"] < g["startTs"]):
                g["startTs"] = p["startTs"]
                g["start"] = pt(p["startTs"])
                g["live"] = p["startTs"] <= now
            key = p["ticker"] + "|" + p["yesNo"]
            slot = g["picks"].setdefault(key, {
                "key": key,
                "ticker": p["ticker"],
                "eventTicker": p.get("eventTicker") or gid,
                "mid": p["ticker"],
                "bt": p["bt"],
                "big": p["label"],
                "sub": p["game"] if p["label"] != p["game"] else p.get("contractTitle") or "",
                "view": {
                    "backing": p["backing"],
                    "marketTitle": p["marketTitle"] or p.get("contractTitle") or p["game"],
                    "outcome": p["backing"],
                    "yesNo": p["yesNo"],
                    "price": p["price"],
                    "ticker": p["ticker"],
                },
                "backers": [],
                "total": 0,
                "tags": [],
                "slip": p.get("slip"),
                "startTs": p["startTs"],
                "state": p["state"],
                "status": p.get("status"),
                "result": p.get("result"),
                "closeTs": p.get("closeTs") or 0,
                "yesAsk": p.get("yesAsk"),
                "noAsk": p.get("noAsk"),
            })
            slot["backers"].append({
                "name": c["nickname"],
                "cost": p["cost"],
                "avg": p.get("entry"),
                "line": rec_line(c["nickname"], rec, c.get("pnl"), None, c["tier"]),
                "rec": {"w": rec["w"], "l": rec["l"], "n": rec["n"]} if rec else None,
                "lastTs": p.get("lastTs"),
                "tier": c["tier"],
            })
            slot["total"] = round(sum(b["cost"] for b in slot["backers"]), 2)
            tags = []
            for b in slot["backers"]:
                if b["tier"] not in tags:
                    tags.append(b["tier"])
            slot["tags"] = tags

    games = []
    dropped = []
    for gid in order:
        g = by[gid]
        picks = list(g["picks"].values())
        # Re-check finished on the grouped game
        if g["startTs"] and g["startTs"] <= now:
            info = {
                "status": picks[0].get("status"),
                "result": picks[0].get("result"),
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
            p.pop("status", None)
            p.pop("result", None)
            p.pop("closeTs", None)
            p.pop("yesAsk", None)
            p.pop("noAsk", None)
        g["picks"] = picks
        games.append(g)

    # soonest first, live first (PE N/A)
    games.sort(key=lambda g: (0 if g["live"] else 1, g["startTs"] or 10**12, g["id"]))
    cov["finishedDropped"] = len(dropped)
    cov["finishedNames"] = dropped
    cov["shown"] = sum(1 for c in cappers if c["picks"])
    cov["picks"] = sum(len(g["picks"]) for g in games)
    cov["games"] = len(games)
    cov["calls"] = http.calls
    cov["retries429"] = http.retries_429
    cov["secs"] = round(time.time() - t0, 1)
    if dropped:
        log("finished games removed: %d: %s" % (len(dropped), "; ".join(dropped[:12])))

    # Drop pick lists off capper rows in the published file (they're on games); keep a count.
    pub_cappers = []
    for c in cappers:
        pub_cappers.append({k: v for k, v in c.items() if k != "picks"} | {"pickCount": len(c["picks"])})
    # Sort cappers: Core, then Top 50, then by win rate then wins, then PnL
    def cap_key(c):
        tier_n = 0 if c["tier"] == "Core" else 1 if c["tier"] == "Top 50" else 2
        g = c.get("graded") or {"w": 0, "l": 0, "n": 0}
        n = (g.get("w") or 0) + (g.get("l") or 0)
        wr = (g.get("w") or 0) / n if n else -1
        sample = 0 if n >= 10 else 1
        return (tier_n, sample, -wr, -(g.get("w") or 0), -(c.get("pnl") or 0))
    pub_cappers.sort(key=cap_key)

    payload = {
        "scannedAt": pt(now),
        "ts": now,
        "source": {
            "note": "Kalshi Sports leaderboard (projected PnL). Kalshi has no 30-day period; monthly is the closest stand-in. Primary pool is all-time top 50 ∩/∪ monthly top 50. Most top traders hide their book; visible traders from all-time/monthly top 100 and weekly top 50 are included so the board is not empty. Positions and W-L come only from public profiles and the public trade tape.",
            "periodUsed": "monthly (no 30-day board exists)",
            "coverage": cov,
        },
        "cappers": pub_cappers,
        "games": games,
    }
    log("scan visible {visible} hidden {hidden} mm {mmDropped} shown {shown} picks {picks} games {games} finished {finishedDropped} calls {calls} 429s {retries429} secs {secs}".format(**cov))
    return payload


def main():
    data = build()
    out = os.path.join(ROOT, "data.json")
    json.dump(data, open(out, "w"), indent=2)
    print("wrote", out, "games", len(data["games"]), "cappers", len(data["cappers"]))


if __name__ == "__main__":
    main()
