#!/usr/bin/env python3
"""Bake src/last20.json from data/scanner_record.json for the capper-row dots."""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REC = os.path.join(ROOT, "data", "scanner_record.json")
OUT = os.path.join(ROOT, "src", "last20.json")


def last20_map(led=None):
    if led is None:
        led = json.load(open(REC)) if os.path.exists(REC) else {"picks": {}}
    by = {}
    for row in (led.get("picks") or {}).values():
        if row.get("status") not in ("win", "loss"):
            continue
        k = (row.get("capper") or "").strip()
        px = row.get("price") or 0
        if row["status"] == "win":
            res, units = "W", ((1.0 / px - 1.0) if isinstance(px, (int, float)) and 0 < px < 1 else 0.0)
        else:
            res, units = "L", -1.0
        ts = row.get("gradedTs") or row.get("startTs") or row.get("firstTs") or 0
        by.setdefault(k, []).append((ts, res, units))
    out = {}
    for k, evs0 in by.items():
        evs = sorted(evs0, key=lambda x: x[0], reverse=True)[:20]
        evs.reverse()
        out[k] = {
            "dots": "".join(x[1] for x in evs),
            "w": sum(1 for x in evs if x[1] == "W"),
            "l": sum(1 for x in evs if x[1] == "L"),
            "n": len(evs),
            "pnl": round(sum(x[2] for x in evs), 2),
        }
    return out


def write(path=OUT):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = last20_map()
    json.dump(data, open(path, "w"), separators=(",", ":"))
    open(path, "a").write("\n")
    return data


if __name__ == "__main__":
    d = write()
    print("last20.json", len(d), "cappers")
