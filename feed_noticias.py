# -*- coding: utf-8 -*-
"""
feed_noticias.py — Módulo de ingestão e cache do Feed de Notícias do Milho.
Criado em 17/09/2026 para Milho Trader v1.0.

Responsabilidade:
  - Coletar notícias e comunicados em tempo real sobre o mercado de milho (físico e futuro).
  - Categorização automática por fonte oficial e relevância:
      * CEPEA: Indicador físico Esalq/BM&F, mercado à vista regional e balanço oferta/demanda.
      * CONAB: Levantamentos de safra brasileira, leilões públicos, estoques e colheita.
      * USDA: Relatórios WASDE, safras globais e americanas, exportações e estoques dos EUA.
      * MERCADO: Contratos futuros B3 (CCM), Chicago (ZC), câmbio e logística.
  - Cache local (dados_noticias_milho.json) com renovação horária (TTL de 60 min).
  - Resiliente: tratamento estrito de timeout e fallback automático para o cache em caso de falha de rede.
"""

import json
import os
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional

PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_CACHE_NOTICIAS = os.path.join(PASTA_PROJETO, "dados_noticias_milho.json")
TTL_SEGUNDOS = 3600  # 1 hora

HEADERS_PADRAO = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def _criar_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _consultar_feed_rss(query: str, timeout: int = 6) -> List[Dict]:
    """Consulta itens RSS do Google News Agro filtrados por query."""
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    req = urllib.request.Request(url, headers=HEADERS_PADRAO)
    ctx = _criar_ssl_context()
    
    itens = []
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
        xml_data = resp.read()
    
    root = ET.fromstring(xml_data)
    for it in root.findall(".//item"):
        raw_title = it.find("title").text if it.find("title") is not None else ""
        link = it.find("link").text if it.find("link") is not None else ""
        pub_date = it.find("pubDate").text if it.find("pubDate") is not None else ""
        source_el = it.find("source")
        fonte = source_el.text if source_el is not None else "Agro"

        # Remove sufixo do nome da fonte presente no título
        clean_title = re.sub(r"\s*-\s*[^-]+$", "", raw_title).strip()
        if clean_title and link:
            itens.append({
                "titulo": clean_title,
                "link": link,
                "pubDate": pub_date,
                "fonte": fonte,
            })
    return itens


def coletar_noticias_online(timeout: int = 6) -> List[Dict]:
    """Coleta notícias online agrupadas pelas categorias chave."""
    queries = [
        ("CEPEA", "milho cepea when:14d"),
        ("CONAB", "milho conab when:14d"),
        ("USDA", "milho usda when:14d"),
        ("MERCADO", "milho futuro b3 ccm when:7d"),
    ]

    todas = []
    vistos = set()

    for cat, q in queries:
        try:
            itens = _consultar_feed_rss(q, timeout=timeout)
            for it in itens[:6]:
                norm_title = it["titulo"].lower()
                if norm_title in vistos:
                    continue
                vistos.add(norm_title)
                todas.append({
                    "categoria": cat,
                    "titulo": it["titulo"],
                    "fonte": it["fonte"],
                    "link": it["link"],
                    "pubDate": it["pubDate"],
                })
        except Exception:
            continue

    return todas


