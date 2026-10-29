"""Primeiro modelo (Ridge em Pipeline) x baselines, no MESMO holdout temporal.

Uso:  python -m src.modelo [--fonte real|amostra]

Por que um horizonte de modelagem diferente do HORIZONTE da regra (5):
com 7 meses completos, H = 5 não deixa nenhuma linha avaliável (ver README). Aqui o
modelo prevê o mês t com informação até t − HORIZONTE_MODELO (1 mês). O descasamento
com o lead time de 4–5 meses é declarado como limite no relatório.

Tudo que aprende com dados (imputação, escala, one-hot, Ridge) fica dentro do Pipeline
e é ajustado só no treino de cada fold. As features são defasadas por SKU antes de
qualquer janela (groupby + shift(h)). O teste de vazamento (src/vazamento.py) perturba as
vendas e compras brutas depois de T0 e roda carga -> preparar -> features inteiro.

A marcação de ruptura NÃO entra em nenhuma feature nem filtro de treino: ela vem do estoque
reconstruído a partir da posição do Sankhya em 20/10/2026, descontando as movimentações
posteriores, então não existe versão dela conhecida no corte t. Ela é usada só como rótulo de
diagnóstico ex post (subconjunto sem ruptura e análise dos piores códigos).
"""
import argparse
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_pinball_loss, make_scorer
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src import avaliar, carregar, config as C, preparar, vazamento

H = C.HORIZONTE_MODELO
Q = C.QUANTIL_OPERACIONAL
NUM = ["lag_1", "media_3", "max_3", "media_hist", "n_meses_hist", "largura_m"]
CAT = ["linha", "acabamento", "marca"]
FEATS_TEMPO = ["lag_1", "lag_2", "media_3", "max_3", "media_hist", "n_meses_hist", "p75_6"]


# ---------------------------------------------------------------- dados
def carregar_produtos(fonte):
    """Atributos fixos do código de demanda (não mudam no tempo, não vazam)."""
    if fonte != "real":
        return None
    p = pd.read_csv(C.DIR_BRUTO / C.ARQUIVO_PRODUTOS, sep=";", decimal=",", encoding="utf-8-sig")
    p = p[p["codigo"] == p["codigo_demanda"]]
    p = p.rename(columns={"codigo_demanda": C.COL_SKU})[[C.COL_SKU, "largura_m", "linha", "acabamento", "marca"]]
    p[C.COL_SKU] = p[C.COL_SKU].astype(str)
    return p


def construir_features(painel, produtos, h=H):
    p = painel.sort_values([C.COL_SKU, C.COL_MES]).copy()
    g = p.groupby(C.COL_SKU, sort=False)
    disp = g[C.COL_QTD].shift(h)                      # demanda conhecida em t − h
    gd = disp.groupby(p[C.COL_SKU], sort=False)
    p["lag_1"] = disp
    p["lag_2"] = g[C.COL_QTD].shift(h + 1)
    p["media_3"] = gd.transform(lambda s: s.rolling(3, min_periods=1).mean())
    p["max_3"] = gd.transform(lambda s: s.rolling(3, min_periods=1).max())
    p["media_hist"] = gd.transform(lambda s: s.expanding().mean())
    p["n_meses_hist"] = gd.transform(lambda s: s.expanding().count())
    p["p75_6"] = gd.transform(lambda s: s.rolling(C.JANELA_OPERACIONAL, min_periods=1).quantile(Q))
    if produtos is not None:
        p = p.merge(produtos, on=C.COL_SKU, how="left")
    else:
        p["largura_m"], p["linha"], p["acabamento"], p["marca"] = np.nan, "NA", "NA", "NA"
    return p.sort_values([C.COL_SKU, C.COL_MES]).reset_index(drop=True)


def corte_treino(df):
    """Último mês do treino: os N_MESES_HOLDOUT últimos meses completos ficam para o teste."""
    meses = np.sort(df.loc[~df["mes_parcial"], C.COL_DATA].dropna().dt.to_period("M").unique())
    return meses[-C.N_MESES_HOLDOUT - 1]


