"""Polymarket slug -> Kalshi market mapper, extracted from the whale scanner (scan.py).

Includes the Nov 24 spread fix: a Polymarket YES on a dog (e.g. Real Madrid +1.5)
maps to BUY NO on the favorite winning by more than the line. Do not "simplify"
that invert. This module is side-effect free on import (no network).
"""
import json, re, time, urllib.request, datetime as dt

try:
    import kalshi_names as _knames
except ImportError:
    from scanner import kalshi_names as _knames  # type: ignore

ESPORTS = ('cs2', 'dota2', 'lol', 'val', 'r6siege', 'rl', 'cod', 'ow', 'mlbb', 'hok', 'kog', 'sc2', 'apex', 'pubg', 'fortnite')

def pub(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'orca-scanner/1.0'}), timeout=30) as r: return json.load(r)
        except Exception: time.sleep(2 * (i + 1))
    return None

def parse(m):
    slug, q = m['slug'], m['question']
    mm = re.match(r'([a-z0-9]+)-(.+?)-(20\d\d-\d\d-\d\d)(?:-(.*))?$', slug)
    league, mid, date, tail = mm.group(1), mm.group(2), mm.group(3), (mm.group(4) or '')
    codes = mid.split('-')
    info = dict(league=league, codes=codes, date=date, tail=tail, kind='other')
    _parts = [re.sub(r'^[^:]*:\s*', '', q), re.sub(r':.*$', '', q)] if league in ESPORTS else [re.sub(r':.*$', '', q), re.sub(r'^[^:]*:\s*', '', q)]
    base = next((p_ for p_ in _parts if re.search(r'\svs\.?\s', p_)), _parts[0])
    base = re.sub(r'\s*\(BO\d\).*$|\s+-\s+.*$', '', base)
    teams = [t.strip() for t in re.split(r'\s+vs\.?\s+', base)] if ' vs' in base else []
    info['teams'] = teams
    tm_ = re.fullmatch(r'total-(\d+(?:pt\d+)?)', tail)
    if tm_:
        info.update(kind='total', line=float(tm_.group(1).replace('pt', '.')), yes='OVER', no='UNDER')
    elif tail.startswith('total'):
        pass
    elif re.fullmatch(r'spread-(home|away)-\d+(pt\d+)?', tail):
        sm = re.match(r'Spread:\s*(.+?)\s*\(([+-]?[\d.]+)\)', q)
        side = 'home' if 'home' in tail else 'away'
        # slug spread-home / spread-away names the team the Polymarket line is about (codes[0] = home).
        named_code = codes[0] if side == 'home' or len(codes) < 2 else codes[1]
        other_code = codes[1] if named_code == codes[0] and len(codes) > 1 else (codes[0] if len(codes) else named_code)
        named = sm.group(1) if sm else '?'
        raw_line = float(sm.group(2)) if sm else None
        line = abs(raw_line) if raw_line is not None else None
        named_is_fav = True if raw_line is None or raw_line <= 0 else False
        fav = named if named_is_fav else None
        favcode = named_code if named_is_fav else other_code
        dogcode = other_code if named_is_fav else named_code
        if named_is_fav:
            yes = f"{named} -{line:g}" if line is not None else named
            no = f"{named} +{line:g} or better for the other side" if line is not None else named
        else:
            yes = f"{named} +{line:g}" if line is not None else named
            no = f"{named} -{line:g} or better for the other side" if line is not None else named
        info.update(kind='spread', line=line, fav=fav or named, favcode=favcode, dogcode=dogcode,
                    named=named, named_code=named_code, named_is_fav=named_is_fav, yes=yes, no=no)
    elif tail == '' and len(teams) == 2:
        info.update(kind='moneyline', yes=teams[0], no=teams[1])
    elif league in ESPORTS and re.fullmatch(r'game(\d+)', tail) and len(teams) == 2 and re.search(r'(?i)\b(map|game)\s*\d+\s*winner', q):
        info.update(kind='map', mapno=int(tail[4:]), yes=teams[0], no=teams[1])  # Map N winner: Kalshi lists these as KX<GAME>MAP series
    elif tail == 'draw':
        info.update(kind='draw', yes='DRAW', no='NO DRAW')
    elif re.fullmatch(r'[a-z0-9]+', tail or '') and q.lower().startswith('will '):
        tm = re.match(r'Will (.+?) win', q); info.update(kind='teamwin', team=tm.group(1) if tm else tail, code=tail,
                                                          yes=(tm.group(1) if tm else tail) + ' WIN', no=(tm.group(1) if tm else tail) + ' NOT TO WIN')
    if info.get('kind') == 'other':
        prop = parse_prop(q, tail, teams)
        if prop:
            info.update(kind='prop', **prop)
    if 'yes' not in info and len(teams) == 2 and not q.lower().startswith('will '):
        info.update(yes=teams[0], no=teams[1])
    return info

