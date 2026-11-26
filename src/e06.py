"""Entrega 6: decomposição do ganho (T1) e defasamento (T2).

Uso:  python -m src.e06 [--fonte auto|real|amostra]

Mesma tabela de features, população (30 códigos `incluir`), horizonte (H = 1) e holdout
(ago–set) do modelo da E05 (src/modelo.py). Nada aqui muda o pipeline da E05.

T1 — três níveis, mesma partição, mesma métrica (pinball em τ):
  B0  regra da empresa: P75 dos últimos 6 meses (coluna p75_6);
  B1  s × B0, com s calibrado SÓ no treino para que ~τ dos reais fiquem abaixo de s × B0;
  M   três modelos de quantil: linear (QuantileRegressor, L1), árvore (DecisionTree + fator s
      calibrado nas previsões fora da amostra do CV de treino) e GradientBoosting(loss=quantile).
  efeito quantil = B1 − B0; efeito modelagem = M − B1. Negativo = melhora.
  Incerteza: bootstrap por código (os 2 meses de teste do mesmo código não são independentes).
  Sensibilidade: τ = 0,6 e 0,9 refazem s e retreinam os modelos naquele τ; B0 fica igual
  (a regra da empresa é sempre P75).

T2 — autocorrelação da demanda mensal por código, lag 1 × lag 4 × lag 5, com cada série
dividida pela média do próprio código antes de juntar os pares. Usa os 7 meses completos
(inclui ago–set): é diagnóstico descritivo, não escolhe modelo nem hiperparâmetro.

T3 e T4: src/e06_decisao.py. Saída: relatorios/<fonte>/e06.json. Imprime só métricas relativas e contagens.
"""
import argparse
import json
import sys
import time

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import QuantileRegressor
from sklearn.metrics import make_scorer, mean_pinball_loss
from sklearn.model_selection import GridSearchCV, ParameterGrid
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeRegressor

from src import avaliar, carregar, config as C, e06_decisao as D, modelo as M, vazamento

X_COLS = M.NUM + M.CAT


# ---------------------------------------------------------------- fator de segurança
def fator_s(y, b, tau):
    """s tal que ~tau dos reais fiquem abaixo de s·b: quantil tau de y/b (só b > 0).

    Com b = 0, s·b = 0 para qualquer s: essas linhas não informam s e ficam de fora.
    """
    y, b = np.asarray(y, float), np.asarray(b, float)
    ok = b > 0
    return float(np.quantile(y[ok] / b[ok], tau))


def fator_s_pinball(y, b, tau):
    """s que minimiza a pinball de s·b no treino (variante, só para sensibilidade).

    Para b > 0, ρτ(y − s·b) = b·ρτ(y/b − s): o ótimo é o quantil tau de y/b PONDERADO por b.
    Difere de fator_s porque códigos de volume alto pesam mais.
    """
    y, b = np.asarray(y, float), np.asarray(b, float)
    ok = b > 0
    r, w = y[ok] / b[ok], b[ok]
    ordem = np.argsort(r)
    acum = np.cumsum(w[ordem])
    return float(r[ordem][np.searchsorted(acum, tau * acum[-1])])


# ---------------------------------------------------------------- modelos de quantil
def pre():
    """O mesmo pré-processamento da E05 (imputação + escala + one-hot), sem ajuste."""
    return clone(M.montar_pipeline().named_steps["pre"])


def pinball_scorer(tau):
    return make_scorer(mean_pinball_loss, alpha=tau, greater_is_better=False)


def ajustar_busca(estimador, grade, treino, cv, tau):
    busca = GridSearchCV(Pipeline([("pre", pre()), ("est", estimador)]),
                         {f"est__{k}": v for k, v in grade.items()}, cv=cv, scoring=pinball_scorer(tau))
    busca.fit(treino[X_COLS], treino["y"])
    return busca.best_estimator_, {k.removeprefix("est__"): v for k, v in busca.best_params_.items()}, \
        -busca.best_score_


