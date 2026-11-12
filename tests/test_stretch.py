import unittest

import numpy as np
import pandas as pd

from stretch import stretch


def ohlc(c):
    c = np.asarray(c, float)
    return pd.DataFrame({"High": c * 1.005, "Low": c * .995, "Close": c})


class StretchTests(unittest.TestCase):
    def test_esticada_e_normal(self):
        rng = np.random.default_rng(1)
        base = 100 + np.cumsum(rng.normal(0, .5, 400))
        up = np.r_[base, base[-1] * np.linspace(1.01, 1.25, 15)]  # arranque final muito acima da SMA50
        a, b = stretch(ohlc(up)), stretch(ohlc(base))
        self.assertGreaterEqual(a["pct"], 95)
        self.assertGreater(a["d"], b["d"])
        self.assertLess(a["x75"], up[-1])  # o nível «de recuo» está abaixo do preço quando está esticada

    def test_poucos_dados(self):
        self.assertIsNone(stretch(ohlc(np.linspace(100, 110, 120))))

    def test_percentil_fraco_em_queda(self):
        c = np.r_[np.linspace(100, 140, 300), np.linspace(140, 100, 60)]
        self.assertLess(stretch(ohlc(c))["pct"], 10)


if __name__ == "__main__":
    unittest.main()
