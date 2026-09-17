# Manual de Operação — Dashboard Milho Trader (CCM B3)

Versão 1.0 — 10/07/2026
Refere-se a `milho_dashboard.html`, alimentado por `dados_milho.json` (gerado por `pipeline.py`).

Este documento é operacional: o que cada campo mostra, como ler, e como decidir. Não repete o racional de projeto (isso está no `milho_trader_GPM_v2_0.docx`) nem o contrato de conteúdo do relatório semanal (isso está no `SYSTEM_PROMPT_v1.0.md`).

---

## 1. Fluxo diário

1. Rode `rodar_pipeline.bat` (ou `python pipeline.py`) **antes** de abrir o dashboard. Ele lê todos os CSVs da pasta e gera `dados_milho.json`.
2. Rode `abrir_dashboard.bat`. Ele sobe um servidor local e abre `http://localhost:8000/milho_dashboard.html`.
3. Se `dados_milho.json` não existir na pasta, o dashboard abre em **modo demonstração** (banner amarelo) com dados fictícios — nunca opere olhando esse modo.
4. Clique em **Atualizar** (canto superior direito) sempre que rodar o pipeline de novo durante o dia — o dashboard não recarrega sozinho.

**Regra prática:** o horário em "Atualizado: HH:MM:SS" no topo é a hora em que o `pipeline.py` rodou, não a hora atual. Se essa hora for de horas atrás, os números na tela são véspera, não agora.

---

## 2. Topbar (sempre visível, em todas as abas)

| Campo | Fonte | O que significa |
|---|---|---|
| CCM Último | CCMFUT (contrato contínuo) | Preço do milho futuro "genérico" — **não é necessariamente igual ao preço do contrato específico em vigor** (ver Seção 8, Limitação 1). |
| WDOFUT | WDOFUT_F_0 | Câmbio operacional (R$/1000 USD ÷ 1000 = R$/USD). |
| ZC Chicago | yfinance (ZC=F) | Milho em Chicago, cents/bushel — referência internacional. |
| Brent | yfinance (BZ=F) | Petróleo — usado como proxy de custo de etanol/demanda. |
| RTCNI | RTCNI_F_0 | Preço físico à vista (Campinas) — a "âncora" real do produto. |
| Spread | CCM − RTCNI | Prêmio do futuro sobre o físico, com Z-score (ver Seção 6). |
| Curva | Classificação automática | CONTANGO / BACKWARDATION / FLAT — ver ressalva na Seção 5. |
| DI Jan/27 | DI1F27_F_0 | Taxa de juros usada no cálculo de custo de carrego. |

---

## 3. Aba Decisão

É o resumo executivo — a primeira coisa a olhar, mas **nunca a única**.

- **Banner grande** (verde/vermelho/cinza): resultado consolidado quando os dois sistemas técnicos (EMA 9/20 e Setup 9.1) apontam para o mesmo lado. Mostra a direção, não a força.
- **CCM Último**: preço, data do último pregão, variação semanal.
- **Sinal EMA 9/20** e **Setup 9.1**: direção de cada sistema + a inclinação da EMA9 (`slope`).
- **Vencimento Ativo**: o contrato específico com maior volume nos últimos 5 pregões (ex.: CCMU26) — é só identificação, os cálculos técnicos continuam vindo do CCMFUT contínuo.
- **Filtros de Entrada**: checklist verde/vermelho para EMA 9/20, Setup 9.1, Convergência (\|Z\|<1,5), Diagnóstico Câmbio, ZC Disponível. É um resumo binário — não mostra magnitude.
- **Alertas Ativos**: aparece algo aqui só se a convergência estourar 1,5σ. Vazio = sem distorção relevante.
- **Sizing por Perfil**: contratos, stop mensal total e capital de margem estimado por perfil de risco (conservador/moderado/arrojado), calculado a partir do ATR do dia.

**Regra de ouro desta aba:** o banner pode dizer "VENDA" com um sinal estatisticamente irrelevante. Nunca opere só pelo banner — confirme na aba **Guia Operador** (Seção 4), que já calcula a força do sinal automaticamente.

---

## 4. Aba Guia Operador

Esta é a aba para quem está na frente da plataforma decidindo se entra ou não — faz o cálculo que antes exigia ir na aba Técnico com calculadora e devolve **um veredito único**:

- 🟢 **OPERAR [direção]** — sinal forte (gap EMA9/EMA20 ≥ 50% do ATR14) e nenhum filtro de contexto contra.
- 🟡 **OPERAR [direção] — TAMANHO REDUZIDO** — sinal moderado (gap entre 15% e 50% do ATR) ou exatamente 1 filtro de contexto reprovado.
- 🔴 **NÃO OPERAR** — sistemas EMA 9/20 e Setup 9.1 divergentes, gap abaixo de 15% do ATR (ruído), ou 2+ filtros de contexto reprovados ao mesmo tempo.

O card "Por que esta decisão?" mostra os 5 critérios que compõem o veredito (Direção, Força do Sinal, Câmbio, Convergência, Sazonalidade), cada um com semáforo verde/amarelo/vermelho — a mesma lógica documentada na Seção 5 (regra do gap_relativo), só que calculada pela própria página em vez de manualmente.

Quando o veredito é OPERAR ou OPERAR REDUZIDO, o card "Execução Recomendada" já traz Stop, Alvo (R:R 2:1) e o número de contratos sugerido para o perfil de risco compatível com aquele veredito — arrojado nunca é o padrão sugerido, mesmo em sinal forte, ele fica disponível como opção manual para quem tem tolerância a mais risco. Se o Alvo R:R passar do Call Wall (compra) ou do Put Wall (venda) — ver Seção 10 — um aviso amarelo aparece nesse mesmo card; é só um alerta de contexto, **não** entra no cálculo do veredito.

**Ressalva:** o critério "Sazonalidade" só entra no cálculo se `sazonalidade.status === 'OK'` no JSON; sem esse dado, o critério fica neutro (amarelo) e não derruba nem aprova o veredito sozinho — igual ao que já vale para os outros filtros de contexto (nenhum reprova sozinho, só em conjunto).

**Convergência é direcional, não é só |Z| < 1,5 (corrigido em 11/07/2026):** o critério só reprova quando o veredito de convergência (Seção 7) é *acionável* (|Z| > 1,5 e vencimento ≤15 dias) **e** aponta para o lado contrário do sinal técnico. Uma distorção distante do vencimento fica neutra; se a convergência concordar com a direção técnica, o critério fica verde — vira um reforço, não uma ameaça.

**Calendário Econômico é o único gate absoluto (adicionado em 11/07/2026):** diferente dos outros 5 critérios (que só reprovam em conjunto, 2+ ao mesmo tempo), se hoje for dia de divulgação WASDE/Estoques Trimestrais (USDA) ou Boletim da Safra de Grãos (CONAB), o veredito é **NÃO OPERAR** sozinho, independente de direção, força do sinal ou qualquer outro filtro. Motivo: volatilidade de divulgação pode passar por cima de qualquer stop técnico calculado com ATR — não é um risco que o resto do sistema foi desenhado para absorver. Ver Seção 12.

---

## 5. Aba Técnico

Onde se mede a **força** do sinal, não só a direção.

- **EMA 9 / EMA 20**: valores absolutos e a inclinação (slope) da EMA9.
- **ATR 14**: volatilidade diária esperada, em R$/saca. É a régua para calibrar tudo nesta aba.
- **Max Pain / Call Wall / Put Wall**: calculado a partir da grade de opções CCM (`CCM_OP.xlsx`, exportada do Profit/Genial), filtrada pelo mesmo vencimento do "Vencimento Ativo". Call Wall = strike de CALL com maior OI acima do preço atual (resistência); Put Wall = strike de PUT com maior OI abaixo do preço atual (suporte); Max Pain = strike que minimiza o payout agregado a titulares no vencimento — definição padrão de mercado por OI bruto, não gamma-weighted. **Ressalva de liquidez:** opções de milho na B3 costumam ter OI concentrado em poucos strikes; nas semanas de baixa liquidez, os três valores podem ficar "—" (grade não encontrada) mesmo com o resto do dashboard atualizado — isso é esperado, não é bug.
- **Sistema Principal (EMA 9/20)**: mostra se o preço está acima/abaixo da EMA20 e a inclinação da EMA9, com o histórico de backtest (WR 66,7%, Payoff 2,52x, 9 trades em Jun/24–Jun/26).
- **Setup 9.1**: sinal de virada de inclinação da EMA9, com seu próprio histórico (WR 37,9%, Payoff 4,03x, 29 trades).
- **Posição do Preço**: barra visual entre suporte e resistência dos últimos 20 pregões.
- **Parâmetros Operacionais**: Stop (ATR×1,5, preço absoluto), Alvo (R:R 2:1, preço absoluto) e Risco por contrato em R$.

