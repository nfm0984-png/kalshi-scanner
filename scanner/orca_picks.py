"""Pull OrcaLayer-lens Polymarket sports bets, map them to Kalshi, merge into Ranked.

$500+ singles, sports-only, next-24-hours + already-started. Flipper / tiny /
exits-early wallets are skipped. Per-lens W-L/ROI lives in data/orca_lens_records.json
and starts weighting Ranked once a lens has ~20 graded picks.
"""
import json, os, re, time, urllib.parse, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(ROOT, "data")
REC_PATH = os.path.join(DATA_DIR, "orca_lens_records.json")
DATA_API = "https://data-api.polymarket.com/v2"
MIN_BET = 500
MAX_ENTRY = 0.90
WINDOW_SECS = 24 * 3600
MIN_LENS_N = 20
SLUG_RE = re.compile(r"^([a-z][a-z0-9]{1,11})-(.+?)-(20\d\d-\d\d-\d\d)(?:-(.*))?$")
NOT_SPORT = {
    "will", "what", "who", "how", "when", "which", "us", "fed", "btc", "eth", "sol", "xrp",
    "bitcoin", "ethereum", "trump", "election", "presidential", "highest", "lowest", "nyc",
    "new", "largest", "top", "elon", "tweets", "bank", "doge",
}


def _get_json(url, tries=3, timeout=25):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kalshi-scanner-orca/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(float(e.headers.get("Retry-After") or 2) + i)
                continue
            if e.code >= 500:
                time.sleep(1 + i)
                continue
            return None
        except Exception:
            time.sleep(1 + i)
    return None


def _pages(params, max_pages=4):
    out, cur = [], None
    for _ in range(max_pages):
        p = dict(params)
        if cur:
            p["cursor"] = cur
        d = _get_json(DATA_API + "/positions?" + urllib.parse.urlencode(p))
        if not d or "data" not in d:
            return out, False
        out += d["data"]
        pg = d.get("pagination") or {}
        cur = pg.get("next_cursor")
        if not pg.get("has_more") or not cur:
            return out, True
    return out, True


def open_positions(wallet):
    xs, ok = _pages({"user": wallet, "status": "OPEN", "limit": 500}, max_pages=4)
    return xs if ok or xs else None


def _load_rec():
    try:
        d = json.load(open(REC_PATH))
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    return {"updatedTs": 0, "minN": MIN_LENS_N, "lenses": {}, "picks": {}}


def _save_rec(d):
    os.makedirs(DATA_DIR, exist_ok=True)
    json.dump(d, open(REC_PATH, "w"), indent=2)
    open(REC_PATH, "a").write("\n")


def _boost_of(row):
    n = row.get("n") or 0
    if n < MIN_LENS_N:
        return 0.0
    roi = row.get("roi")
    if roi is None:
        return 0.0
    # roi is units/n * 100 (flat $1). A +20% lens gets +0.025; cap ±5c on hit chance.
    return max(-0.05, min(0.05, (float(roi) / 100.0) * 0.25 * min(1.0, n / 40.0)))


def lens_boost(lids, rec=None):
    rec = rec or _load_rec()
    lenses = rec.get("lenses") or {}
    xs = []
    for lid in lids or []:
        row = lenses.get(lid)
        if not row:
            continue
        b = _boost_of(row)
        if (row.get("n") or 0) >= MIN_LENS_N:
            xs.append(b)
    if not xs:
        return 0.0
    return round(sum(xs) / len(xs), 4)


def _empty_lens_row(label):
    return {"label": label, "n": 0, "w": 0, "l": 0, "units": 0.0, "roi": None, "boost": 0.0}