def tabela_features(fonte, bruto=None, ate=None):
    """carga -> preparar -> features. Retorna (f, painel, info_carga, info_prep, corte).

    ate: fim do treino usado na seleção da população; None = calculado dos meses completos.
    """
    df, info_carga = carregar.carregar_vendas(fonte, bruto)
    corte = corte_treino(df) if ate is None else ate
    # população (SKUs e 1º mês de cada um) escolhida só com dados até o fim do treino
    painel, info_prep = preparar.preparar_painel(df, ate=corte)
    f = construir_features(painel, carregar_produtos(info_carga["fonte"])).rename(columns={C.COL_QTD: "y"})
    f = f[f["lag_1"].notna()].reset_index(drop=True)          # precisa de ao menos 1 mês conhecido
    return f, painel, info_carga, info_prep, corte


# ---------------------------------------------------------------- modelo
def montar_pipeline():
    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("esc", StandardScaler())]), NUM),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT),
    ])
    return Pipeline([("pre", pre), ("ridge", Ridge(random_state=C.SEMENTE))])


def splits_por_mes(meses_linha, n_splits):
    """TimeSeriesSplit aplicado aos MESES (não às linhas): cada validação é um mês inteiro."""
    meses = np.sort(meses_linha.unique())
    for tr, va in TimeSeriesSplit(n_splits=n_splits).split(meses):
        yield (np.where(meses_linha.isin(meses[tr]))[0], np.where(meses_linha.isin(meses[va]))[0])


def pinball_rel(y, p):
    return 100 * mean_pinball_loss(y, p, alpha=Q) / np.mean(y)


# ---------------------------------------------------------------- gráficos
def graficos(teste, pasta):
    pasta.mkdir(parents=True, exist_ok=True)
    esc = teste["y"].mean()                         # unidade relativa: não revela volume em m²
    r = (teste["y"] - teste["modelo"]) / esc
    pr = teste["modelo"] / esc
    fig, ax = plt.subplots(2, 2, figsize=(10, 7))
    ax[0, 0].scatter(pr, r, s=14, alpha=.7)
    ax[0, 0].axhline(0, color="k", lw=.8)
    ax[0, 0].set(title="Resíduo × previsto", xlabel="previsto (÷ média do teste)", ylabel="resíduo (÷ média)")
    meses = sorted(teste[C.COL_MES].unique())
    ax[0, 1].boxplot([r[teste[C.COL_MES] == m] for m in meses], tick_labels=[str(m) for m in meses])
    ax[0, 1].axhline(0, color="k", lw=.8)
    ax[0, 1].set(title="Resíduo por mês do teste", ylabel="resíduo (÷ média)")
    faixa = pd.qcut(teste["media_hist"].rank(method="first"), 3, labels=["baixo giro", "médio", "alto giro"])
    ax[1, 0].boxplot([r[faixa == f] for f in faixa.cat.categories], tick_labels=list(faixa.cat.categories))
    ax[1, 0].axhline(0, color="k", lw=.8)
    ax[1, 0].set(title="Resíduo por faixa de volume", ylabel="resíduo (÷ média)")
    ax[1, 1].hist(r, bins=25)
    ax[1, 1].set(title="Histograma dos resíduos", xlabel="resíduo (÷ média)")
    fig.tight_layout()
    fig.savefig(pasta / "residuos.png", dpi=160)
    plt.close(fig)


