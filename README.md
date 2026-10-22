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
```bash
pip install -r requirements.txt
python -m src.gerar_amostra          # só na primeira vez, para a amostra sintética
python -m src.main                   # usa dados/bruto/ se houver arquivos; senão, a amostra
python -m src.main --fonte amostra   # força a amostra
python -m src.main --fonte real --horizonte 1 --min-meses-janela 1   # diagnóstico, não é a regra
```
Para os dados reais, preencha `FONTE_REAL` em `src/config.py` (arquivo, encoding, separador e
colunas) com base no perfil.

## Estrutura
| Arquivo | Papel |
|---|---|
| `src/config.py` | caminhos, schema e parâmetros (horizonte, janela, quantil, cobertura) |
| `src/carregar.py` | escolhe a fonte, lê a tabela de vendas e valida o schema |
| `src/preparar.py` | remove linhas de total e linhas incompletas, trata negativos e monta o painel SKU × mês com zeros |
| `src/particao.py` | cria features defasadas de *H* meses, faz o split temporal e o teste de vazamento |
| `src/baselines.py` | baselines de média, mediana, sazonal ingênuo e operacional (P75 em 6 meses) |
| `src/avaliar.py` | métricas agregadas |
| `src/main.py` | fluxo ponta a ponta |
| `src/perfil_dados.py` | perfil agregado dos arquivos brutos |
| `src/gerar_amostra.py` | gerador da amostra sintética |

## Declaração de uso de IA
<!-- RASCUNHO gerado pelo assistente com base no que de fato aconteceu; a equipe revisa, corrige e assina. -->
- **Ferramenta:** Claude Code (modelo Claude Opus 5.5, Anthropic), usado no terminal do projeto.
- **O que a IA gerou:** o código de `src/` (perfil de dados, carga, preparo, partição com teste de
  vazamento, baselines, avaliação, fluxo principal e gerador da amostra sintética), o
  `requirements.txt`, este README e o modelo de verificação de vazamento em `docs/vazamento/`.
- **O que a equipe fez:** definiu o problema, a regra operacional e os parâmetros (horizonte,
  janela, quantil, cobertura), passou a lógica da regra da empresa em palavras, tomou as decisões
  de tratamento, rodou e revisou o código, fez todos os commits e escreveu as verificações
  individuais de vazamento.
- **Sigilo:** a IA não recebeu linhas nem valores individuais dos dados reais. Ela só viu
  metadados agregados (o perfil) e métricas agregadas. Arquivos de trabalho com informação
  sigilosa foram bloqueados para leitura pela IA (`.claude/settings.json`) e ficaram fora do git.
  **Incidente:** no início, antes do bloqueio, a IA leu o começo de três desses arquivos de
  trabalho. O conteúdo não foi usado nem reproduzido, e as regras de bloqueio foram criadas em
  seguida.
- **Validação:** <!-- equipe: o que vocês conferiram à mão (ex.: teste de vazamento, métricas, leitura do código) -->