class ArvoreComFator:
    """Árvore de regressão (prevê a média da folha) × fator s calibrado fora da amostra.

    O sklearn não tem árvore com perda quantil. Calibrar s nas previsões do próprio treino
    daria s ≈ 1 (a árvore decora o treino); por isso s vem das previsões de validação do CV
    temporal, que são previsões honestas de meses que a árvore não viu.
    """

    def __init__(self, pipeline, s):
        self.pipeline, self.s = pipeline, s

    def predict(self, X):
        return self.s * np.clip(self.pipeline.predict(X), 0, None)


def ajustar_arvore(treino, cv, tau):
    X, y = treino[X_COLS], treino["y"]

    def novo(params):
        return Pipeline([("pre", pre()), ("est", DecisionTreeRegressor(random_state=C.SEMENTE, **params))])

    melhor = None
    for params in ParameterGrid(C.GRADE_ARVORE):
        oof = [(va, np.clip(novo(params).fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[va]), 0, None))
               for tr, va in cv]
        idx = np.concatenate([va for va, _ in oof])
        s = fator_s(y.iloc[idx], np.concatenate([p for _, p in oof]), tau)
        # mesmo critério do GridSearchCV: média da pinball por fold
        score = np.mean([mean_pinball_loss(y.iloc[va], s * p, alpha=tau) for va, p in oof])
        if melhor is None or score < melhor[0]:
            melhor = (score, params, s)
    score, params, s = melhor
    return ArvoreComFator(novo(params).fit(X, y), s), {**params, "s_oof": round(s, 3)}, score


def ajustar_modelos(treino, tau):
    cv = list(M.splits_por_mes(treino[C.COL_MES], C.N_SPLITS_CV))
    out = {}
    for nome, ajuste in [
        ("M_linear_quantil", lambda: ajustar_busca(QuantileRegressor(quantile=tau, solver="highs"),
                                                   C.GRADE_LINEAR, treino, cv, tau)),
        ("M_arvore_fator", lambda: ajustar_arvore(treino, cv, tau)),
        ("M_gb_quantil", lambda: ajustar_busca(
            GradientBoostingRegressor(loss="quantile", alpha=tau, random_state=C.SEMENTE),
            C.GRADE_GB, treino, cv, tau)),
    ]:
        t0 = time.perf_counter()
        est, params, cv_pinball = ajuste()
        out[nome] = {"est": est, "params": params, "cv_pinball": cv_pinball,
                     "tempo_busca_s": time.perf_counter() - t0}
    return out


# ---------------------------------------------------------------- avaliação
def pinball_rel(y, p, tau):
    """Pinball ÷ média do real, em %. Mesmo denominador para todos: diferenças são comparáveis."""
    return 100 * mean_pinball_loss(y, p, alpha=tau) / np.mean(y)


def quadro(teste, abord, tau):
    linhas = []
    for a in abord:
        m = avaliar.metricas(teste["y"], teste[a], tau)
        linhas.append({"abordagem": a, "n": m["n"], "pinball_rel_%": pinball_rel(teste["y"], teste[a], tau),
                       "MAE": m["MAE"], "WAPE_%": m["WAPE_%"], "vies_%": m["vies_%"],
                       "cobertura_%": m["cobertura_%"]})
    return pd.DataFrame(linhas)


def bootstrap_diferencas(teste, pares, tau, n_boot=C.N_BOOT, semente=C.SEMENTE):
    """IC 95% das diferenças de pinball relativa, reamostrando CÓDIGOS (não linhas)."""
    rng = np.random.default_rng(semente)
    grupos = [g.index.to_numpy() for _, g in teste.groupby(C.COL_SKU)]
    dif = {f"{a} - {b}": [] for a, b in pares}
    for _ in range(n_boot):
        idx = np.concatenate([grupos[i] for i in rng.integers(0, len(grupos), len(grupos))])
        d = teste.loc[idx]
        for a, b in pares:
            dif[f"{a} - {b}"].append(pinball_rel(d["y"], d[a], tau) - pinball_rel(d["y"], d[b], tau))
    out = {}
    for (a, b), (k, v) in zip(pares, dif.items()):
        v = np.array(v)
        out[k] = {"ponto": pinball_rel(teste["y"], teste[a], tau) - pinball_rel(teste["y"], teste[b], tau),
                  "ic95": [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))],
                  "pct_boot_melhora": float(100 * np.mean(v < 0))}
    return out


