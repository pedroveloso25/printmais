# Devolutiva com o demandante — custo do erro e capacidade

**Entrega 6 · Equipe E · Responsável: João Filipe Dantas** · conversas de 23 e 25/11/2026 com Francisco Cavalcanti Junior, gestor de compras da Print Mais

## O que o gestor disse
| Pergunta | Resposta |
|---|---|
| Quando falta produto | Pode perder o cliente para o concorrente. A maioria volta, mas **a venda perdida não volta**. |
| Margem | Cerca de **40%**. |
| Produto parado | Gira em cerca de 1 mês. Depois de **~45 dias** parado, às vezes precisa de **10% a 15% de desconto**, mas isso **acontece pouco**. |
| Limite do pedido | **Container cheio** e caixa: 1 a 2 containers por mês. |

## Dados da empresa
- **Lead time:** 113 a 162 dias entre o sinal e a chegada.
- **Container:** ~93.400 m² de mídia (soma da área das bobinas), cerca de 1.600 bobinas.
- **Lote:** piso de 30 bobinas por código que entra; acima disso, qualquer número inteiro de bobinas.
- **Baseline operacional:** média de venda dos 3 últimos meses fechados (coluna "Giro Média 30 à 90" do Sankhya).

## Decisão: τ = 0,75
- **Faltar** custa a margem perdida: **0,40 do preço**.
- **Sobrar**, sem limite de espaço, custa pouco: ~1,5 mês de capital parado (1,5% ao mês, **hipótese da equipe**; a empresa não tem esse número) mais um desconto raro. Faltar seria dezenas de vezes pior, e o τ ideal ficaria acima de 0,9.
- **Mas o container sai cheio.** Cada m² a mais num código é um m² a menos em outro. O custo real de exagerar é a venda que se perde no código que ficou de fora, da mesma ordem do custo de faltar. Isso puxa o τ para baixo, perto de 0,5.
- **Adotamos τ = 0,75**, entre os dois extremos, com **sensibilidade em 0,6 e 0,9**.
- **A restrição que morde é o container cheio e o caixa**, não o número de produtos. O modelo reparte os ~93.400 m² entre os códigos, priorizando os de maior risco de falta, com o piso de 30 bobinas.

## Limite assumido
O pedido é fechado 4 a 5 meses antes da chegada, e o modelo prevê 1 mês à frente, porque com 7 meses de histórico não há dados para treinar um horizonte maior. Está registrado como limitação da formulação.