KSER = {'nba': ('KXNBAGAME', 'KXNBATOTAL', 'KXNBASPREAD'), 'nfl': ('KXNFLGAME', 'KXNFLTOTAL', 'KXNFLSPREAD'),
        'nhl': ('KXNHLGAME', 'KXNHLTOTAL', 'KXNHLSPREAD'), 'cfb': ('KXNCAAFGAME', 'KXNCAAFTOTAL', 'KXNCAAFSPREAD'),
        'cbb': ('KXNCAAMBGAME', 'KXNCAAMBTOTAL', 'KXNCAAMBSPREAD'), 'cwbb': ('KXNCAAWBGAME', 'KXNCAAWBTOTAL', 'KXNCAAWBSPREAD'),
        'epl': ('KXEPLGAME', 'KXEPLTOTAL', 'KXEPLSPREAD'),
        'ucl': ('KXUCLGAME', 'KXUCLTOTAL', 'KXUCLSPREAD'), 'uel': ('KXUELGAME', 'KXUELTOTAL', 'KXUELSPREAD'), 'uecl': ('KXUECLGAME', 'KXUECLTOTAL', 'KXUECLSPREAD'),
        'lal': ('KXLALIGAGAME', 'KXLALIGATOTAL', 'KXLALIGASPREAD'),
        'unl': ('KXUEFANLGAME', 'KXUEFANLTOTAL', 'KXUEFANLSPREAD'), 'fif': ('KXFIFAGAME', 'KXFIFATOTAL', 'KXFIFASPREAD'), 'ifr': ('KXINTLFRIENDLYGAME', None, None),
        'cdr': ('KXCOPADELREYGAME', 'KXCOPADELREYTOTAL', 'KXCOPADELREYSPREAD'), 'uwcl': ('KXUCLWGAME', None, None),
        'bun': ('KXBUNDESLIGAGAME', 'KXBUNDESLIGATOTAL', 'KXBUNDESLIGASPREAD'), 'bl2': ('KXBUNDESLIGA2GAME', 'KXBUNDESLIGA2TOTAL', 'KXBUNDESLIGA2SPREAD'),
        'sea': ('KXSERIEAGAME', 'KXSERIEATOTAL', 'KXSERIEASPREAD'), 'itb': ('KXSERIEBGAME', 'KXSERIEBTOTAL', 'KXSERIEBSPREAD'),
        'fl1': ('KXLIGUE1GAME', 'KXLIGUE1TOTAL', 'KXLIGUE1SPREAD'), 'fl2': ('KXLIGUE2GAME', 'KXLIGUE2TOTAL', 'KXLIGUE2SPREAD'),
        'ere': ('KXEREDIVISIEGAME', 'KXEREDIVISIETOTAL', 'KXEREDIVISIESPREAD'), 'por': ('KXLIGAPORTUGALGAME', 'KXLIGAPORTUGALTOTAL', 'KXLIGAPORTUGALSPREAD'),
        'mex': ('KXLIGAMXGAME', 'KXLIGAMXTOTAL', 'KXLIGAMXSPREAD'), 'bra': ('KXBRASILEIROGAME', 'KXBRASILEIROTOTAL', 'KXBRASILEIROSPREAD'),
        'arg': ('KXARGPREMDIVGAME', 'KXARGPREMDIVTOTAL', 'KXARGPREMDIVSPREAD'), 'spl': ('KXSAUDIPLGAME', 'KXSAUDIPLTOTAL', 'KXSAUDIPLSPREAD'),
        'efl': ('KXEFLCHAMPIONSHIPGAME', 'KXEFLCHAMPIONSHIPTOTAL', 'KXEFLCHAMPIONSHIPSPREAD'), 'elc': ('KXEFLCHAMPIONSHIPGAME', 'KXEFLCHAMPIONSHIPTOTAL', 'KXEFLCHAMPIONSHIPSPREAD'),
        'efa': ('KXFACUPGAME', 'KXFACUPTOTAL', 'KXFACUPSPREAD'), 'facup': ('KXFACUPGAME', 'KXFACUPTOTAL', 'KXFACUPSPREAD'),
        'lcup': ('KXEFLCUPGAME', 'KXEFLCUPTOTAL', 'KXEFLCUPSPREAD'), 'tur': ('KXSUPERLIGGAME', 'KXSUPERLIGTOTAL', 'KXSUPERLIGSPREAD'),
        'sco': ('KXSCOTTISHPREMGAME', 'KXSCOTTISHPREMTOTAL', 'KXSCOTTISHPREMSPREAD'), 'bel': ('KXBELGIANPLGAME', 'KXBELGIANPLTOTAL', 'KXBELGIANPLSPREAD'),
        'den': ('KXDENSUPERLIGAGAME', 'KXDENSUPERLIGATOTAL', 'KXDENSUPERLIGASPREAD'), 'nor': ('KXELITESERIENGAME', 'KXELITESERIENTOTAL', 'KXELITESERIENSPREAD'),
        'swe': ('KXALLSVENSKANGAME', 'KXALLSVENSKANTOTAL', 'KXALLSVENSKANSPREAD'), 'jap': ('KXJLEAGUEGAME', 'KXJLEAGUETOTAL', 'KXJLEAGUESPREAD'),
        'kor': ('KXKLEAGUEGAME', 'KXKLEAGUETOTAL', 'KXKLEAGUESPREAD'), 'aus': ('KXALEAGUEGAME', 'KXALEAGUETOTAL', 'KXALEAGUESPREAD'),
        'lib': ('KXCONMEBOLLIBGAME', 'KXCONMEBOLLIBTOTAL', 'KXCONMEBOLLIBSPREAD'), 'sud': ('KXCONMEBOLSUDGAME', 'KXCONMEBOLSUDTOTAL', 'KXCONMEBOLSUDSPREAD'),
        'cof': ('KXCOUPEDEFRANCEGAME', 'KXCOUPEDEFRANCETOTAL', 'KXCOUPEDEFRANCESPREAD'), 'dfb': ('KXDFBPOKALGAME', 'KXDFBPOKALTOTAL', 'KXDFBPOKALSPREAD'),
        'itc': ('KXCOPPAITALIAGAME', 'KXCOPPAITALIATOTAL', 'KXCOPPAITALIASPREAD'), 'nwsl': ('KXNWSLGAME', 'KXNWSLTOTAL', 'KXNWSLSPREAD'),
        'mls': ('KXMLSGAME', 'KXMLSTOTAL', 'KXMLSSPREAD'), 'wnba': ('KXWNBAGAME', 'KXWNBATOTAL', 'KXWNBASPREAD'), 'mlb': ('KXMLBGAME', 'KXMLBTOTAL', 'KXMLBSPREAD'),
        'kbo': ('KXKBOGAME', 'KXKBOTOTAL', 'KXKBOSPREAD'), 'npb': ('KXNPBGAME', 'KXNPBTOTAL', 'KXNPBSPREAD'), 'khl': ('KXKHLGAME', None, None), 'shl': ('KXSHLGAME', None, None), 'ahl': ('KXAHLGAME', None, None),
        'euroleague': ('KXEUROLEAGUEGAME', 'KXEUROLEAGUETOTAL', 'KXEUROLEAGUESPREAD'), 'euro': ('KXEUROLEAGUEGAME', 'KXEUROLEAGUETOTAL', 'KXEUROLEAGUESPREAD'),
        'acb': ('KXACBGAME', 'KXACBTOTAL', 'KXACBSPREAD'), 'nbl': ('KXNBLGAME', 'KXNBLTOTAL', 'KXNBLSPREAD'), 'cba': ('KXCBAGAME', 'KXCBATOTAL', 'KXCBASPREAD'),
        'atp': ('KXATPMATCH', None, None), 'wta': ('KXWTAMATCH', None, None), 'ufc': ('KXUFCFIGHT', None, None), 'mma': ('KXMMAFIGHT', None, None), 'box': ('KXBOXINGFIGHT', None, None),
        'cs2': ('KXCS2GAME', None, None), 'dota2': ('KXDOTA2GAME', None, None), 'lol': ('KXLOLGAME', None, None), 'val': ('KXVALORANTGAME', None, None),
        'r6siege': ('KXR6GAME', None, None), 'cod': ('KXCODGAME', None, None), 'ow': ('KXOWGAME', None, None), 'rl': ('KXROCKETLEAGUEGAME', None, None),
        'cricipl': ('KXIPLGAME', None, None), 'afl': ('KXAFLGAME', None, None), 'cfl': ('KXCFLGAME', 'KXCFLTOTAL', 'KXCFLSPREAD'), 'nrl': ('KXRUGBYNRLMATCH', None, None),
        # golf / racing / darts: verified series (open or real past tickers). Player/driver markets use NAME_ONLY.
        'pga': ('KXGOLFTOURN', None, None), 'golf': ('KXGOLFTOURN', None, None), 'lpga': ('KXLPGATOUR', None, None),
        'f1': ('KXF1H2H', None, None), 'nascar': ('KXNASCARRACE', None, None), 'indycar': ('KXINDYCARRACE', None, None), 'indy': ('KXINDYCARRACE', None, None),
        'darts': ('KXDARTSMATCH', None, None), 'motogp': ('KXMOTOGPRACE', None, None),
        # Nov 15: non-US leagues whales bet that Kalshi lists (Polymarket slug prefix -> Kalshi series)
        'itf': ('KXITFMATCH', None, None), 'es2': ('KXLALIGA2GAME', 'KXLALIGA2TOTAL', 'KXLALIGA2SPREAD'),
        'conl': ('KXCONCACAFNLGAME', None, None), 'el1': ('KXEFLL1GAME', None, None), 'el2': ('KXEFLL2GAME', None, None),
        'per1': ('KXPERLIGA1GAME', None, None), 'uru1': ('KXURYPDGAME', None, None), 'ecu1': ('KXECULPGAME', None, None), 'bol1': ('KXBOLPDIVGAME', None, None),
        'argpn': ('KXARGNACBGAME', None, None), 'ja2': ('KXJ2LEAGUEGAME', None, None), 'ja3': ('KXJ3LEAGUEGAME', None, None),
        'chi': ('KXCHNSLGAME', None, None), 'chi1': ('KXCHNL1GAME', None, None), 'afcq': ('KXAFCONGAME', None, None),
        'hr1': ('KXHNLGAME', None, None), 'lva1': ('KXLVAVIRGAME', None, None), 'ned2': ('KXEERSTEDIVGAME', None, None), 'uslc': ('KXUSLGAME', None, None),
        'liiga': ('KXLIIGAGAME', None, None),
        'bkjpn': ('KXJBLEAGUEGAME', None, None), 'bkkbl': ('KXKBLGAME', 'KXKBLTOTAL', 'KXKBLSPREAD'), 'bknbl': ('KXNBLGAME', 'KXNBLTOTAL', 'KXNBLSPREAD'),
        'bkbbl': ('KXBBLGAME', None, None), 'bkbsl': ('KXBSLGAME', 'KXBSLTOTAL', 'KXBSLSPREAD'), 'bkaba': ('KXABAGAME', 'KXABATOTAL', 'KXABASPREAD'),
        'bkfr1': ('KXLNBELITEGAME', 'KXLNBELITETOTAL', 'KXLNBELITESPREAD'), 'bkarg': ('KXARGLNBGAME', None, None), 'bknbb': ('KXNBBGAME', None, None),
        'bkligend': ('KXACBGAME', 'KXACBTOTAL', 'KXACBSPREAD'), 'bkcba': ('KXCBAGAME', 'KXCBATOTAL', 'KXCBASPREAD'), 'bkvtb': ('KXVTBGAME', 'KXVTBTOTAL', 'KXVTBSPREAD')}

