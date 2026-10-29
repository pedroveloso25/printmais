"""Prova de que o teste de vazamento na entrada (src/vazamento.py) detecta o vazamento da ruptura.

Roda o teste NOVO contra o pipeline de outro checkout (ex.: o commit 2ddbe2e, que ainda usava
ruptura_lag como feature). Esperado: FALHA no 2ddbe2e e PASSA na versão atual.

    git worktree add ../printmais_2ddbe2e 2ddbe2e
    python scripts/provar_teste_vazamento.py ../printmais_2ddbe2e dados/bruto src/vazamento.py 1
    git worktree remove ../printmais_2ddbe2e

Último argumento: 1 = refaz estoque e ruptura após perturbar (teste completo);
0 = controle sem esse passo (mostra que, sem ele, o vazamento passaria despercebido).
Imprime só nomes de features e meses.
"""
import sys, importlib.util
from pathlib import Path
codigo, bruto_dir, vaz_path, reconstruir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4] == "1"
sys.path.insert(0, str(codigo))
from src import config as C, carregar, preparar, modelo as M
C.DIR_BRUTO = bruto_dir
spec = importlib.util.spec_from_file_location("vazamento_novo", vaz_path)
V = importlib.util.module_from_spec(spec); spec.loader.exec_module(V)
cfg = dict(C.FONTE_REAL, estoque_reconstruido={"chave": "codigo", "compras": "compras_m2",
                                              "inicio": "estoque_inicio_m2", "fim": "estoque_fim_m2"})
if not reconstruir:
    V.reconstruir_estoque = lambda b, cfg: b          # controle: sem refazer o derivado
_ler_original = carregar._ler
def pipeline(b):
    carregar._ler = lambda caminho, cfg_: b.copy()
    try:
        df, info = carregar.carregar_vendas("real")
    finally:
        carregar._ler = _ler_original
    painel, _ = preparar.preparar_painel(df)
    f = M.construir_features(painel, M.carregar_produtos("real")).rename(columns={C.COL_QTD: "y"})
    return f[f["lag_1"].notna()].reset_index(drop=True)
bruto = carregar._ler(C.DIR_BRUTO / cfg["arquivo"], cfg)
feats = list(dict.fromkeys(M.FEATS_TEMPO + M.NUM + M.CAT))
print("checkout:", codigo.name, "| ruptura_lag nas features:", "ruptura_lag" in feats, "| reconstrói estoque:", reconstruir)
try:
    print("PASSOU, cortes", V.testar_entrada(bruto, cfg, pipeline, feats, M.H))
except AssertionError as e:
    print("FALHOU:", e)
