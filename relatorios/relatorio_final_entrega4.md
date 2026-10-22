# Relatório final — Entrega 4 (dados + baselines) · Print Mais

> Este relatório só tem informação agregada: nenhuma linha, valor individual, volume em m²,
> custo ou nome de fornecedor.

## 1. Problema
- **Decisão apoiada:** quanto pedir em cada importação. O lead time é de 4 a 5 meses, e a venda
  perdida por falta de estoque não volta.
- **Alvo:** demanda mensal por código de demanda, em m² vendidos.
- **Unidade de análise:** código de demanda × mês.

  **Termos usados neste relatório:**
  - **código** (coluna `codigo`) é o SKU como está no cadastro da empresa;
  - **código de demanda** (coluna `codigo_demanda`) agrupa códigos equivalentes ou substitutos,
    porque a venda migra entre eles quando um falta.

  Quando não está escrito "código", o número se refere a **códigos de demanda**.
- **Horizonte:** H = 5. A previsão do mês *t* usa só informação até *t − 5*.
- **Regra operacional da empresa (baseline a bater):** P75 da demanda mensal dos últimos 6
  meses disponíveis na data do pedido.
- **Uso a jusante:** o pedido cobre 2 meses após a chegada. A demanda é convertida em bobinas
  (m² por bobina de cada código), com lote mínimo por código e capacidade do container fixa em m².

## 2. O que está pronto no repositório
| Módulo | Função |
|---|---|
| `src/perfil_dados.py` | perfil só com metadados agregados: tipos, nulos, cardinalidade, datas, estatísticas, duplicatas, casamento de chaves |
| `src/config.py` | schema real, caminhos e parâmetros (`HORIZONTE=5`, `JANELA_OPERACIONAL=6`, `QUANTIL=0.75`, `MESES_COBERTURA=2`) |
| `src/carregar.py` | lê as vendas e valida o schema; usa a amostra sintética se `dados/bruto/` estiver vazio |
| `src/preparar.py` | monta o painel código de demanda × mês, completa com zeros a partir da 1ª venda, remove meses parciais e linhas de total, trata negativos e agrega o sinal de ruptura |
| `src/particao.py` | features com `groupby + shift(H)`, split temporal e **teste de vazamento por perturbação** (embaralha o futuro e exige features iguais); validado com uma versão de propósito errada |
| `src/baselines.py` | média e mediana históricas, sazonal ingênuo (desliga se houver menos de 24 meses) e operacional P75 em **janela móvel** |
| `src/avaliar.py` | MAE, WAPE, viés, pinball (q = 0,75) e cobertura em três níveis: código de demanda × mês, total do mês e código de demanda × mês sem ruptura; sem MAPE |
| `src/main.py` | fluxo ponta a ponta; `--horizonte` e `--min-meses-janela` servem só para diagnóstico |
| `src/gerar_amostra.py` | amostra 100% sintética, versionada |
| `notebooks/01_qualidade_dados.ipynb` | relatório de qualidade |
| `docs/vazamento/` | verificações individuais de vazamento, sem IA |
| README | problema, regra, limitações, como rodar e declaração de uso de IA |

**Sigilo:** dados reais e relatórios sobre eles são ignorados pelo git. A leitura pela IA está
bloqueada em `.claude/settings.json`. As métricas reais ficam em `relatorios/real/`, que também
é ignorado.

## 3. Dados recebidos (do perfil agregado)
- Os arquivos são CSV/XLSX montados manualmente pela empresa, que não tem ERP. Chegaram **já
  agregados por código × mês**.
- **Tabela de vendas:** `vendas_estoque_mensal.csv`, com `mes`, `codigo_demanda`, `vendas_m2`,
  `incluir`, `mes_parcial` e `possivel_ruptura`.
- **Demais tabelas:**
  - cadastro de produtos;
  - estoque atual (foto do dia);
  - itens em trânsito e chegadas previstas;
  - pagamentos das importações, irrelevante para a demanda;
  - duas tabelas que são **saída da regra atual**, excluídas como entrada para evitar
    circularidade e vazamento.
- **Período:** fev–out/2026. Fevereiro e outubro são parciais e foram excluídos, o que deixa
  **7 meses completos** (mar–set/2026).
- **Da base ao painel:**

| Etapa | Códigos | Códigos de demanda |
|---|---:|---:|
| Na base | 73 | 64 |
| Removidos pelo filtro `incluir` | 19 | 19 |
| Depois do filtro | 54 | 45 |
| Removidos por não terem venda nos 7 meses completos | — | 15 |
| **No painel** | — | **30** (204 linhas código de demanda × mês) |