KALT = {'itf': ('KXITFWMATCH',), 'bkjpn': ('KXBLEAGUEONEGAME',), 'atp': ('KXATPCHALLENGERMATCH',), 'wta': ('KXWTACHALLENGERMATCH',), 'ufc': ('KXMMAFIGHT',), 'cs2': ('KXCSGOGAME',), 'lol': ('KXLOLLONGGAME', 'KXLOLSHORTGAME'), 'rl': ('KXRLGAME',),
        'f1': ('KXF1RACE',), 'pga': ('KXGOLFTOURN',), 'golf': ('KXGOLFTOURN',), 'lpga': ('KXLPGATOUR',)}

NAME_ONLY = ('atp', 'wta', 'itf', 'ufc', 'mma', 'box', 'pga', 'golf', 'lpga', 'f1', 'nascar', 'indycar', 'indy', 'darts', 'motogp')  # player/fighter/driver markets: match by name, not slug code

KM = {}

KPROP = {
    'nba': {'points': 'KXNBAPTS', 'rebounds': 'KXNBAREB', 'assists': 'KXNBAAST', 'pra': 'KXNBAPRA', 'pr': 'KXNBAPR', 'pa': 'KXNBAPA', 'ra': 'KXNBARA', 'threes': 'KXNBA3PT', 'blocks': 'KXNBABLK', 'steals': 'KXNBASTL', 'stocks': 'KXNBASTOCK'},
    'wnba': {'points': 'KXWNBAPTS', 'rebounds': 'KXWNBAREB', 'assists': 'KXWNBAAST', 'threes': 'KXWNBA3PT'},
    'nfl': {'passing_yards': 'KXNFLPASSYDS', 'rushing_yards': 'KXNFLRSHYDS', 'receiving_yards': 'KXNFLRECYDS', 'rush_rec_yards': 'KXNFLRRYDS', 'passing_tds': 'KXNFLPASSTDS', 'touchdowns': 'KXNFLTD', 'receptions': 'KXNFLREC', 'first_td': 'KXNFLFIRSTTD'},
    'nhl': {'points': 'KXNHLPTS', 'assists': 'KXNHLAST', 'goals': 'KXNHLGOAL', 'anytime_goal': 'KXNHLANYGOAL', 'first_goal': 'KXNHLFIRSTGOAL'},
    'mlb': {'hits': 'KXMLBHIT', 'home_runs': 'KXMLBHR', 'strikeouts': 'KXMLBKS'},
    'epl': {'anytime_goal': 'KXEPLANYGOAL', 'goals': 'KXEPLGOAL', 'first_goal': 'KXEPLFIRSTGOAL', 'assists': 'KXEPLAST'},
    'ucl': {'anytime_goal': 'KXUCLGOAL', 'goals': 'KXUCLGOAL', 'first_goal': 'KXUCLFIRSTGOAL', 'assists': 'KXUCLAST', 'shots': 'KXUCLSHOT'},
}

