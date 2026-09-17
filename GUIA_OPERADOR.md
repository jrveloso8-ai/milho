# Guia Rápido do Operador — Milho Trader (CCM B3)

Para consulta na frente da plataforma antes de qualquer ordem.

**Atualizado 17/09/2026** — sistema técnico migrado de EMA9/20 + Setup 9.1
para **TRIX v5** (TRIX(7)/SMA(3) + filtro de tendência SMA(100)), validado
em `C:\Projetos Antigravity\backtest\` (Monte Carlo p=0,012, walk-forward
5/5, holdout PF 1,47). Ver `/areas/milho-trader.md` para o histórico da
decisão.

---

## Onde olhar

Abra a aba **🧭 Guia Operador** no dashboard. O veredito já vem pronto do
pipeline (`calcular_veredito_consolidado`) — a aba só traduz para o banner e
cruza com os filtros de contexto (câmbio, convergência, sazonalidade,
calendário). Quatro estados possíveis, não mais três:

- 🟢 **ENTRAR [direção]** — o TRIX v5 cruzou HOJE, abrindo uma posição nova.
  Convicção ALTA = sem atrito; "— TAMANHO REDUZIDO" = Bias Estrutural
  moderado contra, reduza o tamanho.
- 📌 **MANTER [direção]** — já existe posição aberta de um cruzamento
  anterior e não houve cruzamento novo hoje. Não é uma ordem nova — é
  "continue como está". Se aparecer alerta de Bias Estrutural forte contra,
  é sinalização para você considerar reduzir manualmente; o sistema em si
  só sai no cruzamento oposto (não tem stop técnico nem alvo fixo).
- ⏳ **AGUARDAR** — TRIX v5 sem posição aberta (FLAT) e sem cruzamento hoje.
  Não há nada para fazer.
- 🔴 **NÃO OPERAR** — divulgação de calendário econômico hoje (WASDE/CONAB),
  ou cruzamento novo com Bias Estrutural fortemente contra. Não force a
  entrada.

O card "Por que esta decisão?" logo abaixo mostra os itens que compõem o
veredito (Direção/TRIX v5, Entrada Hoje, Câmbio, Convergência, Sazonalidade,
Calendário) com semáforo verde/amarelo/vermelho.

**Importante:** os valores de Stop e Alvo mostrados no card de execução são
só referência de gestão de risco/dimensionamento — o TRIX v5 validado não
usa stop técnico nem alvo fixo. Não trate esses valores como onde o sistema
sai.

---

## Freshness (única checagem manual que continua existindo)

Antes de confiar no veredito: "Atualizado: HH:MM" no topo é de hoje, depois da última exportação de CSV?
**Não** → rode `rodar_pipeline.bat`, recarregue a página (Ctrl+F5), só então olhe o veredito.

---

## Execução

Quando o veredito for ENTRAR ou MANTER, o próprio card já traz:

- **Stop de Referência** e **Alvo de Referência (R:R 2:1)** — preços absolutos de gestão de risco, não a regra de saída do sistema (o TRIX v5 sai no cruzamento oposto, sem stop técnico).
- **Contratos sugeridos** — perfil moderado só quando é ENTRAR com convicção ALTA e zero atritos; caso contrário, conservador.
- **Vencimento a operar** — o contrato específico (não o CCMFUT contínuo, que é só referência de cálculo).

---

## Regra de ouro

> Se o veredito é vermelho (NÃO OPERAR), não opera. Ponto. Não há custo de oportunidade em esperar o próximo pregão; há custo real em forçar uma entrada que o próprio dashboard já sinalizou como bloqueada ou fortemente contraditória.
>
> Se o veredito é MANTER, não é um convite a mexer na posição — é a confirmação de que o sistema segue na mesma direção desde a última entrada. Reduzir por conta própria fora da regra de saída (cruzamento oposto) é decisão sua, não do sistema validado.
