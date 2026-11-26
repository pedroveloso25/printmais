"""Entrega 6: ganho em unidade de decisão (T3) e análise de erros e equidade (T4).

Chamado por src/e06.py (comando único). Recebe o teste de τ = 0,75 já com as previsões
de todas as abordagens e devolve dicionários prontos para o JSON.

Unidade de decisão (T3), por mês de teste e somando os códigos:
  sobra (m²)  = Σ max(previsto − real, 0)  -> capital parado, ocupa espaço do container;
  falta (m²)  = Σ max(real − previsto, 0)  -> venda perdida (margem de 0,40 do preço);
  meses-código com falta.
Versão "pedido": previsto arredondado para cima em bobinas (m² por bobina do código) e piso
de 30 bobinas. Cobertura de 1 mês (o alvo do modelo é mensal). Os valores absolutos (m²,
bobinas, fração de container) vão só para o JSON; a tela mostra % da demanda real.

Erros (T4): faixas do previsto, giro (definido com o treino), atributos de produto, tamanho do
histórico, códigos fora do filtro `incluir`, meses com ruptura e concentração por código.
Cada grupo usa a pinball relativa à média do PRÓPRIO grupo: erro relativo de cauda longa.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import mean_pinball_loss

from src import carregar, config as C, modelo as M

FOCO = ["B0_media3", "B0_p75_6", "M_gb_quantil"]   # regra atual, baseline da E04/E05, melhor modelo


# ---------------------------------------------------------------- bobinas
def m2_por_bobina(fonte):
    """m² por bobina de cada código de demanda; sem cadastro (amostra) usa a média do container."""
    media = C.M2_CONTAINER / C.BOBINAS_CONTAINER
    if fonte != "real":
        return {}, media
    p = pd.read_csv(C.DIR_BRUTO / C.ARQUIVO_PRODUTOS, sep=";", decimal=",", encoding="utf-8-sig")
    p = p[p["codigo"] == p["codigo_demanda"]]
    return dict(zip(p["codigo_demanda"].astype(str), p["m2_por_bobina"].astype(float))), media


def pedido_m2(prev, skus, mapa, media, piso=True):
    """Previsão em m² -> pedido em bobinas inteiras (para cima), com piso, de volta a m²."""
    bob = skus.map(mapa).fillna(media).to_numpy(float)
    n = np.ceil(np.asarray(prev, float) / bob - 1e-9)
    if piso:
        n = np.where(n > 0, np.maximum(n, C.PISO_BOBINAS), 0)
    return n * bob, n


# ---------------------------------------------------------------- T3
def unidade_decisao(teste, abord, mapa, media):
    linhas = []
    for a in abord:
        for versao in ["previsao_m2", "pedido_bobinas_sem_piso", "pedido_bobinas_com_piso"]:
            if versao == "previsao_m2":
                prev, n_bob = teste[a].to_numpy(float), None
            else:
                prev, n_bob = pedido_m2(teste[a], teste[C.COL_SKU], mapa, media, piso=versao.endswith("com_piso"))
            y = teste["y"].to_numpy(float)
            d = pd.DataFrame({"mes": teste[C.COL_MES].astype(str), "y": y,
                              "sobra": np.maximum(prev - y, 0), "falta": np.maximum(y - prev, 0),
                              "faltou": y > prev + 1e-9, "pedido": prev})
            por_mes = d.groupby("mes").agg(y=("y", "sum"), sobra=("sobra", "sum"), falta=("falta", "sum"),
                                           meses_codigo_com_falta=("faltou", "sum"), pedido=("pedido", "sum"))
            tot = por_mes.mean()          # média por ciclo (1 ciclo = 1 mês de cobertura)
            linhas.append({
                "abordagem": a, "versao": versao,
                "sobra_%_demanda": 100 * tot["sobra"] / tot["y"], "falta_%_demanda": 100 * tot["falta"] / tot["y"],
                "pedido_%_demanda": 100 * tot["pedido"] / tot["y"],
                "meses_codigo_com_falta_por_ciclo": tot["meses_codigo_com_falta"],
                # absolutos: só JSON (relatorios/real/ não é versionado)
                "sobra_m2_por_ciclo": tot["sobra"], "falta_m2_por_ciclo": tot["falta"],
                "pedido_m2_por_ciclo": tot["pedido"], "pedido_containers_por_ciclo": tot["pedido"] / C.M2_CONTAINER,
                "bobinas_por_ciclo": float(n_bob.sum() / d["mes"].nunique()) if n_bob is not None else None,
            })
    return pd.DataFrame(linhas)


def ganho_vs(tab, modelo, contra, versao="pedido_bobinas_com_piso"):
    t = tab[tab["versao"] == versao].set_index("abordagem")
    a, b = t.loc[modelo], t.loc[contra]
    return {"versao": versao, "modelo": modelo, "contra": contra,
            "delta_sobra_m2_por_ciclo": a["sobra_m2_por_ciclo"] - b["sobra_m2_por_ciclo"],
            "delta_falta_m2_por_ciclo": a["falta_m2_por_ciclo"] - b["falta_m2_por_ciclo"],
            "delta_sobra_%_demanda": a["sobra_%_demanda"] - b["sobra_%_demanda"],
            "delta_falta_%_demanda": a["falta_%_demanda"] - b["falta_%_demanda"],
            "delta_meses_codigo_com_falta_por_ciclo": a["meses_codigo_com_falta_por_ciclo"]
            - b["meses_codigo_com_falta_por_ciclo"],
            "delta_containers_por_ciclo": a["pedido_containers_por_ciclo"] - b["pedido_containers_por_ciclo"]}


# ---------------------------------------------------------------- T4
def _resumo_grupo(d, abord, tau):
    out = {"linhas": len(d), "codigos": int(d[C.COL_SKU].nunique())}
    for a in abord:
        y, p = d["y"], d[a]
        out[a] = {"pinball_rel_%": 100 * mean_pinball_loss(y, p, alpha=tau) / y.mean() if y.mean() > 0 else None,
                  "vies_%": 100 * (p - y).sum() / y.sum() if y.sum() > 0 else None,
                  "cobertura_%": 100 * float((y <= p).mean()),
                  # parcela do custo: falta pesa 0,40, sobra 0,026 (sem restrição de espaço)
                  "parcela_custo_falta_%": _parcela_falta(y, p)}
    return out


def _parcela_falta(y, p):
    falta = C.MARGEM_FALTA * np.maximum(y - p, 0).sum()
    sobra = C.CUSTO_SOBRA_IRRESTRITO * np.maximum(p - y, 0).sum()
    return 100 * float(falta / (falta + sobra)) if falta + sobra > 0 else None


def por_grupo(teste, col, abord, tau, total_y):
    res = {}
    for g, d in teste.groupby(col, observed=True, dropna=False):
        r = _resumo_grupo(d, abord, tau)
        r["parcela_demanda_%"] = 100 * d["y"].sum() / total_y
        res[str(g)] = r
    return res


def analise_erros(treino, teste, abord, tau, fonte, modelo_gb):
    t = teste.copy()
    total_y = t["y"].sum()
    giro = treino.groupby(C.COL_SKU)["y"].mean()                  # giro medido SÓ no treino
    corte_giro = giro.quantile([1 / 3, 2 / 3]).to_numpy()
    t["giro"] = pd.cut(t[C.COL_SKU].map(giro), [-np.inf, *corte_giro, np.inf],
                       labels=["baixo", "medio", "alto"]).astype(str).replace("nan", "sem_treino")
    t["faixa_previsto_gb"] = pd.qcut(t["M_gb_quantil"].rank(method="first"), 3,
                                     labels=["baixa", "media", "alta"]).astype(str)
    t["historico"] = np.where(t["n_meses_hist"] <= 3, "curto_ate_3m", "longo_4m+")
    t["ruptura_no_mes"] = np.where(t["ruptura"], "com_ruptura", "sem_ruptura")
    grupos = {c: por_grupo(t, c, abord, tau, total_y)
              for c in ["faixa_previsto_gb", "giro", "historico", "ruptura_no_mes", "marca", "acabamento"]}

    # concentração: que fração do erro absoluto do GB vem dos 20% de códigos com mais erro
    e = (t["y"] - t["M_gb_quantil"]).abs().groupby(t[C.COL_SKU]).sum().sort_values(ascending=False)
    k = max(1, int(np.ceil(0.2 * len(e))))
    v = t.groupby(C.COL_SKU)["y"].sum().sort_values(ascending=False)
    concentracao = {"codigos": len(e), "top20pct_codigos": k,
                    "parcela_erro_abs_gb_top20pct_%": 100 * e.iloc[:k].sum() / e.sum(),
                    "parcela_demanda_top20pct_volume_%": 100 * v.iloc[:k].sum() / v.sum()}

    # erro de dado: em mês com ruptura a venda registrada < demanda; quanto da SOBRA aparente está lá
    sobra = np.maximum(t["M_gb_quantil"] - t["y"], 0)
    dado = {"parcela_sobra_gb_em_meses_com_ruptura_%": 100 * sobra[t["ruptura"]].sum() / sobra.sum()
            if sobra.sum() > 0 else None,
            "parcela_linhas_com_ruptura_%": 100 * float(t["ruptura"].mean())}

    return {"grupos": grupos, "concentracao": concentracao, "erro_de_dado": dado,
            "fora_do_filtro_incluir": fora_do_filtro(treino, teste, modelo_gb, tau) if fonte == "real" else None,
            "cortes_giro_m2_treino_omitidos": "tercis da média de venda no treino (valores no código, não no JSON)"}


def fora_do_filtro(treino, teste, modelo_gb, tau):
    """Códigos excluídos por `incluir`: o GB treinado nos 30 oficiais aplicado a eles (sem retreino)."""
    bruto = carregar.ler_bruto("real")
    for col in C.FONTE_REAL["filtro_verdadeiro"]:
        bruto[col] = "True"
    corte = treino[C.COL_MES].max()
    g, *_ = M.tabela_features("real", bruto, ate=corte)
    novos = sorted(set(g[C.COL_SKU]) - set(treino[C.COL_SKU]) - set(teste[C.COL_SKU]))
    te = g[(g[C.COL_MES] > corte) & g[C.COL_SKU].isin(novos)].copy()
    if te.empty:
        return {"codigos": 0}
    te["M_gb_quantil"] = np.clip(modelo_gb.predict(te[M.NUM + M.CAT]), 0, None)
    te["B0_p75_6"], te["B0_media3"] = te["p75_6"], te["media_3"]
    r = _resumo_grupo(te, FOCO, tau)
    r["demanda_relativa_aos_oficiais_%"] = 100 * te["y"].sum() / teste["y"].sum()
    return r