STAT_PAT = [
    ('pra', r'points?\s*\+\s*rebounds?\s*\+\s*assists?|pts\s*\+\s*reb(?:ounds?)?\s*\+\s*ast|\bpra\b'),
    ('pr', r'points?\s*\+\s*rebounds?|pts\s*\+\s*reb'),
    ('pa', r'points?\s*\+\s*assists?|pts\s*\+\s*ast'),
    ('ra', r'rebounds?\s*\+\s*assists?|reb\s*\+\s*ast'),
    ('rush_rec_yards', r'rush(?:ing)?\s*(?:and|&|\+)\s*receiv(?:ing)?\s*yards'),
    ('passing_yards', r'passing yards|pass(?:ing)? yds'),
    ('rushing_yards', r'rushing yards|rush(?:es|ing)? yds|rushes for'),
    ('receiving_yards', r'receiving yards|rec(?:eiving)? yds'),
    ('passing_tds', r'passing touchdowns?|pass(?:ing)? tds?'),
    ('rushing_tds', r'rushing touchdowns?|rush(?:ing)? tds?'),
    ('receiving_tds', r'receiving touchdowns?|rec(?:eiving)? tds?'),
    ('receptions', r'\breceptions?\b'),
    ('anytime_td', r'anytime\s+(?:td|touchdown)|to score a touchdown'),
    ('first_td', r'first touchdown|first td'),
    ('first_goal', r'first goal(?:scorer)?'),
    ('anytime_goal', r'anytime goal(?:scorer)?'),
    ('touchdowns', r'\btouchdowns?\b|\btds?\b'),
    ('threes', r'three[-\s]?pointers?|\bthrees?\b|\b3[-\s]?pt(?:s|ers?)?\b'),
    ('points', r'\bpoints?\b|\bpts\b'),
    ('rebounds', r'\brebounds?\b|\brebs?\b'),
    ('assists', r'\bassists?\b|\basts?\b'),
    ('steals', r'\bsteals?\b'),
    ('blocks', r'\bblocks?\b'),
    ('stocks', r'steals?\s*(?:and|&|\+)\s*blocks?|\bstocks?\b'),
    ('hits', r'\bhits\b'),
    ('home_runs', r'home runs?|\bhrs?\b'),
    ('strikeouts', r'strikeouts?|\bks\b'),
    ('goals', r'\bgoals?\b'),
    ('shots', r'shots on goal|\bshots\b'),
]