def update_records(games, now, log=print):
    """Record open Orca-backed picks and grade them from scanner_record.json."""
    import orca_lenses as ol
    rec = _load_rec()
    picks = rec.setdefault("picks", {})
    lenses = rec.setdefault("lenses", {})
    for lid, label, _per, _ex in ol.LENS_DEFS:
        lenses.setdefault(lid, _empty_lens_row(label))
        lenses[lid]["label"] = label

    added = 0
    for g in games or []:
        for p in g.get("picks") or []:
            st = p.get("startTs") or g.get("startTs") or 0
            view = p.get("view") or {}
            px = view.get("price")
            side = view.get("yesNo") or (p.get("key") or "|").split("|")[-1]
            for b in p.get("backers") or []:
                if not b.get("orca"):
                    continue
                if (b.get("cost") or 0) < MIN_BET or not b.get("name"):
                    continue
                rid = "%s|%s" % ((b.get("name") or ""), p.get("key") or "")
                if rid in picks:
                    # keep lenses updated if we learn more
                    have = list(picks[rid].get("lenses") or [])
                    for lid in b.get("lenses") or []:
                        if lid not in have:
                            have.append(lid)
                    picks[rid]["lenses"] = have
                    continue
                if not st or st <= now:
                    continue  # same rule as the scanner record: pre-game only
                price = px if isinstance(px, (int, float)) and 0 < px < 1 else b.get("avg")
                picks[rid] = {
                    "capper": b.get("name"),
                    "ticker": p.get("ticker"),
                    "side": side,
                    "price": price,
                    "startTs": st,
                    "firstTs": now,
                    "lenses": list(b.get("lenses") or []),
                    "status": "open",
                }
                added += 1

    # Copy grades from the existing auto-grader ledger when present.
    try:
        import scan as S
        led = S.load_json(S.SCANNER_REC_PATH, {"picks": {}})
        by = led.get("picks") or {}
    except Exception:
        by = {}
    graded = 0
    for rid, row in list(picks.items()):
        if row.get("status") in ("win", "loss", "push"):
            continue
        # scanner_record keys are nick|ticker|side
        nick = (row.get("capper") or "")
        key = "%s|%s" % (nick, (row.get("ticker") or "") + "|" + (row.get("side") or ""))
        alt = None
        for k, v in by.items():
            if (v.get("capper") or "") == nick and (v.get("ticker") or "") == (row.get("ticker") or "") and str(v.get("side") or "") == str(row.get("side") or ""):
                alt = v
                break
        src = by.get(key) or by.get(rid) or alt
        if src and src.get("status") in ("win", "loss", "push"):
            row["status"] = src["status"]
            row["gradedTs"] = src.get("gradedTs") or now
            if src.get("price"):
                row["price"] = src["price"]
            graded += 1

    # Recompute per-lens tallies (flat $1 at first shown price).
    for lid in list(lenses):
        lenses[lid].update(_empty_lens_row(lenses[lid].get("label") or lid))
    for row in picks.values():
        if row.get("status") not in ("win", "loss"):
            continue
        px = row.get("price") or 0
        if row["status"] == "win":
            units = (1.0 / px - 1.0) if 0 < px < 1 else 0.0
            w, l = 1, 0
        else:
            units, w, l = -1.0, 0, 1
        for lid in row.get("lenses") or []:
            s = lenses.setdefault(lid, _empty_lens_row(lid))
            s["n"] += 1
            s["w"] += w
            s["l"] += l
            s["units"] += units
    for s in lenses.values():
        s["units"] = round(s["units"], 2)
        s["roi"] = round(100.0 * s["units"] / s["n"], 1) if s["n"] else None
        s["boost"] = _boost_of(s)

    rec["updatedTs"] = now
    rec["minN"] = MIN_LENS_N
    rec["missing"] = (ol.state().get("missing") or [])
    _save_rec(rec)
    log("orca lens records: +%d new, graded %d, lenses %d" % (added, graded, len(lenses)))
    return rec


def attach_boosts(games, rec=None):
    rec = rec or _load_rec()
    for g in games or []:
        for p in g.get("picks") or []:
            lids = []
            for b in p.get("backers") or []:
                if b.get("orca"):
                    for lid in b.get("lenses") or []:
                        if lid not in lids:
                            lids.append(lid)
            if lids:
                p["orca"] = True
                p["orcaLenses"] = lids
                p["orcaBoost"] = lens_boost(lids, rec)
            elif "orcaBoost" not in p and any(b.get("orca") for b in (p.get("backers") or [])):
                p["orca"] = True
                p["orcaBoost"] = 0.0
    return games


def _extract_prev(prev):
    rows = []
    for g in (prev or {}).get("games") or []:
        for p in g.get("picks") or []:
            orca_bs = [b for b in (p.get("backers") or []) if b.get("orca")]
            if not orca_bs:
                continue
            rows.append(dict(game=g, pick=p, backers=orca_bs))
    return rows


def _hydrate(http, ticker, mcache, ecache):
    try:
        import lib_cappers as lib
        return lib.hydrate_market(http, ticker, mcache, ecache) or {}
    except Exception:
        return {}


def _is_sports(info, ticker):
    try:
        import lib_cappers as lib
        return lib.is_sports_market(info, ticker)
    except Exception:
        return not str(ticker or "").upper().startswith(("KXBTC", "KXETH", "KXSPX", "KXFED", "KXPRES"))


