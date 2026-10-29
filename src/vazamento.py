"""Teste de vazamento na ENTRADA: perturba os dados brutos depois de T0 e roda o pipeline inteiro.

Para cada corte T0 sorteado:
1. troca, na tabela bruta, as vendas e as compras dos meses > T0 por valores aleatórios;
2. refaz o que o tratamento deriva delas (estoque reconstruído e sinal de ruptura);
3. roda carga -> preparar -> features e exige que toda feature com corte <= T0 (linhas de mês
   <= T0 + h) seja idêntica à da base sem perturbação, e que o conjunto dessas linhas não mude.

Por que o passo 2: o estoque mensal da base é reconstruído a partir da posição do Sankhya em
20/10/2026 descontando as movimentações posteriores (fim(t) = posição − Σ_{s>t}(compras − vendas)).
Essa identidade vale em 100% das linhas da base. O critério exato de `possivel_ruptura` está no
script de tratamento (fora do repositório); aqui ele é aproximado por "estoque no início ou no fim
do mês <= 0", que coincide com a marcação em 90% das linhas. Base e perturbação passam pelo mesmo
passo 2, então a comparação isola o efeito do futuro.

As mensagens de erro só citam nomes de features e meses, nunca valores.
"""
import numpy as np
import pandas as pd

from src import carregar, config as C


def _meses(bruto, cfg):
    data = pd.to_datetime(bruto[cfg["colunas"][C.COL_DATA]], errors="coerce",
                          dayfirst=cfg["dayfirst"], format="mixed")
    return data.dt.to_period("M")


def _texto(x, decimal):
    s = pd.Series(x, dtype=float).map(lambda v: f"{v:.4f}")
    return s.str.replace(".", ",", regex=False) if decimal == "," else s


def reconstruir_estoque(bruto, cfg):
    """Refaz estoque início/fim e o sinal de ruptura a partir da posição final e das movimentações."""
    rc = cfg.get("estoque_reconstruido")
    if not rc:
        return bruto
    b = bruto.copy()
    num = lambda col: carregar._numero(b[col], cfg["decimal"]).fillna(0.0)
    mes = _meses(b, cfg)
    mov = num(rc["compras"]) - num(cfg["colunas"][C.COL_QTD])
    ordem = pd.DataFrame({"chave": b[rc["chave"]], "mes": mes, "mov": mov, "fim": num(rc["fim"])})
    ordem = ordem.sort_values(["chave", "mes"])
    g = ordem.groupby("chave", sort=False)
    posicao = g["fim"].transform("last")                                # posição do Sankhya
    depois = g["mov"].transform(lambda s: s[::-1].cumsum()[::-1]) - ordem["mov"]   # Σ_{s>t}
    fim = posicao - depois
    inicio = fim - ordem["mov"]
    b.loc[ordem.index, rc["fim"]] = _texto(fim, cfg["decimal"]).to_numpy()
    b.loc[ordem.index, rc["inicio"]] = _texto(inicio, cfg["decimal"]).to_numpy()
    if cfg.get("col_ruptura"):
        b.loc[ordem.index, cfg["col_ruptura"]] = np.where((inicio <= 0) | (fim <= 0), "True", "False")
    return b


def perturbar_bruto(bruto, cfg, t0, rng):
    """Vendas (e compras, se houver) dos meses > t0 viram valores aleatórios."""
    b = bruto.copy()
    fut = (_meses(b, cfg) > t0).to_numpy()
    cols = [cfg["colunas"][C.COL_QTD]]
    if cfg.get("estoque_reconstruido"):
        cols.append(cfg["estoque_reconstruido"]["compras"])
    for col in cols:
        b.loc[fut, col] = _texto(rng.uniform(0, 1e6, fut.sum()), cfg["decimal"]).to_numpy()
    return b


def _iguais(a, b):
    if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
        return np.isclose(a.to_numpy(float), b.to_numpy(float), equal_nan=True)
    return (a.astype("string").fillna("<NA>") == b.astype("string").fillna("<NA>")).to_numpy()


def testar_entrada(bruto, cfg, tabela, feats, h, n_cortes=3, semente=C.SEMENTE):
    """tabela(bruto) -> DataFrame com C.COL_SKU, C.COL_MES e as features. Retorna os cortes testados.

    Levanta AssertionError se alguma feature com corte <= T0 mudar."""
    idx = [C.COL_SKU, C.COL_MES]
    base = tabela(reconstruir_estoque(bruto, cfg)).set_index(idx)[feats].sort_index()
    meses = np.sort(base.index.get_level_values(C.COL_MES).unique())
    candidatos = [m for m in meses if m + h <= meses[-1]]
    rng = np.random.default_rng(semente)
    cortes = sorted(rng.choice(candidatos, size=min(n_cortes, len(candidatos)), replace=False))
    for t0 in cortes:
        alt = tabela(reconstruir_estoque(perturbar_bruto(bruto, cfg, t0, rng), cfg))
        alt = alt.set_index(idx)[feats].sort_index()
        vb = base[base.index.get_level_values(C.COL_MES) <= t0 + h]
        va = alt[alt.index.get_level_values(C.COL_MES) <= t0 + h]
        assert vb.index.equals(va.index), (
            f"VAZAMENTO: linhas com corte <= {t0} mudaram ({len(vb)} -> {len(va)})")
        ruins = [f for f in feats if not _iguais(vb[f], va[f]).all()]
        assert not ruins, f"VAZAMENTO em {ruins} (corte {t0})"
    return [str(t) for t in cortes]
