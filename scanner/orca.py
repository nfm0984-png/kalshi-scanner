"""OrcaLayer HTTP client. Key comes from ORCA_API_KEY or scanner/.orca_api_key.

Never logs, prints, or writes the API key.
"""
import json, time, urllib.request, urllib.error, urllib.parse
import os as _os
import hashlib, os

_HERE = _os.path.dirname(_os.path.abspath(__file__))

def _load_key():
    k = (_os.environ.get('ORCA_API_KEY') or '').strip()
    if k:
        return k
    path = _os.path.join(_HERE, '.orca_api_key')
    try:
        return open(path).read().strip()
    except Exception:
        return ''

_K = _load_key()
BASE = "https://orcalayer.com"
CALLS = {'n': 0, 'units': 0, 'errors': [], 'last_limit': None, 'last_remaining': None}
CACHE_DIR = _os.path.join(_HERE, '.cache')
CACHE_TTL = int(os.environ.get('ORCA_CACHE_TTL', '0'))


def has_key():
    return bool(_K)


def orca(path, params=None, body=None, units=1, tries=4, timeout=90, wait202=True):
    if not _K:
        CALLS['errors'].append('missing key')
        return None
    url = BASE + path + ('?' + urllib.parse.urlencode(params) if params else '')
    if CACHE_TTL and body is None:
        os.makedirs(CACHE_DIR, exist_ok=True)
        cf = os.path.join(CACHE_DIR, hashlib.md5(url.encode()).hexdigest())
        if os.path.exists(cf) and time.time() - os.path.getmtime(cf) < CACHE_TTL:
            return json.load(open(cf))
        r = _orca(url, body, units, tries, timeout, wait202)
        if r is not None:
            json.dump(r, open(cf, 'w'))
        return r
    return _orca(url, body, units, tries, timeout, wait202)


def _orca(url, body, units, tries, timeout=90, wait202=True):
    path = url[len(BASE):].split('?')[0]
    h = {'Authorization': 'Bearer ' + _K, 'x-api-key': _K, 'User-Agent': 'kalshi-scanner-orca/1.0', 'Accept': 'application/json'}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h['Content-Type'] = 'application/json'
    for i in range(tries):
        CALLS['n'] += 1
        CALLS['units'] += units
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=timeout) as r:
                CALLS['last_limit'] = r.headers.get('X-RateLimit-Limit')
                CALLS['last_remaining'] = r.headers.get('X-RateLimit-Remaining')
                if r.status == 202:
                    if not wait202:
                        return {'_pending': True}
                    time.sleep(30)
                    continue
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504):
                ra = e.headers.get('Retry-After')
                time.sleep(min(float(ra) if ra and ra.isdigit() else 5 * (i + 1), 65))
                continue
            CALLS['errors'].append("%s %s" % (e.code, path))
            return None
        except Exception as e:
            CALLS['errors'].append("%s %s" % (type(e).__name__, path))
            time.sleep(3)
    CALLS['errors'].append("gave up %s" % path)
    return None
