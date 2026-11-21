#!/usr/bin/env python3
import json, sys, os
label = sys.argv[1] if len(sys.argv) > 1 else "check"
paths = sys.argv[2:] or ["data.json"]
for p in paths:
    if not os.path.exists(p):
        print(label, "missing", p)
        sys.exit(1)
    try:
        json.load(open(p))
    except Exception as e:
        print(label, "invalid JSON", p, e)
        sys.exit(1)
    print(label, "ok", p)
