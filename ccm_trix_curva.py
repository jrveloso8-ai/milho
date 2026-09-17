# -*- coding: utf-8 -*-
"""
ccm_trix_curva.py — Módulo TRIX v5 por Contrato (Curva CCM Futuro B3).
==============================================================================
MÓDULO NOVO E ISOLADO — Projeto Milho Trader
Roda em paralelo, sem alterar nenhum arquivo em produção (ccm_dados.py,
pipeline.py, milho_dashboard.html, sazonalidade_milho.py, trix_v5.py, leitor_csv.py).

Funcionalidades:
  1. Ingestão da curva de vencimentos vivos do CCM via BRAPI.
  2. Coleta de histórico diário próprio por contrato via BRAPI.
  3. Costura com seed contínuo (ccmfut_seed_2008_2026.csv) via offset aditivo
     para viabilizar a SMA(100) em contratos com histórico recente curto.
  4. Execução do indicador validado trix_v5.calc_sinais_trix_v5() sem alterações.
  5. Motor de classificação estrita de proveniência de dados (MEDIDO, DERIVADO,
     ESTIMADO, INDISPONIVEL, SIMULADO) com regra de contágio de janelas.
  6. Extração de barreiras de opções (Call Wall, Put Wall com contratos em aberto,
     Max Pain) via BRAPI ou N/D explícito se indisponível.
  7. Geração de resumo textual (console e resumo_trix_curva.txt).
  8. Geração de gráfico interativo com seletor de contratos (ccm_trix_curva.html),
     replicando fielmente o mockup aprovado (cor por estado NTSL, linha única
     SMA(100), marcadores de entrada e paredes de opções).
==============================================================================
"""

import os
import sys
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# Ingestão, convergência e indicador (reaproveita módulos existentes sem alteração)
import ingestao_brapi as ib
import convergencia
import trix_v5

SEED_FILE = os.path.join(os.path.dirname(__file__), "ccmfut_seed_2008_2026.csv")
ARQUIVO_RESUMO_TXT = os.path.join(os.path.dirname(__file__), "resumo_trix_curva.txt")
ARQUIVO_HTML = os.path.join(os.path.dirname(__file__), "ccm_trix_curva.html")
PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))


# ══════════════════════════════════════════════════════════════════════════
# 1. CARREGAMENTO DO SEED HISTÓRICO (CCMFUT CONTÍNUO)
# ══════════════════════════════════════════════════════════════════════════

def carregar_seed(caminho: str = SEED_FILE) -> pd.DataFrame:
    """
    Carrega o seed histórico fixo gerado a partir de CCM_HIST.xlsx.
    Tratado como read-only pelo resto do módulo.
    """
    if not os.path.isfile(caminho):
        raise FileNotFoundError(
            f"Arquivo de seed {caminho} não encontrado. Execute converter_seed_ccm.py primeiro."
        )
    df = pd.read_csv(caminho, comment="#")
    df["Data"] = pd.to_datetime(df["Data"]).dt.normalize()
    df = df.sort_values("Data").reset_index(drop=True)
    return df


# ══════════════════════════════════════════════════════════════════════════
# 2. FUNÇÃO DE AJUSTE E COSTURA DE SÉRIE (SEÇÃO 2.3)
# ══════════════════════════════════════════════════════════════════════════

def montar_serie_ajustada(
    codigo_contrato: str,
    df_contrato: pd.DataFrame,
    df_seed: pd.DataFrame,
) -> pd.DataFrame:
    """
    Trunca o seed até a véspera do primeiro pregão real de df_contrato;
    Calcula offset aditivo = (primeiro Close real) - (último Close do seed truncado);
    Soma esse offset a todo o trecho truncado do seed (Open, High, Low, Close);
    Concatena [seed ajustado] + [dado real do contrato], ordenado por data;
    Marca explicitamente a coluna 'is_sintetico':
      True  -> dias vindos do seed ajustado
      False -> dias reais de negociação do contrato.
    """
    if df_contrato is None or df_contrato.empty:
        raise ValueError(f"Contrato {codigo_contrato} sem dados históricos.")

    df_real = df_contrato.copy().sort_values("Data").reset_index(drop=True)
    df_real["Data"] = pd.to_datetime(df_real["Data"]).dt.normalize()
    data_primeiro_real = df_real["Data"].iloc[0]
    primeiro_close_real = df_real["Close"].iloc[0]

    # Trunca o seed até a véspera da data do primeiro registro real
    df_seed_trunc = df_seed[df_seed["Data"] < data_primeiro_real].copy()
    if df_seed_trunc.empty:
        # Contrato já tem histórico cobrindo todo o período do seed
        df_real["is_sintetico"] = False
        return df_real

    ultimo_close_seed = df_seed_trunc["Close"].iloc[-1]
    offset_aditivo = primeiro_close_real - ultimo_close_seed

    # Aplica o offset a todo o trecho truncado do seed
    for col in ["Open", "High", "Low", "Close"]:
        if col in df_seed_trunc.columns:
            df_seed_trunc[col] = df_seed_trunc[col] + offset_aditivo

    if "Volume" not in df_seed_trunc.columns:
        df_seed_trunc["Volume"] = 0.0
    if "Qtd" not in df_seed_trunc.columns:
        df_seed_trunc["Qtd"] = 0.0

    df_seed_trunc["is_sintetico"] = True
    df_real["is_sintetico"] = False

    cols = ["Data", "Open", "High", "Low", "Close", "Volume", "Qtd", "is_sintetico"]
    df_comb = pd.concat([df_seed_trunc[cols], df_real[cols]], ignore_index=True)
    df_comb = df_comb.sort_values("Data").reset_index(drop=True)

    return df_comb