def _collect_fresh(http, now, mcache, ecache, log=print):
    import orca_lenses as ol
    import poly_kalshi as pk
    import scan as S
    import lib_cappers as lib

    st = ol.refresh(log=log)
    sources = ol.source_wallets()
    if not sources:
        log("orca picks: no source wallets (missing=%s)" % ",".join(st.get("missing") or []))
        return [], {"wallets": 0, "positions": 0, "mapped": 0, "added": 0, "missing": st.get("missing") or []}

    wallets = list(sources)
    pos_map, failed = {}, 0
    workers = min(12, max(2, len(wallets)))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(open_positions, w): w for w in wallets}
        for fut in as_completed(futs):
            w = futs[fut]
            try:
                pos_map[w] = fut.result() or []
            except Exception:
                pos_map[w] = []
                failed += 1
    npos = sum(len(v) for v in pos_map.values())
    log("orca positions: %d wallets, %d open rows, %d failed, %.0fs" % (len(wallets), npos, failed, time.time() - t0))

    # Dedup by wallet+condition: keep the larger side if both YES and NO are held.
    by_wallet = {}
    names = dict(st.get("names") or {})
    for w, ps in pos_map.items():
        sides = {}
        for x in ps or []:
            slug = x.get("slug") or x.get("event_slug") or ""
            if not SLUG_RE.match(slug) and not SLUG_RE.match(x.get("event_slug") or ""):
                # still try event_slug as sports check
                ev = x.get("event_slug") or slug
                mm = SLUG_RE.match(ev)
                if not mm or mm.group(1) in NOT_SPORT:
                    continue
                slug = slug or ev
            mm = SLUG_RE.match(slug) or SLUG_RE.match(x.get("event_slug") or "")
            if not mm or mm.group(1) in NOT_SPORT:
                continue
            try:
                avg = float(x.get("avg_price") or x.get("avg_entry") or 0)
                size = float(x.get("current_size") or x.get("tokens") or 0)
            except (TypeError, ValueError):
                continue
            cost = avg * size
            if cost < MIN_BET:
                # also accept initial_value / buy_cost from Orca-shaped payloads
                try:
                    cost = float(x.get("initial_value") or x.get("buy_cost") or cost)
                except (TypeError, ValueError):
                    pass
            if cost < MIN_BET:
                continue
            try:
                cp = x.get("current_price")
                cp = float(cp) if cp is not None else None
            except (TypeError, ValueError):
                cp = None
            if cp is not None and (cp >= 0.99 or cp <= 0.01):
                continue
            if avg >= MAX_ENTRY:
                continue
            oi = x.get("outcome_index")
            if oi is None:
                side_raw = (x.get("side") or "")
                oi = 0 if side_raw in ("token1", "yes", "YES") else 1
            try:
                oi = int(oi)
            except (TypeError, ValueError):
                oi = 0
            cid = (x.get("condition_id") or slug).lower()
            row = dict(slug=slug, question=x.get("title") or x.get("question") or "", cost=cost,
                       avg=avg, cp=cp, oi=oi, x=x)
            prev = sides.get(cid)
            if prev is None or row["cost"] > prev["cost"]:
                sides[cid] = row
        # drop hedges (both sides)
        # already kept only the larger side
        by_wallet[w] = list(sides.values())
        for x in ps or []:
            n = (x.get("name") or "").strip()
            if n and not n.startswith("0x"):
                names[w] = n[:40]

    rows = []
    mapped = unmatched = skipped = 0
    seen_map = {}  # ticker|side|name
    for w, bets in by_wallet.items():
        lids = sources.get(w) or []
        cap_name = names.get(w) or (ol.name_of(w) or (w[:6] + "…" + w[-4:]))
        for b in bets:
            side = "yes" if b["oi"] == 0 else "no"
            kal = pk.map_bet(b["slug"], b["question"], side, avg_entry=b["avg"], price=b["cp"])
            if not kal or kal.get("status") != "ok" or not kal.get("ticker"):
                unmatched += 1
                continue
            mapped += 1
            tk = kal["ticker"]
            yes_no = "Yes" if (kal.get("action") or "").upper() == "BUY YES" else "No"
            info = _hydrate(http, tk, mcache, ecache)
            if not info:
                skipped += 1
                continue
            if not _is_sports(info, tk):
                skipped += 1
                continue
            league = info.get("league") or lib.league_of(tk, info.get("category")) or "Sports"
            start_ts = info.get("start_ts") or 0
            if not start_ts and kal.get("occ"):
                try:
                    start_ts = int(__import__("datetime").datetime.fromisoformat(str(kal["occ"]).replace("Z", "+00:00")).timestamp())
                except Exception:
                    start_ts = 0
            # 24h window + already started
            if start_ts and start_ts > now + WINDOW_SECS:
                skipped += 1
                continue
            if not start_ts:
                skipped += 1
                continue
            done, _why = S.game_finished(info, now, league)
            if done:
                skipped += 1
                continue
            state = "live" if start_ts <= now else "upcoming"
            ask = info.get("yes_ask") if yes_no == "Yes" else info.get("no_ask")
            entry = b["avg"] if b["avg"] else None
            if entry is not None and entry >= MAX_ENTRY:
                skipped += 1
                continue
            px = ask if ask is not None else (kal.get("price") if kal.get("price") else entry)
            slip = round((ask - entry) * 100, 1) if entry is not None and ask is not None else None
            backing = (info.get("yes_sub_title") if yes_no == "Yes" else info.get("no_sub_title")) or kal.get("contract") or info.get("title") or tk
            game = info.get("event_title") or kal.get("eventTitle") or kal.get("marketTitle") or info.get("title") or tk
            ev_tk = info.get("event_ticker") or ""
            label = backing
            key = tk + "|" + yes_no
            dup = "%s|%s" % (key, cap_name.lower())
            if dup in seen_map:
                continue
            seen_map[dup] = True
            last_ts = b["x"].get("last_event_at") or b["x"].get("last_trade_ts")
            try:
                last_ts = int(last_ts) if last_ts else None
            except (TypeError, ValueError):
                last_ts = None
            backer = {
                "name": cap_name,
                "cost": round(b["cost"], 2),
                "avg": round(entry, 4) if entry is not None else None,
                "line": cap_name + " · Orca",
                "rec": None,
                "sportRec": None,
                "bestAt": None,
                "pnl": None,
                "pinned": False,
                "lastTs": last_ts,
                "tier": "Orca",
                "orca": True,
                "lenses": list(lids),
                "lensLabels": ol.labels_of(lids),
                "wallet": w,
            }
            pick = {
                "key": key,
                "ticker": tk,
                "eventTicker": ev_tk,
                "mid": tk,
                "bt": S.bet_type(tk, backing or info.get("title") or ""),
                "big": label,
                "sub": game if label != game else (info.get("title") or ""),
                "view": {
                    "backing": backing,
                    "marketTitle": game,
                    "outcome": backing,
                    "yesNo": yes_no,
                    "price": round(px, 4) if px is not None else None,
                    "ticker": tk,
                },
                "backers": [backer],
                "total": round(b["cost"], 2),
                "tags": ["Orca"],
                "slip": slip,
                "startTs": start_ts,
                "state": state,
                "status": info.get("status"),
                "result": info.get("result"),
                "closeTs": info.get("close_ts") or 0,
                "yesAsk": info.get("yes_ask"),
                "noAsk": info.get("no_ask"),
                "orca": True,
                "game": game,
                "league": league,
            }
            rows.append(pick)
    log("orca map: %d matched, %d unmatched, %d skipped, %d pick rows" % (mapped, unmatched, skipped, len(rows)))
    return rows, {
        "wallets": len(wallets),
        "positions": npos,
        "mapped": mapped,
        "unmatched": unmatched,
        "skipped": skipped,
        "added": len(rows),
        "failedPositions": failed,
        "missing": st.get("missing") or [],
        "reachable": bool(st.get("reachable")),
    }


