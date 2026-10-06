import unittest

from ds1_prebreakout import WEIGHTS, score_prebreakout


def make_bars():
    bars = []
    for i in range(60):
        if i < 40:
            close = 75.0 + i * 0.5
            low, high = close - 1.0, close + 1.0
        else:
            close = 98.0 if i < 59 else 99.0
            low = 97.0 if i < 55 else 98.0
            high = 101.0
        open_price = close - 0.3 if i % 4 else close + 0.3
        volume = 50.0 if i >= 55 else 100.0
        bars.append({"o": open_price, "h": high, "l": low, "c": close, "v": volume})
    # Keep a positive down-volume denominator while preserving strong up/down volume.
    bars[45]["o"] = bars[45]["c"] + 0.3
    bars[45]["v"] = 100.0
    return bars + [{"o": 99, "h": 100, "l": 98, "c": 99, "v": 1}]


def make_market():
    return [{"o": 100 + i * 0.1, "h": 101 + i * 0.1, "l": 99 + i * 0.1,
             "c": 100 + i * 0.1, "v": 1000} for i in range(61)]


class PrebreakoutTests(unittest.TestCase):
    def test_weights_sum_to_one_hundred(self):
        self.assertEqual(sum(WEIGHTS.values()), 100)

    def test_good_prebreakout_has_dynamic_trade_plan(self):
        result = score_prebreakout("MWG", make_bars(), make_market(),
                                   "TREND_UP", sector_return=0.12,
                                   catalyst=True)
        self.assertGreaterEqual(result["score"], 70)
        self.assertIn(result["classification"], {"PRE-BREAKOUT BUY", "WATCH/BUY SMALL"})
        self.assertLess(result["entry"], result["resistance"])
        self.assertLess(result["sl"], result["entry"])
        self.assertTrue(result["trigger"])
        self.assertTrue(result["invalidation"])
        self.assertFalse(result["blocked"])

    def test_missing_sector_data_fails_closed(self):
        result = score_prebreakout("MWG", make_bars(), make_market(),
                                   "TREND_UP", sector_return=None)
        self.assertEqual(result["classification"], "NO TRADE")
        self.assertTrue(result["blocked"])

    def test_completed_breakout_is_not_prebreakout_entry(self):
        bars = make_bars()
        bars[-2].update({"o": 101.0, "h": 103.0, "l": 100.0, "c": 102.0})
        result = score_prebreakout("MWG", bars, make_market(),
                                   "TREND_UP", sector_return=0.12)
        self.assertIn("breakout_already_occurred_use_confirmation_engine",
                      result["blocked"])

    def test_down_market_is_blocked(self):
        result = score_prebreakout("MWG", make_bars(), make_market(),
                                   "TREND_DOWN", sector_return=0.12)
        self.assertIn("market_regime_not_tradeable", result["blocked"])


if __name__ == "__main__":
    unittest.main()