def obter_noticias_milho(caminho_cache: str = ARQUIVO_CACHE_NOTICIAS, forcar: bool = False, timeout: int = 6) -> List[Dict]:
    """
    Retorna a lista de notícias do milho com cache de 1 hora.
    Se o cache for recente e forcar=False, retorna o cache local imediatamente.
    Se o cache estiver expirado ou ausente, busca online e atualiza o arquivo local.
    """
    # 1. Verifica cache local existente
    if not forcar and os.path.isfile(caminho_cache):
        try:
            mtime = os.path.getmtime(caminho_cache)
            idade = datetime.now().timestamp() - mtime
            if idade < TTL_SEGUNDOS:
                with open(caminho_cache, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                if dados and isinstance(dados, list):
                    return dados
        except Exception:
            pass

    # 2. Tenta coleta online
    noticias = coletar_noticias_online(timeout=timeout)
    if noticias:
        try:
            with open(caminho_cache, "w", encoding="utf-8") as f:
                json.dump(noticias, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return noticias

    # 3. Fallback defensivo para o cache antigo caso a busca online falhe
    if os.path.isfile(caminho_cache):
        try:
            with open(caminho_cache, "r", encoding="utf-8") as f:
                dados = json.load(f)
            if dados and isinstance(dados, list):
                return dados
        except Exception:
            pass

    return []


def montar_html_feed_noticias() -> tuple[str, str, str]:
    """
    Gera os blocos HTML, CSS e JS para a sidebar do Feed de Notícias do Milho
    integrada ao dashboard Profit Pro.
    """
    noticias = obter_noticias_milho()

    contagem = {"TODOS": len(noticias), "CEPEA": 0, "CONAB": 0, "USDA": 0, "MERCADO": 0}
    cards_html = []

    badge_colors = {
        "CEPEA": ("#f59e0b", "rgba(245, 158, 11, 0.15)", "rgba(245, 158, 11, 0.4)"),
        "CONAB": ("#10b981", "rgba(16, 185, 129, 0.15)", "rgba(16, 185, 129, 0.4)"),
        "USDA": ("#3b82f6", "rgba(59, 130, 246, 0.15)", "rgba(59, 130, 246, 0.4)"),
        "MERCADO": ("#c084fc", "rgba(192, 132, 252, 0.15)", "rgba(192, 132, 252, 0.4)"),
    }

    for n in noticias:
        cat = n.get("categoria", "MERCADO").upper()
        if cat in contagem:
            contagem[cat] += 1
        else:
            contagem["MERCADO"] += 1

        cor_texto, cor_bg, cor_border = badge_colors.get(cat, badge_colors["MERCADO"])

        pub = n.get("pubDate", "")
        data_formatada = "Recente"
        try:
            partes = pub.split()
            if len(partes) >= 5:
                data_formatada = f"{partes[1]} {partes[2]} {partes[4][:5]}"
        except Exception:
            data_formatada = pub[:16]

        card = f"""
        <div class="news-item-card" data-cat="{cat}" onclick="window.open('{n['link']}', '_blank')">
            <div class="news-card-top">
                <span class="news-badge" style="color: {cor_texto}; background: {cor_bg}; border: 1px solid {cor_border};">
                    {cat}
                </span>
                <span class="news-source">{n.get('fonte', 'Agro')}</span>
                <span class="news-time">{data_formatada}</span>
            </div>
            <div class="news-title">{n['titulo']}</div>
            <div class="news-footer">
                <span class="news-read-more">Ler notícia completa &rarr;</span>
            </div>
        </div>
        """
        cards_html.append(card)

    cards_str = "\n".join(cards_html) if cards_html else "<div style='color: #8b9bb4; padding: 20px; text-align: center;'>Nenhuma notícia recente disponível no momento.</div>"

    sidebar_html = f"""
    <aside class="news-sidebar" id="newsSidebar">
        <div class="news-header">
            <div class="news-header-left">
                <span class="news-pulse-dot"></span>
                <span class="news-header-title">Feed do Milho</span>
            </div>
            <button class="news-toggle-btn" id="btnToggleSidebar" onclick="alternarSidebarFeed()" title="Recolher/Expandir Feed">&#9664;</button>
        </div>

        <div class="news-status-bar">
            <span id="newsStatusText">Atualização Horária &bull; Monitorando CEPEA/CONAB/USDA</span>
            <button class="news-refresh-btn" onclick="atualizarFeedHorario()">&#8635; Atualizar</button>
        </div>

        <div class="news-tabs">
            <button class="news-tab active" onclick="filtrarNoticias('TODOS', this)">TODOS ({contagem['TODOS']})</button>
            <button class="news-tab" onclick="filtrarNoticias('CEPEA', this)">CEPEA ({contagem['CEPEA']})</button>
            <button class="news-tab" onclick="filtrarNoticias('CONAB', this)">CONAB ({contagem['CONAB']})</button>
            <button class="news-tab" onclick="filtrarNoticias('USDA', this)">USDA ({contagem['USDA']})</button>
            <button class="news-tab" onclick="filtrarNoticias('MERCADO', this)">MERCADO ({contagem['MERCADO']})</button>
        </div>

        <div class="news-search-box">
            <input type="text" id="newsSearchInput" class="news-search-input" placeholder="Pesquisar notícias do milho..." oninput="buscarNoticias()">
        </div>

        <div class="news-cards-container">
            {cards_str}
        </div>
    </aside>
    """

    css_feed = """
    <style>
    .dashboard-outer-container {
        display: flex;
        flex-direction: column;
        gap: 24px;
        max-width: 1560px;
        margin: 0 auto;
        width: 100%;
        box-sizing: border-box;
    }

    .chart-and-news-wrapper {
        display: flex;
        flex-direction: row;
        gap: 16px;
        align-items: stretch;
        height: 740px;
        position: relative;
        width: 100%;
        box-sizing: border-box;
    }

    .news-sidebar {
        width: 360px;
        min-width: 360px;
        max-width: 360px;
        background: #13161f;
        border: 1px solid #232a38;
        border-radius: 10px;
        display: flex;
        flex-direction: column;
        overflow: hidden;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
        transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1), min-width 0.3s, max-width 0.3s;
        height: 100%;
        box-sizing: border-box;
    }

    .news-sidebar.collapsed {
        width: 52px;
        min-width: 52px;
        max-width: 52px;
    }

    .news-sidebar.collapsed .news-header-title,
    .news-sidebar.collapsed .news-status-bar,
    .news-sidebar.collapsed .news-tabs,
    .news-sidebar.collapsed .news-search-box,
    .news-sidebar.collapsed .news-cards-container {
        display: none !important;
    }

    .news-sidebar.collapsed .news-header {
        padding: 16px 8px;
        justify-content: center;
        flex-direction: column;
        gap: 12px;
    }

    .news-sidebar.collapsed .news-toggle-btn {
        transform: rotate(180deg);
    }

    .news-header {
        padding: 14px 16px;
        background: #171b26;
        border-bottom: 1px solid #232a38;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .news-header-left {
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .news-pulse-dot {
        width: 10px;
        height: 10px;
        background: #00d060;
        border-radius: 50%;
        box-shadow: 0 0 10px #00d060;
        animation: pulse 2s infinite;
    }

    @keyframes pulse {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 208, 96, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 8px rgba(0, 208, 96, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 208, 96, 0); }
    }

    .news-header-title {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 14px;
        font-weight: 700;
        color: #ffffff;
        letter-spacing: 0.5px;
        text-transform: uppercase;
    }

    .news-toggle-btn {
        background: #1f2636;
        border: 1px solid #313b4f;
        color: #cad5e2;
        width: 28px;
        height: 28px;
        border-radius: 6px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        font-size: 12px;
        transition: all 0.2s;
    }

    .news-toggle-btn:hover {
        background: #2b354a;
        color: #ffffff;
    }

    .news-status-bar {
        padding: 8px 14px;
        background: #10131b;
        border-bottom: 1px solid #1c222e;
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 11px;
        color: #8b9bb4;
    }

    .news-refresh-btn {
        background: transparent;
        border: none;
        color: #4a9eff;
        cursor: pointer;
        font-size: 11px;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 4px;
        padding: 2px 6px;
        border-radius: 4px;
        transition: background 0.2s;
    }

    .news-refresh-btn:hover {
        background: rgba(74, 158, 255, 0.12);
    }

    .news-tabs {
        display: flex;
        gap: 4px;
        padding: 10px 12px;
        background: #13161f;
        border-bottom: 1px solid #1f2533;
        overflow-x: auto;
    }

    .news-tab {
        background: #1a1f2c;
        border: 1px solid #273042;
        color: #94a3b8;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 700;
        cursor: pointer;
        white-space: nowrap;
        transition: all 0.2s;
    }

    .news-tab:hover {
        background: #242c3d;
        color: #ffffff;
    }

    .news-tab.active {
        background: #1f6feb;
        border-color: #388bfd;
        color: #ffffff;
    }

    .news-search-box {
        padding: 8px 12px;
        border-bottom: 1px solid #1c222e;
    }

    .news-search-input {
        width: 100%;
        background: #0d1017;
        border: 1px solid #262e3d;
        border-radius: 5px;
        padding: 6px 10px;
        color: #ffffff;
        font-size: 12px;
        outline: none;
        box-sizing: border-box;
    }

    .news-search-input:focus {
        border-color: #1f6feb;
    }

    .news-cards-container {
        flex: 1;
        overflow-y: auto;
        padding: 10px 12px;
        display: flex;
        flex-direction: column;
        gap: 10px;
    }

    .news-cards-container::-webkit-scrollbar {
        width: 6px;
    }
    .news-cards-container::-webkit-scrollbar-track {
        background: #101217;
    }
    .news-cards-container::-webkit-scrollbar-thumb {
        background: #262e3d;
        border-radius: 3px;
    }
    .news-cards-container::-webkit-scrollbar-thumb:hover {
        background: #3a455a;
    }

    .news-item-card {
        background: #171b26;
        border: 1px solid #232b3a;
        border-radius: 6px;
        padding: 12px 14px;
        cursor: pointer;
        transition: transform 0.15s ease, border-color 0.15s ease, background 0.15s ease;
        display: flex;
        flex-direction: column;
        gap: 8px;
    }

    .news-item-card:hover {
        background: #1d2331;
        border-color: #3b82f6;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
    }

    .news-card-top {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 11px;
    }

    .news-badge {
        font-size: 10px;
        font-weight: 800;
        padding: 2px 6px;
        border-radius: 3px;
        letter-spacing: 0.4px;
    }

    .news-source {
        color: #94a3b8;
        font-weight: 600;
    }

    .news-time {
        color: #64748b;
        margin-left: auto;
        font-size: 10px;
        font-family: Consolas, monospace;
    }

    .news-title {
        color: #e2e8f0;
        font-size: 13px;
        font-weight: 600;
        line-height: 1.4;
        transition: color 0.15s;
    }

    .news-item-card:hover .news-title {
        color: #60a5fa;
    }

    .news-footer {
        display: flex;
        justify-content: flex-end;
    }

    .news-read-more {
        font-size: 11px;
        color: #4a9eff;
        font-weight: 600;
    }

    .chart-main-container {
        flex: 1;
        min-width: 0;
        background: #101217;
        border: 1px solid #232a38;
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
        height: 100%;
        box-sizing: border-box;
    }

    .profit-card {
        max-width: 1560px !important;
        margin: 24px auto !important;
        box-sizing: border-box;
    }

    /* ── RESPONSIVIDADE MULTI-DISPOSITIVO (TABLET E MOBILE) ────────────── */
    @media (max-width: 1080px) {
        .chart-and-news-wrapper {
            flex-direction: column !important;
            height: auto !important;
        }
        .news-sidebar {
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
            height: 380px !important;
        }
        .news-sidebar.collapsed {
            height: 52px !important;
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
        }
        .news-sidebar.collapsed .news-header {
            flex-direction: row !important;
            justify-content: space-between !important;
            padding: 12px 16px !important;
        }
        .chart-main-container {
            width: 100% !important;
            height: 600px !important;
        }
        .plotly-graph-div {
            height: 600px !important;
        }
    }

    @media (max-width: 768px) {
        body {
            padding: 8px 8px 32px 8px !important;
        }
        .dashboard-outer-container {
            gap: 16px !important;
        }
        .profit-card {
            margin: 14px auto !important;
            border-radius: 8px !important;
        }
        .profit-card-header {
            padding: 12px 14px !important;
            flex-direction: column !important;
            align-items: flex-start !important;
            gap: 8px !important;
        }
        .profit-title-text {
            font-size: 14px !important;
        }
        .profit-subtitle {
            font-size: 11px !important;
        }
        .chart-main-container {
            height: 480px !important;
        }
        .plotly-graph-div {
            height: 480px !important;
        }
        .news-sidebar {
            height: 340px !important;
        }
        .grade-kpi-bar {
            padding: 10px 12px !important;
            gap: 12px !important;
        }
        .grade-kpi-item .kpi-val {
            font-size: 12px !important;
        }
        .opcoes-nav {
            padding: 8px 10px !important;
            gap: 6px !important;
        }
        .btn-contrato-opcoes {
            padding: 6px 10px !important;
            font-size: 11px !important;
        }
    }
    </style>
    """

    js_feed = """
    <script>
    function alternarSidebarFeed() {
        const sidebar = document.getElementById('newsSidebar');
        sidebar.classList.toggle('collapsed');
        
        setTimeout(() => {
            var gd = document.getElementsByClassName('plotly-graph-div')[0];
            if (gd && window.Plotly) {
                Plotly.Plots.resize(gd);
            }
        }, 310);
    }

    window.addEventListener('resize', function() {
        var gd = document.getElementsByClassName('plotly-graph-div')[0];
        if (gd && window.Plotly) {
            Plotly.Plots.resize(gd);
        }
    });

    function filtrarNoticias(cat, el) {
        document.querySelectorAll('.news-tab').forEach(t => t.classList.remove('active'));
        el.classList.add('active');

        const cards = document.querySelectorAll('.news-item-card');
        cards.forEach(card => {
            if (cat === 'TODOS' || card.getAttribute('data-cat') === cat) {
                card.style.display = 'flex';
            } else {
                card.style.display = 'none';
            }
        });
    }

    function buscarNoticias() {
        const termo = document.getElementById('newsSearchInput').value.toLowerCase();
        const activeTab = document.querySelector('.news-tab.active').innerText.split(' ')[0];
        
        const cards = document.querySelectorAll('.news-item-card');
        cards.forEach(card => {
            const cat = card.getAttribute('data-cat');
            const titulo = card.querySelector('.news-title').innerText.toLowerCase();
            const bateCat = (activeTab === 'TODOS' || cat === activeTab);
            const bateBusca = titulo.includes(termo);

            if (bateCat && bateBusca) {
                card.style.display = 'flex';
            } else {
                card.style.display = 'none';
            }
        });
    }

    function atualizarFeedHorario() {
        const btn = document.querySelector('.news-refresh-btn');
        const statusText = document.getElementById('newsStatusText');
        if (btn) {
            btn.innerHTML = '&#8635; Atualizando...';
            btn.style.opacity = '0.5';
        }
        setTimeout(() => {
            if (btn) {
                btn.innerHTML = '&#8635; Atualizar';
                btn.style.opacity = '1';
            }
            const agora = new Date();
            const horaStr = agora.toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'});
            if (statusText) {
                statusText.innerHTML = `Feed online (${horaStr}) &bull; Monitorando 24/7`;
            }
        }, 400);
    }
    </script>
    """

    return sidebar_html, css_feed, js_feed

