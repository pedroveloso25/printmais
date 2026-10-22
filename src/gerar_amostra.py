"""Gera dados/amostra/vendas_amostra.csv — 100% SINTÉTICO, sem relação com a Print Mais.

Serve para testar o pipeline sem os dados reais. Inclui o que o pipeline precisa tratar:
sazonalidade, SKUs intermitentes, SKUs lançados no meio do período, devoluções
(quantidade negativa) e uma linha de total no fim.

Uso:  python -m src.gerar_amostra [--forcar]
"""
import sys

import numpy as np
import pandas as pd

from src import config as C

SEMENTE, N_SKUS = 42, 40
INICIO, FIM = "2023-10-01", "2026-09-30"


def gerar():
    rng = np.random.default_rng(SEMENTE)
    meses = pd.period_range(INICIO, FIM, freq="M")
    linhas = []
    for i in range(N_SKUS):
        sku = f"SKU{i + 1:03d}"
        nivel = rng.lognormal(5, 0.8)                       # m²/mês típico
        amp = rng.uniform(0, 0.4)                           # força da sazonalidade
        intermitente = rng.random() < 0.2
        lancamento = rng.integers(0, 20) if rng.random() < 0.15 else 0
        for k, m in enumerate(meses[lancamento:], start=lancamento):
            if intermitente and rng.random() < 0.5:
                continue
            media = nivel * (1 + amp * np.sin(2 * np.pi * (m.month - 3) / 12)) * (1 + 0.01 * k)
            total_mes = rng.gamma(4, media / 4)
            n_vendas = max(1, rng.poisson(6))
            partes = rng.dirichlet(np.ones(n_vendas)) * total_mes
            dias = rng.integers(1, m.days_in_month + 1, n_vendas)
            for d, q in zip(dias, partes):
                linhas.append((f"{d:02d}/{m.month:02d}/{m.year}", sku, round(q, 2)))
            if rng.random() < 0.05:                         # devolução
                linhas.append((f"{m.days_in_month:02d}/{m.month:02d}/{m.year}", sku,
                               -round(rng.uniform(0.05, 0.3) * total_mes, 2)))
    df = pd.DataFrame(linhas, columns=list(C.FONTE_AMOSTRA["colunas"].values()))
    df.loc[len(df)] = ["", "TOTAL GERAL", round(df.iloc[:, 2].sum(), 2)]
    return df


if __name__ == "__main__":
    destino = C.DIR_AMOSTRA / C.FONTE_AMOSTRA["arquivo"]
    if destino.exists() and "--forcar" not in sys.argv:
        raise SystemExit(f"{destino.name} já existe; use --forcar para sobrescrever.")
    df = gerar()
    df.to_csv(destino, sep=";", decimal=",", index=False, encoding="utf-8")
    print(f"Amostra sintética gerada: {destino.name} ({len(df)} linhas)")