def _merge_rows(games, picks, now, log=print):
    import scan as S
    by_id = {g.get("id"): g for g in games or []}
    order = [g.get("id") for g in (games or [])]
    added_picks = added_backers = new_games = 0
    for p in picks or []:
        start_ts = p.get("startTs") or 0
        if start_ts and start_ts > now + WINDOW_SECS:
            continue
        gid = p.get("eventTicker") or ((p.get("game") or "") + "|" + str(start_ts or 0))
        if gid not in by_id:
            by_id[gid] = {
                "id": gid,
                "game": p.get("game") or p.get("big") or gid,
                "league": p.get("league") or "Sports",
                "startTs": start_ts or 0,
                "start": S.pt(start_ts) if start_ts else "",
                "live": bool(start_ts and start_ts <= now),
                "state": "live" if (start_ts and start_ts <= now) else "upcoming",
                "picks": [],
            }
            order.append(gid)
            new_games += 1
        g = by_id[gid]
        if start_ts and (not g.get("startTs") or start_ts < g["startTs"]):
            g["startTs"] = start_ts
            g["start"] = S.pt(start_ts)
        if start_ts and start_ts <= now:
            g["live"] = True
            g["state"] = "live"
        key = p.get("key") or (p.get("ticker") + "|" + ((p.get("view") or {}).get("yesNo") or ""))
        slot = None
        for existing in g.get("picks") or []:
            if existing.get("key") == key:
                slot = existing
                break
        if slot is None:
            slot = {k: v for k, v in p.items() if k not in ("backers", "game", "league")}
            slot["backers"] = []
            slot["key"] = key
            slot.setdefault("tags", [])
            if "Orca" not in slot["tags"]:
                slot["tags"] = list(slot["tags"]) + ["Orca"]
            g.setdefault("picks", []).append(slot)
            added_picks += 1
        else:
            if "Orca" not in (slot.get("tags") or []):
                slot["tags"] = list(slot.get("tags") or []) + ["Orca"]
            # keep existing view/price; just add backers
        have = {(b.get("name") or "").lower() for b in (slot.get("backers") or [])}
        for b in p.get("backers") or []:
            nm = (b.get("name") or "").lower()
            if not nm or nm in have:
                # if already present (same Kalshi capper name), stamp orca lenses onto them
                for ex in slot.get("backers") or []:
                    if (ex.get("name") or "").lower() == nm:
                        ex["orca"] = True if b.get("orca") else ex.get("orca")
                        lids = list(ex.get("lenses") or [])
                        for lid in b.get("lenses") or []:
                            if lid not in lids:
                                lids.append(lid)
                        if lids:
                            ex["lenses"] = lids
                            ex["lensLabels"] = b.get("lensLabels") or ex.get("lensLabels")
                continue
            slot.setdefault("backers", []).append(b)
            have.add(nm)
            added_backers += 1
        slot["backers"] = [b for b in (slot.get("backers") or []) if (b.get("cost") or 0) >= (S.MIN_COMBO_BET if slot.get("isCombo") else MIN_BET)]
        if not slot["backers"]:
            g["picks"] = [x for x in g["picks"] if x is not slot]
            continue
        slot["backers"].sort(key=lambda b: -(b.get("cost") or 0))
        slot["total"] = round(sum(b.get("cost") or 0 for b in slot["backers"]), 2)
        if p.get("orca"):
            slot["orca"] = True
    games_out = []
    for gid in order:
        g = by_id.get(gid)
        if g and g.get("picks"):
            games_out.append(g)
    log("orca merge: +%d new pick slots, +%d backers, +%d games" % (added_picks, added_backers, new_games))
    return games_out, added_picks, added_backers


