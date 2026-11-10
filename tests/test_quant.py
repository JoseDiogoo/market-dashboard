import unittest

import numpy as np
import pandas as pd

import fetch
import quality


def frames(ni, cfo, ta, rev=None, ebit=None, cash=None, ca=None, cl=None, ppe=None, debt=None, rd=0.0, capex=-5.0, sga=10.0):
    """Demonstrações sintéticas no formato do yfinance (colunas = exercícios, do mais recente para o mais antigo)."""
    n = len(ta)
    cols = pd.to_datetime([f"{2025 - k}-12-31" for k in range(n)])
    rev = rev or [100.0] * n
    fin = pd.DataFrame({"Net Income": ni, "Total Revenue": rev, "Research And Development": [rd] * n, "Selling General And Administration": [sga] * n,
                        "EBIT": ebit or [10.0] * n}, index=cols).T
    bs = pd.DataFrame({"Total Assets": ta, "Cash And Cash Equivalents": cash or [10.0] * n, "Current Assets": ca or [50.0] * n, "Current Liabilities": cl or [30.0] * n,
                       "Net PPE": ppe or [40.0] * n, "Total Debt": debt or [20.0] * n}, index=cols).T
    cf = pd.DataFrame({"Operating Cash Flow": cfo, "Capital Expenditure": [capex] * n}, index=cols).T
    return fin, bs, cf


class SloanTests(unittest.TestCase):
    def test_zones(self):
        # accruals = (NI - CFO) / ativos médios; ativos 200 → médios 200
        for ni, cfo, zone in [(10, 30, "baixo"), (20, 6, "medio"), (30, 0, "alto")]:
            with self.subTest(zone=zone):
                fin, bs, cf = frames([ni] * 4, [cfo] * 4, [200.0] * 4)
                q = quality.quant_raw(fin, bs, cf, {"sector": "Technology"}, False, True, 500.0)
                self.assertEqual(q["sloan"]["zone"], zone)
                self.assertAlmostEqual(q["sloan"]["ratio"], round(100 * (ni - cfo) / 200, 1))

    def test_financials_excluded(self):
        fin, bs, cf = frames([10] * 4, [5] * 4, [200.0] * 4)
        q = quality.quant_raw(fin, bs, cf, {"sector": "Financial Services"}, True, True, 500.0)
        self.assertNotIn("sloan", q)
        self.assertNotIn("g", q)
        self.assertTrue(q["magic"]["excluded"])


class MagicTests(unittest.TestCase):
    def test_inputs(self):
        fin, bs, cf = frames([10] * 4, [12] * 4, [200.0] * 4, ebit=[20.0] * 4, cash=[10.0] * 4, debt=[30.0] * 4, ca=[60.0] * 4, cl=[30.0] * 4, ppe=[50.0] * 4)
        q = quality.quant_raw(fin, bs, cf, {"sector": "Technology"}, False, True, 400.0)["magic"]
        self.assertAlmostEqual(q["ey"], round(20 / (400 + 30 - 10), 4))       # EBIT / EV
        self.assertAlmostEqual(q["roc"], round(20 / ((60 - 10) - (30 - 0) + 50), 4))  # EBIT / (NWC sem caixa + ativos fixos)

    def test_ranking_and_top(self):
        T = {}
        for k in range(20):  # k=0: melhor nas duas medidas
            T[f"S{k}"] = {"q": {"quant": {"magic": {"ey": 0.20 - 0.005 * k, "roc": 0.50 - 0.01 * k, "excluded": False}}}}
        T["UTIL"] = {"q": {"quant": {"magic": {"ey": 0.9, "roc": 0.9, "excluded": True}}}}
        T["SEM"] = {"q": {"quant": {"magic": {"ey": None, "roc": None, "excluded": False}}}}
        fetch.quant_finalize(T)
        self.assertEqual(T["S0"]["q"]["quant"]["magic"]["rank"], 1)
        self.assertEqual(T["S19"]["q"]["quant"]["magic"]["rank"], 20)
        self.assertEqual(T["S0"]["q"]["quant"]["magic"]["of"], 20)
        self.assertEqual([k for k, t in T.items() if t["q"]["quant"]["magic"].get("top")], ["S0", "S1"])  # decil superior de 20 = 2
        self.assertNotIn("rank", T["UTIL"]["q"]["quant"]["magic"])
        self.assertNotIn("rank", T["SEM"]["q"]["quant"]["magic"])