### Regra prática — filtro de magnitude (não existe no código, aplique manualmente)

O sistema dispara COMPRA/VENDA sempre que `EMA9` cruza `EMA20`, **sem piso de magnitude**. Antes de tratar um sinal como acionável, compare:

```
gap = |EMA9 − EMA20|
gap_relativo = gap / ATR14
```

- `gap_relativo` < ~15% → sinal marginal, tratar como **ruído**, não operar só por ele mesmo que o rótulo diga COMPRA/VENDA.
- `gap_relativo` > ~50% → sinal com separação real entre as médias, mais confiável.

Isso não está automatizado no dashboard — é uma leitura que você faz olhando os dois números (EMA9/EMA20 no card, ATR14 no card ao lado).

Lembre também: o backtest do sistema principal tem só **9 trades** em 2 anos — amostra pequena para qualquer sinal isolado, use como contexto histórico, não como garantia estatística.

---

## 6. Aba Macro

Responde uma pergunta central: **isso é milho ou é câmbio?**

- **USDBRL / DXY / ZC Chicago / Brent**: níveis e variação semanal.
- **Câmbio – Diagnóstico**: `MILHO`, `CAMBIO` ou `MISTO` — compara o câmbio implícito no preço do CCM contra o WDOFUT real. Se `CAMBIO`, o movimento do CCM em reais está sendo puxado pelo dólar, não por fundamentos de milho — não trate como sinal direcional de milho.
- **ZC Chicago vs CCM — Paridade**: paridade internacional calculada (`ZC × 0,3937 × USDBRL / 100`) e se o CCM negocia com prêmio ou desconto sobre ela.
- **Custo de Carrego — DI Futuro**: taxa DI Jan/27, DI Jan/29 e o preço justo teórico Jan/27 (quanto o contrato de janeiro *deveria* valer, dado o custo de capital). Compare com o preço realmente negociado desse vencimento na aba Curva.

---

## 7. Aba Convergência

Mede se o futuro está caro ou barato **frente ao físico** (RTCNI) — e, desde 11/07/2026, diz **o que fazer com isso**, não só mostra o número.

- **RTCNI**: preço físico à vista, Campinas.
- **Spread Futuro × Físico**: `CCMFUT − RTCNI`.
- **Z-Score**: quantos desvios-padrão o spread atual está da média histórica. **Corrigido em 11/07/2026** — média e desvio-padrão agora vêm do histórico real (todas as datas em que CCMFUT e RTCNI têm pregão em comum, hoje ~2 anos, janela que cresce a cada rodada do pipeline), não mais das constantes fixas R$6,51/R$3,50 que estavam no código sem origem documentada. O desvio-padrão real medido é bem maior (~R$5,31/sc) que a constante antiga assumia — ou seja, o Z-score antigo superestimava distorções.
- **Banner de veredito** (novo): resume em uma frase o que fazer.
  - 🟢/🔴 **TESE: pressão de alta/queda (convergência)** — só aparece quando |Z| > 1,5 **e** o vencimento do contrato ativo está a ≤15 dias. É aqui que a convergência vira tese de operação de verdade: como o CCM é liquidação financeira, perto do vencimento existe um mecanismo real empurrando o futuro para perto do físico — não é teoria especulativa, é o próprio mecanismo de liquidação.
  - 🟡 **DISTORÇÃO — MONITORAR** — |Z| > 1,5 mas vencimento ainda longe. Distorção real, mas nada obriga o preço a convergir ainda; pode persistir ou alargar por semanas. Não é tese de operação, é só um item para acompanhar.
  - ➖ **SEM TESE DE CONVERGÊNCIA** — |Z| ≤ 1,5, spread dentro do normal.
- **Gráfico histórico**: agora mostra o spread semanal **real** dos últimos meses (antes era ruído aleatório gerado no navegador — bug corrigido em 11/07/2026), contra a banda de ±1,5σ calculada com o desvio real.