def decomposicao(treino, teste, tau):
    teste = teste.copy()
    s = fator_s(treino["y"], treino["p75_6"], tau)
    s_pin = fator_s_pinball(treino["y"], treino["p75_6"], tau)
    s_m3 = fator_s(treino["y"], treino["media_3"], tau)
    teste["B0_p75_6"] = teste["p75_6"]
    teste["B1_s_x_p75_6"] = s * teste["p75_6"]
    teste["B1pin_s_x_p75_6"] = s_pin * teste["p75_6"]
    teste["ref_media3"] = teste["media_3"]
    teste["ref_s_x_media3"] = s_m3 * teste["media_3"]

    modelos = ajustar_modelos(treino, tau)
    custo = {}
    for nome, m in modelos.items():
        t0 = time.perf_counter()
        teste[nome] = np.clip(m["est"].predict(teste[X_COLS]), 0, None)
        custo[nome] = {"tempo_busca_s": round(m["tempo_busca_s"], 2),
                       "tempo_inferencia_ms": round(1000 * (time.perf_counter() - t0), 2)}
    nomes_m = list(modelos)
    abord = ["B0_p75_6", "B1_s_x_p75_6", *nomes_m, "B1pin_s_x_p75_6", "ref_media3", "ref_s_x_media3"]
    tab = quadro(teste, abord, tau)
    pares = [("B1_s_x_p75_6", "B0_p75_6")] + [(m, "B1_s_x_p75_6") for m in nomes_m] \
        + [("ref_s_x_media3", "ref_media3")]
    return {
        "tau": tau,
        "s_cobertura_treino": s, "s_pinball_treino": s_pin, "s_media3_treino": s_m3,
        "cobertura_treino_B0_%": float(100 * np.mean(treino["y"] <= treino["p75_6"])),
        "cobertura_treino_B1_%": float(100 * np.mean(treino["y"] <= s * treino["p75_6"])),
        "modelos": {n: {"params": m["params"], "cv_pinball_rel_%": 100 * m["cv_pinball"] / treino["y"].mean(),
                        **custo[n]} for n, m in modelos.items()},
        "quadro": tab,
        "efeitos": bootstrap_diferencas(teste, pares, tau),
    }, teste, modelos


# ---------------------------------------------------------------- T2
def _pares(p, k, sem_ruptura):
    """Pares (x_t, x_{t+k}) dentro de cada código; com sem_ruptura, descarta par com ruptura."""
    g = p.groupby(C.COL_SKU, sort=False)
    d = pd.DataFrame({C.COL_SKU: p[C.COL_SKU], "a": p["x"], "b": g["x"].shift(-k),
                      "rup": p["ruptura"] | g["ruptura"].shift(-k, fill_value=False)}).dropna()
    return d[~d["rup"]] if sem_ruptura else d


def _medir(d):
    a, b = d["a"] - 1, d["b"] - 1          # desvio em relação à média do código (= 1)
    den = np.sqrt((a ** 2).sum() * (b ** 2).sum())
    return (float((a * b).sum() / den) if den > 0 else np.nan, float((d["b"] - d["a"]).abs().mean()))


