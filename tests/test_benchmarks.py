import json, pathlib, unittest

import benchmarks as B

ROOT = pathlib.Path(__file__).parent.parent


class BenchTests(unittest.TestCase):
    def test_mapeamento_cobre_dados_e_damodaran(self):
        d = json.loads((ROOT / "data.js").read_text(encoding="utf-8")[len("window.DATA="):])
        inds = {t.get("industry") for t in d["tickers"].values() if t.get("industry")}
        self.assertEqual(inds - set(B.YMAP), set(), "indústrias do Yahoo sem mapeamento")
        for y, (dn, _) in B.YMAP.items():
            self.assertIn(dn, B.DAM["ind"], f"{y} -> {dn} não existe no Damodaran")

    def test_percentil_e_grupo(self):
        mk = lambda om: {"sector": "S", "industry": "Software - Application", "om": om, "q": {}}
        T = {str(i): mk(i) for i in range(1, 13)}  # margens 1..12, mesma indústria (n=12 >= MIN_IND)
        st = B.peer_stats(T)
        b = B.bench(T["12"], st)["om"]
        self.assertEqual((b["grp"], b["n"], b["q"][1]), ("ind", 12, 6.5))
        self.assertGreater(b["pct"], 90)
        self.assertEqual(B.bench(T["1"], st)["om"]["pct"], 4)  # posto médio: (0+1)/2 de 12 = 4%

    def test_pequeno_grupo_cai_para_setor_e_financeiras_ignoram_ebitda(self):
        T = {str(i): {"sector": "S", "industry": f"X{i}", "om": i, "q": {}} for i in range(1, 12)}
        self.assertEqual(B.bench(T["5"], B.peer_stats(T))["om"]["grp"], "sec")
        bank = {"sector": "Financial Services", "industry": "Banks - Regional", "om": 40, "eve": 9, "fpe": 11, "q": {}}
        b = B.bench(bank, B.peer_stats({"b": bank}))
        self.assertNotIn("om", b); self.assertNotIn("eve", b)

    def test_valores_absurdos_excluidos(self):
        self.assertIsNone(B._clean(-3, (0.01, 100)))
        self.assertIsNone(B._clean(float("nan"), (0, 1)))
        self.assertEqual(B._clean(12, (0.01, 100)), 12.0)


if __name__ == "__main__":
    unittest.main()