- **Filtro `incluir`:**
  - É uma marcação verdadeiro/falso por código, que vem do tratamento feito antes de os dados
    chegarem ao repositório. Ela é constante em todos os meses de cada código.
  - Cada um dos 19 códigos excluídos é o seu próprio código de demanda. Nenhum código de demanda
    mistura códigos incluídos e excluídos.
  - O cadastro tem a coluna `motivo_exclusao`, com 5 motivos distintos.
  - **Quem definiu o filtro e com qual critério ainda não está documentado.** A pergunta foi
    para a lista da seção 6.
- **Qualidade:**
  - nenhum nulo, negativo, duplicata ou linha de total na tabela de vendas;
  - casamento de chaves de 100% entre vendas e cadastro;
  - 10,3% das linhas código de demanda × mês do painel são zero;
  - 15,2% dessas linhas têm ruptura, contada só quando todos os códigos do grupo estavam sem
    estoque;
  - o estoque reconstruído fica negativo em cerca de 100 linhas, por isso não é usado como
    feature.

## 4. Resultados
- **Regra exata (H = 5, janela 6): 0 linhas avaliáveis.** Para que a janela tenha 6 meses em
  *t − 5*, *t* precisa ser pelo menos o 11º mês completo, e a base tem 7.
- **Diagnóstico com H = 5 e janela com os meses disponíveis:** só 2 meses de teste e janela de 1
  a 2 meses. Não serve como evidência.
- **Diagnóstico com H = 1**, só para validar o pipeline com dados reais (174 linhas código de
  demanda × mês, com teste de abr a set/2026):

| baseline | WAPE % | viés % | cobertura % | pinball (relativo) |
|---|---|---|---|---|
| média histórica | 38,7 | +10,2 | 62,6 | 2º |
| mediana histórica | 38,0 | +8,7 | 59,8 | 3º |
| operacional P75 | 42,9 | +20,9 | 69,0 | **1º (menor)** |

**Atenção: este diagnóstico NÃO é a regra da empresa.**
- **A janela do P75 é expansiva**, de 1 a 6 meses, e não os 6 meses da regra real. Com H = 1, a
  previsão de abril usa só março, a de maio usa mar–abr, e assim por diante. Só setembro chega a
  ter 6 meses na janela. No 1º mês de teste, o "P75" é simplesmente o valor do mês anterior.
- **Média e mediana usam o mesmo histórico curto.**
- **O teste tem cerca de 6 meses e cerca de 30 códigos de demanda.**

Por isso, **a ordem entre os baselines não é evidência.** O diagnóstico só confirma que o
pipeline roda com os dados reais.

O padrão observado é coerente com o esperado de um P75: WAPE pior, pinball menor e cobertura
mais perto de 75%. Mas, com essa janela e esse teste, isso não permite concluir nada sobre a
regra.

## 5. Decisões de tratamento e efeito nos baselines
| Decisão | Efeito |
|---|---|
| Excluir meses parciais | evita meses de meia venda; reduz o histórico de 9 para 7 meses |
| Código de demanda começa na 1ª venda > 0; os sem venda são removidos | média e P75 não são puxados por zeros anteriores ao lançamento |
| Somar equivalentes (`codigo_demanda`) | reduz a ruptura aparente, porque a demanda que migrou para o equivalente continua contada |
| Ruptura mantida no treino e reportada à parte | mostra quanto a ruptura distorce as métricas (venda abaixo da demanda) |
| Janela móvel no backtest | repete a decisão de cada pedido sem vazar informação |
| Sem MAPE; pinball e cobertura como métricas principais | avaliam o P75 pelo que ele tenta fazer |

## 6. Bloqueio e pendências
1. **Histórico:** é preciso de **pelo menos 17 meses completos** (H 5 + janela 6 + 6 de teste)
   para avaliar a regra, e 24 para o sazonal ingênuo. A equipe pediu histórico anterior a
   fev/2026.
2. **Perguntas à empresa (ou a quem fez o tratamento):**
   - quem define o filtro `incluir` e com qual critério? Ele remove 19 de 64 códigos de demanda;
   - as vendas já vêm líquidas de devolução?
   - como o estoque foi reconstruído e por que fica negativo?
   - qual é o critério de `possivel_ruptura`?
3. Conferir a data de recebimento dos dados contra a data de posição do estoque.
4. Verificação individual de vazamento do segundo integrante.

## 7. Próximos passos propostos (para discutir)
- **Se vier histórico:** rodar de novo o perfil e o `config.py`, fixar `DATA_CORTE = último − 6`
  e avaliar a regra exata.
- **Se não vier, reformular:**
  - avaliar com horizontes curtos (1 a 2 meses) como aproximação, declarando a limitação;
  - modelar no agregado (linha × largura) para ter mais sinal;
  - tratar a ruptura como demanda censurada, imputando nos meses de ruptura;
  - acumular dados mês a mês daqui em diante e avaliar com origem móvel conforme o histórico
    crescer.
- **Avaliar pelo custo:** simular o custo de faltar × o custo de sobrar na decisão em bobinas,
  com lote mínimo e container, não só pelas métricas de previsão.