def defasamento(painel, lags=C.LAGS_DEFASAMENTO, n_boot=C.N_BOOT, semente=C.SEMENTE, sem_ruptura=False):
    """Correlação entre x_t e x_{t+k}, x = venda ÷ média do próprio código, pares juntados.

    - Pearson sobre os pares, e não o estimador clássico de ACF: este divide pela variância da
      série inteira e encolhe os lags altos para 0 só porque há menos pares.
    - Variação absoluta média |x_{t+k} − x_t|, em fração da média do código: quanto a demanda
      anda em k meses (leitura direta do estrago do proxy).
    - IC 95% por bootstrap de códigos.
    - Referência nula: meses embaralhados DENTRO de cada código (venda e ruptura juntas). Séries
      curtas centradas na própria média têm correlação negativa mesmo sem estrutura temporal
      (≈ −1/(n−1)); o valor observado se compara a essa referência, não a zero.
    """
    p = painel.sort_values([C.COL_SKU, C.COL_MES]).copy()
    media = p.groupby(C.COL_SKU)[C.COL_QTD].transform("mean")
    p = p[media > 0].copy()
    p["x"] = p[C.COL_QTD] / media[media > 0]
    p = p.reset_index(drop=True)
    rng = np.random.default_rng(semente)
    skus = p[C.COL_SKU].unique()
    blocos = [g.index.to_numpy() for _, g in p.groupby(C.COL_SKU, sort=False)]
    out = {}
    for k in lags:
        d = _pares(p, k, sem_ruptura)
        r, var = _medir(d)
        por_sku = {s: g_ for s, g_ in d.groupby(C.COL_SKU)}
        boot = []
        for _ in range(n_boot):
            amostra = [por_sku[s] for s in rng.choice(skus, len(skus)) if s in por_sku]
            boot.append(_medir(pd.concat(amostra)) if amostra else (np.nan, np.nan))
        boot = np.array(boot)
        nulo = []
        for _ in range(n_boot):
            perm = np.concatenate([rng.permutation(b) for b in blocos])
            q = p.copy()
            q[["x", "ruptura"]] = p.loc[perm, ["x", "ruptura"]].to_numpy()
            nulo.append(_medir(_pares(q, k, sem_ruptura))[0])
        nulo = np.array(nulo)
        m0 = float(np.nanmean(nulo))
        out[f"lag_{k}"] = {
            "pares": len(d), "codigos_com_par": int(d[C.COL_SKU].nunique()),
            "pares_por_codigo_max": int(d.groupby(C.COL_SKU).size().max()) if len(d) else 0,
            "correlacao": r, "correlacao_ic95": np.nanpercentile(boot[:, 0], [2.5, 97.5]).tolist(),
            "correlacao_nula_media": m0, "correlacao_nula_ic95": np.nanpercentile(nulo, [2.5, 97.5]).tolist(),
            "p_valor_bilateral": float(np.mean(np.abs(nulo - m0) >= abs(r - m0))),
            "variacao_abs_media_x": var, "variacao_ic95": np.nanpercentile(boot[:, 1], [2.5, 97.5]).tolist(),
        }
    return out


# ---------------------------------------------------------------- fluxo
def _arred(o, n=3):
    if isinstance(o, dict):
        return {k: _arred(v, n) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_arred(v, n) for v in o]
    if isinstance(o, pd.DataFrame):
        return _arred(o.to_dict("records"), n)
    if isinstance(o, (float, np.floating)):
        return round(float(o), n)
    if isinstance(o, np.integer):
        return int(o)
    return o


