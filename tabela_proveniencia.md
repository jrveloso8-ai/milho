# Tabela de Proveniência de Dados — Módulo TRIX v5 por Contrato (Curva CCM)

Este documento registra a proveniência e rastreabilidade estrita de cada valor exibido no módulo `ccm_trix_curva.py` (gráfico interativo e resumo textual), conforme especificado na Seção 3 do contrato operacional.

---

## 1. Classificações Formais

| Classificação | Definição Operacional no Módulo |
| :--- | :--- |
| **MEDIDO** | Dado real observado diretamente no mercado e retornado pela BRAPI/B3 para o contrato específico em pregão com negócio. Inclui OHLC real, volume, trades e contagem de contratos em aberto de opções. |
| **DERIVADO** | Indicador ou barreira calculado matematicamente por código determinístico (`trix_v5.py`, `calcular_wall`, `calcular_max_pain`) **a partir de insumos 100% reais** (sem contaminação de dados sintéticos). |
| **ESTIMADO** | Qualquer valor cujo cálculo dependa de aproximação ou de dados sintéticos. Inclui todo o trecho sintético do seed (ajustado por offset aditivo) e **qualquer valor de SMA(100), TRIX ou posição** cuja janela de cálculo toque pelo menos um dia sintético (regra de contágio). |
| **INDISPONIVEL** | Ausência real de dado na fonte oficial. Representado explicitamente como `N/D`. Jamais preenchido com dados aproximados ou de outro vencimento. |
| **SIMULADO** | Proibido. Nenhum dado deste tipo existe ou é permitido neste módulo. |

---

## 2. Regra de Contágio

Quando um valor combina insumos de mais de uma classificação, o resultado herda a **pior classificação** entre elas:
$$\text{ESTIMADO} \text{ contamina } \text{DERIVADO}$$

*Impacto Prático:*
- A média móvel de longo prazo **SMA(100)** precisa de 100 pregões passados.
- Nos primeiros 99 pregões reais após a costura do seed histórico, a janela da SMA(100) toca pelo menos um pregão sintético. Portanto, a SMA(100) e o estado do sistema (`posicao_trix_v5`) são classificados como **ESTIMADO**.
- Apenas a partir do **100º pregão real** com negócio é que a janela se torna 100% composta por dias reais medidos, transicionando o status para **DERIVADO** puro.

---

## 3. Matriz de Proveniência por Campo

| Campo Exibido | Origem / Mecanismo de Obtenção | Classificação | Justificativa / Rastreabilidade |
| :--- | :--- | :--- | :--- |
| **Preço Candle (Close, High, Low)** | BRAPI `/v2/futures/historical?symbol={ticker}` (`history.close/high/low`) | **MEDIDO** | Preço real negociado em pregão com negócio (`is_sintetico = False`). O trecho sintético nunca é plotado como candle. |
| **Preço Candle (Open)** | Proxy: `Close_{t-1}` (primeiro pregão usa `Close_t`) | **MEDIDO** (ou **ESTIMADO** no 1º pregão real) | Abertura não é fornecida pela B3/BRAPI para CCM. O proxy documentado reflete o fechamento anterior medido (MEDIDO). No 1º pregão real pós-seed, o código classifica explicitamente como ESTIMADO (Opção a), pois o valor decorre do último Close sintético. |
| **Volume de Negociação** | BRAPI `/v2/futures/historical` (`history.volume`) | **MEDIDO** | Quantidade real de contratos CCM negociados no pregão. |
| **Quantidade de Negócios (Qtd)** | BRAPI `/v2/futures/historical` (`history.trades`) | **MEDIDO** | Número real de negócios fechados no pregão. |
| **Série do Seed Histórico (2008–2026)** | Arquivo fixo `ccmfut_seed_2008_2026.csv` + offset aditivo | **ESTIMADO** | Histórico contínuo do CCMFUT exportado do Profit/Genial, truncado e deslocado por offset aditivo. Existe apenas para alimentar o cálculo inicial dos indicadores, sem ser plotado. |
| **trend_sma100 (SMA 100)** | Média móvel aritmética dos últimos 100 pregões de Close | **DERIVADO** ou **ESTIMADO** | **DERIVADO** se todos os 100 pregões da janela forem reais (`is_sintetico = False`). **ESTIMADO** se qualquer um dos 100 pregões tocar o seed sintético (regra de contágio). |
| **trix / trix_sinal** | Tripla EMA(7) e SMA(3) calculados por `trix_v5.py` | **DERIVADO** ou **ESTIMADO** | **DERIVADO** quando os últimos 100 pregões da janela forem reais. **ESTIMADO** se tocar o seed (corte unificado em 100 pregões por consistência metodológica com a SMA(100)). |
| **posicao_trix_v5 (Estado)** | Máquina de estados em `trix_v5.calc_sinais_trix_v5` | **DERIVADO** ou **ESTIMADO** | Depende do cruzamento e do filtro de tendência `trend_sma100`. Herda a pior classificação entre o preço e a SMA(100). |
| **entrada_hoje / saida_hoje** | Evento de abertura/fechamento de posição no bar | **DERIVADO** ou **ESTIMADO** | Gerado na barra exata do evento de sinal. Herda a classificação do estado naquele bar. |
| **Call Wall (preço)** | `ingestao_brapi.calcular_wall(calls, preco, 'call')` | **DERIVADO** ou **INDISPONIVEL** | Strike com maior concentração de OI acima do preço atual. Classificado como **DERIVADO** quando há opções ativas; **INDISPONIVEL** (`N/D`) caso não haja opções líquidas. |
| **Put Wall (preço)** | `ingestao_brapi.calcular_wall(puts, preco, 'put')` | **DERIVADO** ou **INDISPONIVEL** | Strike com maior concentração de OI abaixo do preço atual. **DERIVADO** com opções ativas; **INDISPONIVEL** (`N/D`) se ausente. |
| **Max Pain (preço)** | `ingestao_brapi.calcular_max_pain(calls, puts)` | **DERIVADO** ou **INDISPONIVEL** | Strike que minimiza o payout dos titulares de opções. **DERIVADO** com dados; **INDISPONIVEL** (`N/D`) se ausente. |
| **Contratos em Aberto da Wall (OI)** | BRAPI `/v2/futures/options/positions` (`calls[strike]` / `puts[strike]`) | **MEDIDO** ou **INDISPONIVEL** | Quantidade real de contratos em aberto registrada na B3 para aquele strike específico. Se a parede for N/D, fica **INDISPONIVEL**. |
| **Dado Inventado / Interpolado** | Inexistente | **SIMULADO** | Proibido expressamente no sistema. Nenhuma simulação é realizada para preencher vazios. |