# ══════════════════════════════════════════════════════════════════════════
# 3. CONTRATO DE PROVENIÊNCIA E REGRA DE CONTÁGIO (SEÇÃO 3)
# ══════════════════════════════════════════════════════════════════════════

def classificar_proveniencia(df: pd.DataFrame, coluna: str, data=None) -> str:
    """
    Função central única de classificação de proveniência:
      MEDIDO       — OHLC real da BRAPI (is_sintetico=False), volume e trades reais,
                     ou contagem de contratos em aberto de opções.
      DERIVADO     — Indicadores técnicos (trix, trend_sma100, posicao, etc.) ou
                     paredes de opções (call/put wall, max pain) calculados a partir
                     de insumos 100% reais (não contaminados).
      ESTIMADO     — Qualquer dia do trecho sintético (seed com offset) e qualquer
                     indicador cuja janela de cálculo toque pelo menos um dia sintético
                     (regra de contágio).
      INDISPONIVEL — Barreiras de opções ou valores não disponíveis na fonte oficial (N/D).
      SIMULADO     — Proibido no módulo.
    """
    # Campos de opções
    if coluna in ("call_wall", "put_wall", "max_pain"):
        return "DERIVADO"
    if coluna in ("call_wall_oi", "put_wall_oi", "total_oi_calls", "total_oi_puts"):
        return "MEDIDO"

    if df is None or df.empty:
        return "INDISPONIVEL"

    # Determinar a linha alvo (por data ou a mais recente)
    if data is None:
        idx = len(df) - 1
    else:
        dt = pd.to_datetime(data).normalize()
        matches = df.index[df["Data"] == dt]
        if len(matches) == 0:
            return "INDISPONIVEL"
        idx = matches[-1]

    row = df.iloc[idx]

    # Preço e volume diretos
    if coluna in ("Open", "High", "Low", "Close", "Volume", "Qtd"):
        if bool(row.get("is_sintetico", False)):
            return "ESTIMADO"
        # Item 6 (Opção a): no primeiro pregão real, o proxy de Open vem do Close do
        # dia sintético anterior, herdando portanto a classificação ESTIMADO.
        if coluna == "Open" and idx > 0 and bool(df.iloc[idx - 1].get("is_sintetico", False)):
            return "ESTIMADO"
        return "MEDIDO"

    # Indicadores técnicos com regra de contágio de janela:
    # Item 5: Unificado em 100 pregões para trend_sma100, trix, trix_sinal, posicao_trix_v5,
    # entrada_hoje e saida_hoje.
    # Justificativa técnica: TRIX(7) é uma tripla EMA(7) cuja memória exponencial decai
    # assintoticamente sem zerar numa marca arbitrária; além disso, a validação de tendência
    # do sistema depende da SMA(100). Adota-se o corte unificado e conservador de 100 pregões
    # reais para todo o conjunto de indicadores do sistema, garantindo consistência estrita.
    tam_janela = 100
    inicio_janela = max(0, idx - tam_janela + 1)
    trecho = df.iloc[inicio_janela : idx + 1]

    # Regra de contágio: se algum dia da janela de cálculo for sintético, herda ESTIMADO
    if trecho["is_sintetico"].any():
        return "ESTIMADO"

    return "DERIVADO"


def calcular_transicao_derivado(df: pd.DataFrame) -> dict:
    """
    Calcula, para a série do contrato, a partir de que data os valores de SMA(100)
    e sinais do TRIX v5 deixam de ser ESTIMADO e passam a ser DERIVADO puro.
    """
    reais = df[~df["is_sintetico"]].reset_index(drop=True)
    total_reais = len(reais)

    if total_reais < 100:
        return {
            "total_pregoes_reais": total_reais,
            "sma100_suficiente": False,
            "data_transicao": None,
            "classificacao_atual": "ESTIMADO",
            "detalhe": f"Possui apenas {total_reais} pregões reais (< 100). Status atual: ESTIMADO por contágio do seed.",
        }

    # O 100º pregão real (índice 99) é o primeiro dia em que a janela de 100 barras é 100% real
    dt_100 = reais.iloc[99]["Data"]
    return {
        "total_pregoes_reais": total_reais,
        "sma100_suficiente": True,
        "data_transicao": dt_100.strftime("%Y-%m-%d"),
        "classificacao_atual": "DERIVADO",
        "detalhe": f"{total_reais} pregões reais (>= 100). Transicionou para DERIVADO puro em {dt_100.strftime('%d/%m/%Y')}.",
    }


