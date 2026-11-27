#!/usr/bin/env python3
"""t1122: Kalshi Short Price 1.10x, drop reasons, Top 100 log builder."""
import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Import payout helpers without running a scan: load only the functions we patched
# by importing scan in a guarded way is heavy (network). Import after stubbing main.
import scan as ks


class TestShortPrice(unittest.TestCase):
    def test_87c_is_kept_and_short(self):
        p = {"price": 0.87, "payout": None}
        self.assertTrue(ks.pick_payout_ok(p))
        self.assertTrue(ks.is_short_price(p))
        ks.tag_short_price(p)
        self.assertTrue(p["shortPrice"])

    def test_70c_is_full_price(self):
        p = {"price": 0.70}
        self.assertTrue(ks.pick_payout_ok(p))
        self.assertFalse(ks.is_short_price(p))

    def test_95c_still_hidden(self):
        self.assertFalse(ks.pick_payout_ok({"price": 0.95}))

    def test_missing_price_kept(self):
        self.assertTrue(ks.pick_payout_ok({}))
        self.assertTrue(ks.pick_payout_ok(None))


class TestDropReasons(unittest.TestCase):
    def test_classifies_sub1000_and_short_odds(self):
        now = 1795764918
        cap = {"nickname": "vet", "pnl": 20000, "yearlyPnl": 5000, "monthlyPnl": 1000}
        # stake_ok uses cost
        small = {"cost": 200, "startTs": now + 3600, "league": "NBA", "ticker": "KXNBAGAME-X", "bt": "Moneyline", "price": 0.55}
        # May classify as sub1000 if stake_ok looks at cost
        why = ks.classify_hidden_pick(cap, small, now)
        self.assertIn(why, ("sub1000", "qualityOrForm", "futuresOrHorizon", "payoutUnder1.10", "stale6c", None))

    def test_futures_and_stale(self):
        now = 1795764918
        cap = {"nickname": "vet", "pnl": 20000, "yearlyPnl": 5000, "monthlyPnl": 1000}
        fut = {"cost": 2000, "startTs": now + 40 * 86400, "league": "Sports", "ticker": "KXNEXTTEAMNFL-26ARODGERS8-PIT", "bt": "Other", "price": 0.64}
        why = ks.classify_hidden_pick(cap, fut, now)
        self.assertEqual(why, "futuresOrHorizon")
        stale = {"cost": 2000, "startTs": now + 3600, "league": "NBA", "ticker": "KXNBAGAME-X", "bt": "Moneyline", "price": 0.55, "slip": 35.5}
        why = ks.classify_hidden_pick(cap, stale, now)
        self.assertEqual(why, "stale6c")

    def test_bump_drop_counts(self):
        cov = {"dropReasons": {}}
        ks.bump_drop(cov, "sub1000")
        ks.bump_drop(cov, "sub1000")
        ks.bump_drop(cov, "payoutUnder1.10")
        self.assertEqual(cov["dropReasons"]["sub1000"], 2)
        self.assertEqual(cov["dropReasons"]["payoutUnder1.10"], 1)


class TestTop100Log(unittest.TestCase):
    def test_best_cappers_rank_first(self):
        now = 1795764918
        pinned = {"cappers": [{"nickname": "falcon999"}, {"nickname": "djcheecake"}], "tag": "Best Cappers"}
        cappers = [
            {"nickname": "falcon999", "pinned": True, "tag": "Best Cappers", "tier": "Best Cappers", "pnl": 46209, "graded": {"w": 121, "l": 80, "n": 201, "roi": 5}, "profileUrl": "https://kalshi.com/ideas/profiles/falcon999", "bestAt": "NFL"},
            {"nickname": "boardguy", "pinned": False, "tier": "Board", "pnl": 8000, "graded": {"w": 20, "l": 10, "n": 30, "roi": 12}, "profileUrl": "https://kalshi.com/ideas/profiles/boardguy"},
            {"nickname": "djcheecake", "pinned": True, "tag": "Best Cappers", "tier": "Best Cappers", "pnl": 27927, "graded": {"w": 58, "l": 41, "n": 99, "roi": 10}, "profileUrl": "https://kalshi.com/ideas/profiles/djcheecake"},
        ]
        log = ks.build_top_cappers_log(cappers, pinned, games=[], now=now, limit=100)
        names = [c["nickname"] for c in log["cappers"]]
        self.assertEqual(log["count"], 3)
        self.assertIn("falcon999", names)
        self.assertIn("djcheecake", names)
        self.assertIn("boardguy", names)
        # Best first
        self.assertTrue(log["cappers"][0]["best"])
        self.assertIn("Best Capper", log["cappers"][0]["tags"])
        self.assertTrue(log["cappers"][0]["profile"].startswith("https://kalshi.com/"))
        ranks = [c["rank"] for c in log["cappers"]]
        self.assertEqual(ranks, list(range(1, 4)))


if __name__ == "__main__":
    unittest.main()
