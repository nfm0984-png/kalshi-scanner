"""OrcaLayer /api/leaderboard lenses for the Kalshi scanner (Noel, Nov 24).

Pulls Proven only, Smart only, Copyable scale + Sports, Niche specialist + Sports,
Under the radar, and supported Style/Habit boards, over 7d / 30d (and All Time
for the core presets). Flippers, tiny-size, and early-exit wallets are skip lists.

Cache: scanner/orca_lenses.json (gitignored). Fresh when older than 3 hours.
Never logs or writes the API key.
"""
import json, os, time

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, 'orca_lenses.json')
TTL = 3 * 3600
LIMIT = 100

# id -> (label, period, extra API params). category Sports is always applied.
# Under the radar turns Smart off (filter=all), matching orcalayer.com.
LENS_DEFS = []

def _add(lid, label, period, extra):
    LENS_DEFS.append((lid, label, period, extra))

for per, tag in (('7d', '7d'), ('30d', '30d'), ('All Time', 'All')):
    _add('smart|' + tag, 'Smart only · ' + tag, per, dict(filter='smart'))
    _add('proven|' + tag, 'Proven only · ' + tag, per, dict(filter='smart', skill='1'))
    _add('copyable|' + tag, 'Copyable scale + Sports · ' + tag, per,
         dict(filter='smart', min_avg_size='50', max_avg_size='500', min_roi='25'))
    _add('niche|' + tag, 'Niche specialist + Sports · ' + tag, per,
         dict(filter='smart', min_conc='70', max_active='20', min_wr='60'))
    _add('radar|' + tag, 'Under the radar · ' + tag, per,
         dict(filter='all', under_radar='1'))

for per, tag in (('7d', '7d'), ('30d', '30d')):
    _add('maker|' + tag, 'Style: Maker · ' + tag, per, dict(filter='smart', style='maker'))
    _add('holds|' + tag, 'Habit: Holds to resolution · ' + tag, per, dict(filter='smart', habit='holds'))
    _add('favorites|' + tag, 'Habit: Buys favorites · ' + tag, per, dict(filter='smart', habit='favorites'))

# Skip lists (not used as pick sources).
SKIP_DEFS = [
    ('flipper', 'Holds <1h', 'All Time', dict(filter='smart', hold_bucket='lt1h')),
    ('tiny', 'Avg bet under $25', 'All Time', dict(filter='smart', max_avg_size='25')),
    ('exits', 'Habit: Exits early', 'All Time', dict(filter='smart', habit='exits')),
]

SOURCE_IDS = [x[0] for x in LENS_DEFS]
SKIP_IDS = [x[0] for x in SKIP_DEFS]
ALL_DEFS = LENS_DEFS + SKIP_DEFS

BASE = dict(sort='total_pnl', sort_dir='desc', page=1, hide_farmers='true', hide_bots='true',
            hide_sports='false', hide_crypto='false', min_markets='10', limit=str(LIMIT),
            category='Sports')

_STATE = None


def _empty():
    out = dict(ts=0, reachable=True, missing=[], names={}, wallets={})
    for lid, _label, _per, _ex in ALL_DEFS:
        out[lid] = []
    return out


def _load_cache():
    try:
        d = json.load(open(CACHE))
        if isinstance(d, dict) and isinstance(d.get('wallets'), dict):
            return d
    except Exception:
        pass
    return None


def _wallets_and_names(rows):
    out, seen, names = [], set(), {}
    for r in rows or []:
        w = (r.get('wallet') or '').lower()
        if not w or w in seen:
            continue
        seen.add(w)
        out.append(w)
        n = (r.get('display_name') or r.get('name') or '').strip()
        if n and not n.startswith('0x'):
            names[w] = n[:40]
    return out, names


def _fetch(lid, period, extra):
    from orca import orca
    params = dict(BASE)
    params['period'] = period
    params.update(extra)
    d = orca('/api/leaderboard', params, tries=2, timeout=45)
    if not d or not isinstance(d, dict) or 'traders' not in d:
        return None
    return _wallets_and_names(d.get('traders'))


def refresh(force=False, log=print):
    """Fetch (or reuse cached) lens membership. Safe to call from a scan."""
    global _STATE
    cached = _load_cache()
    if not force and cached and (time.time() - (cached.get('ts') or 0)) < TTL:
        _STATE = cached
        return cached
    from orca import has_key
    if not has_key():
        if cached:
            cached = dict(cached)
            cached['missing'] = list(cached.get('missing') or []) + ['no-api-key']
            cached['reachable'] = False
            _STATE = cached
            log('orca lenses: no API key, keeping cache')
            return cached
        out = _empty()
        out['missing'] = ['no-api-key']
        out['reachable'] = False
        _STATE = out
        log('orca lenses: no API key, skipping')
        return out
    out = _empty()
    out['ts'] = int(time.time())
    missing = []
    names = dict((cached or {}).get('names') or {})
    for lid, label, period, extra in ALL_DEFS:
        rows = None
        try:
            rows = _fetch(lid, period, extra)
        except Exception as e:
            missing.append('%s:%s' % (lid, type(e).__name__))
            rows = None
        if rows is None:
            missing.append(lid)
            if cached and cached.get(lid):
                out[lid] = list(cached[lid])
            else:
                out[lid] = []
        else:
            wallets, got_names = rows
            out[lid] = wallets
            names.update(got_names)
    if missing and cached and len(missing) >= len(ALL_DEFS):
        cached = dict(cached)
        cached['missing'] = missing
        cached['reachable'] = False
        _STATE = cached
        log('orca lenses: all fetches failed, keeping cache (%s)' % ','.join(missing[:8]))
        return cached
    # wallet -> list of source lens ids
    wallets = {}
    for lid, _label, _per, _ex in LENS_DEFS:
        for w in out.get(lid) or []:
            wallets.setdefault(w, [])
            if lid not in wallets[w]:
                wallets[w].append(lid)
    out['names'] = names
    out['wallets'] = wallets
    out['missing'] = missing
    out['reachable'] = not missing
    try:
        json.dump(out, open(CACHE, 'w'), separators=(',', ':'))
    except Exception:
        pass
    _STATE = out
    bits = []
    for lid, label, _per, _ex in LENS_DEFS + SKIP_DEFS:
        bits.append('%s %d' % (lid, len(out.get(lid) or [])))
    log('orca lenses: %s%s' % (', '.join(bits),
                               (' (missing: ' + ','.join(missing) + ')' if missing else '')))
    return out


def state():
    global _STATE
    if _STATE is None:
        _STATE = _load_cache() or _empty()
    return _STATE


def labels_of(lids):
    lab = {x[0]: x[1] for x in ALL_DEFS}
    return [lab[i] for i in (lids or []) if i in lab]


def skip(wallet):
    w = (wallet or '').lower()
    s = state()
    if not w:
        return False
    for lid in SKIP_IDS:
        if w in (s.get(lid) or []):
            return True
    return False


def source_wallets():
    """Wallets that appear on at least one source lens and are not skip-listed."""
    s = state()
    out = {}
    for w, lids in (s.get('wallets') or {}).items():
        if skip(w):
            continue
        out[w] = list(lids)
    return out


def name_of(wallet):
    w = (wallet or '').lower()
    return (state().get('names') or {}).get(w) or ''


def payload():
    s = state()
    compact = {lid: s.get(lid) or [] for lid, _l, _p, _e in ALL_DEFS}
    compact.update(ts=s.get('ts') or 0, missing=s.get('missing') or [], reachable=bool(s.get('reachable')))
    return compact