**Por que isso também mudou o Guia Operador:** o critério "Convergência" na aba Guia Operador agora só conta como falha quando o veredito de convergência é acionável **e** aponta para o lado contrário da direção técnica (EMA/Setup 9.1). Se for uma distorção distante do vencimento, ou se concordar com a direção técnica, não reprova mais a operação — pelo contrário, concordância soma a favor.

**Atenção a dados desatualizados:** o RTCNI é um dos arquivos que mais historicamente ficou atrasado em relação ao CCMFUT (ver Seção 10). Confira a data do RTCNI no card antes de confiar no Z-score do dia.

---

## 8. Aba Curva

Estrutura de preços por vencimento — CONTANGO (preços sobem com o tempo, custo de carrego normal) ou BACKWARDATION (preços caem com o tempo, sinal de escassez de curto prazo ou prêmio por entrega imediata).

- **Estrutura da Curva**: classificação automática (ver ressalva abaixo).
- **Spread Ponta a Ponta**: diferença entre o contrato mais distante e o mais próximo.
- **Gráfico e Tabela de Contratos Ativos**: preço e spread vs. o contrato anterior **na ordem cronológica correta** (corrigido em 10/07/2026 — antes a ordenação era alfabética pelo código do contrato, o que misturava anos e produzia leituras erradas de contango/backwardation).

**Ressalva sobre a classificação CONTANGO/BACKWARDATION/FLAT:** o método atual conta quantos trechos consecutivos da curva sobem vs. descem — é um proxy simples, não uma régua formal (ex.: não diferencia "sobe muito uma vez, cai pouco quatro vezes" de uma tendência real). Trate o rótulo (ex.: "FLAT") como orientação inicial, e olhe a tabela de contratos para confirmar visualmente o formato da curva antes de montar qualquer operação de calendar spread.

**Contratos vencidos são excluídos automaticamente (corrigido em 10/07/2026).** A curva só entra com contratos cujo mês/ano de vencimento ainda não passou em relação à data de hoje. Antes, contratos mortos (ex.: CCMH26 vencido em Mar/2026) continuavam contando no "Spread Ponta a Ponta" e na classificação da estrutura mesmo sem atualização — o que já havia distorcido uma leitura de "FLAT" quando a curva viva era, de fato, CONTANGO.

**Leitura de consistência com a Sazonalidade** (novo, 11/07/2026): banner no topo da aba dizendo se a estrutura observada é normal para a época do ano. Regra: viés sazonal BAIXISTA (tipicamente colheita, oferta alta) → CONTANGO é o esperado; viés ALTISTA (tipicamente entressafra/aperto) → BACKWARDATION é o esperado. Se destoar, é sinal de que algo fora do padrão sazonal típico pode estar em jogo (quebra de safra, demanda atípica) — vale investigar antes de assumir contango/backwardation "normal". **Limitação assumida conscientemente:** isso não substitui uma análise formal de custo de carrego ponto-a-ponto na curva inteira — o projeto só tem 2 vencimentos de DI (DI1F27 e DI1F29), insuficiente para cobrir os ~8 pares de vencimentos do milho sem extrapolar. O custo de carrego formal (via DI) continua restrito ao card "Preço Justo Jan/27" na aba Macro.

---

## 9. Aba Sazonalidade

Camada de contexto histórico — não é um sinal de entrada, é um filtro de convicção para o sinal técnico (aba Técnico).

- **Fase Agrícola**: fase do ciclo produtivo vigente (ex.: colheita da safrinha, plantio, entressafra) e sua descrição.
- **Desvio Atual**: quanto o preço, historicamente, se desvia da média anual nesta quinzena — e o desvio-padrão (1σ) dessa amostra.
- **Próxima Quinzena**: a mesma leitura para os próximos ~15 dias, com o delta esperado (`delta_quinzenal_pct`).
- **Tendência Sazonal**: ALTISTA/BAIXISTA/NEUTRO — direção do delta entre a quinzena atual e a próxima. `virada_sazonal = true` sinaliza que estamos no ponto de inflexão do ciclo.
- **Gráfico de barras**: desvio médio histórico por mês, com o mês corrente destacado.
- **Tabela**: calendário completo (12 meses) com fase, viés, desvio médio, amplitude (mín/máx) e número de observações — quanto menor `n_obs`, menor a confiança estatística daquele mês.