def merge(games, http, now, mcache, ecache, prev=None, refresh=True, log=print):
    """Merge Orca-mapped picks into games[]. Never raises out to the caller."""
    stats = {"added": 0, "backers": 0, "wallets": 0, "mapped": 0, "missing": [], "refresh": bool(refresh)}
    try:
        if refresh:
            picks, st = _collect_fresh(http, now, mcache, ecache, log)
            stats.update(st)
        else:
            prev_rows = _extract_prev(prev)
            picks = []
            for row in prev_rows:
                p = dict(row["pick"])
                p["backers"] = list(row["backers"])
                p["orca"] = True
                p["game"] = row["game"].get("game") or p.get("big")
                p["league"] = row["game"].get("league") or p.get("league") or "Sports"
                # drop finished / out of window
                start_ts = p.get("startTs") or row["game"].get("startTs") or 0
                p["startTs"] = start_ts
                if start_ts and start_ts > now + WINDOW_SECS:
                    continue
                picks.append(p)
            stats["added"] = len(picks)
            log("orca picks: carried %d from previous scan" % len(picks))
        games, n_picks, n_backers = _merge_rows(games, picks, now, log)
        rec = update_records(games, now, log)
        attach_boosts(games, rec)
        stats["added"] = n_picks
        stats["backers"] = n_backers
        stats["rankPicks"] = sum(1 for g in games for p in (g.get("picks") or []) if p.get("orca") or any(b.get("orca") for b in (p.get("backers") or [])))
        return games, stats
    except Exception as e:
        log("orca picks failed: %s" % e)
        stats["error"] = type(e).__name__
        return games, stats
