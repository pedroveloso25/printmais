"""Figura de 2 painéis do relatório (seção 8): resíduo × previsto e resíduo por faixa de volume.

Uso:  python -m scripts.figura_residuos_2p [--fonte real|amostra]
Rodar depois de `python -m src.modelo`. Refaz o MESMO ajuste de src/modelo.py (mesma config,
mesma semente, mesmos splits por mês) e confere α e métricas contra metricas_modelo.json antes
de plotar: se divergir, para com erro em vez de gerar uma figura de outro modelo.
Resíduo = (real − previsto) ÷ demanda média do teste; mesmos rótulos de residuos.png.
"""
import argparse
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import make_scorer, mean_pinball_loss
from sklearn.model_selection import GridSearchCV

from src import avaliar, carregar, config as C, modelo as M, preparar


def main(fonte="auto"):
    df, info_carga = carregar.carregar_vendas(fonte)
    painel, _ = preparar.preparar_painel(df)
    f = M.construir_features(painel, M.carregar_produtos(info_carga["fonte"])).rename(columns={C.COL_QTD: "y"})
    f = f[f["lag_1"].notna()].reset_index(drop=True)
    meses = np.sort(f[C.COL_MES].unique())
    corte = meses[-C.N_MESES_HOLDOUT - 1]
    treino, teste = f[f[C.COL_MES] <= corte].copy(), f[f[C.COL_MES] > corte].copy()
    busca = GridSearchCV(
        M.montar_pipeline(), {"ridge__alpha": C.ALPHAS_RIDGE},
        cv=list(M.splits_por_mes(treino[C.COL_MES].reset_index(drop=True), C.N_SPLITS_CV)),
        scoring=make_scorer(mean_pinball_loss, alpha=M.Q, greater_is_better=False))
    busca.fit(treino[M.NUM + M.CAT], treino["y"])
    teste["modelo"] = np.clip(busca.best_estimator_.predict(teste[M.NUM + M.CAT]), 0, None)

    saida = C.DIR_SAIDA_REAL if info_carga["fonte"] == "real" else C.DIR_SAIDA_AMOSTRA
    ref = json.loads((saida / "metricas_modelo.json").read_text(encoding="utf-8"))
    assert busca.best_params_["ridge__alpha"] == ref["alpha_escolhido"], "α diferente do metricas_modelo.json"
    m_ref = next(m for m in ref["metricas"] if m["nivel"] == "sku_mes" and m["abordagem"] == "modelo")
    m = avaliar.metricas(teste["y"], teste["modelo"], M.Q)
    assert round(M.pinball_rel(teste["y"], teste["modelo"]), 2) == m_ref["pinball_rel_%"], "pinball diverge"
    assert round(m["vies_%"], 2) == m_ref["vies_%"], "viés diverge"

    esc = teste["y"].mean()                         # unidade relativa: não revela volume em m²
    r = (teste["y"] - teste["modelo"]) / esc
    pr = teste["modelo"] / esc
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.2))
    ax[0].scatter(pr, r, s=14, alpha=.7)
    ax[0].axhline(0, color="k", lw=.8)
    ax[0].set(title="Resíduo × previsto", xlabel="previsto (÷ média do teste)", ylabel="resíduo (÷ média)")
    faixa = pd.qcut(teste["media_hist"].rank(method="first"), 3, labels=["baixo giro", "médio", "alto giro"])
    ax[1].boxplot([r[faixa == fx] for fx in faixa.cat.categories], tick_labels=list(faixa.cat.categories))
    ax[1].axhline(0, color="k", lw=.8)
    ax[1].set(title="Resíduo por faixa de volume", ylabel="resíduo (÷ média)")
    fig.tight_layout()
    (saida / "figs").mkdir(parents=True, exist_ok=True)
    fig.savefig(saida / "figs" / "residuos_2p.png", dpi=200)
    plt.close(fig)
    print("ok:", saida.name + "/figs/residuos_2p.png (confere com metricas_modelo.json)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonte", choices=["auto", "real", "amostra"], default="auto")
    main(ap.parse_args().fonte)