**Regra prática:** quando a tendência sazonal contradiz o sinal técnico (ex.: técnico aponta venda, mas a sazonalidade indica que o ativo está perto do fundo histórico do ano e prestes a virar), trate o sinal técnico com convicção reduzida — não descarte nenhum dos dois isoladamente.

---

## 10. Aba Opções (OI)

Barreiras de opções calculadas a partir da grade `CCM_OP.xlsx`, **puramente informativa** — nenhum destes números entra no veredito da aba Guia Operador nem em nenhum cálculo de sinal.

- **Call Wall / Put Wall**: strike de CALL/PUT com maior OI acima/abaixo do preço atual, **só dentro do vencimento das opções mostrado no card**. Interprete como zona de concentração de interesse (resistência/suporte), não como sinal de compra ou venda.
- **Call Wall / Put Wall agregado** (novo, 11/07/2026): a mesma conta, mas somando o OI de **todas as expirações** presentes no arquivo (hoje 9 vencimentos diferentes) — mostra os níveis que o mercado inteiro está defendendo, não só quem opera aquele mês específico. Na prática, esse número muda bastante do específico: no primeiro teste real, o Call Wall específico saiu R$84 mas o agregado saiu R$70 — o R$84 era um lote concentrado num único vencimento, o R$70 é onde há interesse espalhado por vários meses (nível mais "psicológico").
- **Max Pain**: strike que minimiza o payout agregado a titulares de opções no vencimento. Tendência estatística fraca — mais relevante nos últimos 1-2 dias antes do vencimento das opções, praticamente irrelevante longe dele.
- **Candles do Contrato Ativo × Paredes Agregadas** (novo, 11/07/2026): candle "artesanal" (barras flutuantes do Chart.js, sem plugin externo) com o OHLC real dos últimos ~40 pregões do contrato específico em operação (ex.: CCMU26, não o CCMFUT contínuo), com o Call Wall e Put Wall **agregados** sobrepostos como linhas de referência — dá pra ver visualmente se o preço já testou essas zonas recentemente.
- **Gráfico OI por Strike**: calls para cima (verde), puts para baixo (vermelho), a barra em destaque (dourado) marca o strike do Call Wall e do Put Wall — este gráfico usa só o vencimento específico, não o agregado.

**Por que isso não é filtro de entrada:** a teoria de "parede de opções" (dealers fazendo hedge de gamma) foi validada em mercados de opções de índice americano, onde se sabe que o volume é dominado por formadores de mercado com livros de hedge previsíveis. Em opções de milho na B3, parte relevante do OI provavelmente vem de produtores/tradings fazendo hedge de safra — não necessariamente do mesmo perfil. Essa premissa não está validada para este mercado, por isso o dado fica só como contexto visual até termos histórico real para avaliar se o preço respeita essas zonas.

**Aviso automático no Guia Operador:** quando o veredito é OPERAR ou OPERAR REDUZIDO, se o Alvo R:R 2:1 ultrapassar o Call Wall (em COMPRA) ou o Put Wall (em VENDA), aparece um aviso amarelo no card de Execução — não muda o veredito, só avisa que o alvo pode encontrar resistência/suporte no caminho.

**Ressalva de disponibilidade:** se `CCM_OP*.xlsx` não for reexportado, a aba mostra aviso de indisponibilidade em vez de dado desatualizado — reexporte com a mesma frequência dos outros arquivos.

---

## 11. Aba Spread Calendário (novo, 11/07/2026)

Cobre o caso de comprar um vencimento e vender outro — antes o dashboard só recomendava operação para o contrato ativo (o de maior volume).

