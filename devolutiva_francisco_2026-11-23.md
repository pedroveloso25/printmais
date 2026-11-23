# Devolutiva com o demandante — custo do erro e capacidade (23/11/2026)

**Entrega 6 · Equipe E · Responsável: João Filipe Dantas**
Conversa com Francisco Cavalcanti Junior, gestor de compras da Print Mais, para fechar duas decisões do plano da E06: o custo de faltar contra o de sobrar, e a capacidade por pedido.

## Respostas do gestor
| Pergunta | Resposta |
|---|---|
| O que acontece quando falta um produto? | Pode perder o cliente para o concorrente, e isso pode ser uma perda irreparável. |
| O cliente volta? | A fidelização é boa: poucos vão embora de vez e a maioria volta a comprar quando o produto chega. Mas **a venda perdida não volta**. |
| Margem | A empresa trabalha para vender com **cerca de 40% de margem**. |
| Produto parado | O giro é controlado pelo estoque mínimo, que é a média de venda para girar em **1 mês**. |
| Limite do pedido | O container e o fluxo de caixa. São **1 a 2 containers por mês**, e só vale a pena **container cheio**. |

## Já confirmado pelos dados da empresa
- Lead time de 4 a 5 meses (113 a 162 dias entre o sinal e a chegada nos processos de 2026).
- Container de ~93.400 m² (~1.600 bobinas), com mínimo de 30 bobinas por código.
- Fornecedor pago antes da venda: sinal de 20% e saldo antes do embarque.

## O que isso decide no projeto
1. **Custo assimétrico.**
   - Faltar custa a margem perdida (~40% do preço) e, às vezes, o cliente.
   - Sobrar custa ~1 mês de capital parado e espaço, porque o excesso gira no mês seguinte.
   - Faltar pesa bem mais que sobrar.
2. **Métrica principal.** Pinball loss em **τ = 0,75** (faltar ~3× pior que sobrar), com sensibilidade em τ = 0,67 e 0,83, porque o gestor não deu um número exato.
3. **Capacidade.** O que limita é o **container cheio e o caixa**, não o número de produtos. O modelo deve repartir os ~93.400 m² de cada container entre os códigos, priorizando os de maior risco de falta.
4. **Baseline operacional.** Média de venda dos 3 últimos meses (estoque mínimo do Sankhya).

## Em aberto
- A razão exata "faltar é X vezes pior que sobrar", que não foi dita em número.
- O custo mensal de capital e espaço. A equipe usa 1,5% ao mês como hipótese.
