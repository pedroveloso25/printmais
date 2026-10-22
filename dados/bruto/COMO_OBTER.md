# Como obter os dados

Os dados brutos não são versionados: são dados comerciais sigilosos da Print Mais,
cedidos à equipe exclusivamente para este projeto acadêmico.

- **Fornecido por:** gestor da Print Mais, a pedido da equipe
- **Data de recebimento:** 19/10/2026
- **Origem:** arquivos CSV e XLSX gerados manualmente nos computadores da empresa
  (a empresa não utiliza ERP; não há extração automatizada)
- **Período coberto:** fev/2026 a ago/2026 (7 meses; vendas por SKU, em m²). A equipe está
  solicitando histórico anterior.

## Arquivos esperados em `dados/bruto/`

| Arquivo | Conteúdo |
| --- | --- |
| `vendas_estoque_mensal.csv` | vendas por SKU e mês, em m² e bobinas, com compras, estoque reconstruído e sinal de ruptura (tabela usada pelo pipeline) |
| `produtos.csv` | cadastro dos SKUs: largura, m² por bobina, código de demanda (equivalentes) e marcação incluir/excluir |
| `chegadas_por_item.csv` | itens das importações em trânsito, com chegada prevista |
| `baseline_cobertura.csv`, `pedido_sugerido.csv` | saídas da regra atual da empresa (só para conferência, não são entrada do modelo) |
| `vinil_dados_tratados.xlsx` | as tabelas acima em abas, mais estoque atual e dados das importações |

## Como obter acesso

Solicitar à equipe (Pedro Rebouças Veloso, João Filipe <sobrenome>), que encaminha o pedido
à empresa. Os dados não podem ser redistribuídos nem enviados a serviços externos.
