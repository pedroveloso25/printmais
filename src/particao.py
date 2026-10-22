"""Features com defasagem mínima de HORIZONTE e split estritamente temporal.

Toda feature da linha (SKU, t) é calculada sobre a série do SKU deslocada de H meses
(groupby + shift(H)), ou seja, só usa demanda até t − H. `verificar_sem_vazamento`
prova isso empiricamente: embaralha a demanda depois de um mês T0 e exige que as
features de todos os meses t ≤ T0 + H continuem idênticas.
"""
import numpy as np
import pandas as pd

from src import config as C

FEATURES = ["media_hist", "mediana_hist", "sazonal_12", "p75_janela", "n_meses_hist"]


def construir_features(painel, h=C.HORIZONTE, janela=C.JANELA_OPERACIONAL, q=C.QUANTIL_OPERACIONAL,
                       min_meses=C.MIN_MESES_JANELA):
    # o painel é contíguo por SKU (preparar.py completa os meses), então shift de posição
    # = shift de calendário
    p = painel.sort_values([C.COL_SKU, C.COL_MES]).copy()
    g = p.groupby(C.COL_SKU, sort=False)[C.COL_QTD]
    # demanda conhecida na data de decisão (t − h); tudo abaixo parte daqui
    disp = g.shift(h)
    gd = disp.groupby(p[C.COL_SKU], sort=False)
    p["media_hist"] = gd.transform(lambda s: s.expanding().mean())
    p["mediana_hist"] = gd.transform(lambda s: s.expanding().median())
    p["n_meses_hist"] = gd.transform(lambda s: s.expanding().count())
    p["p75_janela"] = gd.transform(lambda s: s.rolling(janela, min_periods=min_meses).quantile(q))
    # mesmo mês do ano anterior: t − 12 ≤ t − h porque h ≤ 12
    assert h <= 12, "sazonal ingênuo exige HORIZONTE ≤ 12"
    p["sazonal_12"] = g.shift(12)
    p["mes_info_max"] = p[C.COL_MES] - h
    return p


def verificar_sem_vazamento(painel, h=C.HORIZONTE, n_cortes=3, semente=0, **kw_features):
    """Falha (AssertionError) se alguma feature em t depender de demanda posterior a t − h."""
    meses = np.sort(painel[C.COL_MES].unique())
    if len(meses) < h + 3:
        return
    rng = np.random.default_rng(semente)
    base = construir_features(painel, h, **kw_features).set_index([C.COL_SKU, C.COL_MES])[FEATURES]
    for t0 in rng.choice(meses[1:-h], size=min(n_cortes, len(meses) - h - 1), replace=False):
        alterado = painel.copy()
        futuro = alterado[C.COL_MES] > t0
        alterado.loc[futuro, C.COL_QTD] = rng.uniform(0, 1e6, futuro.sum())
        novo = construir_features(alterado, h, **kw_features).set_index([C.COL_SKU, C.COL_MES])[FEATURES]
        meses_idx = base.index.get_level_values(C.COL_MES)
        visiveis = meses_idx <= t0 + h
        a, b = base[visiveis], novo.loc[base.index[visiveis]]
        iguais = np.isclose(a.to_numpy(float), b.to_numpy(float), equal_nan=True)
        assert iguais.all(), (
            f"VAZAMENTO: features {[str(x) for x in np.array(FEATURES)[~iguais.all(axis=0)]]} "
            f"usam dado posterior a t - {h} (corte de teste {t0})")


def data_corte(painel):
    if C.DATA_CORTE:
        return pd.Period(C.DATA_CORTE, "M")
    return painel[C.COL_MES].max() - C.N_MESES_TESTE


def dividir_temporal(feats, corte, h=C.HORIZONTE):
    treino = feats[feats[C.COL_MES] <= corte]
    teste = feats[feats[C.COL_MES] > corte]
    assert treino[C.COL_MES].max() < teste[C.COL_MES].min(), "split não é temporal"
    assert (feats["mes_info_max"] <= feats[C.COL_MES] - h).all()
    return treino, teste