STAT_WORDS = {k: k.replace('_', ' ') for k, _pat in STAT_PAT}

def is_btts(q):
    return bool(re.search(r'(?i)both teams to score', q or ''))

def match_stat(text):
    t = text or ''
    for key, pat in STAT_PAT:
        if re.search(pat, t, re.I):
            return key
    return None

def parse_prop(q, tail, teams):
    if is_btts(q):
        return None
    if re.search(r'(?i)\b(o/?u|over/under|total)\b', q or '') and not re.search(r'(?i)points|rebounds|assists|yards|touchdown|receptions|threes|strikeouts|home runs|hits|steals|blocks', q or ''):
        return None
    stat = match_stat(q) or match_stat((tail or '').replace('-', ' '))
    if not stat:
        return None
    line = None
    m = re.search(r'(\d+(?:\.\d+)?)\s*\+', q or '') or re.search(r'(?i)(?:o/?u|over/under|over|under)\s*(\d+(?:\.\d+)?)', q or '')
    if m:
        line = float(m.group(1))
    if line is None and tail:
        tm = re.search(r'(\d+)pt(\d+)', tail)
        if tm:
            line = float(tm.group(1) + '.' + tm.group(2))
        else:
            tm = re.search(r'(\d+(?:\.\d+)?)$', tail)
            if tm:
                line = float(tm.group(1))
    player = None
    qm = re.match(r'^(.+?)\s*:\s*', q or '')
    if qm:
        head = qm.group(1).strip()
        if re.search(r'\svs\.?\s', head) and teams:
            rest = (q or '')[qm.end():]
            pm = re.match(r'(.+?)\s+(?:o/?u|over|under|\d)', rest, re.I) or re.match(r'(.+?)\s*$', rest)
            if pm and not match_stat(pm.group(1)):
                player = pm.group(1).strip()
        elif not re.search(r'\svs\.?\s', head):
            player = head
    if not player:
        pm = re.match(r'^(.+?)\s+(?:\d+\+?|over|under|o/?u|rushes|rushing|receiving|passing|records)', q or '', re.I)
        if pm and not re.search(r'\svs\.?\s', pm.group(1)):
            player = pm.group(1).strip()
    if not player and tail:
        parts = re.split(r'-(?:points?|pts|rebounds?|reb|assists?|ast|pra|threes?|3pt|yards?|yds|rushing|receiving|passing|touchdowns?|tds?|receptions?|hits|hrs?|ks|goals?|shots?)-', tail, maxsplit=1)
        if parts and parts[0] and not parts[0].startswith('total') and not parts[0].startswith('spread'):
            player = parts[0].replace('-', ' ').strip()
    if not player:
        return None
    if teams and any(player.lower() == t.lower() or player.lower() in t.lower() or t.lower() in player.lower() for t in teams) and stat in ('points', 'goals') and re.search(r'(?i)o/?u|over/under|total', q or ''):
        return None
    word = STAT_WORDS.get(stat, stat.replace('_', ' '))
    if line is not None and float(line) == int(line):
        ln = f"{int(line)}+"
        yes = f"{player} {ln} {word}"
        no = f"{player} under {int(line)} {word}"
    elif line is not None:
        yes = f"{player} over {line:g} {word}"
        no = f"{player} under {line:g} {word}"
    else:
        yes = f"{player} {word}"
        no = f"{player} not {word}"
    return dict(stat=stat, line=line, player=player, yes=yes, no=no)