# ---------------------------------------------------------------- fluxo
def main(fonte="real"):
    f, painel, info_carga, info_prep, corte = tabela_features(fonte)
    fonte, cfg, _ = carregar.escolher_fonte(info_carga["fonte"])
    cortes_vazamento = vazamento.testar_entrada(
        carregar.ler_bruto(fonte), cfg, lambda b: tabela_features(fonte, b, ate=corte)[0],
        list(dict.fromkeys(FEATS_TEMPO + NUM + CAT)), H)
    # Cada linha t exige o SKU no painel em t − 1, ou seja, 1ª venda <= t − 1 (conhecida no
    # corte da previsão). Por isso a população de cada fold do CV já é causal sem recorte extra.
    inicio = painel.groupby(C.COL_SKU)[C.COL_MES].min()
    assert (f[C.COL_MES] > f[C.COL_SKU].map(inicio)).all()

    meses = np.sort(f[C.COL_MES].unique())
    assert meses[-C.N_MESES_HOLDOUT - 1] == corte
    treino, teste = f[f[C.COL_MES] <= corte].copy(), f[f[C.COL_MES] > corte].copy()
    assert treino[C.COL_MES].max() < teste[C.COL_MES].min()

    busca = GridSearchCV(
        montar_pipeline(), {"ridge__alpha": C.ALPHAS_RIDGE},
        cv=list(splits_por_mes(treino[C.COL_MES].reset_index(drop=True), C.N_SPLITS_CV)),
        scoring=make_scorer(mean_pinball_loss, alpha=Q, greater_is_better=False))
    busca.fit(treino[NUM + CAT], treino["y"])
    alpha = busca.best_params_["ridge__alpha"]

    # CV temporal do modelo escolhido: pinball relativo por fold
    cv_folds = []
    for tr, va in splits_por_mes(treino[C.COL_MES].reset_index(drop=True), C.N_SPLITS_CV):
        m = montar_pipeline().set_params(ridge__alpha=alpha).fit(treino.iloc[tr][NUM + CAT], treino.iloc[tr]["y"])
        pv = np.clip(m.predict(treino.iloc[va][NUM + CAT]), 0, None)
        cv_folds.append(pinball_rel(treino.iloc[va]["y"], pv))

    bruto = busca.best_estimator_.predict(teste[NUM + CAT])
    n_neg = int((bruto < 0).sum())
    teste["modelo"] = np.clip(bruto, 0, None)
    teste["trivial_media"] = teste["media_hist"]
    teste["operacional_media3"] = teste["media_3"]
    teste["operacional_p75_6"] = teste["p75_6"]
    abord = ["trivial_media", "operacional_media3", "operacional_p75_6", "modelo"]

    linhas = []
    for nivel, d in [("sku_mes", teste), ("sku_mes_sem_ruptura", teste[~teste["ruptura"]])]:
        for a in abord:
            m = avaliar.metricas(d["y"], d[a], Q)
            linhas.append({"abordagem": a, "nivel": nivel, "n": m["n"],
                           "pinball_rel_%": pinball_rel(d["y"], d[a]), "WAPE_%": m["WAPE_%"],
                           "vies_%": m["vies_%"], "cobertura_%": m["cobertura_%"]})
    tab = pd.DataFrame(linhas)

    saida = C.DIR_SAIDA_REAL if info_carga["fonte"] == "real" else C.DIR_SAIDA_AMOSTRA
    graficos(teste, saida / "figs")
    teste["erro_abs"] = (teste["y"] - teste["modelo"]).abs()
    piores = (teste.groupby(C.COL_SKU)
              .agg(erro_abs=("erro_abs", "sum"), y=("y", "sum"), ruptura_meses=("ruptura", "sum"),
                   linha=("linha", "first"))
              .assign(parcela_erro_pct=lambda x: 100 * x["erro_abs"] / x["erro_abs"].sum())
              .sort_values("erro_abs", ascending=False).head(5))
    resumo = {
        "fonte": info_carga["fonte"], "horizonte_modelo": H, "corte_treino": str(corte),
        "meses_treino": [str(m) for m in np.sort(treino[C.COL_MES].unique())],
        "meses_teste": [str(m) for m in np.sort(teste[C.COL_MES].unique())],
        "linhas_treino": len(treino), "linhas_teste": len(teste), "skus": int(f[C.COL_SKU].nunique()),
        "skus_treino": int(treino[C.COL_SKU].nunique()), "skus_teste": int(teste[C.COL_SKU].nunique()),
        "painel": {k: info_prep[k] for k in ("selecao_ate", "skus", "linhas_sku_mes",
                                             "pct_sku_mes_zerados", "pct_sku_mes_com_ruptura")},
        "features": NUM + CAT, "alpha_escolhido": alpha, "cv_pinball_rel_folds": [round(x, 1) for x in cv_folds],
        "cv_pinball_rel_media": round(float(np.mean(cv_folds)), 1),
        "cv_pinball_rel_desvio": round(float(np.std(cv_folds, ddof=1)), 1),   # amostral: só 3 folds
        "previsoes_negativas_antes_do_clip": n_neg,
        "teste_vazamento": {"tipo": "perturbação na entrada (vendas e compras > T0)", "cortes": cortes_vazamento,
                            "resultado": "passou"},
        "pct_teste_com_ruptura": round(100 * teste["ruptura"].mean(), 1),
    }
    (saida / "metricas_modelo.json").write_text(json.dumps(
        {"metricas": tab.round(2).to_dict("records"), **resumo,
         "piores_skus": piores.round(1).reset_index().to_dict("records")},
        ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    pd.set_option("display.width", 200)
    print(tab.round(1).to_string(index=False))
    print(json.dumps(resumo, ensure_ascii=False, indent=1, default=str))
    print(piores.round(1).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonte", choices=["auto", "real", "amostra"], default="auto")
    main(ap.parse_args().fonte)