---

## 4. Auditoria Analítica por Contrato Ativo (Snapshot Atual)

Com base na execução sobre os dados reais da curva de contratos vivos em 18/09/2026:

| Contrato | Vencimento | Pregões Reais | Status SMA(100) Atual | Data de Transição para DERIVADO Puro | Barreiras de Opções |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **CCMX26** | 16/11/2026 | 235 | **DERIVADO** | **02/03/2026** (100º pregão real) | Call Wall: R$ 80.00 (6,580 contratos) \| Put Wall: R$ 75.00 (3,104 contratos) \| Max Pain: R$ 71.00 |
| **CCMF27** | 15/01/2027 | 169 | **DERIVADO** | **11/06/2026** (100º pregão real) | Call Wall: R$ 90.00 (4,000 contratos) \| Put Wall: R$ 70.00 (3,430 contratos) \| Max Pain: R$ 76.00 |
| **CCMH27** | 15/03/2027 | 157 | **DERIVADO** | **29/06/2026** (100º pregão real) | Call Wall: R$ 84.00 (1,273 contratos) \| Put Wall: R$ 75.00 (629 contratos) \| Max Pain: R$ 75.25 |
| **CCMK27** | 17/05/2027 | 81 | **ESTIMADO** | *Pendente* (faltam 19 pregões reais) | Call Wall: R$ 85.00 (700 contratos) \| Put Wall: R$ 73.00 (772 contratos) \| Max Pain: R$ 78.00 |
| **CCMN27** | 15/07/2027 | 60 | **ESTIMADO** | *Pendente* (faltam 40 pregões reais) | Call Wall: R$ 79.50 (850 contratos) \| Put Wall: R$ 72.75 (2,200 contratos) \| Max Pain: R$ 73.50 |
| **CCMU27** | 15/09/2027 | 120 | **DERIVADO** | **19/08/2026** (100º pregão real) | Call Wall: R$ 80.00 (7,354 contratos) \| Put Wall: R$ 67.00 (5,724 contratos) \| Max Pain: R$ 74.00 |
| **CCMX27** | 16/11/2027 | 42 | **ESTIMADO** | *Pendente* (faltam 58 pregões reais) | Call Wall: R$ 83.00 (6 contratos) \| Put Wall: R$ 68.00 (500 contratos) \| Max Pain: R$ 72.00 |

---

## 5. Proveniência da Watchlist (Curva CCM vs RTCNI Físico)

Conforme especificado na seção 2.6b do prompt original, a Watchlist apresenta a lista de observação dos contratos vivos da curva CCM lado a lado com o preço físico do milho (RTCNI):