def kmarkets(series):

    if not series: return []
    if series not in KM:
        out, cur = [], None
        for _ in range(8):
            d = pub(f"https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={series}&status=open&limit=1000" + (f"&cursor={cur}" if cur else ''))
            if not d: break
            out += d.get('markets', []); cur = d.get('cursor')
            if not cur: break
        KM[series] = out
    return KM[series]

MON = {m: i + 1 for i, m in enumerate(['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'])}

def kdate(evt):
    mm = re.search(r'-(\d\d)([A-Z]{3})(\d\d)', evt)
    return dt.date(2000 + int(mm.group(1)), MON[mm.group(2)], int(mm.group(3))) if mm else None

def occ_date(ms):
    for m in ms:
        occ = m.get('occurrence_datetime')
        if not occ: continue
        try: return dt.datetime.fromisoformat(occ.replace('Z', '+00:00')).date()
        except Exception: pass
    return None

def find_event(series, info, kind=None):
    if not series: return None
    pd = dt.date.fromisoformat(info['date']); codes = [c.upper() for c in info['codes']]
    ev = collections.defaultdict(list)
    for m in kmarkets(series): ev[m['event_ticker']].append(m)
    best = None
    names = list(info.get('teams') or [])
    if info.get('team') and info['team'] not in names: names.append(info['team'])
    if info.get('fav') and info['fav'] not in names: names.append(info['fav'])  # spread/total questions carry one team name only (Polymarket codes differ from Kalshi's)
    kind = kind or info.get('kind')
    esp = info['league'] in ESPORTS or info['league'] in NAME_ONLY
    window = 4 if esp else 1  # golf tournaments / race weekends can span a few days vs the Polymarket slug date
    for e, ms in ev.items():
        kd = kdate(e) or occ_date(ms)
        if not kd or abs((kd - pd).days) > window: continue
        # Two-player moneyline (X vs Y) must not match a multi-runner field (F1 race with 20 drivers, golf tournament, etc.)
        if kind == 'moneyline' and esp and len(ms) > 3: continue
        teampart = e.split('-')[1][7:] if len(e.split('-')) > 1 and len(e.split('-')[1]) > 7 else ''
        hits = 0 if esp else sum(1 for c in codes if teampart.startswith(c) or teampart.endswith(c) or any(m['ticker'].endswith('-' + c) for m in ms))
        if not hits and names:
            subs = [norm(m.get('yes_sub_title') or '') for m in ms]
            hits = sum(1 for t in names if any(namematch(t, x) for x in subs))
            need = 2 if len(info.get('teams') or []) >= 2 else 1
            if hits < need: hits = 0
        if hits and (not best or hits > best[0]): best = (hits, e, ms)
    return best

def norm(x): return re.sub(r'[^a-z0-9 ]', '', (x or '').lower()).strip()

def namematch(a, b):
    return _knames.name_hit(a, b)

def suffix(m): return m['ticker'].rsplit('-', 1)[1]

def fp(x):
    try: return float(x)
    except Exception: return None