- **Como funciona:** identifica os 3 contratos CCM vivos com maior volume médio (10 pregões), **excluindo qualquer contrato a ≤15 dias do próprio vencimento** (ver limitação abaixo), e monta todos os pares entre eles (3 contratos → 3 pares). Para cada par, trata o spread `preço(A) − preço(B)` como sua própria série histórica, com média/desvio-padrão/Z-score reais calculados sobre uma **janela móvel dos últimos 113 pregões pareados** — não o histórico expansível inteiro, e não o sistema EMA9/20 (que só foi validado no CCMFUT contínuo, não em contratos específicos de liquidez menor).
- **Leitura:** `|Z| > 1,5σ` é tese de reversão à média — vender a perna cara, comprar a barata. Abaixo disso, "sem tese", o par fica só como contexto.
- **Gráfico:** um card por par, com o histórico semanal real do spread e faixas de referência ±1,5σ, no mesmo padrão visual da aba Convergência.
- **Por que janela móvel de 113 pregões, não expansível (corrigido em 11/07/2026):** a versão original usava todo o histórico disponível (janela expansível). Um cross-check real contra o indicador nativo de Bollinger (113 períodos) da plataforma do usuário no par CCMU26/CCMX26 mostrou Z=-1,89σ (janela expansível) contra Z=-1,27σ no fechamento do indicador da plataforma — mesma direção, magnitude bem diferente. A causa: janela expansível pondera dado de ~1 ano atrás com o mesmo peso do pregão de ontem; se o spread está em tendência estrutural, isso infla o Z-score. Janela móvel de 113 pregões corrige isso e aproxima a leitura do que o operador já vê na tela de execução.
- **Por que exclui contratos perto do vencimento:** achado real em produção — sem esse filtro, CCMN26 (a 4 dias do vencimento no teste de 11/07/2026) entrava como perna de spread. Um contrato tão perto do vencimento já está sob o mesmo mecanismo de convergência forçada futuro×físico que justifica o gate da aba Convergência (liquidação financeira do CCM); o spread dele contra outro vencimento passa a refletir essa convergência, não uma distorção de calendário genuína — e não sobra tempo útil para abrir/segurar a posição de qualquer forma. O limiar usado é o mesmo da Convergência: 15 dias.
- **Limitação:** cada par é independente — o sistema não avalia se os 3 sinais juntos fazem sentido como uma estrutura combinada (ex.: borboleta entre os 3 vencimentos). Trate cada par isoladamente.

---

## 12. Calendário Econômico (novo, 11/07/2026)

Bloqueio duro (não um filtro suave) para dias de divulgação que movem o preço do milho por surpresa — o único critério do Guia Operador que reprova sozinho, independente de direção técnica, força do sinal ou qualquer outro filtro.

- **Fontes cobertas:** WASDE e Estoques Trimestrais (USDA) e Boletim da Safra de Grãos (CONAB). Datas de 2026 obtidas via busca na web em 11/07/2026 (calendário oficial USDA/NASS/CME Group e comunicado oficial da Conab) — não vêm do conhecimento de treinamento.
  - WASDE: 12 datas/ano, sempre 12:00 ET (~13h-14h BRT, dependendo do horário de verão americano).
  - Estoques Trimestrais: jan, mar, jun, set — jan/12 e jun/30 coincidem com outras divulgações de altíssimo impacto (Crop Production Anual e Acreage/Área Plantada respectivamente), marcadas como impacto MÁXIMO.
  - CONAB: dia 15 de cada mês (ajustado para o próximo dia útil em fim de semana). Só 3 das 12 datas de 2026 foram confirmadas individualmente contra o comunicado oficial (jan, set, out); as demais seguem a regra do dia 15 — reconferir periodicamente contra o calendário oficial da Conab.
- **Por que CEPEA fica de fora:** CEPEA publica um índice de preço físico **diário**, construído de transações já realizadas — não é uma divulgação agendada e surpresa como WASDE/CONAB. Incluir um "dia de divulgação" para CEPEA simularia um evento que não existe.
- **Como o gate funciona:** se hoje é dia de evento, o veredito do Guia Operador é **NÃO OPERAR**, ponto final, mostrado tanto no banner quanto no checklist. Se o evento é amanhã, aparece um aviso amarelo (não bloqueia hoje, mas sugere reduzir posição ou zerar antes do fechamento). O card "Próximos Eventos" na aba Guia Operador sempre lista os 5 próximos, mesmo em dias normais.
- **Limitação conhecida:** não cobre USDA Crop Progress (semanal, toda segunda-feira na safra) nem Export Sales (semanal, quinta-feira) — decisão deliberada: bloquear toda segunda-feira da safra por um relatório de impacto incremental (não surpresa pontual como WASDE) pareceu desproporcional sem evidência de que ele sozinho gera volatilidade capaz de estourar um stop ATR×1,5. Se isso se mostrar errado na prática, é fácil adicionar.

