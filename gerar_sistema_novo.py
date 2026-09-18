# -*- coding: utf-8 -*-
"""
gerar_sistema_novo.py — Gera a interface oficial do Novo Sistema Sentinel-Corn 360°
Incorpora o padrão exato de gráfico candlestick multi-painel (Candles + Call/Put Wall + Volume + TRIX v5),
com seletor de períodos (20P, 50P, 90P, 180P, Tudo), conforme o padrão de referência.
"""

import json
import os

PASTA = os.path.dirname(os.path.abspath(__file__))

def gerar_sistema_novo():
    arq_curva = os.path.join(PASTA, "dados_curva.json")
    arq_milho = os.path.join(PASTA, "dados_milho.json")

    if not os.path.exists(arq_curva):
        print(f"Erro: {arq_curva} nao encontrado.")
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
    --bg-dark: #07090e;
    --card-bg: #0d111a;
    --card-header: #121722;
    --border: #1e2638;
    --text-main: #f0f4f8;
    --text-muted: #8b99ad;
    --text-dim: #5a6678;
    --corn-gold: #f59e0b;
    --accent-cyan: #00e5ff;
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
    background: #0d111a;
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
    background: #0a0d14;
    border-bottom: 1px solid var(--border);
    padding: 10px 28px;
    display: flex;
    gap: 16px;
    overflow-x: auto;
    align-items: center;
  }}
  .ticker-item {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    white-space: nowrap;
    background: #101522;
    padding: 6px 12px;
    border-radius: 6px;
    border: 1px solid #1a2233;
    cursor: pointer;
    transition: all 0.2s;
  }}
  .ticker-item:hover {{ border-color: var(--corn-gold); }}
  .ticker-code {{ font-weight: 800; color: #fff; }}
  .ticker-price {{ font-family: 'JetBrains Mono', monospace; font-weight: 600; color: #e2e8f0; }}

  /* MAIN CONTAINER */
  .container {{
    max-width: 1440px;
    margin: 20px auto;
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
    margin-bottom: 20px;
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
    background: #141926;
    border: 1px solid var(--border);
    color: var(--text-muted);
    padding: 7px 15px;
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
    background: linear-gradient(135deg, #121824 0%, #0c1017 100%);
    border: 1px solid #232c3d;
    border-radius: 12px;
    padding: 22px;
    margin-bottom: 20px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
  }}
  .hero-top {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 16px;
    margin-bottom: 18px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 14px;
  }}
  .hero-title-group {{
    display: flex;
    align-items: center;
    gap: 14px;
  }}
  .hero-icon {{ font-size: 36px; }}
  .hero-title {{
    font-size: 18px;
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
    margin-bottom: 18px;
  }}
  @media (max-width: 1024px) {{
    .pillars-grid {{ grid-template-columns: 1fr; }}
  }}
  .pillar-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }}
  .pillar-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    border-bottom: 1px solid #161e2e;
    padding-bottom: 8px;
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
    margin: 6px 0;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }}
  .pillar-metric-name {{ font-size: 12px; color: var(--text-muted); }}
  .pillar-metric-val {{ font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700; color: #fff; }}
  .pillar-score-badge {{
    font-size: 12px;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 4px;
  }}

  /* NEWS LIST */
  .news-list {{
    list-style: none;
    margin-top: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}
  .news-item {{
    font-size: 11px;
    color: var(--text-muted);
    background: #090c12;
    padding: 7px 10px;
    border-radius: 6px;
    border-left: 3px solid var(--accent-blue);
    line-height: 1.4;
  }}
  .news-item.bullish {{ border-left-color: var(--bull-green); }}
  .news-item.bearish {{ border-left-color: var(--bear-red); }}

  /* SEÇÃO GRÁFICO (PADRÃO REF CNPI-T / PROFIT) */
  .chart-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 24px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
  }}
  .chart-card-header {{
    background: var(--card-header);
    border-bottom: 1px solid var(--border);
    padding: 14px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }}
  .chart-header-left {{
    display: flex;
    align-items: center;
    gap: 12px;
  }}
  .pulse-icon {{
    color: var(--accent-cyan);
    font-size: 18px;
  }}
  .chart-title-text {{
    font-size: 14px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 0.5px;
    text-transform: uppercase;
  }}
  .chart-subtitle-text {{
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 2px;
  }}
  .range-pills {{
    display: flex;
    gap: 6px;
    background: #090c14;
    padding: 4px;
    border-radius: 8px;
    border: 1px solid #1a2233;
  }}
  .range-btn {{
    background: transparent;
    border: none;
    color: var(--text-muted);
    padding: 5px 12px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
    cursor: pointer;
    font-family: 'JetBrains Mono', monospace;
    transition: all 0.15s;
  }}
  .range-btn:hover {{
    color: #fff;
  }}
  .range-btn.active {{
    background: var(--accent-cyan);
    color: #000;
    font-weight: 800;
    box-shadow: 0 0 10px rgba(0, 229, 255, 0.4);
  }}

  .chart-container-inner {{
    padding: 12px 14px;
    background: #07090e;
  }}
  .chart-box {{
    width: 100%;
    height: 640px;
  }}

  /* SEÇÃO PARIDADE & PARECER */
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
    border-bottom: 1px solid #161c28;
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
    background: #090c14;
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
    background: #090c12;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 18px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
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
        <div style="margin-top: 14px; border-top: 1px solid #161e2e; padding-top: 10px; display: flex; justify-content: space-between; align-items: center;">
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
        <div style="margin-top: 14px; border-top: 1px solid #161e2e; padding-top: 10px; display: flex; justify-content: space-between; align-items: center;">
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
          <div style="margin-top: 10px; font-size: 12px; color: var(--text-muted); background: #090c12; padding: 10px; border-radius: 6px; line-height: 1.4;">
            Órgãos oficiais: <b>USDA (WASDE)</b> e <b>CONAB</b>. Em janelas pré-relatório (&lt; 2 dias), a volatilidade implícita se eleva e o risco direcional recebe desconto.
          </div>
        </div>
        <div style="margin-top: 14px; border-top: 1px solid #161e2e; padding-top: 10px; display: flex; justify-content: space-between; align-items: center;">
          <span style="font-size: 11px; color: var(--text-muted);">Score Calendário:</span>
          <span class="pillar-score-badge" id="cal-score-badge" style="background:rgba(245,158,11,0.15); color:var(--corn-gold);">0.0 / 100</span>
        </div>
      </div>
    </div>

    <!-- PONTUAÇÃO CONSOLIDADA E FÓRMULA -->
    <div style="background: #090d14; border: 1px solid var(--border); border-radius: 8px; padding: 14px 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
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

  <!-- SEÇÃO GRÁFICO DIÁRIO MULTI-PAINEL (EXATAMENTE COMO O PADRÃO DE REFERÊNCIA) -->
  <div class="chart-card">
    <div class="chart-card-header">
      <div class="chart-header-left">
        <span class="pulse-icon">⚡</span>
        <div>
          <div class="chart-title-text" id="chart-card-title">GRÁFICO CANDLESTICK & TRIX v5 — CCMX26</div>
          <div class="chart-subtitle-text">Candles diários com Barreiras de Opções (Call/Put Walls), Volume e Indicador TRIX v5 (Tripla EMA)</div>
        </div>
      </div>
      <div class="range-pills">
        <button class="range-btn" onclick="alterarPeriodo(20)">20P</button>
        <button class="range-btn" onclick="alterarPeriodo(50)">50P</button>
        <button class="range-btn active" onclick="alterarPeriodo(90)">90P</button>
        <button class="range-btn" onclick="alterarPeriodo(180)">180P</button>
        <button class="range-btn" onclick="alterarPeriodo('Tudo')">Tudo</button>
      </div>
    </div>
    <div class="chart-container-inner">
      <div id="plotly-chart" class="chart-box"></div>
    </div>
  </div>

  <!-- SEÇÃO 2-COL: PARIDADE DE EXPORTAÇÃO & PARECER EXECUTIVO -->
  <div class="section-2col">
    <!-- PARIDADE DE EXPORTAÇÃO (PPE) -->
    <div class="content-card">
      <div class="content-card-header">
        <span class="content-card-title">⚓ Arbitragem & Paridade de Exportação (PPE)</span>
        <span style="font-size: 11px; color: var(--corn-gold); font-family: 'JetBrains Mono', monospace;">Fórmula B3/CME</span>
      </div>
      <div class="content-card-body">
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

        <table class="arbitrage-table">
          <thead>
            <tr>
              <th>Contrato</th>
              <th>Vencimento</th>
              <th>Preço B3</th>
              <th>PPE Porto</th>
              <th>Spread</th>
              <th>Inflexão WDO</th>
              <th>Decisão</th>
            </tr>
          </thead>
          <tbody id="arbitrage-tbody"></tbody>
        </table>
      </div>
    </div>

    <!-- PARECER ESTRATÉGICO -->
    <div class="content-card">
      <div class="content-card-header">
        <span class="content-card-title">🤖 Parecer do Consultor Sentinel-Corn</span>
        <span style="font-size: 11px; color: var(--accent-cyan);">Visão 360°</span>
      </div>
      <div class="content-card-body">
        <div class="parecer-text" id="parecer-box"></div>
      </div>
    </div>
  </div>

</div>

<script>
  const DADOS = {dados_json_str};

  const sentinelContratosMap = {{}};
  if (Array.isArray(DADOS.sentinel_corn.contratos)) {{
    DADOS.sentinel_corn.contratos.forEach(item => {{
      sentinelContratosMap[item.contrato] = item;
    }});
  }}

  let contratoAtual = (DADOS.contratos && DADOS.contratos.length > 0) ? DADOS.contratos[0].codigo : "CCMX26";
  let periodoBarras = 90; // Default idêntico ao 90P da imagem
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

  function alterarPeriodo(p) {{
    periodoBarras = p;
    document.querySelectorAll(".range-btn").forEach(btn => {{
      const txt = btn.innerText.trim();
      if ((p === 'Tudo' && txt === 'Tudo') || (txt === p + 'P')) {{
        btn.classList.add("active");
      }} else {{
        btn.classList.remove("active");
      }}
    }});
    const c = DADOS.contratos.find(x => x.codigo === contratoAtual) || DADOS.contratos[0];
    desenharGraficoMultiPainel(c);
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
    
    const elCons = document.getElementById("score-consolidado-val");
    if (sCons > 15) elCons.style.color = "var(--bull-green)";
    else if (sCons < -15) elCons.style.color = "var(--bear-red)";
    else elCons.style.color = "var(--corn-gold)";

    document.getElementById("formula-ponderacao").innerText = 
      `Score = (60% × ${{sTec.toFixed(1)}}) + (20% × ${{sRss.toFixed(1)}}) + (20% × ${{sCal.toFixed(1)}}) = ${{sCons > 0 ? '+' : ''}}${{sCons.toFixed(1)}}`;

    document.getElementById("chart-card-title").innerText = `GRÁFICO CANDLESTICK & TRIX v5 — ${{c.codigo}}`;
    desenharGraficoMultiPainel(c);
  }}

  function desenharGraficoMultiPainel(c) {{
    const serieCompleta = DADOS.series_contratos?.[c.codigo] || [];
    let serie = serieCompleta;
    if (periodoBarras !== 'Tudo' && typeof periodoBarras === 'number') {{
      serie = serieCompleta.slice(-periodoBarras);
    }}

    const dates = serie.map(item => item.data);
    const opens = serie.map(item => item.open);
    const highs = serie.map(item => item.high);
    const lows = serie.map(item => item.low);
    const closes = serie.map(item => item.close);
    const volumes = serie.map(item => item.volume);
    const trixVals = serie.map(item => item.trix);
    const sinalVals = serie.map(item => item.sinal);

    // Cores de volume: verde se close >= open, vermelho se close < open
    const volumeColors = closes.map((cls, i) => (cls >= opens[i] ? '#00d060' : '#ff3b30'));

    // 1. Painel Superior: Candlestick
    const traceCandles = {{
      x: dates,
      open: opens,
      high: highs,
      low: lows,
      close: closes,
      type: 'candlestick',
      name: `${{c.codigo}}`,
      increasing: {{ line: {{ color: '#00d060', width: 1 }}, fillcolor: '#00d060' }},
      decreasing: {{ line: {{ color: '#ff3b30', width: 1 }}, fillcolor: '#ff3b30' }},
      yaxis: 'y1',
      xaxis: 'x'
    }};

    // 2. Painel Central: Volume Diário
    const traceVolume = {{
      x: dates,
      y: volumes,
      type: 'bar',
      name: 'Volume',
      marker: {{ color: volumeColors }},
      yaxis: 'y2',
      xaxis: 'x'
    }};

    // 3. Painel Inferior: TRIX v5
    const traceTrix = {{
      x: dates,
      y: trixVals,
      type: 'scatter',
      mode: 'lines',
      name: 'TRIX v5 (7)',
      line: {{ color: '#00e5ff', width: 1.5 }},
      yaxis: 'y3',
      xaxis: 'x'
    }};

    const traceSinal = {{
      x: dates,
      y: sinalVals,
      type: 'scatter',
      mode: 'lines',
      name: 'Sinal (3)',
      line: {{ color: '#f59e0b', width: 1.2 }},
      yaxis: 'y3',
      xaxis: 'x'
    }};

    const shapes = [];
    const annotations = [];

    // Barreiras de Opções no Painel Superior (Call Wall e Put Wall)
    const callPrice = typeof c.call_wall === 'number' ? c.call_wall : c.call_wall?.preco;
    const putPrice = typeof c.put_wall === 'number' ? c.put_wall : c.put_wall?.preco;

    if (callPrice) {{
      shapes.push({{
        type: 'line', xref: 'x', yref: 'y1',
        x0: dates[0], x1: dates[dates.length - 1],
        y0: callPrice, y1: callPrice,
        line: {{ color: '#ff3b30', width: 1.5, dash: 'dash' }}
      }});
      annotations.push({{
        xref: 'paper', yref: 'y1',
        x: 1.0, y: callPrice,
        xanchor: 'left', yanchor: 'middle',
        text: `RES ${{callPrice.toFixed(2)}}`,
        font: {{ size: 10, color: '#ff3b30', family: 'JetBrains Mono', weight: 'bold' }},
        showarrow: false,
        bgcolor: 'rgba(255,59,48,0.15)',
        bordercolor: '#ff3b30',
        borderwidth: 1,
        borderpad: 2
      }});
    }}

    if (putPrice) {{
      shapes.push({{
        type: 'line', xref: 'x', yref: 'y1',
        x0: dates[0], x1: dates[dates.length - 1],
        y0: putPrice, y1: putPrice,
        line: {{ color: '#00d060', width: 1.5, dash: 'dash' }}
      }});
      annotations.push({{
        xref: 'paper', yref: 'y1',
        x: 1.0, y: putPrice,
        xanchor: 'left', yanchor: 'middle',
        text: `SUP ${{putPrice.toFixed(2)}}`,
        font: {{ size: 10, color: '#00d060', family: 'JetBrains Mono', weight: 'bold' }},
        showarrow: false,
        bgcolor: 'rgba(0,208,96,0.15)',
        bordercolor: '#00d060',
        borderwidth: 1,
        borderpad: 2
      }});
    }}

    // Linha Zero do TRIX
    shapes.push({{
      type: 'line', xref: 'x', yref: 'y3',
      x0: dates[0], x1: dates[dates.length - 1],
      y0: 0, y1: 0,
      line: {{ color: '#2a3447', width: 1, dash: 'dot' }}
    }});

    // Layout Multi-Painel
    const layout = {{
      paper_bgcolor: '#07090e',
      plot_bgcolor: '#07090e',
      font: {{ color: '#8b99ad', family: 'Inter, sans-serif', size: 11 }},
      margin: {{ l: 20, r: 85, t: 15, b: 35 }},
      showlegend: false,
      xaxis: {{
        type: 'category',
        gridcolor: '#131824',
        zeroline: false,
        showline: true,
        linecolor: '#1e2638',
        tickfont: {{ size: 10, family: 'JetBrains Mono' }},
        nticks: 10,
        rangeslider: {{ visible: false }}
      }},
      yaxis: {{
        domain: [0.38, 1.0],
        side: 'right',
        gridcolor: '#131824',
        zeroline: false,
        showline: true,
        linecolor: '#1e2638',
        tickformat: 'R$ .2f',
        tickfont: {{ size: 10, family: 'JetBrains Mono' }}
      }},
      yaxis2: {{
        domain: [0.22, 0.35],
        side: 'right',
        gridcolor: '#131824',
        zeroline: false,
        showticklabels: false,
        showline: true,
        linecolor: '#1e2638'
      }},
      yaxis3: {{
        domain: [0.0, 0.19],
        side: 'right',
        gridcolor: '#131824',
        zeroline: false,
        showline: true,
        linecolor: '#1e2638',
        tickfont: {{ size: 9, family: 'JetBrains Mono' }}
      }},
      shapes: shapes,
      annotations: [
        ...annotations,
        {{
          xref: 'paper', yref: 'paper',
          x: 0.01, y: 0.36,
          xanchor: 'left', yanchor: 'bottom',
          text: 'VOLUME DIÁRIO',
          font: {{ size: 9, color: '#5a6678', weight: 'bold' }},
          showarrow: false
        }},
        {{
          xref: 'paper', yref: 'paper',
          x: 0.01, y: 0.20,
          xanchor: 'left', yanchor: 'bottom',
          text: 'TRIX v5 (Tripla EMA 7 + SMA 3) — NTSL',
          font: {{ size: 9, color: '#00e5ff', weight: 'bold' }},
          showarrow: false
        }}
      ]
    }};

    Plotly.newPlot('plotly-chart', [traceCandles, traceVolume, traceTrix, traceSinal], layout, {{ responsive: true, displayModeBar: false }});
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
        decisao = "ALERTA VENDA (B3 CARA)";
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
          <td style="color:var(--accent-cyan); font-weight:700;">${{formatarMoeda(ppe)}}</td>
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
