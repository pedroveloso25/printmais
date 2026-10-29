"""Sensibilidade ao filtro `incluir` (exclusões de negócio: marca, descrição e código).

Uso:  python -m scripts.sensibilidade_incluir
Rodar depois de `python -m src.modelo --fonte real`. Não altera o modelo oficial.

Não foi possível confirmar se todas as exclusões de negócio já eram conhecidas em jul/2026.
Para medir o efeito, ignora `incluir` (todas as linhas entram). Os códigos excluídos sem venda
até o fim do treino continuam fora pela regra de população (preparar_painel com ate=corte).
Nenhum código de demanda mistura SKUs incluídos e excluídos, então os alvos dos códigos
oficiais não mudam: só entram códigos novos.

  A) modelo oficial (treinado sem esses códigos), avaliado no teste com eles;
  B) pipeline inteiro com esses códigos (busca de α, treino e teste).

Saída: relatorios/real/sensibilidade_incluir.json. Imprime só métricas relativas e contagens.
"""
import json

import numpy as np
import pandas as pd
from sklearn.metrics import make_scorer, mean_pinball_loss
from sklearn.model_selection import GridSearchCV

from src import avaliar, carregar, config as C, modelo as M

ABORD = {"trivial_media": "media_hist", "operacional_media3": "media_3", "operacional_p75_6": "p75_6"}


def ajustar(treino):
    busca = GridSearchCV(
        M.montar_pipeline(), {"ridge__alpha": C.ALPHAS_RIDGE},
        cv=list(M.splits_por_mes(treino[C.COL_MES].reset_index(drop=True), C.N_SPLITS_CV)),
        scoring=make_scorer(mean_pinball_loss, alpha=M.Q, greater_is_better=False))
    return busca.fit(treino[M.NUM + M.CAT], treino["y"])


def quadro(teste, previsto):
    linhas = []
    for nivel, d in [("sku_mes", teste), ("sku_mes_sem_ruptura", teste[~teste["ruptura"]])]:
        prev = {**{a: d[c] for a, c in ABORD.items()}, "modelo": previsto[d.index]}
        for a, p in prev.items():
            m = avaliar.metricas(d["y"], p, M.Q)
            linhas.append({"abordagem": a, "nivel": nivel, "n": m["n"],
                           "pinball_rel_%": round(M.pinball_rel(d["y"], p), 2),
                           "vies_%": round(m["vies_%"], 2), "WAPE_%": round(m["WAPE_%"], 2)})
    return linhas


def main():
    f, _, _, _, corte = M.tabela_features("real")
    bruto = carregar.ler_bruto("real")
    for col in C.FONTE_REAL["filtro_verdadeiro"]:
        bruto[col] = "True"
    g, _, _, _, _ = M.tabela_features("real", bruto, ate=corte)

    tr_of, te_of = f[f[C.COL_MES] <= corte], f[f[C.COL_MES] > corte]
    tr, te = g[g[C.COL_MES] <= corte].copy(), g[g[C.COL_MES] > corte].copy()
    novos = sorted(set(g[C.COL_SKU]) - set(f[C.COL_SKU]))
    oficial = ajustar(tr_of)
    completo = ajustar(tr)
    prev_a = pd.Series(np.clip(oficial.predict(te[M.NUM + M.CAT]), 0, None), index=te.index)
    prev_b = pd.Series(np.clip(completo.predict(te[M.NUM + M.CAT]), 0, None), index=te.index)

    # parcela do erro do modelo oficial que cai nos códigos novos (cenário A)
    erro = (te["y"] - prev_a).abs()
    novo = te[C.COL_SKU].isin(novos)
    resumo = {
        "codigos_oficiais": int(f[C.COL_SKU].nunique()), "codigos_novos": len(novos),
        "linhas_treino": [len(tr_of), len(tr)], "linhas_teste": [len(te_of), len(te)],
        "linhas_teste_novas": int(novo.sum()),
        "pct_erro_abs_teste_nos_novos_A": round(100 * erro[novo].sum() / erro.sum(), 1),
        "pct_demanda_teste_nos_novos": round(100 * te.loc[novo, "y"].sum() / te["y"].sum(), 1),
        "alpha_A": oficial.best_params_["ridge__alpha"], "alpha_B": completo.best_params_["ridge__alpha"],
        "A_modelo_oficial_teste_ampliado": quadro(te, prev_a),
        "B_pipeline_com_codigos": quadro(te, prev_b),
    }
    (C.DIR_SAIDA_REAL / "sensibilidade_incluir.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    for k, v in resumo.items():
        if not isinstance(v, list) or not v or not isinstance(v[0], dict):
            print(f"{k}: {v}")
    for cen in ("A_modelo_oficial_teste_ampliado", "B_pipeline_com_codigos"):
        print(cen)
        print(pd.DataFrame(resumo[cen]).to_string(index=False))


if __name__ == "__main__":
    main()
