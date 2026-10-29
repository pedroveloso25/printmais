# Previsão de demanda mensal por SKU — Print Mais

Projeto da disciplina de Machine Learning (UFPB). Os dados reais da empresa são sigilosos e não
estão neste repositório.

## Problema e decisão apoiada
A Print Mais importa os produtos com lead time de 4 a 5 meses. No dia do pedido, ela precisa
estimar quanto cada SKU vai vender quando a mercadoria chegar. Se estimar pouco, falta estoque,
e a venda perdida não volta. Se estimar muito, o capital fica parado em estoque.

O projeto estima a **demanda mensal de cada SKU**. Essa estimativa alimenta a decisão de **quanto
pedir** em cada importação.

## Formulação
| Item | Definição |
|---|---|
| Unidade de análise | SKU × mês |
| Alvo | m² vendidos no mês |
| Horizonte | 5 meses: a previsão do mês *t* usa só informação até *t − 5* |
| Partição | temporal. O treino vai até a data de corte (`DATA_CORTE` em `src/config.py`) e o teste são os meses seguintes |
| Métricas | MAE, WAPE, viés, pinball loss (q = 0,75) e taxa de cobertura, calculadas por SKU × mês e no total do mês. Não usamos MAPE porque ele quebra em meses com demanda zero |

## Regra operacional atual (baseline a bater)
A empresa estima a demanda mensal de cada SKU pelo **percentil 75 da demanda mensal dos últimos
6 meses** disponíveis na data do pedido. No backtest, a regra é recalculada em janela móvel para
cada mês do teste, sempre terminando em *t − 5*.

Os outros baselines são a média e a mediana históricas do SKU e o sazonal ingênuo (mesmo mês do
ano anterior). O sazonal ingênuo só roda se a base tiver pelo menos 24 meses.

## Uso a jusante
A previsão sai em m². A decisão de compra fica fora deste repositório e segue três passos:
1. Soma a demanda prevista dos **2 meses seguintes à chegada** (cobertura).
2. Desconta o estoque projetado e converte o resultado para **bobinas** (m² por bobina de cada SKU).
3. Aplica o **lote mínimo por código** e a **capacidade do container**, que é fixa em m².

## Limitações
- **Histórico curto (bloqueio atual).** A base real tem 7 meses completos. Um backtest com
  horizonte 5, janela de 6 meses e 6 meses de teste precisa de pelo menos 17. Com a regra exata,
  nenhuma linha é avaliável. Os diagnósticos `--horizonte` e `--min-meses-janela` só servem para
  testar o pipeline. Detalhes em `notebooks/01_qualidade_dados.ipynb`.
- **Ruptura subestima a demanda.** Quando falta estoque, a venda registrada é menor que a demanda
  real. Treinar e avaliar com venda trata a falta como se fosse demanda baixa, e a regra P75
  herda esse viés.
- **SKUs intermitentes**, com muitos meses zerados, deixam a WAPE e o P75 instáveis.
- **SKUs novos** só ganham previsão operacional depois de 6 meses de histórico disponível
  (mais o horizonte). Cada SKU entra no painel a partir do primeiro mês com venda, sem zeros antes
  do lançamento.
- Devoluções são abatidas no mês em que acontecem, e um mês líquido negativo vira zero
  (`TRATAMENTO_NEGATIVOS` em `src/config.py`).

## Dados
- `dados/bruto/`: dados reais, que vêm da empresa mediante autorização. Estão bloqueados no git.
  Veja `dados/bruto/COMO_OBTER.md`.
- `dados/amostra/`: amostra **100% sintética**, gerada por `python -m src.gerar_amostra`. Serve
  para rodar o pipeline sem os dados reais.
- `relatorios/perfil_dados.md`: perfil só com metadados agregados, gerado por
  `python -m src.perfil_dados`. Não é versionado.
- As métricas sobre os dados reais vão para `relatorios/real/`, que é ignorado pelo git, porque
  até números agregados em m² revelam o volume de vendas.

## Como rodar

### 1. Instalação
```bash
git clone https://github.com/pedroveloso25/printmais
cd printmais
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt                     # versões fixadas; testado com Python 3.13
```
No Windows, se o `pip` falhar com erro de caminho longo, crie o ambiente num caminho curto
(ex.: `C:\venvs\printmais`).

### 2. Dados
Coloque `vendas_estoque_mensal.csv` e `produtos.csv` em `dados/bruto/`. A base é privada: o
professor solicita à equipe, que encaminha à empresa (ver `dados/bruto/COMO_OBTER.md`).

### 3. Modelo da Entrega 5 (números do relatório)
```bash
python -m src.modelo --fonte real
```
- Métricas (seção 7 do relatório): `relatorios/real/metricas_modelo.json`
- Gráficos de resíduos: `relatorios/real/figs/residuos.png` (4 painéis)
- Figura da seção 8 (2 painéis), depois do comando acima:
  `python -m scripts.figura_residuos_2p --fonte real` → `relatorios/real/figs/residuos_2p.png`.
  O script confere α e métricas contra `metricas_modelo.json` antes de plotar.
- `relatorios/real/` é ignorado pelo git: os arquivos só existem depois de rodar com a base.
- O resultado é determinístico (`SEMENTE = 42` em `src/config.py`): duas execuções geram o
  mesmo `metricas_modelo.json`, byte a byte.