def kalshi(s):
    info = s['info']; ser = KSER.get(info['league'])
    if not ser: return dict(status='none', why=f"Kalshi doesn't list {info['league'].upper()}")
    event_title = None; opp_ticker = None; opp_contract = None; opp_action = None; opp_price = None
    gm, tot, spr = ser
    if info['kind'] in ('moneyline', 'teamwin', 'draw'):
        ev = find_event(gm, info, info['kind'])
        for alt in KALT.get(info['league'], ()):
            if ev: break
            ev = find_event(alt, info, info['kind'])
        if not ev: return dict(status='none', why='No open Kalshi game market found for this matchup')
        hits, e, ms = ev
        codes = [c.upper() for c in info['codes']]
        def mfor(code):
            for m in ms:
                if suffix(m) == code: return m
            return None
        if info['kind'] == 'moneyline':
            yes_code, no_code = codes[0], codes[-1]
            m_yes, m_no = mfor(yes_code), mfor(no_code)
            if info['league'] in ESPORTS or info['league'] in NAME_ONLY: m_yes = m_no = None
            if hits == 1 and len(ms) >= 2 and info['league'] not in ESPORTS and info['league'] not in NAME_ONLY:
                if m_yes and not m_no: m_no = next((m for m in ms if m is not m_yes and suffix(m) != 'TIE'), None)
                if m_no and not m_yes: m_yes = next((m for m in ms if m is not m_no and suffix(m) != 'TIE'), None)
            if not (m_yes and m_no) and len(info.get('teams', [])) == 2:
                byname = lambda t: next((m for m in ms if namematch(t, m.get('yes_sub_title'))), None)
                m_yes = m_yes or byname(info['teams'][0]); m_no = m_no or byname(info['teams'][1])
            target = m_yes if s['side'] == 'yes' else m_no
            if (info['league'] in ESPORTS or info['league'] in NAME_ONLY) and target and not namematch(info['teams'][0 if s['side'] == 'yes' else 1], target.get('yes_sub_title')): target = None
            if not target: return dict(status='none', why='Kalshi event found but team contract not matched')
            # Prefer Yes on the backed team's own contract. Only use No on the
            # opponent's contract when this team has no Yes ask.
            yes_px = fp(target.get('yes_ask_dollars'))
            if yes_px and yes_px > 0:
                act, m, p = 'BUY YES', target, yes_px
            else:
                other = m_no if s['side'] == 'yes' else m_yes
                no_px = fp(other.get('no_ask_dollars')) if other else None
                if not (other and no_px and no_px > 0):
                    return dict(status='none', why='Kalshi market matched but has no ask right now')
                act, m, p = 'BUY NO', other, no_px
            peer = m_no if s['side'] == 'yes' else m_yes
            if peer:
                opp_ticker = peer.get('ticker')
                opp_contract = peer.get('yes_sub_title') or peer.get('title')
                opp_action = 'BUY YES'
                opp_price = fp(peer.get('yes_ask_dollars'))
            names = [x.get('yes_sub_title') for x in (m_yes, m_no) if x and x.get('yes_sub_title')]
            if len(names) == 2:
                event_title = names[0] + ' vs ' + names[1] + ' winner'
        elif info['kind'] == 'teamwin':
            m = mfor(info['code'].upper())
            if not m and info.get('team'):
                m = next((x for x in ms if namematch(info['team'], x.get('yes_sub_title'))), None)
            if not m: return dict(status='none', why='Kalshi event found but team contract not matched')
            act = 'BUY YES' if s['side'] == 'yes' else 'BUY NO'; p = fp(m['yes_ask_dollars' if act == 'BUY YES' else 'no_ask_dollars'])
        else:
            m = mfor('TIE')
            if not m: return dict(status='none', why='No Kalshi tie contract')
            act = 'BUY YES' if s['side'] == 'yes' else 'BUY NO'; p = fp(m['yes_ask_dollars' if act == 'BUY YES' else 'no_ask_dollars'])
    elif info['kind'] == 'total':
        ev = find_event(tot, info)
        if not ev: return dict(status='none', why='No open Kalshi total market for this game')
        ms = ev[2]; m = next((x for x in ms if fp(x.get('floor_strike')) == info['line']), None)
        if not m:
            lines = sorted(fp(x.get('floor_strike')) for x in ms if fp(x.get('floor_strike')) is not None)
            near = min(lines, key=lambda l: abs(l - info['line'])) if lines else None
            return dict(status='none', why=f"No Kalshi total at {info['line']:g}" + (f" (nearest {near:g})" if near is not None else ''))
        act = 'BUY YES' if s['side'] == 'yes' else 'BUY NO'; p = fp(m['yes_ask_dollars' if act == 'BUY YES' else 'no_ask_dollars'])
    elif info['kind'] == 'spread':
        ev = find_event(spr, info)
        if not ev: return dict(status='none', why='No open Kalshi spread market for this game')
        ms = ev[2]; fc = (info.get('favcode') or '').upper()
        def spread_team(t):
            return re.sub(r'\s+wins by (?:over|more than).*$', '', t or '', flags=re.I)
        name_hits = [x for x in ms if fp(x.get('floor_strike')) == info['line'] and namematch(info.get('fav'), spread_team(x.get('yes_sub_title') or x.get('title') or ''))]
        code_hits = [x for x in ms if fp(x.get('floor_strike')) == info['line'] and suffix(x).rstrip('0123456789') == fc]
        cand = name_hits or code_hits
        if not cand: return dict(status='none', why=f"No Kalshi line for {info.get('fav')} by over {info['line']:g}")
        m = cand[0]
        # Poly YES on a favorite (negative line) = BUY YES on that team's "wins by over N".
        # Poly YES on a dog (positive line, e.g. Real Madrid +1.5) = BUY NO on the favorite's line.
        invert = not info.get('named_is_fav', True)
        if s['side'] == 'yes':
            act = 'BUY NO' if invert else 'BUY YES'
        else:
            act = 'BUY YES' if invert else 'BUY NO'
        p = fp(m['yes_ask_dollars' if act == 'BUY YES' else 'no_ask_dollars'])
    elif info['kind'] == 'prop':
        series = (KPROP.get(info['league']) or {}).get(info.get('stat'))
        if not series:
            return dict(status='none', why="No Kalshi " + (info.get('stat') or 'player') + " prop series for " + info['league'].upper())
        ev = find_event(series, info, 'prop')
        if not ev:
            return dict(status='none', why="No open Kalshi " + STAT_WORDS.get(info.get('stat'), 'player prop') + " market for this game")
        ms = ev[2]
        player = info.get('player') or ''
        def mtitle(m):
            return m.get('title') or m.get('yes_sub_title') or ''
        cands = [m for m in ms if namematch(player, re.sub(r':\s*.*$', '', mtitle(m))) or namematch(player, mtitle(m))]
        if not cands:
            return dict(status='none', why="No Kalshi line for " + player)
        def mline(m):
            tm = re.search(r'(\d+(?:\.\d+)?)\s*\+', mtitle(m))
            if tm: return float(tm.group(1))
            fs = fp(m.get('floor_strike'))
            if fs is None: return None
            return fs + 0.5 if (m.get('strike_type') == 'greater' and abs(fs - int(fs) - 0.5) < 0.01) else fs
        line = info.get('line')
        if line is not None:
            exact = [m for m in cands if mline(m) is not None and min(abs(mline(m) - line), abs(mline(m) - 0.5 - line), abs(mline(m) + 0.5 - line)) < 0.06]
            if exact:
                cands = exact
            else:
                near = min((mline(m) for m in cands if mline(m) is not None), default=None, key=lambda l: abs(l - line))
                return dict(status='none', why="No Kalshi " + STAT_WORDS.get(info.get('stat'), 'prop') + " line at " + f"{line:g}" + " for " + player + ((" (nearest " + f"{near:g}" + ")") if near is not None else ''))
        m = cands[0]
        act = 'BUY YES' if s['side'] == 'yes' else 'BUY NO'
        p = fp(m['yes_ask_dollars' if act == 'BUY YES' else 'no_ask_dollars'])
    elif info['kind'] == 'map':
        MAPSER = {'cs2': 'KXCS2MAP', 'dota2': 'KXDOTA2MAP', 'val': 'KXVALORANTMAP', 'lol': 'KXLOLMAP'}
        mser = MAPSER.get(info['league'])
        if not mser: return dict(status='none', why='Kalshi has no map-winner series for ' + info['league'].upper())
        pd = dt.date.fromisoformat(info['date']); tms = list(info.get('teams') or [])
        evs = collections.defaultdict(list)
        for x in kmarkets(mser): evs[x['event_ticker']].append(x)
        pick = None
        for e, ms in evs.items():
            if not e.endswith('-%d' % info['mapno']): continue
            kd = kdate(e) or occ_date(ms)
            if not kd or abs((kd - pd).days) > 4: continue
            sub = lambda t: next((x for x in ms if namematch(t, x.get('yes_sub_title'))), None)
            a_, b_ = sub(tms[0]), sub(tms[1])
            if a_ and b_ and a_ is not b_: pick = (a_, b_); break
        if not pick: return dict(status='none', why='No open Kalshi map winner market for this map')
        m_yes, m_no = pick
        target = m_yes if s['side'] == 'yes' else m_no
        other = m_no if s['side'] == 'yes' else m_yes
        yes_px = fp(target.get('yes_ask_dollars'))
        if yes_px and yes_px > 0: act, m, p = 'BUY YES', target, yes_px
        else:
            no_px = fp(other.get('no_ask_dollars'))
            if not (no_px and no_px > 0): return dict(status='none', why='Kalshi market matched but has no ask right now')
            act, m, p = 'BUY NO', other, no_px
        opp_ticker = other.get('ticker'); opp_contract = other.get('yes_sub_title'); opp_action = 'BUY YES'; opp_price = fp(other.get('yes_ask_dollars'))
        event_title = (m_yes.get('yes_sub_title') or tms[0]) + ' vs ' + (m_no.get('yes_sub_title') or tms[1]) + ' map %d winner' % info['mapno']
    else:
        return dict(status='none', why='Market type has no Kalshi equivalent')
    if not p: return dict(status='none', why='Kalshi market matched but has no ask right now')
    rule = m.get('rules_primary') or ''
    sel = (m.get('title') if info.get('kind') == 'prop' else None) or m.get('yes_sub_title') or ''
    edge = round((s['avg_entry'] - p) * 100, 1) if s['avg_entry'] else None
    yes_ask = fp(m.get('yes_ask_dollars'))
    no_ask = fp(m.get('no_ask_dollars'))
    market_title = m.get('title') or sel
    out = dict(status='ok', occ=m.get('occurrence_datetime'), action=act, price=p, ticker=m['ticker'], contract=sel, rule=rule[:260], url=f"https://kalshi.com/markets/{m['event_ticker'].split('-')[0].lower()}",
                edge_vs_whales=edge, edge_vs_poly=round((s['price'] - p) * 100, 1),
                light='green' if edge is not None and edge >= 0 else ('yellow' if edge is not None and edge >= -5 else 'red'),
                yesAsk=yes_ask, noAsk=no_ask, marketTitle=event_title or market_title, yesSubTitle=m.get('yes_sub_title'), noSubTitle=m.get('no_sub_title'))
    if event_title:
        out['eventTitle'] = event_title
        out['marketTitle'] = event_title
    else:
        out['marketTitle'] = market_title
    if opp_ticker:
        out['oppTicker'] = opp_ticker
        out['oppContract'] = opp_contract
        out['oppAction'] = opp_action or 'BUY YES'
        if opp_price:
            out['oppPrice'] = opp_price
    return out


def map_bet(slug, question, side, avg_entry=None, price=None):
    """Map a Polymarket sports position to a Kalshi contract.

    side: 'yes' or 'no' (Polymarket outcome_index 0/1). Returns the kalshi()
    dict (status 'ok' or 'none').
    """
    try:
        info = parse(dict(slug=slug or '', question=question or ''))
    except Exception as e:
        return dict(status='none', why='Could not parse Polymarket slug (%s)' % type(e).__name__)
    return kalshi(dict(info=info, side=(side or 'yes').lower(), avg_entry=avg_entry, price=price or 0))
