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
