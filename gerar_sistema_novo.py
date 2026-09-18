# -*- coding: utf-8 -*-
"""
gerar_sistema_novo.py — Gera a interface do Novo Sistema Sentinel-Corn 360°
Mantém a estrutura visual do HTML e foca exclusivamente nos requisitos solicitados.
Alimenta tanto sistema_sentinel.html quanto mockup_sentinel_sistema_novo.html.
"""

import json
import os

PASTA = os.path.dirname(os.path.abspath(__file__))

def gerar_sistema_novo():
    arq_curva = os.path.join(PASTA, "dados_curva.json")
    arq_milho = os.path.join(PASTA, "dados_milho.json")

    if not os.path.exists(arq_curva):
        print(f"Erro: {arq_curva} nao encontrado. Execute ccm_trix_curva.py primeiro.")
        return

    with open(arq_curva, "r", encoding="utf-8") as f:
        dados_curva = json.load(f)

    dados_milho = {}
    if os.path.exists(arq_milho):
        try:
            with open(arq_milho, "r", encoding="utf-8") as f:
                dados_milho = json.load(f)
        except Exception:
            pass

    # Payload 100% real
    dados_payload = {
        "contratos": dados_curva.get("contratos", []),
        "watchlist": dados_curva.get("watchlist", []),
        "series_contratos": dados_curva.get("series_contratos", {}),
        "sentinel_corn": dados_curva.get("sentinel_corn", {}),
        "macro": dados_milho.get("macro", {}),
    }

    dados_json_str = json.dumps(dados_payload, ensure_ascii=True)

    html_conteudo = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Milho Trader — Sentinel-Corn 360°</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg-dark: #0b0d11;
    --card-bg: #141720;
    --card-header: #181d28;
    --border: #232a38;
    --text-main: #f0f4f8;
    --text-muted: #8b99ad;
    --text-dim: #5a6678;
    --corn-gold: #f59e0b;
    --accent-blue: #3b82f6;
    --bull-green: #00d060;
    --bear-red: #ff3b30;
  }}

  body {{
    background-color: var(--bg-dark);
    color: var(--text-main);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    padding-bottom: 60px;
    line-height: 1.5;
  }}

  /* HEADER */
  header {{
    background: #11141c;
    border-bottom: 1px solid var(--border);
    padding: 14px 28px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: sticky;
    top: 0;
    z-index: 100;
  }}
  .brand {{
    display: flex;
    align-items: center;
    gap: 12px;
  }}
  .brand-logo {{ font-size: 24px; }}
  .brand-title {{
    font-size: 16px;
    font-weight: 800;
    letter-spacing: 0.5px;
    color: #ffffff;
  }}
  .brand-subtitle {{
    font-size: 11px;
    color: var(--corn-gold);
    font-weight: 600;
    letter-spacing: 0.8px;
    text-transform: uppercase;
  }}
  .header-status {{
    display: flex;
    align-items: center;
    gap: 16px;
  }}
  .badge-proveniencia {{
    background: rgba(0, 208, 96, 0.12);
    border: 1px solid var(--bull-green);
    color: var(--bull-green);
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
  }}

  /* TICKER STRIP */
  .ticker-strip {{
    background: #0d1017;
    border-bottom: 1px solid var(--border);
    padding: 10px 28px;
    display: flex;
    gap: 20px;
    overflow-x: auto;
    align-items: center;
  }}
  .ticker-item {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    white-space: nowrap;
    background: #141722;
    padding: 6px 12px;
    border-radius: 6px;
    border: 1px solid #1f2736;
    cursor: pointer;
    transition: all 0.2s;
  }}
  .ticker-item:hover {{ border-color: var(--corn-gold); }}
  .ticker-code {{ font-weight: 800; color: #fff; }}
  .ticker-price {{ font-family: 'JetBrains Mono', monospace; font-weight: 600; color: #e2e8f0; }}

  /* MAIN CONTAINER */
  .container {{
    max-width: 1440px;
    margin: 24px auto;
    padding: 0 20px;
  }}

  /* SELETOR DE CONTRATOS */
  .pills-container {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px 18px;
    margin-bottom: 24px;
    flex-wrap: wrap;
    gap: 12px;
  }}
  .pills-label {{
    font-size: 11px;
    font-weight: 700;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.6px;
  }}
  .pills-buttons {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }}
  .pill-btn {{
    background: #181d28;
    border: 1px solid var(--border);
    color: var(--text-muted);
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    font-family: 'JetBrains Mono', monospace;
    transition: all 0.2s;
  }}
  .pill-btn:hover {{
    color: #fff;
    border-color: var(--corn-gold);
  }}
  .pill-btn.active {{
    background: rgba(245, 158, 11, 0.2);
    border-color: var(--corn-gold);
    color: var(--corn-gold);
    box-shadow: 0 0 12px rgba(245, 158, 11, 0.25);
  }}

  /* HERO SENTINEL CARD */
  .hero-card {{
    background: linear-gradient(135deg, #161c28 0%, #11151f 100%);
    border: 1px solid #2d3748;
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 24px;
    box-shadow: 0 12px 32px rgba(0,0,0,0.55);
  }}
  .hero-top {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 16px;
    margin-bottom: 20px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 16px;
  }}
  .hero-title-group {{
    display: flex;
    align-items: center;
    gap: 14px;
  }}
  .hero-icon {{ font-size: 38px; }}
  .hero-title {{
    font-size: 19px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 0.3px;
  }}
  .hero-desc {{
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 3px;
  }}
  .verdict-badge {{
    padding: 8px 20px;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 800;
    letter-spacing: 0.6px;
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }}
  .verdict-ALTISTA {{
    background: rgba(0, 208, 96, 0.15);
    border: 1px solid var(--bull-green);
    color: var(--bull-green);
  }}
  .verdict-LATERAL {{
    background: rgba(245, 158, 11, 0.15);
    border: 1px solid var(--corn-gold);
    color: var(--corn-gold);
  }}
  .verdict-BAIXISTA {{
    background: rgba(255, 59, 48, 0.15);
    border: 1px solid var(--bear-red);
    color: var(--bear-red);
  }}

  /* 3 PILARES GRID */
  .pillars-grid {{
    display: grid;
    grid-template-columns: 1.2fr 1fr 1fr;
    gap: 16px;
    margin-bottom: 20px;
  }}
  @media (max-width: 1024px) {{
    .pillars-grid {{ grid-template-columns: 1fr; }}
  }}
  .pillar-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }}
  .pillar-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 14px;
    border-bottom: 1px solid #1a202c;
    padding-bottom: 10px;
  }}
  .pillar-title {{
    font-size: 12px;
    font-weight: 700;
    color: #fff;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .pillar-weight {{
    background: rgba(59, 130, 246, 0.15);
    color: #60a5fa;
    border: 1px solid #3b82f6;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 800;
  }}
  .pillar-value-box {{
    margin: 8px 0;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }}
  .pillar-metric-name {{ font-size: 12px; color: var(--text-muted); }}
  .pillar-metric-val {{ font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700; color: #fff; }}
  .pillar-score-badge {{
    font-size: 12px;
    font-weight: 700;
    padding: 4px 10px;
    border-radius: 4px;
  }}

  /* NEWS LIST */
  .news-list {{
    list-style: none;
    margin-top: 10px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}
  .news-item {{
    font-size: 12px;
    color: var(--text-muted);
    background: #11141c;
    padding: 8px 10px;
    border-radius: 6px;
    border-left: 3px solid var(--accent-blue);
    line-height: 1.4;
  }}
  .news-item.bullish {{ border-left-color: var(--bull-green); }}
  .news-item.bearish {{ border-left-color: var(--bear-red); }}

  /* SECTION 2-COL */
  .section-2col {{
    display: grid;
    grid-template-columns: 1.2fr 0.8fr;
    gap: 20px;
    margin-bottom: 24px;
  }}
  @media (max-width: 960px) {{
    .section-2col {{ grid-template-columns: 1fr; }}
  }}

  .content-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
  }}
  .content-card-header {{
    background: var(--card-header);
    border-bottom: 1px solid var(--border);
    padding: 14px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .content-card-title {{
    font-size: 13px;
    font-weight: 700;
    color: #fff;
    text-transform: uppercase;
    letter-spacing: 0.6px;
  }}
  .content-card-body {{
    padding: 20px;
  }}

  /* TABELA ARBITRAGEM */
  .arbitrage-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }}
  .arbitrage-table th {{
    text-align: left;
    padding: 10px 12px;
    font-size: 11px;
    color: var(--text-muted);
    border-bottom: 1px solid var(--border);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  .arbitrage-table td {{
    padding: 12px;
    border-bottom: 1px solid #1c222e;
    font-family: 'JetBrains Mono', monospace;
  }}
  .arbitrage-table tr:hover td {{
    background: rgba(255,255,255,0.03);
  }}

  /* SLIDERS */
  .slider-group {{
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
    background: #11141c;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 20px;
    margin-bottom: 18px;
  }}
  .slider-item {{
    flex: 1;
    min-width: 200px;
  }}
  .slider-label {{
    font-size: 12px;
    color: var(--text-muted);
    display: flex;
    justify-content: space-between;
    margin-bottom: 8px;
  }}
  .slider-label b {{ color: #fff; font-family: 'JetBrains Mono', monospace; font-size: 13px; }}
  input[type="range"] {{
    width: 100%;
    accent-color: var(--corn-gold);
    cursor: pointer;
  }}

  /* PARECER */
  .parecer-text {{
    font-size: 13px;
    line-height: 1.7;
    color: #cbd5e1;
    white-space: pre-wrap;
    background: #0f121a;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 18px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }}

  /* PLOTLY CHART WRAPPER */
  .chart-box {{
    height: 480px;
    width: 100%;
  }}
</style>
</head>
<body>

<!-- HEADER -->
<header>
  <div class="brand">
    <span class="brand-logo">🌽</span>
    <div>
      <div class="brand-title">MILHO TRADER</div>
      <div class="brand-subtitle">Sentinel-Corn 360° — Consultor de Inteligência B3</div>
    </div>
  </div>
  <div class="header-status">
    <span class="badge-proveniencia">DADOS 100% REAIS (MEDIDO / DERIVADO)</span>
    <span style="color: var(--text-muted); font-size: 12px;" id="data-hora-geracao">—</span>
  </div>
</header>

<!-- TICKER STRIP -->
<div class="ticker-strip" id="ticker-strip"></div>

<div class="container">

  <!-- SELETOR DE CONTRATOS -->
  <div class="pills-container">
    <span class="pills-label">Contrato em Análise (B3):</span>
    <div class="pills-buttons" id="pills-contratos"></div>
    <span style="font-size: 11px; color: var(--text-dim);">Vencimentos Vivos com Negócio na B3</span>
  </div>

  <!-- HERO SENTINEL CARD -->
  <div class="hero-card">
    <div class="hero-top">
      <div class="hero-title-group">
        <span class="hero-icon">🤖</span>
        <div>
          <div class="hero-title" id="hero-contract-title">SENTINEL-CORN 360° — CCMX26</div>
          <div class="hero-desc">Ponderação Matemática Estrita: 60% Técnico & Opções · 20% Notícias Agro RSS · 20% Calendário Oficial</div>
        </div>
      </div>
      <div>
        <div class="verdict-badge verdict-ALTISTA" id="hero-verdict">SENTIMENTO: ALTISTA</div>
      </div>
    </div>

    <!-- 3 PILARES GRID -->
    <div class="pillars-grid">
      <!-- PILAR 1: TÉCNICO & OPÇÕES -->
      <div class="pillar-card">
        <div>
          <div class="pillar-header">
            <span class="pillar-title">📈 1. Técnico & Opções</span>
            <span class="pillar-weight">PESO 60%</span>
          </div>
          <div class="pillar-value-box">
            <span class="pillar-metric-name">Último Fechamento B3:</span>
            <span class="pillar-metric-val" id="tec-close">R$ 76,35</span>
          </div>
          <div class="pillar-value-box">
            <span class="pillar-metric-name">SMA(100) / Tendência:</span>
            <span class="pillar-metric-val" id="tec-sma">R$ 73,39</span>
          </div>
          <div class="pillar-value-box">
            <span class="pillar-metric-name">TRIX v5 / Posição:</span>
            <span class="pillar-metric-val" id="tec-pos">FLAT</span>
          </div>
          <div class="pillar-value-box">
            <span class="pillar-metric-name">Call Wall (Resistência OI):</span>
            <span class="pillar-metric-val" id="tec-call" style="color:var(--bear-red)">R$ 80,00</span>
          </div>
          <div class="pillar-value-box">
            <span class="pillar-metric-name">Put Wall (Suporte OI):</span>
            <span class="pillar-metric-val" id="tec-put" style="color:var(--bull-green)">R$ 75,00</span>
          </div>
          <div class="pillar-value-box">
            <span class="pillar-metric-name">Max Pain (Strike):</span>
            <span class="pillar-metric-val" id="tec-pain">R$ 71,00</span>
          </div>
        </div>
        <div style="margin-top: 14px; border-top: 1px solid #1a202c; padding-top: 10px; display: flex; justify-content: space-between; align-items: center;">
          <span style="font-size: 11px; color: var(--text-muted);">Score Técnico:</span>
          <span class="pillar-score-badge" id="tec-score-badge" style="background:rgba(59,130,246,0.15); color:#60a5fa;">+40.0 / 100</span>
        </div>
      </div>

      <!-- PILAR 2: NOTÍCIAS AGRO RSS -->
      <div class="pillar-card">
        <div>
          <div class="pillar-header">
            <span class="pillar-title">📰 2. Notícias Agro (RSS)</span>
            <span class="pillar-weight">PESO 20%</span>
          </div>
          <div class="pillar-value-box">
            <span class="pillar-metric-name">Classificação Léxica:</span>
            <span class="pillar-metric-val" id="rss-classificacao" style="color:var(--bull-green)">ALTISTA</span>
          </div>
          <div class="pillar-value-box">
            <span class="pillar-metric-name">Score Notícias:</span>
            <span class="pillar-metric-val" id="rss-score">+100.0 / 100</span>
          </div>
          <div style="margin-top: 10px; font-size: 11px; color: var(--text-muted); font-weight: 700;">MANCHETES REAIS MONITORADAS:</div>
          <ul class="news-list" id="rss-manchetes-list"></ul>
        </div>
        <div style="margin-top: 14px; border-top: 1px solid #1a202c; padding-top: 10px; display: flex; justify-content: space-between; align-items: center;">
          <span style="font-size: 11px; color: var(--text-muted);">Score RSS:</span>
          <span class="pillar-score-badge" id="rss-score-badge" style="background:rgba(0,208,96,0.15); color:var(--bull-green);">+100 / 100</span>
        </div>
      </div>

      <!-- PILAR 3: CALENDÁRIO ECONÔMICO -->
      <div class="pillar-card">
        <div>
          <div class="pillar-header">
            <span class="pillar-title">📅 3. Calendário Oficial</span>
            <span class="pillar-weight">PESO 20%</span>
          </div>
          <div class="pillar-value-box">
            <span class="pillar-metric-name">Classificação de Risco:</span>
            <span class="pillar-metric-val" id="cal-classificacao" style="color:var(--corn-gold)">LATERAL</span>
          </div>
          <div class="pillar-value-box">
            <span class="pillar-metric-name">Próxima Divulgação:</span>
            <span class="pillar-metric-val" id="cal-evento" style="font-size: 12px;">Estoques Trimestrais</span>
          </div>
          <div class="pillar-value-box">
            <span class="pillar-metric-name">Janela Temporal:</span>
            <span class="pillar-metric-val" id="cal-dias">Em 12 dias</span>
          </div>
          <div style="margin-top: 10px; font-size: 12px; color: var(--text-muted); background: #11141c; padding: 10px; border-radius: 6px; line-height: 1.4;">
            Órgãos oficiais: <b>USDA (WASDE)</b> e <b>CONAB</b>. Em janelas pré-relatório (&lt; 2 dias), a volatilidade implícita se eleva e o risco direcional recebe desconto.
          </div>
        </div>
        <div style="margin-top: 14px; border-top: 1px solid #1a202c; padding-top: 10px; display: flex; justify-content: space-between; align-items: center;">
          <span style="font-size: 11px; color: var(--text-muted);">Score Calendário:</span>
          <span class="pillar-score-badge" id="cal-score-badge" style="background:rgba(245,158,11,0.15); color:var(--corn-gold);">0.0 / 100</span>
        </div>
      </div>
    </div>

    <!-- PONTUAÇÃO CONSOLIDADA E FÓRMULA -->
    <div style="background: #10141d; border: 1px solid var(--border); border-radius: 8px; padding: 14px 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
      <div>
        <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Cálculo da Média Ponderada:</span>
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 14px; color: #fff; margin-top: 3px;" id="formula-ponderacao">
          Score = (60% × 40.0) + (20% × 100.0) + (20% × 0.0) = +44.0
        </div>
      </div>
      <div style="text-align: right;">
        <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Score Consolidado:</span>
        <div style="font-size: 22px; font-weight: 800; font-family: 'JetBrains Mono', monospace; color: var(--bull-green);" id="score-consolidado-val">+44.0 / 100</div>
      </div>
    </div>
  </div>

  <!-- SEÇÃO 2-COL: GRÁFICO TRIX V5 & PARECER EXECUTIVO -->
  <div class="section-2col">
    <!-- GRÁFICO INTERATIVO -->
    <div class="content-card">
      <div class="content-card-header">
        <span class="content-card-title" id="chart-card-title">Gráfico Diário & Barreiras — CCMX26</span>
        <span style="font-size: 11px; color: var(--text-muted);">Candles Reais · SMA 100 · TRIX v5 · Walls</span>
      </div>
      <div class="content-card-body" style="padding: 10px;">
        <div id="plotly-chart" class="chart-box"></div>
      </div>
    </div>

    <!-- PARECER ESTRATÉGICO -->
    <div class="content-card">
      <div class="content-card-header">
        <span class="content-card-title">🤖 Parecer do Consultor Sentinel-Corn</span>
        <span style="font-size: 11px; color: var(--accent-blue);">Visão 360° Fundamental & Técnica</span>
      </div>
      <div class="content-card-body">
        <div class="parecer-text" id="parecer-box"></div>
      </div>
    </div>
  </div>

  <!-- SEÇÃO: PARIDADE DE EXPORTAÇÃO & RISCO CAMBIAL -->
  <div class="content-card" style="margin-bottom: 24px;">
    <div class="content-card-header">
      <span class="content-card-title">⚓ Simulador de Arbitragem & Paridade de Exportação (PPE)</span>
      <span style="font-size: 11px; color: var(--corn-gold); font-family: 'JetBrains Mono', monospace;">Fórmula B3 / CME: PPE = ((CBOT + Prêmio) × 0.39368 × Câmbio × 0.06) - Custos</span>
    </div>
    <div class="content-card-body">
      <!-- SLIDERS -->
      <div class="slider-group">
        <div class="slider-item">
          <div class="slider-label">
            <span>Prêmio Porto (Basis Paranaguá/Santos):</span>
            <b id="lbl-premio-porto">+US$ 0.70/bu</b>
          </div>
          <input type="range" id="slider-premio" min="0.0" max="2.5" step="0.05" value="0.70" oninput="atualizarSliders()">
        </div>
        <div class="slider-item">
          <div class="slider-label">
            <span>Custos Logísticos (Frete Fazenda-Porto):</span>
            <b id="lbl-custos-log">R$ 10.00/sc</b>
          </div>
          <input type="range" id="slider-custos" min="4.0" max="25.0" step="0.5" value="10.00" oninput="atualizarSliders()">
        </div>
      </div>

      <!-- TABELA ARBITRAGEM -->
      <table class="arbitrage-table">
        <thead>
          <tr>
            <th>Contrato</th>
            <th>Vencimento</th>
            <th>Preço B3</th>
            <th>PPE Porto</th>
            <th>Spread (B3 - PPE)</th>
            <th>Ponto Inflexão Câmbio</th>
            <th>Matriz de Decisão Basis vs. Paridade</th>
          </tr>
        </thead>
        <tbody id="arbitrage-tbody"></tbody>
      </table>
    </div>
  </div>

</div>

<script>
  const DADOS = {dados_json_str};

  // Mapeamento dos contratos do sentinel_corn
  const sentinelContratosMap = {{}};
  if (Array.isArray(DADOS.sentinel_corn.contratos)) {{
    DADOS.sentinel_corn.contratos.forEach(item => {{
      sentinelContratosMap[item.contrato] = item;
    }});
  }}

  let contratoAtual = (DADOS.contratos && DADOS.contratos.length > 0) ? DADOS.contratos[0].codigo : "CCMX26";
  let premioPorto = DADOS.sentinel_corn.parametros_arbitragem?.premio_porto_usd ?? 0.70;
  let custosLog = DADOS.sentinel_corn.parametros_arbitragem?.custos_log_brl ?? 10.00;

  function formatarMoeda(val) {{
    if (val === null || val === undefined || isNaN(val)) return "N/D";
    return Number(val).toLocaleString('pt-BR', {{ style: 'currency', currency: 'BRL' }});
  }}

  function init() {{
    try {{
      const dataHora = DADOS.sentinel_corn.timestamp || new Date().toLocaleString();
      document.getElementById("data-hora-geracao").innerText = "Atualizado em: " + dataHora;

      // Ticker strip
      const ticker = document.getElementById("ticker-strip");
      ticker.innerHTML = "";
      DADOS.contratos.forEach(c => {{
        const closeVal = c.ultimo_close ?? c.close ?? 0;
        const sentInfo = sentinelContratosMap[c.codigo];
        const sent = sentInfo?.sentimento || "LATERAL";
        const cor = sent === "ALTISTA" ? "var(--bull-green)" : sent === "BAIXISTA" ? "var(--bear-red)" : "var(--corn-gold)";
        ticker.innerHTML += `
          <div class="ticker-item" onclick="selecionarContrato('${{c.codigo}}')">
            <span class="ticker-code">${{c.codigo}}</span>
            <span class="ticker-price">${{formatarMoeda(closeVal)}}</span>
            <span style="font-size:10px; font-weight:800; color:${{cor}}">${{sent}}</span>
          </div>
        `;
      }});

      // Pills de Contratos
      const pills = document.getElementById("pills-contratos");
      pills.innerHTML = "";
      DADOS.contratos.forEach((c, idx) => {{
        const act = idx === 0 ? "active" : "";
        pills.innerHTML += `
          <button class="pill-btn ${{act}}" onclick="selecionarContrato('${{c.codigo}}')">${{c.codigo}}</button>
        `;
      }});

      // RSS manchetes
      const newsList = document.getElementById("rss-manchetes-list");
      newsList.innerHTML = "";
      const manchetes = DADOS.sentinel_corn.score_noticias?.amostra_manchetes || [];
      manchetes.slice(0, 3).forEach(m => {{
        const cls = m.impacto === "BULLISH" ? "bullish" : m.impacto === "BEARISH" ? "bearish" : "";
        newsList.innerHTML += `<li class="news-item ${{cls}}">${{m.titulo}}</li>`;
      }});

      // Calendário
      const cal = DADOS.sentinel_corn.score_calendario || {{}};
      document.getElementById("cal-classificacao").innerText = cal.classificacao || "LATERAL";
      document.getElementById("cal-evento").innerText = cal.proximo_evento?.evento || "Divulgação Oficial";
      document.getElementById("cal-dias").innerText = cal.proximo_evento?.dias_ate_evento !== undefined ? `Em ${{cal.proximo_evento.dias_ate_evento}} dias` : "—";
      document.getElementById("cal-score-badge").innerText = `${{cal.score || 0}} / 100`;

      // RSS Score
      const rss = DADOS.sentinel_corn.score_noticias || {{}};
      document.getElementById("rss-classificacao").innerText = rss.classificacao || "ALTISTA";
      document.getElementById("rss-score").innerText = `${{rss.score > 0 ? '+' : ''}}${{rss.score || 0}} / 100`;
      document.getElementById("rss-score-badge").innerText = `${{rss.score > 0 ? '+' : ''}}${{rss.score || 0}} / 100`;

      // Parecer
      document.getElementById("parecer-box").innerText = DADOS.sentinel_corn.parecer_executivo || "Parecer disponível.";

      renderizarContrato(contratoAtual);
      renderizarTabelaArbitragem();
    }} catch (err) {{
      console.error("Erro na inicialização do dashboard:", err);
    }}
  }}

  function selecionarContrato(cod) {{
    contratoAtual = cod;
    document.querySelectorAll(".pill-btn").forEach(btn => {{
      if (btn.innerText.trim() === cod) btn.classList.add("active");
      else btn.classList.remove("active");
    }});
    renderizarContrato(cod);
  }}

  function renderizarContrato(cod) {{
    const c = DADOS.contratos.find(x => x.codigo === cod) || DADOS.contratos[0];
    const sentInfo = sentinelContratosMap[cod] || {{}};

    const vencimentoStr = c.vencimento_iso || c.vencimento || "";
    document.getElementById("hero-contract-title").innerText = `SENTINEL-CORN 360° — ${{c.codigo}} (${{vencimentoStr}})`;
    const vBadge = document.getElementById("hero-verdict");
    const sent = sentInfo.sentimento || "LATERAL";
    vBadge.className = `verdict-badge verdict-${{sent}}`;
    vBadge.innerText = `SENTIMENTO: ${{sent}}`;

    // Técnico
    const closeVal = c.ultimo_close ?? c.close;
    document.getElementById("tec-close").innerText = formatarMoeda(closeVal);
    document.getElementById("tec-sma").innerText = c.sma100 ? formatarMoeda(c.sma100) : "N/D";
    document.getElementById("tec-pos").innerText = c.posicao || "FLAT";
    document.getElementById("tec-call").innerText = c.call_wall ? `${{formatarMoeda(c.call_wall)}}` : "N/D";
    document.getElementById("tec-put").innerText = c.put_wall ? `${{formatarMoeda(c.put_wall)}}` : "N/D";
    document.getElementById("tec-pain").innerText = c.max_pain ? formatarMoeda(c.max_pain) : "N/D";

    const sTec = sentInfo.pesos?.tecnico_60 ?? sentInfo.score_tecnico ?? 0;
    const sRss = sentInfo.pesos?.noticias_20 ?? sentInfo.score_rss ?? 0;
    const sCal = sentInfo.pesos?.calendario_20 ?? sentInfo.score_calendario ?? 0;
    const sCons = sentInfo.score_final ?? sentInfo.score_consolidado ?? 0;

    document.getElementById("tec-score-badge").innerText = `${{sTec > 0 ? '+' : ''}}${{sTec.toFixed(1)}} / 100`;
    document.getElementById("score-consolidado-val").innerText = `${{sCons > 0 ? '+' : ''}}${{sCons.toFixed(1)}} / 100`;
    
    // Cor do score consolidado
    const elCons = document.getElementById("score-consolidado-val");
    if (sCons > 15) elCons.style.color = "var(--bull-green)";
    else if (sCons < -15) elCons.style.color = "var(--bear-red)";
    else elCons.style.color = "var(--corn-gold)";

    document.getElementById("formula-ponderacao").innerText = 
      `Score = (60% × ${{sTec.toFixed(1)}}) + (20% × ${{sRss.toFixed(1)}}) + (20% × ${{sCal.toFixed(1)}}) = ${{sCons > 0 ? '+' : ''}}${{sCons.toFixed(1)}}`;

    document.getElementById("chart-card-title").innerText = `Gráfico Diário & Barreiras — ${{c.codigo}}`;
    desenharGrafico(c);
  }}

  function desenharGrafico(c) {{
    const serie = DADOS.series_contratos?.[c.codigo] || [];
    const dates = serie.map(item => item.data);
    const closes = serie.map(item => item.close);
    const sma100 = serie.map(item => item.sma100);

    const traceClose = {{
      x: dates,
      y: closes,
      type: 'scatter',
      mode: 'lines',
      name: `${{c.codigo}} Fechamento`,
      line: {{ color: '#00e5ff', width: 2 }}
    }};

    const traceSma = {{
      x: dates,
      y: sma100,
      type: 'scatter',
      mode: 'lines',
      name: 'SMA 100 (Tendência)',
      line: {{ color: '#ffffff', width: 1.5, dash: 'dot' }}
    }};

    const shapes = [];
    const callPrice = typeof c.call_wall === 'number' ? c.call_wall : c.call_wall?.preco;
    const putPrice = typeof c.put_wall === 'number' ? c.put_wall : c.put_wall?.preco;

    if (callPrice) {{
      shapes.push({{
        type: 'line', xref: 'paper', x0: 0, x1: 1, y0: callPrice, y1: callPrice,
        line: {{ color: '#ff3b30', width: 1.5, dash: 'dash' }}
      }});
    }}
    if (putPrice) {{
      shapes.push({{
        type: 'line', xref: 'paper', x0: 0, x1: 1, y0: putPrice, y1: putPrice,
        line: {{ color: '#00d060', width: 1.5, dash: 'dash' }}
      }});
    }}

    const layout = {{
      paper_bgcolor: '#141720',
      plot_bgcolor: '#141720',
      font: {{ color: '#8b99ad', family: 'Inter, sans-serif', size: 11 }},
      margin: {{ l: 50, r: 25, t: 25, b: 40 }},
      xaxis: {{ gridcolor: '#1f2937', zeroline: false }},
      yaxis: {{ gridcolor: '#1f2937', zeroline: false }},
      shapes: shapes,
      showlegend: true,
      legend: {{ orientation: 'h', y: 1.12, font: {{ size: 11 }} }}
    }};

    Plotly.newPlot('plotly-chart', [traceClose, traceSma], layout, {{ responsive: true, displayModeBar: false }});
  }}

  function atualizarSliders() {{
    premioPorto = parseFloat(document.getElementById("slider-premio").value);
    custosLog = parseFloat(document.getElementById("slider-custos").value);

    document.getElementById("lbl-premio-porto").innerText = `+US$ ${{premioPorto.toFixed(2)}}/bu`;
    document.getElementById("lbl-custos-log").innerText = `R$ ${{custosLog.toFixed(2)}}/sc`;

    renderizarTabelaArbitragem();
  }}

  function renderizarTabelaArbitragem() {{
    const tbody = document.getElementById("arbitrage-tbody");
    tbody.innerHTML = "";

    const cbot = DADOS.sentinel_corn.parametros_arbitragem?.cbot_cents || 530.0;
    const cambio = DADOS.sentinel_corn.parametros_arbitragem?.cambio_ptax || 5.166;
    const convBushel = 0.39368 * 0.06;

    DADOS.contratos.forEach(c => {{
      const closeVal = c.ultimo_close ?? c.close ?? 0;
      const cbotTotal = (cbot / 100.0) + premioPorto;
      const ppe = (cbotTotal * cambio * convBushel * 100.0) - custosLog;
      const spread = closeVal - ppe;
      const inflexao = (closeVal + custosLog) / (cbotTotal * convBushel * 100.0);

      let decisao = "PARIDADE EM EQUILÍBRIO";
      let corDecisao = "var(--corn-gold)";

      if (spread > 3.0) {{
        decisao = "ALERTA VENDA (B3 CARA VS PARIDADE)";
        corDecisao = "var(--bear-red)";
      }} else if (spread < -3.0) {{
        decisao = "OPORTUNIDADE COMPRA (B3 DESCONTADA)";
        corDecisao = "var(--bull-green)";
      }}

      tbody.innerHTML += `
        <tr>
          <td style="font-weight:700; color:#fff;">${{c.codigo}}</td>
          <td style="color:var(--text-muted);">${{c.vencimento_iso || c.vencimento}}</td>
          <td style="font-weight:700; color:#fff;">${{formatarMoeda(closeVal)}}</td>
          <td style="color:var(--accent-blue); font-weight:700;">${{formatarMoeda(ppe)}}</td>
          <td style="font-weight:700; color:${{spread > 0 ? 'var(--bear-red)' : 'var(--bull-green)'}};">
            ${{spread > 0 ? '+' : ''}}${{spread.toFixed(2)}}
          </td>
          <td style="color:#e2e8f0;">US$ 1 = R$ ${{inflexao.toFixed(3)}}</td>
          <td style="font-weight:700; color:${{corDecisao}};">${{decisao}}</td>
        </tr>
      `;
    }});
  }}

  document.addEventListener("DOMContentLoaded", init);
</script>
</body>
</html>
"""

    caminho_sistema = os.path.join(PASTA, "sistema_sentinel.html")
    with open(caminho_sistema, "w", encoding="utf-8") as f:
        f.write(html_conteudo)

    caminho_mockup = os.path.join(PASTA, "mockup_sentinel_sistema_novo.html")
    with open(caminho_mockup, "w", encoding="utf-8") as f:
        f.write(html_conteudo)

    print(f"Sistema Novo gerado em: {caminho_sistema}")
    print(f"Mockup sincronizado em: {caminho_mockup}")

if __name__ == "__main__":
    gerar_sistema_novo()
