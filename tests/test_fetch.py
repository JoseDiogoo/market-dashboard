import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
import fetch


class RankingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads(Path('data.js').read_text(encoding='utf-8')[len('window.DATA='):])

    def setUp(self):
        self.d = copy.deepcopy(self.snapshot)

    def test_elite_requires_cash_and_debt(self):
        fetch.rerank(self.d)
        elite = next(k for k, t in self.d['tickers'].items() if t['elite'])
        for field, value in [('fcfy', None), ('fcfy', 0), ('nd', None), ('nd', 4)]:
            with self.subTest(field=field, value=value):
                d = copy.deepcopy(self.d)
                d['tickers'][elite][field] = value
                fetch.rerank(d)
                self.assertFalse(d['tickers'][elite]['elite'])

    def test_target_does_not_change_fundamental_score(self):
        fetch.rerank(self.d)
        t = next(iter(self.d['tickers'].values()))
        score = t['score']
        t['upside'] = -50
        fetch.rerank(self.d)
        low = t['rank']
        t['upside'] = 50
        fetch.rerank(self.d)
        self.assertEqual(t['score'], score)
        self.assertEqual(t['rank'] - low, 23)

    def test_analyst_factor_is_not_counted_again_in_final_ranking(self):
        fetch.rerank(self.d)
        ranks = {k: t['rank'] for k, t in self.d['tickers'].items()}
        ci = self.d['cols'].index('fa')
        for row in self.d['rows']:
            row[ci] = 0
        fetch.rerank(self.d)
        self.assertEqual(ranks, {k: t['rank'] for k, t in self.d['tickers'].items()})

    @patch('fetch.news.market', side_effect=RuntimeError('offline'))
    @patch('fetch.yf.download', side_effect=RuntimeError('offline'))
    @patch('fetch.fetch_universe', side_effect=RuntimeError('offline'))
    def test_failed_refresh_preserves_dates(self, *_):
        original = self.d['updated']
        prices = [(r[0], r[5], r[-1]) for r in self.d['rows']]
        fetch.refresh_rows(self.d)
        self.assertEqual(self.d['updated'], original)
        self.assertEqual(self.d['analysis_updated'], original)
        self.assertEqual([(r[0], r[5], r[-1]) for r in self.d['rows']], prices)
        self.assertFalse(self.d['source']['ok'])
        self.assertEqual(self.d['source']['mode'], 'stale')

    @patch('fetch.news.market', side_effect=RuntimeError('offline'))
    @patch('fetch.fetch_universe', side_effect=RuntimeError('offline'))
    def test_download_preserves_bar_date_and_recomputes_ranking(self, *_):
        k = self.d['order'][0]
        old = self.d['tickers'][k]['price']
        h = pd.DataFrame({('Close', k): [old, old * 1.5]}, index=pd.to_datetime(['2026-11-05', '2026-11-06'], utc=True))
        with patch('fetch.yf.download', return_value=h):
            fetch.refresh_rows(self.d)
        tm = dict(zip(self.d['cols'], next(r for r in self.d['rows'] if r[0] == k)))['tm']
        self.assertEqual(tm, int(h.index[-1].timestamp() / 60))
        self.assertEqual(self.d['source']['mode'], 'partial')
        self.assertTrue(self.d['source']['ok'])
        t = self.d['tickers'][k]
        self.assertEqual(t['price'], round(old * 1.5, 2))
        if t['target']:
            self.assertAlmostEqual(t['upside'], (t['target'] / t['price'] - 1) * 100, delta=.11)
        expected = fetch.rerank(copy.deepcopy(self.d))
        self.assertEqual(self.d['order'], expected['order'])
        self.assertEqual(self.d['highlights'], expected['highlights'])


if __name__ == '__main__':
    unittest.main()
