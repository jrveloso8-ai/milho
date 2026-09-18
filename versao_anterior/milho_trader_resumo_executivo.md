# Milho Trader (GPM v2.0) — Resumo Executivo
Data: 20/07/2026

## Objetivo do projeto

Sistema de inteligência de decisão para negociar milho futuro (CCM) na B3. A função central é reduzir decisão discricionária/emocional numa operação: em vez de o operador julgar "na cabeça" se compra, vende ou fica de fora, o sistema cruza sinal técnico validado por backtest, física de mercado (convergência futuro×físico), sazonalidade proprietária, estrutura da curva de vencimentos e calendário de eventos de risco, e devolve um veredito objetivo a cada rodada — com stop, alvo e tamanho de posição já calculados.

Existe um segundo objetivo, hoje ainda não iniciado: transformar a mesma inteligência em relatório educacional para cooperativas, mesas de hedge e produtores rurais (a Fase 4 do roadmap, "automação e distribuição"). Até aqui, 100% do esforço foi construção do motor interno para uso pessoal — a parte de produto/distribuição não começou.

## Para quem é destinado

Hoje, na prática: só para você, para apoiar suas próprias operações no CCM. O tom duplo (resumo executivo para produtor + seção técnica para operador), mencionado na base de conhecimento do projeto, é um objetivo de produto futuro, não o uso atual.

## Dados de entrada

- **CCMFUT / contratos específicos (CCMU26, CCMX26, CCMF27...)** — OHLCV diário, exportado do Profit/Genial. CCMFUT é a série contínua; hoje ela coincide exatamente com o contrato mais líquido (CCMU26), confirmado comparando os arquivos.
- **RTCNI** — preço físico de referência (o mesmo usado pela B3 como lastro do contrato futuro), atualizado diariamente por você.
- **Grade de opções (CCM_OP.xlsx)** — Open Interest de calls/puts por strike, para Call Wall / Put Wall / Max Pain.
- **WDOFUT** — câmbio futuro, usado para calcular câmbio implícito no CCM e paridade internacional.
- **DI1F27 / DI1F29** — taxas de juro futuro, usadas para custo de carrego (preço justo teórico vs mercado).
- **DOLINDEX (DXY)** — índice do dólar, contexto macro.
- **ZC=F e BZ=F (yfinance)** — milho Chicago e Brent, gratuitos, sem chave.
- **Fundamentos CONAB/WASDE** — manual, atualizado por você (`FUNDAMENTOS_DEFAULT`).
- **Calendário de divulgações (WASDE, Boletim CONAB)** — datas cadastradas manualmente em `calendario_economico.py`.
- **Histórico de 497 observações do CCMFUT (jul/2024–jun/2026)** — base da sazonalidade proprietária.

Nenhum dado é inventado quando ausente — os módulos retornam vazio/None e o pipeline continua, sem travar.

## Como são calculados

O `pipeline.py` orquestra 13 módulos, cada um cobrindo um ângulo diferente, sem sobreposição de método:

Técnico (EMA9/20, Setup 9.1, ATR14) — validado por backtest real (WR e payoff documentados). Curva de vencimentos — classifica contango/backwardation a partir dos contratos vivos. OI de opções — Call Wall/Put Wall/Max Pain, por vencimento e agregado. Convergência futuro×físico — z-score real do spread CCM×RTCNI contra ~2 anos de histórico pareado. Câmbio/DI/ZC/Brent — câmbio implícito, custo de carrego, paridade internacional. Sazonalidade — desvio percentual relativo à média anual, 497 obs, com fase agrícola e viés esperado. Curva×Sazonalidade — cruza a estrutura observada da curva com o que a fase agrícola esperaria, sinalizando quando destoa. Spread calendário — z-score real entre pares dos 3 contratos mais líquidos. Calendário econômico — bloqueio duro em dia de WASDE/CONAB. Bias Estrutural (novo, hoje) — agrega Sazonalidade + Físico + Macro + Técnico num único score ponderado (30/30/20/20), com o mesmo veto de calendário.

Tudo alimenta um validador de qualidade (`gerar_resumo_analise.py`) que audita completude e consistência antes de qualquer relatório ser considerado confiável.

## Resultado(s)

`dados_milho.json` (payload estruturado, fonte de verdade), `milho_dashboard.html` (10 abas, atualizado hoje com a aba Bias Estrutural), e `milho_resumo_AAAAMMDD_HHMM.json` (auditoria de qualidade). O output prático de cada rodada é: um veredito tático (Decisão/Guia Operador — operar/aguardar, direção, stop, alvo, tamanho) e, a partir de hoje, um viés estrutural de médio prazo (Bias Estrutural), mais os alertas de contexto (convergência, calendário econômico, divergência técnico×fundamento).

## O que fazer com eles

Rotina semanal (SOP às segundas antes da abertura da B3) e emergencial em eventos extraordinários (WASDE, CONAB, choques cambiais). A aba Decisão/Guia Operador decide timing de entrada tática. O Bias Estrutural serve como filtro de contexto e calibração de tamanho de posição de médio prazo — nunca como gatilho de entrada isolado. O relatório de QA deve ser conferido antes de confiar cegamente no dashboard: completude abaixo de 100% ou status diferente de OK merece investigação antes de operar com base nele.

---

## E estamos criando um monstro sem utilidade?

Não — mas está no limite, e vale dizer isso com todas as letras em vez de só validar o que já foi construído.

**Por que não é um monstro:** cada um dos 13 módulos cobre um ângulo genuinamente diferente — não há dois módulos calculando a mesma coisa de jeitos diferentes por acidente. Cada decisão de design tem data e motivo documentado (11/07/2026 aparece repetidamente como o dia em que várias regras foram fechadas com você, não como especulação minha). O sistema reconhece as próprias limitações — a sazonalidade avisa que a base é curta (2 anos), o Bias Score declara sua própria confiança (X/4 dimensões validadas), e nada é apresentado como mais robusto do que realmente é.

**Onde o risco real está:** o Bias Estrutural que acabamos de subir tem sobreposição conceitual com o Guia Operador. Os dois fazem a mesma coisa em espírito — agregam múltiplos fatores (técnico, câmbio, convergência, sazonalidade, calendário) num veredito único — só que em escalas de tempo diferentes (tático vs estrutural) e com pesos diferentes. Isso não é redundância inútil por definição, mas é a peça do sistema que mais precisa provar seu valor antes de você confiar nela como se fosse óbvia. Se, rodando por algumas semanas, o Bias Estrutural nunca discordar do Guia Operador de um jeito que mude sua decisão prática, ele vira peso morto — informação bonita que ninguém usa.

A segunda coisa a apontar: a complexidade de manutenção já é real, não hipotética. Hoje mesmo apareceram três problemas de manutenção — Python errado no PATH, um campo com nome trocado entre dois módulos seus, e um vocabulário que eu tive que confirmar lendo o código-fonte em vez de assumir. Nenhum era grave, mas é o tipo de atrito que cresce junto com o número de módulos, não proporcionalmente ao valor que cada módulo novo entrega.

**Minha recomendação, direta:** pare de adicionar peças novas por enquanto. O próximo passo não deveria ser mais um módulo — deveria ser rodar o sistema como está por algumas semanas reais de mercado e observar duas coisas: se o Bias Estrutural chegou a mudar uma decisão prática que o Guia Operador sozinho não teria mudado, e se você consegue manter essa rotina semanal sem o sistema virar um segundo trabalho. Só depois disso faz sentido decidir entre avançar para a Fase 4 (distribuição institucional) ou aceitar que, para uso pessoal em 1–8 contratos, o sistema já entregou o que precisava entregar.
