"""Configuração central: caminhos, schema das fontes e parâmetros da regra operacional.

O schema REAL (arquivo, colunas, leitura) só pode ser preenchido a partir de
relatorios/perfil_dados.md. Enquanto estiver com None, carregar.py recusa os dados
reais com uma mensagem clara (sem abrir nenhum arquivo).
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_BRUTO = RAIZ / "dados" / "bruto"
DIR_AMOSTRA = RAIZ / "dados" / "amostra"
DIR_RELATORIOS = RAIZ / "relatorios"
# Métricas sobre dados reais ficam em relatorios/real/ (ignorado pelo git): mesmo
# agregadas, MAE e totais em m² revelam volume de vendas.
DIR_SAIDA_REAL = DIR_RELATORIOS / "real"
DIR_SAIDA_AMOSTRA = DIR_RELATORIOS / "amostra"

ARQUIVOS_IGNORADOS = {".gitkeep", "COMO_OBTER.md"}

# Nomes internos padronizados (o resto do código só conhece estes)
COL_DATA, COL_SKU, COL_QTD = "data", "sku", "m2"
COL_MES = "mes"

# ---------------------------------------------------------------- fonte real
# Preenchido a partir de relatorios/perfil_dados.md (2026-10-22). A tabela de vendas já vem
# agregada por SKU × mês (planilha tratada), não por nota fiscal.
FONTE_REAL = {
    "arquivo": "vendas_estoque_mensal.csv",
    "aba": None,
    "encoding": "utf-8-sig",
    "sep": ";",
    "decimal": ",",
    "linhas_titulo": 0,
    "colunas": {            # nome no arquivo -> nome interno
        COL_DATA: "mes",
        # código de demanda: SKUs equivalentes/substitutos somados num só código
        COL_SKU: "codigo_demanda",
        COL_QTD: "vendas_m2",
    },
    "dayfirst": False,
    "filtro_verdadeiro": ["incluir"],       # só SKUs marcados para o modelo
    "col_mes_parcial": "mes_parcial",       # meses incompletos (primeiro e último)
    "col_ruptura": "possivel_ruptura",      # mês com sinal de falta de estoque
    # Estoque mensal reconstruído no tratamento: posição do Sankhya (20/10/2026) menos as
    # movimentações posteriores. Usado só pelo teste de vazamento (src/vazamento.py) para
    # refazer o estoque e a ruptura quando as vendas/compras futuras são perturbadas.
    "estoque_reconstruido": {
        "chave": "codigo", "compras": "compras_m2",
        "inicio": "estoque_inicio_m2", "fim": "estoque_fim_m2",
    },
}

# ---------------------------------------------------------------- amostra sintética
FONTE_AMOSTRA = {
    "arquivo": "vendas_amostra.csv",
    "aba": None,
    "encoding": "utf-8",
    "sep": ";",
    "decimal": ",",
    "linhas_titulo": 0,
    "colunas": {COL_DATA: "data", COL_SKU: "sku", COL_QTD: "m2_vendidos"},
    "dayfirst": True,
    "filtro_verdadeiro": [],
    "col_mes_parcial": None,
    "col_ruptura": None,
}

# ---------------------------------------------------------------- tratamento
# Linhas de total/subtotal de relatório (qualquer célula de texto)
PADRAO_TOTAL = r"\b(?:sub)?total\b"
# Negativos (devoluções/estornos). Opções:
#   "liquido_piso_zero": soma líquida no mês e piso em 0 (devolução abate a venda do mês;
#                         mês líquido negativo vira 0, pois demanda negativa não existe)
#   "descartar":         ignora linhas negativas (conta só a venda bruta)
#   "manter":            soma líquida sem piso
# Na base real não há vendas negativas (perfil: 0 negativos em vendas_m2); fica para a amostra.
TRATAMENTO_NEGATIVOS = "liquido_piso_zero"

# ---------------------------------------------------------------- partição e regra
HORIZONTE = 5                 # lead time de 4–5 meses: prever t com info até t − 5
JANELA_OPERACIONAL = 6        # últimos 6 meses disponíveis
MIN_MESES_JANELA = 6          # meses mínimos na janela para prever (diagnóstico: --min-meses-janela)
QUANTIL_OPERACIONAL = 0.75    # P75
MESES_COBERTURA = 2           # pedido cobre 2 meses após a chegada (uso a jusante)
MESES_MIN_SAZONAL = 24        # histórico mínimo para o sazonal ingênuo
N_MESES_TESTE = 6             # usado se DATA_CORTE for None
# Base real: meses completos 2026-03..2026-09 (7). Corte no 1º mês completo deixa os 6
# seguintes como teste; com HORIZONTE = 5 só os últimos têm informação em t − 5.
DATA_CORTE = None             # último mês do treino ("AAAA-MM"); None = fim − N_MESES_TESTE

# ---------------------------------------------------------------- modelo (Entrega 5)
# Com 7 meses completos, HORIZONTE = 5 não deixa linhas avaliáveis. O primeiro modelo usa
# horizonte de 1 mês e declara o descasamento com o lead time nos Limites do relatório.
HORIZONTE_MODELO = 1
N_MESES_HOLDOUT = 2            # últimos 2 meses completos = teste final (usado uma vez)
N_SPLITS_CV = 3                # TimeSeriesSplit sobre os meses do treino
ALPHAS_RIDGE = [0.1, 1, 10, 100, 1000]
SEMENTE = 42
ARQUIVO_PRODUTOS = "produtos.csv"   # atributos fixos: largura, linha, acabamento, marca

# ---------------------------------------------------------------- Entrega 6
# B0 principal = média dos 3 últimos meses fechados ("Giro Média 30 à 90" do Sankhya, confirmada na
# devolutiva de 23–25/11). P75 de 6 meses = baseline da E04/E05, mantido para comparação.
BASES_B0 = {"media3": "media_3", "p75_6": "p75_6"}   # nome -> coluna da tabela de features
TAUS_SENSIBILIDADE = [0.6, 0.9]
# Grades da busca por CV temporal (seção 5 do relatório). y em m² e features padronizadas:
# a penalidade L1 do QuantileRegressor soma alpha × |coef em m²| à perda média em m².
GRADE_LINEAR = {"alpha": [0, 0.01, 0.1, 1, 10, 100, 1000]}
GRADE_ARVORE = {"max_depth": [2, 3, 4, 6], "min_samples_leaf": [3, 5, 10, 20]}
GRADE_GB = {"n_estimators": [50, 100, 200], "max_depth": [2, 3], "learning_rate": [0.05, 0.1],
            "min_samples_leaf": [5, 10]}
N_BOOT = 2000                 # bootstrap por código (os 2 meses do mesmo código andam juntos)
LAGS_DEFASAMENTO = [1, 4, 5]  # T2: lag 1 (o que o modelo prevê) × 4–5 (lead time real)
# Camada de decisão (T3/T4). Cobertura de 1 mês: entram 1–2 containers/mês (CONTEXTO §1).
M2_CONTAINER = 93_400         # capacidade de mídia por container
BOBINAS_CONTAINER = 1_600
PISO_BOBINAS = 30             # lote mínimo por código que entra no pedido
MARGEM_FALTA = 0.40           # custo de faltar, fração do preço (margem perdida)
CUSTO_SOBRA_IRRESTRITO = 0.026  # custo de sobrar sem restrição de espaço (capital + desconto)
