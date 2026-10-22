"""Métricas agregadas (nunca por SKU). Sem MAPE: quebra com meses de demanda zero.

Dois níveis:
- "sku_mes": cada par SKU × mês do teste é uma observação;
- "total_mes": soma de todos os SKUs por mês (visão do pedido inteiro).
- "sku_mes_sem_ruptura": só SKU × mês sem sinal de ruptura (venda ≈ demanda).
Todos os baselines são avaliados no MESMO conjunto de linhas (onde todos têm previsão).
"""
import numpy as np
import pandas as pd

from src import config as C


def pinball(y, p, q=C.QUANTIL_OPERACIONAL):
    e = y - p
    return float(np.mean(np.maximum(q * e, (q - 1) * e)))


def metricas(y, p, q=C.QUANTIL_OPERACIONAL):
    y, p = np.asarray(y, float), np.asarray(p, float)
    if y.size == 0:
        return {"n": 0, "MAE": np.nan, "WAPE_%": np.nan, "vies_%": np.nan,
                f"pinball_q{q:g}": np.nan, "cobertura_%": np.nan}
    soma = y.sum()
    return {
        "n": int(y.size),
        "MAE": float(np.mean(np.abs(y - p))),
        "WAPE_%": 100 * float(np.abs(y - p).sum() / soma) if soma else np.nan,
        "vies_%": 100 * float((p - y).sum() / soma) if soma else np.nan,
        f"pinball_q{q:g}": pinball(y, p, q),
        "cobertura_%": 100 * float(np.mean(y <= p)),
    }


def avaliar(teste, previsoes):
    """teste: painel de teste com C.COL_QTD; previsoes: {nome: Series alinhada ao teste}."""
    prev = pd.DataFrame({k: v.loc[teste.index] for k, v in previsoes.items()})
    comum = prev.notna().all(axis=1)
    base = teste.loc[comum, [C.COL_MES, C.COL_QTD, "ruptura"]].join(prev[comum])
    linhas = []
    for nome in previsoes:
        m_sku = metricas(base[C.COL_QTD], base[nome])
        tot = base.groupby(C.COL_MES)[[C.COL_QTD, nome]].sum()
        m_tot = metricas(tot[C.COL_QTD], tot[nome])
        linhas.append({"baseline": nome, "nivel": "sku_mes", **m_sku})
        linhas.append({"baseline": nome, "nivel": "total_mes", **m_tot})
        ok = base[~base["ruptura"]]
        linhas.append({"baseline": nome, "nivel": "sku_mes_sem_ruptura",
                       **metricas(ok[C.COL_QTD], ok[nome])})
    info = {"linhas_teste": int(len(teste)), "linhas_avaliadas": int(comum.sum()),
            "skus_avaliados": int(teste.loc[comum, C.COL_SKU].nunique()),
            "meses_teste": int(base[C.COL_MES].nunique()),
            "cobertura_previsao_por_baseline_%": {k: round(100 * float(prev[k].notna().mean()), 1)
                                                  for k in prev}}
    return pd.DataFrame(linhas), info
