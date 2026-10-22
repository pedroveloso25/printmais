"""Fluxo ponta a ponta: carregar -> preparar -> features -> split -> baselines -> métricas.

Uso:  python -m src.main [--fonte auto|real|amostra] [--horizonte H] [--min-meses-janela M]

--horizonte e --min-meses-janela são só para DIAGNÓSTICO (o padrão é a regra da empresa,
em config.py); saídas com esses ajustes ganham sufixo no nome do arquivo.

Imprime e salva SÓ métricas agregadas. Saída em relatorios/real/ (ignorado pelo git)
ou relatorios/amostra/.
"""
import argparse
import json

import pandas as pd

from src import avaliar, baselines, carregar, config as C, particao, preparar


def _tabela_md(df):
    cols = list(df.columns)
    fmt = lambda v: f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") \
        if isinstance(v, float) else str(v)
    L = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    L += ["| " + " | ".join(fmt(v) for v in linha) + " |" for linha in df.itertuples(index=False)]
    return "\n".join(L)


def main(fonte="auto", h=C.HORIZONTE, min_meses=C.MIN_MESES_JANELA):
    df, info_carga = carregar.carregar_vendas(fonte)
    painel, info_prep = preparar.preparar_painel(df)
    del df

    particao.verificar_sem_vazamento(painel, h, min_meses=min_meses)
    feats = particao.construir_features(painel, h, min_meses=min_meses)
    corte = particao.data_corte(painel)
    _, teste = particao.dividir_temporal(feats, corte, h)

    prev = baselines.todos(teste, info_prep["meses_cobertos"])
    tabela, info_aval = avaliar.avaliar(teste, prev)

    saida = C.DIR_SAIDA_REAL if info_carga["fonte"] == "real" else C.DIR_SAIDA_AMOSTRA
    saida.mkdir(parents=True, exist_ok=True)
    resumo = {"carga": info_carga, "preparo": info_prep, "avaliacao": info_aval,
              "parametros": {"data_corte": str(corte), "horizonte": h, "min_meses_janela": min_meses,
                             "janela_operacional": C.JANELA_OPERACIONAL,
                             "quantil": C.QUANTIL_OPERACIONAL,
                             "tratamento_negativos": C.TRATAMENTO_NEGATIVOS,
                             "sazonal_rodou": "sazonal_ingenuo" in prev}}
    md = "\n\n".join([
        "# Métricas dos baselines (agregadas)",
        f"Fonte: {info_carga['fonte']} | corte (último mês de treino): {corte} | "
        f"horizonte: {h} | mín. meses na janela: {min_meses} | linhas SKU×mês avaliadas: {info_aval['linhas_avaliadas']} "
        f"de {info_aval['linhas_teste']} no teste",
        _tabela_md(tabela),
        "```json\n" + json.dumps(resumo, ensure_ascii=False, indent=2, default=str) + "\n```",
    ])
    sufixo = "" if (h, min_meses) == (C.HORIZONTE, C.MIN_MESES_JANELA) else f"_diag_h{h}_min{min_meses}"
    (saida / f"metricas_baselines{sufixo}.md").write_text(md, encoding="utf-8")
    (saida / f"metricas_baselines{sufixo}.json").write_text(
        json.dumps({"metricas": tabela.to_dict("records"), **resumo},
                   ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(md.split("```json")[0])
    print(f"Salvo em {saida.relative_to(C.RAIZ).as_posix()}/metricas_baselines{sufixo}.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonte", choices=["auto", "real", "amostra"], default="auto")
    ap.add_argument("--horizonte", type=int, default=C.HORIZONTE)
    ap.add_argument("--min-meses-janela", type=int, default=C.MIN_MESES_JANELA)
    a = ap.parse_args()
    try:
        main(a.fonte, a.horizonte, a.min_meses_janela)
    except carregar.ErroSchema as e:
        raise SystemExit(f"ERRO de schema: {e}")
