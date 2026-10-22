# Métricas dos baselines (agregadas)

Fonte: amostra | corte (último mês de treino): 2026-03 | horizonte: 5 | mín. meses na janela: 6 | linhas SKU×mês avaliadas: 240 de 240 no teste

| baseline | nivel | n | MAE | WAPE_% | vies_% | pinball_q0.75 | cobertura_% |
|---|---|---|---|---|---|---|---|
| media_hist | sku_mes | 240 | 135,93 | 52,35 | -27,34 | 85,72 | 40,83 |
| media_hist | total_mes | 6 | 2.840,05 | 27,34 | -27,34 | 2.130,04 | 0,00 |
| media_hist | sku_mes_sem_ruptura | 240 | 135,93 | 52,35 | -27,34 | 85,72 | 40,83 |
| mediana_hist | sku_mes | 240 | 143,57 | 55,29 | -37,79 | 96,32 | 37,08 |
| mediana_hist | total_mes | 6 | 3.925,61 | 37,79 | -37,79 | 2.944,20 | 0,00 |
| mediana_hist | sku_mes_sem_ruptura | 240 | 143,57 | 55,29 | -37,79 | 96,32 | 37,08 |
| sazonal_ingenuo | sku_mes | 240 | 162,51 | 62,58 | -7,90 | 86,38 | 53,33 |
| sazonal_ingenuo | total_mes | 6 | 969,11 | 9,33 | -7,90 | 689,60 | 16,67 |
| sazonal_ingenuo | sku_mes_sem_ruptura | 240 | 162,51 | 62,58 | -7,90 | 86,38 | 53,33 |
| operacional_p75 | sku_mes | 240 | 141,23 | 54,39 | -8,01 | 75,81 | 52,50 |
| operacional_p75 | total_mes | 6 | 1.509,95 | 14,54 | -8,01 | 962,85 | 50,00 |
| operacional_p75 | sku_mes_sem_ruptura | 240 | 141,23 | 54,39 | -8,01 | 75,81 | 52,50 |

```json
{
  "carga": {
    "fonte": "amostra",
    "arquivo": "vendas_amostra.csv",
    "linhas_lidas": 7637,
    "data_nao_convertidos": 0,
    "m2_nao_convertidos": 0
  },
  "preparo": {
    "linhas_total_removidas": 1,
    "linhas_incompletas_removidas": 0,
    "meses_parciais_removidos": [],
    "linhas_negativas": 71,
    "sku_mes_liquido_negativo_zerados": 0,
    "skus_sem_nenhuma_venda_removidos": 0,
    "skus": 40,
    "mes_inicial": "2023-10",
    "mes_final": "2026-09",
    "meses_cobertos": 36,
    "linhas_sku_mes": 1380,
    "pct_sku_mes_zerados": 8.5,
    "pct_sku_mes_com_ruptura": 0.0
  },
  "avaliacao": {
    "linhas_teste": 240,
    "linhas_avaliadas": 240,
    "skus_avaliados": 40,
    "meses_teste": 6,
    "cobertura_previsao_por_baseline_%": {
      "media_hist": 100.0,
      "mediana_hist": 100.0,
      "sazonal_ingenuo": 100.0,
      "operacional_p75": 100.0
    }
  },
  "parametros": {
    "data_corte": "2026-03",
    "horizonte": 5,
    "min_meses_janela": 6,
    "janela_operacional": 6,
    "quantil": 0.75,
    "tratamento_negativos": "liquido_piso_zero",
    "sazonal_rodou": true
  }
}
```