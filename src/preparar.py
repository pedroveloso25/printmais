"""Linhas de venda -> painel SKU × mês em m², com meses sem venda = 0.

Decisões:
- remove linhas de total/subtotal (qualquer célula de texto com a palavra) e linhas sem
  data, SKU ou quantidade;
- negativos (devoluções) conforme config.TRATAMENTO_NEGATIVOS;
- meses parciais (primeiro/último da extração) saem: venda de meio mês não é demanda mensal;
- ruptura do SKU de demanda no mês = TODOS os códigos agregados nele com sinal de ruptura
  (se um equivalente tinha estoque, a demanda migrou para ele e a soma continua válida);
- cada SKU entra no painel a partir do seu PRIMEIRO mês com venda > 0 até o último mês da base:
  zeros antes do lançamento seriam falsos (o SKU não existia) e puxariam a média para baixo;
- com `ate` (fim do treino), a seleção dos SKUs e o primeiro mês de cada um usam só meses
  <= ate: um SKU sem venda até o corte fica fora do painel, inclusive no teste.
"""
import pandas as pd

from src import config as C


def remover_totais(df):
    texto = df.select_dtypes(include=["object", "string"])
    if texto.empty:
        return df, 0
    eh_total = texto.apply(lambda s: s.astype("string").str.contains(C.PADRAO_TOTAL, case=False,
                                                                       regex=True, na=False)).any(axis=1)
    return df[~eh_total], int(eh_total.sum())


def preparar_painel(df, ate=None):
    """ate: último mês (Period) que a seleção de SKUs pode olhar; None = base inteira."""
    info = {}
    df, info["linhas_total_removidas"] = remover_totais(df)
    obrig = [C.COL_DATA, C.COL_SKU, C.COL_QTD]
    incompletas = df[obrig].isna().any(axis=1)
    info["linhas_incompletas_removidas"] = int(incompletas.sum())
    df = df.loc[~incompletas, obrig + ["mes_parcial", "ruptura"]].copy()
    info["meses_parciais_removidos"] = sorted(str(m) for m in
                                              df.loc[df["mes_parcial"], C.COL_DATA].dt.to_period("M").unique())
    df = df[~df["mes_parcial"]]

    neg = df[C.COL_QTD] < 0
    info["linhas_negativas"] = int(neg.sum())
    if C.TRATAMENTO_NEGATIVOS == "descartar":
        df = df[~neg]

    df[C.COL_MES] = df[C.COL_DATA].dt.to_period("M")
    mensal = df.groupby([C.COL_SKU, C.COL_MES], as_index=False).agg(
        **{C.COL_QTD: (C.COL_QTD, "sum"), "ruptura": ("ruptura", "all")})
    if C.TRATAMENTO_NEGATIVOS == "liquido_piso_zero":
        info["sku_mes_liquido_negativo_zerados"] = int((mensal[C.COL_QTD] < 0).sum())
        mensal[C.COL_QTD] = mensal[C.COL_QTD].clip(lower=0)

    fim = mensal[C.COL_MES].max()
    com_venda = mensal[mensal[C.COL_QTD] > 0]
    if ate is not None:
        com_venda = com_venda[com_venda[C.COL_MES] <= ate]
        info["selecao_ate"] = str(ate)
    inicio_sku = com_venda.groupby(C.COL_SKU)[C.COL_MES].min()
    info["skus_sem_nenhuma_venda_removidos"] = int(mensal[C.COL_SKU].nunique() - inicio_sku.size)
    grade = pd.DataFrame(
        [(sku, m) for sku, ini in inicio_sku.items() for m in pd.period_range(ini, fim, freq="M")],
        columns=[C.COL_SKU, C.COL_MES])
    painel = grade.merge(mensal, on=[C.COL_SKU, C.COL_MES], how="left")
    painel[C.COL_QTD] = painel[C.COL_QTD].fillna(0.0)
    painel["ruptura"] = painel["ruptura"].fillna(False).astype(bool)
    painel = painel.sort_values([C.COL_SKU, C.COL_MES]).reset_index(drop=True)

    info.update({
        "skus": int(painel[C.COL_SKU].nunique()),
        "mes_inicial": str(painel[C.COL_MES].min()), "mes_final": str(fim),
        "meses_cobertos": int(painel[C.COL_MES].nunique()),
        "linhas_sku_mes": len(painel),
        "pct_sku_mes_zerados": round(100 * (painel[C.COL_QTD] == 0).mean(), 1),
        "pct_sku_mes_com_ruptura": round(100 * painel["ruptura"].mean(), 1),
    })
    return painel, info