| Campo da Watchlist | Origem dos Dados | Classificação | Justificativa / Rastreabilidade |
| :--- | :--- | :--- | :--- |
| **Último Fechamento CCM (R$)** | Close do dia mais recente com `is_sintetico=False` via BRAPI `/v2/futures/historical` | **MEDIDO** | Último preço de fechamento real e efetivamente negociado na B3 para o contrato CCM. |
| **Preço RTCNI Físico (R$)** | `convergencia.obter_rtcni_atual()`, campo `rtcni_preco` | **MEDIDO** | Indicador físico Cepea/Esalq (RTCNI) obtido sem reimplementação, estritamente medido no mercado à vista. |
| **Base / Spread (R$)** | Diferença aritmética simples (`Fechamento CCM - RTCNI`) | **DERIVADO** | Cálculo aritmético direto entre duas grandezas puramente medidas. |

*Nota de Limitação e Rastreabilidade do RTCNI*: O RTCNI é obtido primordialmente via integração e ingestão online direta na fonte oficial (CEPEA/ESALQ) e espelho confiável (Notícias Agrícolas), eliminando a dependência de arquivo exportado manualmente do Profit/Genial (que permanece no sistema unicamente como base histórica prévia e fallback defensivo para indisponibilidade de conexão). A data de referência (`rtcni_data`) reflete o fechamento diário medido mais recente (defasagem típica de 0 a 1 dia útil). Quando a defasagem entre Data CCM e Data RTCNI ultrapassar 7 dias corridos (ex.: feriados prolongados ou falha persistente de rede sem sincronização), um aviso explícito `[DEFASADO — Xd]` é exibido ao lado do valor no resumo de texto e no dashboard HTML, preservando a classificação **MEDIDO** (o valor reflete o último fechamento real medido no físico, sem alteração de proveniência).

*Nota de Auditoria*: Nenhum indicador técnico, sinal de posição, interpolação ou cor de estado é aplicado na Watchlist. Todos os preços exibidos têm proveniência estritamente **MEDIDO**.

---

## 6. Proveniência do Módulo Sentinel-Corn 2.0 (Análise 360°)

Conforme implementado em `sentinel_engine.py` e integrado no pipeline e dashboard:

| **CME Chicago Corn (CBOT ZC)** | Coleta via `yfinance` (`ZC=F`) de cotação real do pregão da CME | **MEDIDO** ou **INDISPONIVEL** | Cotação em centavos de dólar por bushel do milho na Bolsa de Chicago. Se indisponível, marcado como `[INDISPONIVEL]`. |
| **Dólar Futuro (WDOFUT)** | BRAPI `/v2/futures/term-structure?asset=WDO` (`settlement`) | **MEDIDO** ou **INDISPONIVEL** | Cotação de liquidação do primeiro contrato vigente do WDO na B3. Se indisponível, marcado como `[INDISPONIVEL]`. |
| **Preço de Paridade de Exportação (PPE)** | Fórmula matemática: `((CBOT + Prêmio) * 0.39368 * Câmbio * 0.06) - Custos` | **DERIVADO** ou **INDISPONIVEL** | Cálculo determinístico com CBOT e Câmbio reais (MEDIDO) e parâmetros de custos portuários auditados. Se insumos faltarem, marcado como `INDISPONIVEL`. |
| **Ponto de Inflexão Cambial (WDO)** | Isolamento algébrico: `(Preço_B3 + Custos) / ((CBOT + Prêmio) * 0.39368 * 0.06)` | **DERIVADO** ou **INDISPONIVEL** | Nível exato de câmbio que iguala paridade de exportação ao mercado interno. |
| **Matriz de Decisão Basis vs Paridade** | Algoritmo determinístico de spreads entre B3, RTCNI físico e PPE | **DERIVADO** | Classificação algorítmica estrita (Alerta de Venda, Oportunidade de Compra, etc.) sem arbitrariedade. Se PPE for N/D, indica `PARIDADE INDISPONÍVEL`. |
| **Sentimento de Mercado (RSS, 20%)** | RSS oficial de notícias agrícolas (feed XML real) + dicionário léxico auditado | **DERIVADO** | Score léxico determinístico no intervalo [-100, +100] sobre manchetes reais. Sem dados inventados. |
| **Calendário Econômico (20%)** | Calendário oficial de relatórios USDA (WASDE) e CONAB | **DERIVADO** / **MEDIDO** | Janela temporal baseada nas datas oficiais de divulgação de safra. |
| **Sentimento Técnico & Opções (60%)** | Ponderação TRIX v5, NTSL e barreiras reais de Call/Put Wall e Max Pain | **DERIVADO** | Indicadores técnicos e concentração de Open Interest apurados pela B3. |
| **Score Consolidado e Classificação** | Média ponderada linear: $0.60 \times \text{Técnico} + 0.20 \times \text{RSS} + 0.20 \times \text{Calendário}$ | **DERIVADO** | Classificação formal em ALTISTA, LATERAL ou BAIXISTA com rastreabilidade 100% matemática. |