class MohanramTests(unittest.TestCase):
    def raw(self, **kw):
        g = {"roa": 0.10, "cfo_roa": 0.12, "cfo_gt_ni": True, "roa_var": 0.001, "sg_var": 0.001, "rd": 0.05, "capex": 0.04, "sga": 0.20, "pb": 8.0, "sector": "Technology"}
        g.update(kw)
        return {"q": {"quant": {"g": g}}}

    def test_score_and_medians(self):
        T = {f"M{k}": self.raw(roa=0.05, cfo_roa=0.05, cfo_gt_ni=False, roa_var=0.01, sg_var=0.01, rd=0.0, capex=0.01, sga=0.05, pb=2.0) for k in range(9)}
        T["BEST"] = self.raw()
        T["WORST"] = self.raw(roa=0.01, cfo_roa=0.01, cfo_gt_ni=False, roa_var=0.5, sg_var=0.5, rd=0.0, capex=0.0, sga=0.0)
        fetch.quant_finalize(T)
        best, worst = T["BEST"]["q"]["quant"]["g"], T["WORST"]["q"]["quant"]["g"]
        self.assertEqual((best["score"], best["of"]), (8, 8))
        self.assertEqual(worst["score"], 0)
        self.assertTrue(best["growth"] and best["grp"] == "setor")

    def test_missing_signal_reduces_available(self):
        T = {f"M{k}": self.raw() for k in range(10)}
        T["X"] = self.raw(roa_var=None, sg_var=None)
        fetch.quant_finalize(T)
        self.assertEqual(T["X"]["q"]["quant"]["g"]["of"], 6)

    def test_growth_flag_by_pb(self):
        T = {f"V{k}": self.raw(sector="Industrials", pb=2.0 + k) for k in range(10)}
        fetch.quant_finalize(T)
        self.assertFalse(T["V0"]["q"]["quant"]["g"]["growth"])  # P/B baixo: valor
        self.assertTrue(T["V9"]["q"]["quant"]["g"]["growth"])


class TechnicalTests(unittest.TestCase):
    @staticmethod
    def series(steps):
        c = [100.0]
        for n, r in steps:
            for _ in range(n):
                c.append(c[-1] * (1 + r))
        return pd.Series(c, index=pd.bdate_range("2025-01-01", periods=len(c)))

    def test_bullish_divergence(self):
        # queda rápida (RSI muito baixo), ressalto, nova queda lenta até um mínimo mais baixo (RSI mais alto), ressalto de confirmação
        s = self.series([(120, 0.001), (25, -0.012), (12, 0.012), (45, -0.0035), (14, 0.01)])
        sig = fetch.tech_signals(s)
        self.assertIsNotNone(sig["bull"], sig)
        self.assertLess(sig["bull"]["p2"], sig["bull"]["p1"] * 0.99)
        self.assertGreater(sig["bull"]["r2"], sig["bull"]["r1"] + 2)
        self.assertLess(sig["bull"]["r1"], 40)
        self.assertIsNone(sig["bear"])

    def test_no_divergence_in_trend(self):
        sig = fetch.tech_signals(self.series([(250, 0.002)]))
        self.assertIsNone(sig["bull"])
        self.assertIsNone(sig["bear"])
        self.assertIsNone(sig["boll"]["touch"])

    def test_bollinger_touch(self):
        rng = np.random.default_rng(1)
        c = list(100 + rng.normal(0, 0.5, 200))
        c.append(c[-1] - 6)  # queda brusca de muitos desvios-padrão
        sig = fetch.tech_signals(pd.Series(c, index=pd.bdate_range("2025-01-01", periods=len(c))))
        self.assertEqual(sig["boll"]["touch"], 0)
        self.assertLess(sig["boll"]["z"], -2.5)

    def test_rsi_bounds(self):
        r = fetch._rsi(np.linspace(100, 50, 100))
        self.assertTrue(((r >= 0) & (r <= 100)).all())
        self.assertLess(r[-1], 5)


if __name__ == "__main__":
    unittest.main()