def main(fonte="auto"):
    sys.stdout.reconfigure(encoding="utf-8")   # console do Windows (cp1252) não tem Δ, −
    f, painel, info_carga, _, corte = M.tabela_features(fonte)
    treino = f[f[C.COL_MES] <= corte].reset_index(drop=True)
    teste = f[f[C.COL_MES] > corte].reset_index(drop=True)
    assert treino[C.COL_MES].max() < teste[C.COL_MES].min()

    # mesmo teste de vazamento da E05: perturba vendas/compras brutas depois de T0 e refaz tudo
    fonte_ok, cfg, _ = carregar.escolher_fonte(info_carga["fonte"])
    cortes_vaz = vazamento.testar_entrada(
        carregar.ler_bruto(fonte_ok), cfg, lambda b: M.tabela_features(fonte_ok, b, ate=corte)[0],
        list(dict.fromkeys(M.FEATS_TEMPO + M.NUM + M.CAT)), M.H)

    # T1 (τ principal + sensibilidade)
    t1 = {}
    for tau in [C.QUANTIL_OPERACIONAL, *C.TAUS_SENSIBILIDADE]:
        t1[f"tau_{tau:g}"], te, mods = decomposicao(treino, teste, tau)
        if tau == C.QUANTIL_OPERACIONAL:
            teste_q, modelos_q = te, mods
    # T2
    t2 = {"todos_os_meses": defasamento(painel), "sem_meses_com_ruptura": defasamento(painel, sem_ruptura=True),
          "meses": sorted(str(m) for m in painel[C.COL_MES].unique()), "codigos": int(painel[C.COL_SKU].nunique())}

    # T3: quadro de comparação + unidade de decisão (τ principal)
    tau = C.QUANTIL_OPERACIONAL
    r = t1[f"tau_{tau:g}"]
    abord_t3 = ["B0_p75_6", "B1_s_x_p75_6", "M_linear_quantil", "M_arvore_fator", "M_gb_quantil", "ref_media3"]
    quadro_t3 = r["quadro"].set_index("abordagem").loc[abord_t3].reset_index()
    hip = {n: str(m["params"]) for n, m in r["modelos"].items()}
    hip |= {"B0_p75_6": "janela 6 meses, P75 (regra fixa)", "ref_media3": "janela 3 meses (regra fixa)",
            "B1_s_x_p75_6": f"s = {r['s_cobertura_treino']:.3f} (cobertura no treino)"}
    quadro_t3["hiperparametros"] = quadro_t3["abordagem"].map(hip)
    quadro_t3["tempo_busca_s"] = quadro_t3["abordagem"].map({n: m["tempo_busca_s"] for n, m in r["modelos"].items()})
    quadro_t3["tempo_inferencia_ms"] = quadro_t3["abordagem"].map(
        {n: m["tempo_inferencia_ms"] for n, m in r["modelos"].items()})
    mapa, media_bob = D.m2_por_bobina(info_carga["fonte"])
    decisao = D.unidade_decisao(teste_q, abord_t3, mapa, media_bob)
    ganhos = [D.ganho_vs(decisao, "M_gb_quantil", c, v) for c in ["B0_p75_6", "ref_media3"]
              for v in ["previsao_m2", "pedido_bobinas_com_piso"]]
    t3 = {"quadro": quadro_t3, "decisao": decisao, "ganho_gb": ganhos,
          "linhas_teste_sem_m2_por_bobina": int((~teste_q[C.COL_SKU].isin(list(mapa))).sum()) if mapa
          else "amostra: média do container",
          "teste_vazamento": {"cortes": [str(c) for c in cortes_vaz], "resultado": "passou"}}
    # T4
    t4 = D.analise_erros(treino, teste_q, D.FOCO, tau, info_carga["fonte"], modelos_q["M_gb_quantil"]["est"])

    saida = C.DIR_SAIDA_REAL if info_carga["fonte"] == "real" else C.DIR_SAIDA_AMOSTRA
    saida.mkdir(parents=True, exist_ok=True)
    res = {"fonte": info_carga["fonte"], "corte_treino": str(corte), "linhas_treino": len(treino),
           "linhas_teste": len(teste), "codigos_teste": int(teste[C.COL_SKU].nunique()),
           "grades": {"linear": C.GRADE_LINEAR, "arvore": C.GRADE_ARVORE, "gb": C.GRADE_GB},
           "T1": t1, "T2": t2, "T3": t3, "T4": t4}
    (saida / "e06.json").write_text(json.dumps(_arred(res), ensure_ascii=False, indent=2, default=str),
                                    encoding="utf-8")
    imprimir(t1, t2, t3, t4)
    print(f"\nSalvo em {saida.relative_to(C.RAIZ).as_posix()}/e06.json")