**Como o calendário é atualizado — leia isto antes de confiar no gate em 2027:** as datas de WASDE/Estoques Trimestrais **não são geradas por regra** (o USDA não segue um padrão fixo tipo "toda segunda terça-feira do mês") — são uma lista fixa em `calendario_economico.py` (`EVENTOS_WASDE_2026`, `EVENTOS_GRAIN_STOCKS_2026`), digitada a partir de uma busca na web feita uma única vez em 11/07/2026. **Não há atualização automática, scraper, nem API.** Quando a lista de um ano se esgota, o pipeline registra um erro explícito no log ("dados WASDE/Estoques esgotados para o ano corrente") e o dashboard mostra um alerta vermelho no card "Próximos Eventos" da aba Guia Operador — sinalizando que o gate pode estar dando falso-negativo para o lado USDA a partir dali (`usda_desatualizado: true` no JSON). **Ação necessária:** a cada virada de ano (ou quando esse alerta aparecer), buscar o calendário WASDE/Estoques Trimestrais do ano seguinte e atualizar as duas listas manualmente no código. O lado CONAB não tem esse problema — é gerado por regra (dia 15) para qualquer ano futuro, embora a precisão mês a mês continue limitada (ver item acima).

---

## 13. Limitações conhecidas (leia antes de operar)

