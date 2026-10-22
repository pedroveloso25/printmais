"""Baselines de demanda do mês t, todos com informação até t − HORIZONTE.

Recebem o painel com features (particao.construir_features) e devolvem uma Series de
previsões alinhada ao índice. NaN = sem histórico suficiente para prever.
"""
from src import config as C


def baseline_media(f):
    """Trivial: média da demanda mensal do SKU em todo o histórico disponível até t − H."""
    return f["media_hist"]


def baseline_mediana(f):
    """Trivial robusto: mediana do mesmo histórico (menos sensível a picos)."""
    return f["mediana_hist"]


def baseline_sazonal_ingenuo(f, meses_disponiveis):
    """Mesmo mês do ano anterior. Só roda se a base tiver ≥ MESES_MIN_SAZONAL meses."""
    if meses_disponiveis < C.MESES_MIN_SAZONAL:
        return None
    return f["sazonal_12"]


def baseline_operacional(f):
    """Regra da empresa: P75 da demanda mensal dos últimos JANELA_OPERACIONAL meses
    disponíveis na data do pedido (t − H).

    Janela MÓVEL: recalculada para cada mês t do teste, terminando em t − H. O script da
    empresa calcula uma vez (janela fixa na data do pedido); para cada pedido a lógica é a
    mesma, o backtest só repete a decisão em cada origem.
    """
    return f["p75_janela"]


def todos(f, meses_disponiveis):
    prev = {
        "media_hist": baseline_media(f),
        "mediana_hist": baseline_mediana(f),
        "sazonal_ingenuo": baseline_sazonal_ingenuo(f, meses_disponiveis),
        "operacional_p75": baseline_operacional(f),
    }
    return {k: v for k, v in prev.items() if v is not None}