# ══════════════════════════════════════════════════════════════════════════
# 4. PROCESSAMENTO DA CURVA E OPÇÕES
# ══════════════════════════════════════════════════════════════════════════

def processar_contrato(
    c_info: dict,
    df_seed: pd.DataFrame,
    oi_todos: dict,
) -> dict:
    """
    Processa o ciclo completo para um contrato CCM específico.
    """
    codigo = c_info["contrato"]
    vencimento_iso = c_info.get("vencimento_iso", "")
    preco_curva = c_info.get("preco")

    # 1. Coleta histórico real do contrato via BRAPI
    df_real = ib.coletar_historico_ccm(codigo)
    if df_real is None or df_real.empty:
        return {
            "codigo": codigo,
            "sucesso": False,
            "erro": "Histórico indisponível na BRAPI.",
        }

    # 2. Costura com seed e gera série ajustada
    df_ajustado = montar_serie_ajustada(codigo, df_real, df_seed)

    # 3. Executa indicador técnico trix_v5 sem alteração
    df_calculado = trix_v5.calc_sinais_trix_v5(df_ajustado)

    # 4. Avalia proveniência e transição
    transicao = calcular_transicao_derivado(df_calculado)

    # Dados da última barra
    ult = df_calculado.iloc[-1]
    data_ult = ult["Data"].strftime("%Y-%m-%d")
    close_ult = float(ult["Close"])
    posicao_ult = str(ult["posicao_trix_v5"])
    entrada_ult = ult.get("entrada_hoje")
    saida_ult = ult.get("saida_hoje")
    sma100_ult = float(ult[f"trend_sma{trix_v5.P_TREND}"]) if pd.notna(ult.get(f"trend_sma{trix_v5.P_TREND}")) else None

    prov_close = classificar_proveniencia(df_calculado, "Close", ult["Data"])
    prov_posicao = classificar_proveniencia(df_calculado, "posicao_trix_v5", ult["Data"])
    prov_sma100 = classificar_proveniencia(df_calculado, "trend_sma100", ult["Data"])

    # 5. Barreiras de Opções via BRAPI
    oi_dados = oi_todos.get(codigo) or {}
    calls = oi_dados.get("calls") or {}
    puts = oi_dados.get("puts") or {}

    tem_opcoes = bool(calls or puts)
    preco_ref = close_ult if close_ult is not None else preco_curva

    call_wall = ib.calcular_wall(calls, preco_ref, "call") if tem_opcoes else None
    put_wall = ib.calcular_wall(puts, preco_ref, "put") if tem_opcoes else None
    max_pain = ib.calcular_max_pain(calls, puts) if tem_opcoes else None

    cw_oi = calls.get(call_wall) if call_wall is not None else None
    pw_oi = puts.get(put_wall) if put_wall is not None else None

    return {
        "codigo": codigo,
        "vencimento_iso": vencimento_iso,
        "sucesso": True,
        "df_calculado": df_calculado,
        "transicao": transicao,
        "ultimo_bar": {
            "data": data_ult,
            "close": close_ult,
            "prov_close": prov_close,
            "posicao": posicao_ult,
            "prov_posicao": prov_posicao,
            "entrada_hoje": entrada_ult if pd.notna(entrada_ult) else None,
            "saida_hoje": saida_ult if pd.notna(saida_ult) else None,
            "sma100": sma100_ult,
            "prov_sma100": prov_sma100,
        },
        "opcoes": {
            "disponivel": tem_opcoes,
            "call_wall": call_wall,
            "call_wall_oi": cw_oi,
            "put_wall": put_wall,
            "put_wall_oi": pw_oi,
            "max_pain": max_pain,
            "total_calls": sum(calls.values()),
            "total_puts": sum(puts.values()),
        },
    }


# ══════════════════════════════════════════════════════════════════════════
# 5. WATCHLIST E GERADOR DO RESUMO EM TEXTO (SEÇÃO 2.6 e 2.6b)
# ══════════════════════════════════════════════════════════════════════════