### 4. Sem a base real (amostra sintética)
```bash
python -m src.modelo --fonte amostra
```
Roda o mesmo pipeline sobre `dados/amostra/vendas_amostra.csv` (100% sintética, versionada) e
grava em `relatorios/amostra/` (a figura de 2 painéis sai com
`python -m scripts.figura_residuos_2p --fonte amostra`). Serve para conferir que o código roda de ponta a ponta; os
números **não** são os do relatório. Com `--fonte auto` (padrão), o código usa `dados/bruto/`
se houver arquivos e cai para a amostra se a pasta estiver vazia.

### Baselines da Entrega 4
```bash
python -m src.main                   # usa dados/bruto/ se houver arquivos; senão, a amostra
python -m src.main --fonte amostra   # força a amostra
python -m src.main --fonte real --horizonte 1 --min-meses-janela 1   # diagnóstico, não é a regra
```

## Estrutura
| Arquivo | Papel |
|---|---|
| `src/config.py` | caminhos, schema e parâmetros (horizonte, janela, quantil, cobertura) |
| `src/carregar.py` | escolhe a fonte, lê a tabela de vendas e valida o schema |
| `src/preparar.py` | remove linhas de total e linhas incompletas, trata negativos e monta o painel SKU × mês com zeros |
| `src/particao.py` | cria features defasadas de *H* meses, faz o split temporal e o teste de vazamento |
| `src/baselines.py` | baselines de média, mediana, sazonal ingênuo e operacional (P75 em 6 meses) |
| `src/avaliar.py` | métricas agregadas |
| `src/main.py` | fluxo ponta a ponta dos baselines (Entrega 4) |
| `src/modelo.py` | modelo da Entrega 5: Ridge em Pipeline × baselines no mesmo holdout temporal |
| `src/vazamento.py` | teste de vazamento na entrada: perturba vendas e compras brutas depois de T0 e roda o pipeline inteiro |
| `src/perfil_dados.py` | perfil agregado dos arquivos brutos |
| `src/gerar_amostra.py` | gerador da amostra sintética |
| `scripts/figura_residuos_2p.py` | figura de resíduos em 2 painéis do relatório da Entrega 5 |
| `scripts/provar_teste_vazamento.py` | mostra que o teste de vazamento falha no commit 2ddbe2e (ruptura como feature) e passa na versão atual |

## Documentos
| Arquivo | Entrega |
|---|---|
| `relatorios/relatorio_final_entrega4.md` | E04: relatório final (dados + baselines) |
| `notebooks/01_qualidade_dados.ipynb` | E04: relatório de qualidade dos dados |
| `docs/vazamento/` | E04: verificações individuais de vazamento |
| **PENDENTE** `docs/E03_canvas_ml_2026-10-08.pdf` | E03: Canvas de ML |
| **PENDENTE** `docs/E04_contrato_dados_*.pdf` | E04: contrato de dados e auditoria |
| **PENDENTE** `docs/E05_ficha_modelo1_2026-10-15.pdf` | ficha do modelo 1 |
| **PENDENTE** `docs/E05_ficha_modelo2_2026-10-22.pdf` | ficha do modelo 2 |

## Notebooks
`notebooks/` é exploratório. O pipeline oficial, que gera todos os números do relatório, é
`src/` (`python -m src.modelo`). Nenhum número do relatório sai de notebook.

## Declaração de uso de IA

**Ferramentas:** Claude (chat, Anthropic) e Claude Code (Anthropic).

**Finalidade:**
- Planejamento da entrega e definição do contrato de dados, da partição temporal e dos baselines.
- Geração da estrutura do repositório e do código em `src/` (perfil de dados, carga, preparação,
  partição, baselines, avaliação e pipeline).
- Geração da amostra sintética (`src/gerar_amostra.py`).
- Redação inicial do README e desta declaração.

**Trechos influenciados:** todo o código em `src/` foi gerado com Claude Code a partir de
especificações escritas pela equipe; a regra operacional (P75 de 6 meses, horizonte de 5 meses)
foi descrita pela equipe a partir do processo real da empresa.

**Dados e sigilo:**
- A IA não viu linhas nem valores individuais dos dados brutos. Os scripts gerados por ela
  foram executados localmente e ela teve acesso apenas a saídas agregadas: o perfil de
  metadados (`src/perfil_dados.py`: nomes de colunas, tipos, contagens, intervalos de datas) e
  métricas agregadas dos baselines (MAE, WAPE, viés, pinball, cobertura), além da amostra
  sintética.
- Incidente: durante a estruturação, o Claude Code leu trechos de arquivos de código e
  planejamento da equipe que continham informações da empresa. A leitura foi bloqueada a
  partir de então por regra de permissão em `.claude/settings.json`, e esses arquivos não
  são versionados.

**Validação:**
- O pipeline foi executado de ponta a ponta sobre a amostra sintética (`python -m src.main`).
- O teste de vazamento em `src/particao.py` foi verificado com uma versão propositalmente errada
  (defasagem de 4 meses em vez de 5), e o assert falhou como esperado.
- A equipe revisou o relatório de perfil e confirmou que ele não contém valores individuais.
- Antes de cada commit, conferimos com `git status` que nenhum arquivo de dados era versionado.
- A equipe revisou a lógica dos baselines e das métricas (pinball loss, taxa de cobertura) e a
  justificativa da janela móvel.
- A verificação individual de vazamento (`docs/vazamento/`) foi escrita por cada integrante
  sem uso de IA.
