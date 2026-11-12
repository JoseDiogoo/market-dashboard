"""Esticamento do preço (ponto B): distância do fecho à SMA 50 em ATR, comparada com a PRÓPRIA história da ação (percentil), sem limiar fixo.
Evidência: backtest próprio (research/calibrate_levels.py, 260 ações, 10 anos): quando este percentil >= 90, o retorno dos 20 dias seguintes foi ~0,9 pp MAIS BAIXO do que no resto
(IC 95%, bootstrap por ação, exclui zero). Não piora a queda máxima (ficou ~0,45 pp mais rasa): é um efeito pequeno sobre o retorno esperado, não um aviso de queda.
Os NÍVEIS técnicos (médias, VWAP ancorado, Volume Profile, pivôs, números redondos) não passaram o teste contra níveis aleatórios (0/20 após Holm) e por isso não são usados."""
import numpy as np
import pandas as pd

MIN_N = 150  # observações mínimas da própria história para calcular o percentil


def stretch(hd, w=50):
    """hd = OHLC diário (idealmente 2 anos). Devolve {d, pct, n, sma, atr, q75, x75} ou None."""
    try:
        d = hd[["High", "Low", "Close"]].dropna()
        c, pc = d["Close"], d["Close"].shift(1)
        tr = pd.concat([d["High"] - d["Low"], (d["High"] - pc).abs(), (d["Low"] - pc).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
        sma = c.rolling(w).mean()
        x = ((c - sma) / atr.clip(lower=1e-9)).dropna().iloc[-504:]
        if len(x) < MIN_N or not np.isfinite(atr.iloc[-1]):
            return None
        cur = float(x.iloc[-1])
        q75 = float(x.iloc[:-1].quantile(.75))
        return {"d": round(cur, 2), "pct": int(round(100 * float((x.iloc[:-1] < cur).mean()))), "n": int(len(x)), "sma": round(float(sma.iloc[-1]), 4),
                "atr": round(float(atr.iloc[-1]), 4), "q75": round(q75, 2), "x75": round(float(sma.iloc[-1]) + q75 * float(atr.iloc[-1]), 4)}
    except Exception:
        return None