def montar_watchlist(resultados: list, pasta_projeto: str = PASTA_PROJETO) -> list:
    """
    Watchlist (Seção 2.6b): cada contrato vivo da curva CCM com seu último
    fechamento REAL (Close do dia mais recente com is_sintetico=False) ao lado
    do último fechamento do RTCNI (via convergencia.analisar_convergencia()).
    Lista simples, sem indicador, sem cor de estado, proveniência MEDIDO para todos os valores.
    """
    # Rodada 2 - Item 1 (Opção a): chamada dedicada a obter_rtcni_atual() para não
    # usar preço futuro fabricado (0.0) nem calcular métricas contaminadas (spread/z-score).
    dados_rtcni = convergencia.obter_rtcni_atual(pasta_projeto)
    rtcni_preco = dados_rtcni.get("rtcni_preco")
    rtcni_data = str(dados_rtcni.get("rtcni_data", "N/D"))

    watchlist = []
    for r in resultados:
        if not r.get("sucesso"):
            continue
        cod = r["codigo"]
        venc = r["vencimento_iso"]
        df_calc = r["df_calculado"]
        reais = df_calc[~df_calc["is_sintetico"]]
        if reais.empty:
            continue
        ult_real = reais.iloc[-1]
        ccm_close = float(ult_real["Close"])
        ccm_data = ult_real["Data"].strftime("%Y-%m-%d")
        spread = round(ccm_close - rtcni_preco, 2) if rtcni_preco is not None else None

        # Rodada 2 - Item 2: cálculo de defasagem de dias corridos entre Data CCM e Data RTCNI
        defasagem_dias = None
        aviso_defasado = ""
        if rtcni_data and rtcni_data != "N/D":
            try:
                dt_ccm = datetime.strptime(ccm_data, "%Y-%m-%d").date()
                dt_rtcni = datetime.strptime(rtcni_data, "%Y-%m-%d").date()
                defasagem_dias = (dt_ccm - dt_rtcni).days
                if defasagem_dias > 7:
                    aviso_defasado = f"[DEFASADO — {defasagem_dias}d]"
            except Exception:
                pass

        watchlist.append({
            "contrato": cod,
            "vencimento_iso": venc,
            "ccm_close": ccm_close,
            "ccm_data": ccm_data,
            "rtcni_preco": rtcni_preco,
            "rtcni_data": rtcni_data,
            "defasagem_dias": defasagem_dias,
            "aviso_defasado": aviso_defasado,
            "spread_vs_rtcni": spread,
            "prov_ccm": "MEDIDO",
            "prov_rtcni": "MEDIDO",
        })
    return watchlist


def gerar_resumo_texto(resultados: list, watchlist: list = None) -> str:
    """
    Gera o relatório formal em texto puro exigido pelos itens 2.6 e 2.6b.
    """
    linhas = []
    linhas.append("=" * 100)
    linhas.append("MILHO TRADER — RELATÓRIO TRIX v5 POR CONTRATO (CURVA CCM)")
    linhas.append(f"Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Fonte Primária: BRAPI | Seed: 2008–2026")
    linhas.append("=" * 100)

    # ── Bloco 2.6b: Watchlist Curva CCM vs RTCNI Físico ───────────────────────
    if watchlist:
        linhas.append("\n" + "=" * 100)
        linhas.append("WATCHLIST — CURVA CCM vs FÍSICO (RTCNI) — PROVENIÊNCIA: MEDIDO (Seção 2.6b)")
        linhas.append("Último fechamento real de cada contrato CCM contra último preço físico RTCNI (convergencia.py)")
        linhas.append("Nota: RTCNI obtido de CSV manual do Profit. Se defasagem > 7 dias corridos, exibe [DEFASADO — Xd].")
        linhas.append("-" * 120)
        linhas.append(f"{'CONTRATO':<10} {'VENCIMENTO':<12} {'CCM REAL':<18} {'RTCNI FÍSICO':<38} {'SPREAD (FUT-FÍS)':<18} {'DATA CCM':<12} {'DATA RTCNI':<12}")
        linhas.append("-" * 120)
        for w in watchlist:
            ccm_str = f"R$ {w['ccm_close']:.2f} [MEDIDO]"
            rtcni_val = f"R$ {w['rtcni_preco']:.2f} [MEDIDO]" if w['rtcni_preco'] else "N/D"
            if w.get('aviso_defasado'):
                rtcni_str = f"{rtcni_val} {w['aviso_defasado']}"
            else:
                rtcni_str = rtcni_val
            spread_str = f"{w['spread_vs_rtcni']:+0.2f}" if w['spread_vs_rtcni'] is not None else "N/D"
            linhas.append(f"{w['contrato']:<10} {w['vencimento_iso']:<12} {ccm_str:<18} {rtcni_str:<38} {spread_str:<18} {w['ccm_data']:<12} {w['rtcni_data']:<12}")
        linhas.append("=" * 120 + "\n")

    # ── Bloco 2.6: Resumo Técnico TRIX v5 e Opções por Contrato ───────────────
    linhas.append("DETALHAMENTO TÉCNICO E PROVENIÊNCIA POR CONTRATO (Seção 2.6)")
    linhas.append("-" * 100)

    for r in resultados:
        if not r.get("sucesso"):
            linhas.append(f"[{r['codigo']}] ERRO: {r.get('erro')}")
            linhas.append("-" * 100)
            continue

        cod = r["codigo"]
        venc = r["vencimento_iso"]
        u = r["ultimo_bar"]
        tr = r["transicao"]
        op = r["opcoes"]

        linhas.append(f"CONTRATO: {cod}  (Vencimento: {venc})")
        linhas.append(f"  Data Referência : {u['data']}")
        linhas.append(f"  Último Preço    : R$ {u['close']:.2f}  [{u['prov_close']}]")
        linhas.append(f"  Posição TRIX v5 : {u['posicao']}  [{u['prov_posicao']}]")
        linhas.append(f"  Entrada Hoje    : {u['entrada_hoje'] if u['entrada_hoje'] else 'Nenhum'}")
        linhas.append(f"  Saída Hoje      : {u['saida_hoje'] if u['saida_hoje'] else 'Nenhum'}")
        linhas.append(f"  SMA(100) / VTend: R$ {u['sma100']:.2f}  [{u['prov_sma100']}]" if u['sma100'] else "  SMA(100): N/D")
        linhas.append(f"  Histórico Real  : {tr['total_pregoes_reais']} pregões reais")
        linhas.append(f"  Status SMA(100) : {tr['detalhe']}")

        # Opções
        if op["disponivel"]:
            cw_str = f"R$ {op['call_wall']:.2f} — {op['call_wall_oi']:,} contratos" if op['call_wall'] else "N/D"
            pw_str = f"R$ {op['put_wall']:.2f} — {op['put_wall_oi']:,} contratos" if op['put_wall'] else "N/D"
            mp_str = f"R$ {op['max_pain']:.2f}" if op['max_pain'] else "N/D"
            linhas.append(f"  Barreiras Opções: Call Wall: {cw_str}  [DERIVADO/MEDIDO]")
            linhas.append(f"                    Put Wall : {pw_str}  [DERIVADO/MEDIDO]")
            linhas.append(f"                    Max Pain : {mp_str}  [DERIVADO]")
        else:
            linhas.append("  Barreiras Opções: Call Wall: N/D  [INDISPONIVEL]")
            linhas.append("                    Put Wall : N/D  [INDISPONIVEL]")
            linhas.append("                    Max Pain : N/D  [INDISPONIVEL]")

        linhas.append("-" * 100)

    texto = "\n".join(linhas)
    return texto