def imprimir(t1, t2, t3, t4):
    """Só métricas relativas e contagens: m², bobinas e containers ficam no JSON."""
    pd.set_option("display.width", 200)
    for k, r in t1.items():
        print(f"\n=== T1 {k} | s={r['s_cobertura_treino']:.3f} (pinball: {r['s_pinball_treino']:.3f}) | "
              f"cobertura treino B0={r['cobertura_treino_B0_%']:.0f}% B1={r['cobertura_treino_B1_%']:.0f}%")
        print(r["quadro"].drop(columns="MAE").round(1).to_string(index=False))
        for par, e in r["efeitos"].items():
            print(f"  {par}: {e['ponto']:+.2f} p.p.  IC95 [{e['ic95'][0]:+.2f}, {e['ic95'][1]:+.2f}]  "
                  f"melhora em {e['pct_boot_melhora']:.0f}% do bootstrap")
        for n, m in r["modelos"].items():
            print(f"  {n}: {m['params']} | CV pinball_rel {m['cv_pinball_rel_%']:.1f}% | "
                  f"busca {m['tempo_busca_s']}s | inferência {m['tempo_inferencia_ms']}ms")
    print("\n=== T2 (x = venda ÷ média do código)")
    for variante in ["todos_os_meses", "sem_meses_com_ruptura"]:
        print(f"-- {variante}")
        for k, v in t2[variante].items():
            print(f"  {k}: pares={v['pares']} códigos={v['codigos_com_par']} | corr={v['correlacao']:+.2f} "
                  f"IC95 [{v['correlacao_ic95'][0]:+.2f}, {v['correlacao_ic95'][1]:+.2f}] | "
                  f"nulo {v['correlacao_nula_media']:+.2f} [{v['correlacao_nula_ic95'][0]:+.2f}, "
                  f"{v['correlacao_nula_ic95'][1]:+.2f}] p={v['p_valor_bilateral']:.3f} | "
                  f"|Δx| médio={v['variacao_abs_media_x']:.2f} IC95 [{v['variacao_ic95'][0]:.2f}, "
                  f"{v['variacao_ic95'][1]:.2f}]")
    print(f"\n=== T3 vazamento: {t3['teste_vazamento']} | linhas sem m²/bobina: {t3['linhas_teste_sem_m2_por_bobina']}")
    print("unidade de decisão (média por ciclo de 1 mês, % da demanda real)")
    print(t3["decisao"][["abordagem", "versao", "sobra_%_demanda", "falta_%_demanda", "pedido_%_demanda",
                         "meses_codigo_com_falta_por_ciclo"]].round(1).to_string(index=False))
    for g in t3["ganho_gb"]:
        print(f"  GB - {g['contra']} [{g['versao']}]: sobra {g['delta_sobra_%_demanda']:+.1f} p.p., "
              f"falta {g['delta_falta_%_demanda']:+.1f} p.p., meses-código com falta "
              f"{g['delta_meses_codigo_com_falta_por_ciclo']:+.1f}")
    print("\n=== T4 grupos: pinball rel. à média do grupo | viés | cobertura | % do custo que é falta")
    nome = {"B0_p75_6": "B0", "ref_media3": "media3", "M_gb_quantil": "GB"}
    fmt = lambda x, f: "  nan" if x is None else format(x, f)
    for col, gs in t4["grupos"].items():
        print(f"-- {col}")
        for g, v in gs.items():
            cel = " | ".join(f"{nome[a]}: {fmt(v[a]['pinball_rel_%'], '.0f')}% v{fmt(v[a]['vies_%'], '+.0f')}% "
                             f"c{v[a]['cobertura_%']:.0f}% f{fmt(v[a]['parcela_custo_falta_%'], '.0f')}%"
                             for a in D.FOCO)
            print(f"  {g:<14} n={v['linhas']:>2} cód={v['codigos']:>2} dem={v['parcela_demanda_%']:4.0f}% | {cel}")
    print("  concentração:", {k: round(v, 1) if isinstance(v, float) else v for k, v in t4["concentracao"].items()})
    print("  erro de dado:", {k: None if v is None else round(v, 1) for k, v in t4["erro_de_dado"].items()})
    f_ = t4["fora_do_filtro_incluir"]
    if f_ and f_.get("codigos"):
        print(f"  fora do filtro incluir: n={f_['linhas']} cód={f_['codigos']} "
              f"demanda={f_['demanda_relativa_aos_oficiais_%']:.0f}% da dos oficiais | " +
              " | ".join(f"{nome[a]}: pin {fmt(f_[a]['pinball_rel_%'], '.0f')}% viés {fmt(f_[a]['vies_%'], '+.0f')}% "
                         f"cob {f_[a]['cobertura_%']:.0f}%" for a in D.FOCO))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonte", choices=["auto", "real", "amostra"], default="auto")
    main(ap.parse_args().fonte)
