#!/usr/bin/env python3
"""Plain, non-secret current-picks summary for cross-scanner badges. Never writes decrypted data.json."""
import json, os
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "public_slate.json")
PT = ZoneInfo("America/Los_Angeles")


def picks_from_data(data):
    out = []
    for g in data.get("games") or []:
        game = (g.get("game") or "").strip()
        start_ts = g.get("startTs") or 0
        for p in g.get("picks") or []:
            backers = p.get("backers") or []
            if not backers:
                continue
            view = p.get("view") or {}
            ticker = (p.get("ticker") or view.get("ticker") or "").strip().upper()
            yes_no = (view.get("yesNo") or p.get("yesNo") or "").strip()
            side = (p.get("big") or view.get("backing") or "").strip()
            out.append({
                "ticker": ticker,
                "yesNo": yes_no,
                "side": side,
                "game": game,
                "startTs": start_ts or p.get("startTs") or 0,
                "bt": p.get("bt") or "",
                "n": len(backers),
            })
    return out


def write(picks, path=OUT, source="kalshi"):
    now = datetime.now(PT)
    data = {
        "source": source,
        "ts": int(now.timestamp()),
        "updatedAt": now.strftime("%a %b %-d · %-I:%M %p PT"),
        "picks": picks,
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return data


def write_from_data(data, path=OUT):
    picks = picks_from_data(data)
    d = write(picks, path)
    print("public_slate", d["updatedAt"], "n", len(picks))
    return d


if __name__ == "__main__":
    # Decrypt in memory only; do not unwrap data.json on disk.
    path = os.path.join(ROOT, "data.json")
    obj = json.load(open(path))
    if isinstance(obj, dict) and obj.get("enc") == 1:
        from gate_crypto import decrypt_obj
        obj = decrypt_obj(obj)
    write_from_data(obj)