# ══════════════════════════════════════════════════════════════════════════
# 6. GERADOR DO GRÁFICO INTERATIVO COM SELETOR (SEÇÃO 2.5 / MOCKUP VALIDADO)
# ══════════════════════════════════════════════════════════════════════════

def gerar_grafico_interativo(resultados: list, output_html: str = ARQUIVO_HTML, watchlist: list = None):
    """
    Gera gráfico interativo standalone em HTML utilizando Plotly,
    replicando com fidelidade visual o mockup aprovado em mockup_ccm_trix_selecao_contrato.html:
      - Candlesticks desenhados SOMENTE para dias reais (is_sintetico == False).
      - Cor dos candles baseada no ESTADO (PaintBar NTSL: COMPRADO=verde, VENDIDO=vermelho, FLAT=cinza).
      - Linha única no painel de preço: SMA(100) / VTend.
      - Sem linhas de TRIX ou Sinal no gráfico.
      - Marcadores de Entrada COMPRA (triângulo verde para cima) e Entrada VENDA (triângulo vermelho para baixo).
      - Linhas horizontais destacadas para Call Wall, Put Wall (com contratos em aberto) e Max Pain.
      - Seletor de contrato via dropdown menu (updatemenus).
      - Tabela visual de Watchlist (Seção 2.6b) no rodapé do documento.
    """
    validos = [r for r in resultados if r.get("sucesso")]
    if not validos:
        print("Nenhum contrato válido para gerar gráfico.")
        return

    all_traces = []
    buttons = []
    trace_offset = 0

    for idx_contrato, r in enumerate(validos):
        cod = r["codigo"]
        venc = r["vencimento_iso"]
        df_calc = r["df_calculado"]
        op = r["opcoes"]

        # Filtra estritamente os dias reais (o trecho sintético NUNCA aparece como candle)
        df_plot = df_calc[~df_calc["is_sintetico"]].copy().reset_index(drop=True)
        datas = df_plot["Data"]

        # Máscaras de estado para colorir candles conforme PaintBar NTSL
        is_comprado = df_plot["posicao_trix_v5"] == "COMPRADO"
        is_vendido = df_plot["posicao_trix_v5"] == "VENDIDO"
        is_flat = df_plot["posicao_trix_v5"] == "FLAT"

        # Trace 0 do contrato: Candlestick base invisível (fornece range/hover)
        t_base = go.Candlestick(
            x=datas,
            open=df_plot["Open"],
            high=df_plot["High"],
            low=df_plot["Low"],
            close=df_plot["Close"],
            name=f"{cod} (preço)",
            increasing={"fillcolor": "rgba(0,0,0,0)", "line": {"color": "rgba(0,0,0,0)"}},
            decreasing={"fillcolor": "rgba(0,0,0,0)", "line": {"color": "rgba(0,0,0,0)"}},
            showlegend=False,
            visible=(idx_contrato == 0),
        )

        # Trace 1: Candles COMPRADO (Verde #3fb950)
        t_comp = go.Candlestick(
            x=datas,
            open=df_plot["Open"].where(is_comprado),
            high=df_plot["High"].where(is_comprado),
            low=df_plot["Low"].where(is_comprado),
            close=df_plot["Close"].where(is_comprado),
            name="COMPRADO",
            increasing={"fillcolor": "#3fb950", "line": {"color": "#3fb950"}},
            decreasing={"fillcolor": "#3fb950", "line": {"color": "#3fb950"}},
            showlegend=True,
            visible=(idx_contrato == 0),
        )

        # Trace 2: Candles VENDIDO (Vermelho #f85149)
        t_vend = go.Candlestick(
            x=datas,
            open=df_plot["Open"].where(is_vendido),
            high=df_plot["High"].where(is_vendido),
            low=df_plot["Low"].where(is_vendido),
            close=df_plot["Close"].where(is_vendido),
            name="VENDIDO",
            increasing={"fillcolor": "#f85149", "line": {"color": "#f85149"}},
            decreasing={"fillcolor": "#f85149", "line": {"color": "#f85149"}},
            showlegend=True,
            visible=(idx_contrato == 0),
        )

        # Trace 3: Candles FLAT (Cinza #c9d1d9)
        t_flat = go.Candlestick(
            x=datas,
            open=df_plot["Open"].where(is_flat),
            high=df_plot["High"].where(is_flat),
            low=df_plot["Low"].where(is_flat),
            close=df_plot["Close"].where(is_flat),
            name="FLAT",
            increasing={"fillcolor": "#c9d1d9", "line": {"color": "#c9d1d9"}},
            decreasing={"fillcolor": "#c9d1d9", "line": {"color": "#c9d1d9"}},
            showlegend=True,
            visible=(idx_contrato == 0),
        )

        # Trace 4: Linha única sobreposta: SMA(100) / VTend
        t_sma = go.Scatter(
            x=datas,
            y=df_plot[f"trend_sma{trix_v5.P_TREND}"],
            mode="lines",
            name="SMA(100) — VTend",
            line={"color": "#e6edf3", "width": 1.5},
            showlegend=True,
            visible=(idx_contrato == 0),
        )

        # Trace 5: Marcador Entrada COMPRA
        ent_comp = df_plot[df_plot["entrada_hoje"] == "COMPRA"]
        t_ent_comp = go.Scatter(
            x=ent_comp["Data"],
            y=ent_comp["Low"] * 0.995,
            mode="markers",
            name="Entrada COMPRA",
            marker={"symbol": "triangle-up", "color": "#3fb950", "size": 13},
            showlegend=True,
            visible=(idx_contrato == 0),
        )

        # Trace 6: Marcador Entrada VENDA
        ent_vend = df_plot[df_plot["entrada_hoje"] == "VENDA"]
        t_ent_vend = go.Scatter(
            x=ent_vend["Data"],
            y=ent_vend["High"] * 1.005,
            mode="markers",
            name="Entrada VENDA",
            marker={"symbol": "triangle-down", "color": "#f85149", "size": 13},
            showlegend=True,
            visible=(idx_contrato == 0),
        )

        contrato_traces = [t_base, t_comp, t_vend, t_flat, t_sma, t_ent_comp, t_ent_vend]

        # Barreiras de opções (Call Wall, Put Wall, Max Pain)
        if op["disponivel"] and op["call_wall"] is not None:
            cw_label = f"Call Wall R$ {op['call_wall']:.2f} — {op['call_wall_oi']:,} contratos"
            t_cw = go.Scatter(
                x=[datas.iloc[0], datas.iloc[-1]],
                y=[op["call_wall"], op["call_wall"]],
                mode="lines",
                name=cw_label,
                line={"color": "#f85149", "dash": "dash", "width": 1.4},
                showlegend=True,
                visible=(idx_contrato == 0),
            )
            contrato_traces.append(t_cw)

        if op["disponivel"] and op["put_wall"] is not None:
            pw_label = f"Put Wall R$ {op['put_wall']:.2f} — {op['put_wall_oi']:,} contratos"
            t_pw = go.Scatter(
                x=[datas.iloc[0], datas.iloc[-1]],
                y=[op["put_wall"], op["put_wall"]],
                mode="lines",
                name=pw_label,
                line={"color": "#3fb950", "dash": "dash", "width": 1.4},
                showlegend=True,
                visible=(idx_contrato == 0),
            )
            contrato_traces.append(t_pw)

        if op["disponivel"] and op["max_pain"] is not None:
            mp_label = f"Max Pain R$ {op['max_pain']:.2f}"
            t_mp = go.Scatter(
                x=[datas.iloc[0], datas.iloc[-1]],
                y=[op["max_pain"], op["max_pain"]],
                mode="lines",
                name=mp_label,
                line={"color": "#d29922", "dash": "dot", "width": 1.4},
                showlegend=True,
                visible=(idx_contrato == 0),
            )
            contrato_traces.append(t_mp)

        all_traces.extend(contrato_traces)
        n_traces_este = len(contrato_traces)

        # Botão para o dropdown
        btn_label = f"{cod}  ·  venc. {venc}"
        if not op["disponivel"]:
            btn_label += "  (sem OI de opções)"

        buttons.append({
            "label": btn_label,
            "method": "update",
            "args": [
                {"visible": []},
                {"title": f"MILHO TRADER · TRIX v5 (cor = estado, PaintBar NTSL) · Contrato: {cod}"},
            ],
            "_start": trace_offset,
            "_count": n_traces_este,
        })
        trace_offset += n_traces_este

    # Configurar máscaras de visibilidade exatas
    total_traces = len(all_traces)
    for b in buttons:
        vis = [False] * total_traces
        s = b["_start"]
        c = b["_count"]
        for j in range(s, s + c):
            vis[j] = True
        b["args"][0]["visible"] = vis
        del b["_start"]
        del b["_count"]

    primeiro_cod = validos[0]["codigo"]
    layout = go.Layout(
        title={"text": f"MILHO TRADER · TRIX v5 (cor = estado, PaintBar NTSL) · Contrato: {primeiro_cod}"},
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font={"color": "#e6edf3", "family": "Inter, sans-serif"},
        height=720,
        xaxis={"rangeslider": {"visible": False}, "title": {"text": "Data"}, "gridcolor": "#21262d"},
        yaxis={"title": {"text": "R$ / saca"}, "gridcolor": "#21262d"},
        legend={"font": {"color": "#c9d1d9"}, "orientation": "h", "y": 1.1, "x": 1, "xanchor": "right"},
        updatemenus=[{
            "buttons": buttons,
            "direction": "down",
            "bgcolor": "#161b22",
            "bordercolor": "#30363d",
            "font": {"color": "#e6edf3"},
            "x": 0.0,
            "xanchor": "left",
            "y": 1.16,
            "active": 0,
        }],
        annotations=[{
            "align": "left",
            "font": {"color": "#8b949e", "size": 10},
            "showarrow": False,
            "text": (
                "Padrão validado NTSL: cor do candle = estado (verde=comprado, vermelho=vendido, cinza=flat). "
                "Linha única sobreposta = SMA(100)/VTend. O trecho sintético do seed (2008–2026) alimenta o cálculo do indicador "
                "mas não é plotado. Barreiras de opções exibem contratos em aberto (OI) ou N/D se indisponíveis."
            ),
            "x": 0,
            "xref": "paper",
            "y": -0.12,
            "yref": "paper",
        }],
    )

    fig = go.Figure(data=all_traces, layout=layout)
    fig.write_html(output_html, config={"responsive": True})

    # Injeta a tabela visual de Watchlist no HTML gerado
    if watchlist:
        linhas_tr = []
        for w in watchlist:
            ccm_str = f"R$ {w['ccm_close']:.2f}"
            rtcni_str = f"R$ {w['rtcni_preco']:.2f}" if w["rtcni_preco"] else "N/D"
            sp = w["spread_vs_rtcni"]
            cor_sp = "#3fb950" if sp and sp > 0 else ("#f85149" if sp and sp < 0 else "#c9d1d9")
            sp_str = f"{sp:+0.2f}" if sp is not None else "N/D"
            rtcni_badge_defasado = ""
            if w.get('aviso_defasado'):
                rtcni_badge_defasado = f" <span style='font-size:10px; color:#f0883e; background:#381704; border:1px solid #bd561d; padding:2px 6px; border-radius:4px; font-weight:600;'>{w['aviso_defasado']}</span>"
            linhas_tr.append(
                f"<tr style='border-bottom: 1px solid #21262d;'>"
                f"<td style='padding: 10px; font-weight: 600; color: #58a6ff;'>{w['contrato']}</td>"
                f"<td style='padding: 10px; color: #8b949e;'>{w['vencimento_iso']}</td>"
                f"<td style='padding: 10px;'>{ccm_str} <span style='font-size:10px; color:#3fb950; font-weight:600;'>[{w['prov_ccm']}]</span></td>"
                f"<td style='padding: 10px;'>{rtcni_str} <span style='font-size:10px; color:#3fb950; font-weight:600;'>[{w['prov_rtcni']}]</span>{rtcni_badge_defasado}</td>"
                f"<td style='padding: 10px; font-weight: 600; color: {cor_sp};'>{sp_str}</td>"
                f"<td style='padding: 10px; color: #8b949e;'>{w['ccm_data']}</td>"
                f"<td style='padding: 10px; color: #8b949e;'>{w['rtcni_data']}</td>"
                f"</tr>"
            )
        corpo_tabela = "\n".join(linhas_tr)
        tabela_html = f"""
        <div style="max-width: 1200px; margin: 24px auto; padding: 20px; background: #161b22; border: 1px solid #30363d; border-radius: 8px; font-family: 'Inter', sans-serif; color: #e6edf3;">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #30363d; padding-bottom: 12px; margin-bottom: 16px;">
                <div>
                    <h3 style="margin: 0; font-size: 16px; font-weight: 600; color: #f0f6fc;">WATCHLIST — Curva CCM vs Físico RTCNI (Seção 2.6b)</h3>
                    <p style="margin: 4px 0 0 0; font-size: 12px; color: #8b949e;">Último fechamento real medido por contrato contra indicador físico ESALQ (convergencia.py). Todos os valores são classificados como MEDIDO. Caso a defasagem entre Data CCM e Data RTCNI exceda 7 dias corridos, exibe o aviso [DEFASADO — Xd].</p>
                </div>
                <span style="background: #238636; color: #fff; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: 600;">PROVENIÊNCIA: MEDIDO</span>
            </div>
            <table style="width: 100%; border-collapse: collapse; font-size: 13px; font-family: 'JetBrains Mono', monospace; text-align: left;">
                <thead>
                    <tr style="border-bottom: 1px solid #30363d; color: #8b949e; font-size: 11px; text-transform: uppercase;">
                        <th style="padding: 8px 10px;">Contrato</th>
                        <th style="padding: 8px 10px;">Vencimento</th>
                        <th style="padding: 8px 10px;">CCM Real</th>
                        <th style="padding: 8px 10px;">RTCNI (Físico)</th>
                        <th style="padding: 8px 10px;">Spread (Fut-Fís)</th>
                        <th style="padding: 8px 10px;">Data CCM</th>
                        <th style="padding: 8px 10px;">Data RTCNI</th>
                    </tr>
                </thead>
                <tbody>
                    {corpo_tabela}
                </tbody>
            </table>
        </div>
        """
        try:
            with open(output_html, "r", encoding="utf-8") as f:
                conteudo = f.read()
            if "</body>" in conteudo:
                conteudo = conteudo.replace("</body>", f"{tabela_html}\n</body>")
                with open(output_html, "w", encoding="utf-8") as f:
                    f.write(conteudo)
        except Exception as e:
            print(f"Aviso ao anexar watchlist ao HTML: {e}")

    print(f"Gráfico interativo gerado com sucesso em: {output_html}")