1. **CCMFUT (contínuo) ≠ contrato específico exibido em outra plataforma.** O "CCM Último" do topo vem do contrato contínuo (ajustado nas rolagens), não do preço bruto do contrato específico (ex.: CCMU26) que você vê no Profit. Pequenas diferenças entre os dois são esperadas e não são erro.
2. **Corrigido em 10/07/2026 — Curva ordenada cronologicamente.** Antes misturava 2026 e 2027 fora de ordem.
3. **Corrigido em 10/07/2026 — DXY aparecia sempre "—".** Estava salvo no bloco errado do JSON (`macro` em vez de `cambio`).
4. **Corrigido em 10/07/2026 — "Alvo R:R 2:1" aparecia como NaN.** Faltava o preço absoluto do alvo no JSON; só existia a distância.
5. **Corrigido em 10/07/2026 — leitura de CSV quebrava com `KeyError: 'Data'` ou `line contains NUL`.** O exportador do Profit deixa, em vários arquivos do projeto (WDOFUT, DOLINDEX, DI1F27/29, alguns contratos CCM), bytes NUL de sobra no final do arquivo, e às vezes grava sem a linha de cabeçalho. A leitura agora remove esses bytes e detecta cabeçalho ausente automaticamente, com um retry curto para locks de I/O transitórios.
6. **Corrigido em 10/07/2026 — contratos vencidos distorciam a curva.** CCMH26 (Mar/2026) e CCMK26 (Mai/2026) continuavam entrando no "Spread Ponta a Ponta" e na classificação CONTANGO/BACKWARDATION/FLAT mesmo depois de vencidos. Agora são excluídos automaticamente com base na data de referência.
7. **Corrigido em 10/07/2026 — aba de Sazonalidade não existia no dashboard.** O dado já era calculado desde a integração do `sazonalidade_milho.py`; agora tem aba própria (Seção 9).
8. **Adicionado em 10/07/2026 — aba Guia Operador.** Antes, avaliar a força do sinal exigia ir na aba Técnico e calcular `gap_relativo` manualmente. Agora a aba Guia Operador (Seção 4) faz esse cálculo e devolve um veredito único (OPERAR/OPERAR REDUZIDO/NÃO OPERAR) com a justificativa.
9. **Pendente, não é bug de código — dados desatualizados.** No momento da auditoria, `RTCNI_F_0_Diário.csv` ainda ficava ~2 dias atrás do `CCMFUT_F_0_Diário.csv` (melhorou de 4 para 2 dias após reexportação). Isso é disciplina de exportação: reexporte todos os arquivos com a mesma frequência, não só o CCMFUT.
10. **Implementado em 11/07/2026 — Max Pain / Call Wall / Put Wall.** Lê a grade de opções `CCM_OP.xlsx` exportada do Profit/Genial (aba com colunas "Instrumento financeiro" e "Contratos em Aberto" — as colunas auxiliares CONTRATO/ANO/TIPO/Strike do arquivo não são usadas porque a amostra real veio com ~53% dessas células erradas; tudo é derivado do próprio ticker, ex.: `CCMU26C006700` → Set/2026, Call, strike R$67,00). **Reexporte `CCM_OP.xlsx` com a mesma frequência dos outros arquivos** (mesmo nome, sobrescrevendo) para o dado não ficar parado. Feche o Excel antes de rodar o pipeline — arquivo aberto gera um lock (`~$CCM_OP.xlsx`) que a leitura já ignora, mas o Windows pode bloquear a leitura do arquivo principal enquanto estiver em edição.
11. **Corrigido em 11/07/2026 — média/desvio-padrão do spread de convergência eram constantes fixas sem origem documentada.** Substituídas por cálculo real a partir do histórico pareado CCMFUT×RTCNI (~2 anos, janela expansível). O desvio-padrão real (~R$5,31/sc) é maior que a constante antiga (R$3,50/sc) — o Z-score antigo superestimava distorções.
12. **Corrigido em 11/07/2026 — gráfico "histórico" da aba Convergência era ruído aleatório.** 19 dos 20 pontos vinham de `Math.random()` no navegador, só o último ponto (hoje) era real. Agora todos os pontos vêm do spread semanal real calculado em `convergencia.py`.
13. **Corrigido em 11/07/2026 — alerta "Vencimento Próximo" nunca disparava com dados reais.** `vencimento_proximo_dias` só existia nos dados de demonstração; `analisar_convergencia()` nunca retornava esse campo. Agora é calculado a partir da regra de vencimento B3 (dia 15 do mês de vencimento, ajustado para o próximo dia útil se cair em fim de semana — sem calendário de feriados B3 no projeto, então feriados no meio da semana não são tratados).
14. **Adicionado em 11/07/2026 — aba Spread Calendário (Seção 11).** Recomendações agora cobrem até 3 vencimentos líquidos simultâneos, não só o contrato ativo — necessário porque o operador pode comprar um vencimento e vender outro. Metodologia: Z-score do spread entre pares, não o sistema EMA9/20 clonado por contrato.
15. **Corrigido em 11/07/2026 — Z-score do Spread Calendário usava janela expansível, superestimando distorções.** Ver detalhe na Seção 11. Trocado para janela móvel de 113 pregões após cross-check real contra o indicador de Bollinger da plataforma do usuário.
16. **Corrigido em 11/07/2026 — alertas WASDE/CONAB na aba Decisão eram mortos.** `d.macro.wasde_proximo` e `d.macro.conab_proximo` eram sempre a string fixa `'N/A'` na saída real do pipeline (só funcionavam nos dados de demonstração, que tinham datas fictícias hardcoded) — mesmo padrão de bug já corrigido em `vencimento_proximo_dias` (item 13). Substituídos pelo novo `calendario_economico`, com datas reais de WASDE/Estoques (USDA) e Boletim (CONAB).
17. **Adicionado em 11/07/2026 — Calendário Econômico (Seção 12) como gate duro no Guia Operador.** É o único critério que reprova sozinho, sobrepondo direção técnica, força do sinal e todos os outros filtros — "não operar em dia de divulgação" é uma regra absoluta, não um filtro que só conta em conjunto com outros.
18. **Manutenção obrigatória anual — calendário WASDE/Estoques não se atualiza sozinho.** É lista fixa para 2026, digitada uma vez via busca na web. A partir do momento em que a lista se esgota (fim de 2026, ou antes se rodar em outro ano), o pipeline registra erro no log e o dashboard mostra alerta vermelho (`usda_desatualizado`) em vez de ficar em silêncio — mas alguém ainda precisa atualizar `calendario_economico.py` manualmente todo início de ano. Ver detalhe na Seção 12.

---

## 14. Checklist rápido antes de qualquer decisão

```
[ ] "Atualizado" no topo é de hoje, depois da última exportação de CSV?
[ ] Aba Guia Operador: veredito é OPERAR ou OPERAR REDUZIDO? (se NÃO OPERAR, pare aqui)
[ ] RTCNI e o contrato específico (aba Curva) têm a mesma data do CCMFUT?
[ ] Estrutura da curva confere visualmente com a tabela, não só o rótulo?
[ ] Aba Spread Calendário: algum par com |Z|>1,5σ e leitura fazendo sentido com sua tese?
[ ] Calendário Econômico: hoje ou amanhã tem WASDE/Estoques/Boletim CONAB?
```

A aba Guia Operador já cobre gap_relativo, Diagnóstico Câmbio, Convergência, Sazonalidade e Calendário Econômico automaticamente (inclusive bloqueando sozinho em dia de divulgação) — os itens de freshness/conferência visual acima são só o que ela **não** cobre.
