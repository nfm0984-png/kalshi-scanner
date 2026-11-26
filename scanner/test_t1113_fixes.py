#!/usr/bin/env python3
"""Split + Coming Up checks for the Kalshi scanner (Nov 26). No network, no secrets."""
import os, re, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import split_policy as sp

class SplitPolicyTests(unittest.TestCase):
    def test_1v1_hidden(self):
        self.assertEqual(sp.stance(1, 10000, 1, 9000), 'hide')
    def test_3v1_majority_shown(self):
        self.assertEqual(sp.stance(3, 29000, 1, 5000), 'majority')
        self.assertEqual(sp.stance(1, 5000, 3, 29000), 'hide')
    def test_2v1_needs_dollars(self):
        self.assertEqual(sp.stance(2, 10000, 1, 10000), 'hide')
        self.assertEqual(sp.stance(2, 25000, 1, 10000), 'majority')

class ComingUpHorizonTests(unittest.TestCase):
    def test_open_games_not_clipped_to_today(self):
        src = open(os.path.join(ROOT, "src", "app.tsx")).read()
        # Coming Up uses openGames (30-day horizon), not todayGames / inSlateWindow.
        self.assertIn('function openGames', src)
        self.assertRegex(src, r'30\s*\*\s*24\s*\*\s*3600|30\s*\*\s*86400')
        # ComingUpTab still reads props.games (openGames), not todayGames
        m = re.search(r'function ComingUpTab\([\s\S]{0,400}', src)
        self.assertTrue(m and 'todayGames' not in m.group(0))
        # Tab badge uses post-split Coming Up count
        self.assertIn('hideSplitsOnGames(games).games.reduce', src)

if __name__ == '__main__':
    unittest.main()