# ══════════════════════════════════════════════════════════════════════════
# 7. EXECUÇÃO PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════

def executar():
    print("=" * 70)
    print("Iniciando Módulo TRIX v5 por Contrato (Curva CCM)")
    print("=" * 70)

    # 1. Carregar seed
    print("Carregando seed histórico contínuo (2008–2026)...")
    df_seed = carregar_seed()
    print(f"Seed carregado: {len(df_seed)} registros ({df_seed['Data'].iloc[0].strftime('%Y-%m-%d')} a {df_seed['Data'].iloc[-1].strftime('%Y-%m-%d')})")

    # 2. Coletar curva de vencimentos vivos
    print("\nConsultando curva de vencimentos vivos do CCM via BRAPI...")
    curva_dados = ib.coletar_curva_ccm()
    if not curva_dados or not curva_dados.get("curva"):
        print("ERRO: BRAPI não retornou curva de vencimentos do CCM.")
        return

    curva = curva_dados["curva"]
    print(f"Contratos vivos na curva: {[c['contrato'] for c in curva]}")

    # 3. Coletar posições de opções de todos os vencimentos
    print("\nConsultando Open Interest de opções para a curva...")
    oi_todos = ib.coletar_oi_todos_vencimentos(curva)

    # 4. Processar cada contrato vivo
    print("\nProcessando histórico, ajuste de seed e TRIX v5 por contrato...")
    resultados = []
    for c in curva:
        cod = c["contrato"]
        print(f"  -> Processando {cod}...")
        res = processar_contrato(c, df_seed, oi_todos)
        resultados.append(res)
        if res.get("sucesso"):
            u = res["ultimo_bar"]
            print(f"     Close: R$ {u['close']:.2f} [{u['prov_close']}] | Pos: {u['posicao']} [{u['prov_posicao']}] | SMA100: {u['sma100']:.2f}")

    # 5. Montar Watchlist (Seção 2.6b)
    print("\nMontando Watchlist (Curva CCM vs Físico RTCNI)...")
    watchlist = montar_watchlist(resultados, PASTA_PROJETO)

    # 6. Gerar resumo em texto simples
    resumo_texto = gerar_resumo_texto(resultados, watchlist=watchlist)
    print("\n" + resumo_texto)

    with open(ARQUIVO_RESUMO_TXT, "w", encoding="utf-8") as f:
        f.write(resumo_texto)
    print(f"\nResumo gravado em: {ARQUIVO_RESUMO_TXT}")

    # 7. Gerar gráfico interativo com seletor
    print("\nGerando gráfico interativo com seletor de contratos e Watchlist...")
    gerar_grafico_interativo(resultados, ARQUIVO_HTML, watchlist=watchlist)

    print("\nProcessamento concluído com sucesso.")


if __name__ == "__main__":
    executar()
