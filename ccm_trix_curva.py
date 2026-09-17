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
import re
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# Ingestão, convergência e indicador (reaproveita módulos existentes sem alteração)
import ingestao_brapi as ib
import convergencia
import trix_v5
import leitor_csv

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

    # Monta a grade detalhada por strike para a tabela de opções
    strikes_todos = sorted(set(list(calls.keys()) + list(puts.keys())))
    grade = []
    preco_comp = preco_ref if preco_ref is not None else 0.0

    strike_atm = None
    if strikes_todos and preco_comp > 0:
        strike_atm = min(strikes_todos, key=lambda s: abs(float(s) - float(preco_comp)))

    for s in strikes_todos:
        s_float = float(s)
        oi_c = int(calls.get(s, 0))
        oi_p = int(puts.get(s, 0))
        s_cents = int(round(s_float * 100))
        ticker_c = f"{codigo}C{s_cents:06d}"
        ticker_p = f"{codigo}P{s_cents:06d}"
        grade.append({
            "strike": s_float,
            "ticker_call": ticker_c,
            "oi_call": oi_c,
            "is_call_wall": bool(call_wall is not None and abs(s_float - float(call_wall)) < 0.001),
            "is_itm_call": bool(s_float <= preco_comp),
            "ticker_put": ticker_p,
            "oi_put": oi_p,
            "is_put_wall": bool(put_wall is not None and abs(s_float - float(put_wall)) < 0.001),
            "is_itm_put": bool(s_float >= preco_comp),
            "is_max_pain": bool(max_pain is not None and abs(s_float - float(max_pain)) < 0.001),
            "is_atm": bool(strike_atm is not None and abs(s_float - float(strike_atm)) < 0.001),
        })

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
            "calls": calls,
            "puts": puts,
            "grade": grade,
            "meta": oi_dados.get("meta"),
            "preco_ref": preco_ref,
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
        linhas.append("Nota: RTCNI obtido online via CEPEA/ESALQ (com fallback local/Profit). Se defasagem > 7 dias corridos, exibe [DEFASADO — Xd].")
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
# 5b. SELEÇÃO DE OPÇÕES A 2 DESVIOS-PADRÃO (TOP 3 CALLS / TOP 3 PUTS)
# ══════════════════════════════════════════════════════════════════════════

def selecionar_top_opcoes_desvio(
    df_calc: pd.DataFrame,
    op: dict,
    close_ref: float,
    n_desvios: float = 2.0,
    top_n: int = 3,
) -> tuple:
    """
    Identifica as top N Calls e top N Puts com maior volume em aberto (OI)
    cujos strikes estejam dentro da faixa de n_desvios desvios-padrão do preço de fechamento.
    Utiliza a janela móvel de até 100 pregões reais (P_TREND do TRIX v5) para calcular o desvio padrão.
    """
    reais = df_calc[~df_calc["is_sintetico"]]
    if reais.empty or not op.get("disponivel"):
        return [], []

    janela_std = min(len(reais), trix_v5.P_TREND)
    std_val = float(reais["Close"].tail(janela_std).std(ddof=1))
    if pd.isna(std_val) or std_val <= 0:
        std_val = 2.0

    limite_inf = close_ref - (n_desvios * std_val)
    limite_sup = close_ref + (n_desvios * std_val)

    calls = op.get("calls") or {}
    puts = op.get("puts") or {}

    calls_f = [
        {"strike": float(s), "oi": int(oi), "tipo": "call"}
        for s, oi in calls.items()
        if limite_inf <= float(s) <= limite_sup and oi > 0
    ]
    calls_f.sort(key=lambda x: x["oi"], reverse=True)

    puts_f = [
        {"strike": float(s), "oi": int(oi), "tipo": "put"}
        for s, oi in puts.items()
        if limite_inf <= float(s) <= limite_sup and oi > 0
    ]
    puts_f.sort(key=lambda x: x["oi"], reverse=True)

    return calls_f[:top_n], puts_f[:top_n]


# ══════════════════════════════════════════════════════════════════════════
# 5c. GERADOR DA GRADE DE OPÇÕES POR CONTRATO (CALLS E PUTS ABERTAS)
# ══════════════════════════════════════════════════════════════════════════

def montar_html_grade_opcoes(resultados: list) -> tuple:
    """
    Gera os blocos HTML, CSS e JavaScript da tabela adicional de Grade de Opções
    (Calls e Puts abertas por contrato), no padrão de design Profit Pro,
    com seletor interativo em abas/botões e sincronização bidirecional com o gráfico Plotly.
    """
    validos = [r for r in resultados if r.get("sucesso")]
    if not validos:
        return "", "", ""

    botoes_nav = []
    containers_contratos = []

    for idx, r in enumerate(validos):
        cod = r["codigo"]
        venc = r["vencimento_iso"]
        op = r.get("opcoes") or {}
        grade = op.get("grade") or []
        tem_opcoes = op.get("disponivel", False) and len(grade) > 0
        total_calls = op.get("total_calls", 0)
        total_puts = op.get("total_puts", 0)
        tot_oi = total_calls + total_puts
        tot_oi_str = f"{tot_oi:,}" if tem_opcoes else "0"
        cw = op.get("call_wall")
        cw_oi = op.get("call_wall_oi")
        pw = op.get("put_wall")
        pw_oi = op.get("put_wall_oi")
        mp = op.get("max_pain")
        preco_ref = op.get("preco_ref")
        meta = op.get("meta") or {}
        data_lote = meta.get("data_referencia_lote", "N/D")

        # Botão de navegação por contrato
        cls_active = "active" if idx == 0 else ""
        botoes_nav.append(
            f'<button class="btn-contrato-opcoes {cls_active}" data-cod="{cod}" onclick="alternarGradeOpcoes(\'{cod}\', true)">'
            f'<span>{cod}</span>'
            f'<span class="btn-oi-badge">{tot_oi_str} OI</span>'
            f'</button>'
        )

        # Barra de KPIs do Contrato Selecionado
        cw_str = f"R$ {cw:.2f} ({cw_oi:,} ct)" if cw is not None and cw_oi is not None else (f"R$ {cw:.2f}" if cw is not None else "N/D")
        pw_str = f"R$ {pw:.2f} ({pw_oi:,} ct)" if pw is not None and pw_oi is not None else (f"R$ {pw:.2f}" if pw is not None else "N/D")
        mp_str = f"R$ {mp:.2f}" if mp is not None else "N/D"
        ref_str = f"R$ {preco_ref:.2f}" if preco_ref is not None else "N/D"
        pc_ratio_str = f"{(total_puts / total_calls):.2f}" if total_calls > 0 else "N/D"

        kpi_bar = f"""
        <div class="grade-kpi-bar">
            <div class="grade-kpi-item">
                <span class="kpi-title">Vencimento Opções</span>
                <span class="kpi-val" style="color: #cad5e2;">{venc}</span>
            </div>
            <div class="grade-kpi-item">
                <span class="kpi-title">Preço CCM Ref</span>
                <span class="kpi-val" style="color: #ffffff;">{ref_str}</span>
            </div>
            <div class="grade-kpi-item">
                <span class="kpi-title">Call Wall (Resistência)</span>
                <span class="kpi-val" style="color: #ff3b30;">{cw_str}</span>
            </div>
            <div class="grade-kpi-item">
                <span class="kpi-title">Put Wall (Suporte)</span>
                <span class="kpi-val" style="color: #00d060;">{pw_str}</span>
            </div>
            <div class="grade-kpi-item">
                <span class="kpi-title">Max Pain</span>
                <span class="kpi-val" style="color: #e3b341;">{mp_str}</span>
            </div>
            <div class="grade-kpi-item">
                <span class="kpi-title">Volume Calls / Puts</span>
                <span class="kpi-val"><span style="color: #00d060;">{total_calls:,} C</span> · <span style="color: #ff3b30;">{total_puts:,} P</span></span>
            </div>
            <div class="grade-kpi-item">
                <span class="kpi-title">Razão P/C</span>
                <span class="kpi-val" style="color: #58a6ff;">{pc_ratio_str}</span>
            </div>
            <div class="grade-kpi-item">
                <span class="kpi-title">Data Lote B3</span>
                <span class="kpi-val" style="color: #8b949e;">{data_lote}</span>
            </div>
        </div>
        """

        if not tem_opcoes:
            corpo_conteudo = f"""
            <div style="padding: 48px 24px; text-align: center; color: #8b949e;">
                <div style="font-size: 16px; font-weight: 600; color: #cad5e2; margin-bottom: 6px;">Nenhuma Posição Aberta em Opções</div>
                <p style="margin: 0; font-size: 13px;">Não foram encontradas posições em aberto de Call ou Put registradas na B3 para o contrato {cod} (vencimento {venc}).</p>
            </div>
            """
        else:
            max_oi = max([g["oi_call"] for g in grade] + [g["oi_put"] for g in grade] + [1])
            linhas_grade = []
            for g in grade:
                oi_c = g["oi_call"]
                oi_p = g["oi_put"]
                pct_c = (oi_c / max_oi) * 100 if max_oi > 0 else 0
                pct_p = (oi_p / max_oi) * 100 if max_oi > 0 else 0

                # Status CALL
                if g["is_call_wall"]:
                    st_call = '<span class="badge-wall-call">CALL WALL</span>'
                elif g["is_itm_call"] and oi_c > 0:
                    st_call = '<span class="badge-itm">ITM</span>'
                elif oi_c > 0:
                    st_call = '<span class="badge-otm">OTM</span>'
                else:
                    st_call = '<span style="color: #30363d;">—</span>'

                # Status PUT
                if g["is_put_wall"]:
                    st_put = '<span class="badge-wall-put">PUT WALL</span>'
                elif g["is_itm_put"] and oi_p > 0:
                    st_put = '<span class="badge-itm">ITM</span>'
                elif oi_p > 0:
                    st_put = '<span class="badge-otm">OTM</span>'
                else:
                    st_put = '<span style="color: #30363d;">—</span>'

                # Badges Strike
                badge_s = ""
                if g["is_max_pain"]:
                    badge_s += '<span class="badge-mp">MAX PAIN</span>'
                if g["is_atm"]:
                    badge_s += '<span class="badge-atm">ATM</span>'

                # Classes de linha
                cls_tr = []
                if g["is_call_wall"]:
                    cls_tr.append("row-call-wall")
                if g["is_put_wall"]:
                    cls_tr.append("row-put-wall")
                if g["is_atm"]:
                    cls_tr.append("row-atm")
                tr_class_str = f' class="{" ".join(cls_tr)}"' if cls_tr else ""

                cor_ticker_c = "#ffffff" if oi_c > 0 else "#484f58"
                cor_ticker_p = "#ffffff" if oi_p > 0 else "#484f58"
                cor_oi_c = "#00d060" if oi_c > 0 else "#484f58"
                cor_oi_p = "#ff3b30" if oi_p > 0 else "#484f58"

                str_oi_c = f"{oi_c:,}" if oi_c > 0 else "—"
                str_oi_p = f"{oi_p:,}" if oi_p > 0 else "—"

                linhas_grade.append(
                    f'<tr{tr_class_str}>'
                    f'<td style="font-family: Consolas, monospace; font-size: 13px; color: {cor_ticker_c}; font-weight: 600; text-align: left;">{g["ticker_call"]}</td>'
                    f'<td style="text-align: center;">{st_call}</td>'
                    f'<td style="font-family: Consolas, monospace; font-size: 13px; font-weight: 700; color: {cor_oi_c}; text-align: right;">{str_oi_c}</td>'
                    f'<td><div class="mini-bar-track" style="justify-content: flex-end;"><div class="mini-bar-fill-call" style="width: {pct_c:.1f}%;"></div></div></td>'
                    f'<td style="font-family: Consolas, monospace; font-size: 14px; font-weight: 700; color: #ffffff; text-align: center; background: #151922; border-left: 1px solid #232a38; border-right: 1px solid #232a38;">R$ {g["strike"]:.2f}{badge_s}</td>'
                    f'<td><div class="mini-bar-track" style="justify-content: flex-start;"><div class="mini-bar-fill-put" style="width: {pct_p:.1f}%;"></div></div></td>'
                    f'<td style="font-family: Consolas, monospace; font-size: 13px; font-weight: 700; color: {cor_oi_p}; text-align: left;">{str_oi_p}</td>'
                    f'<td style="text-align: center;">{st_put}</td>'
                    f'<td style="font-family: Consolas, monospace; font-size: 13px; color: {cor_ticker_p}; font-weight: 600; text-align: right;">{g["ticker_put"]}</td>'
                    f'</tr>'
                )

            tabela_corpo = "\n".join(linhas_grade)
            corpo_conteudo = f"""
            <div style="overflow-x: auto; max-height: 560px; overflow-y: auto;">
                <table class="opcoes-table">
                    <thead>
                        <tr>
                            <th colspan="4" class="th-call-group">CALLS (ALTA)</th>
                            <th class="th-strike-group">STRIKE</th>
                            <th colspan="4" class="th-put-group">PUTS (BAIXA)</th>
                        </tr>
                        <tr class="th-sub">
                            <th style="width: 130px; text-align: left;">Ticker Call</th>
                            <th style="width: 90px; text-align: center;">Status</th>
                            <th style="width: 90px; text-align: right;">OI Aberto</th>
                            <th style="width: 100px; text-align: right;">Volume</th>
                            <th style="width: 130px; text-align: center;">Strike (R$)</th>
                            <th style="width: 100px; text-align: left;">Volume</th>
                            <th style="width: 90px; text-align: left;">OI Aberto</th>
                            <th style="width: 90px; text-align: center;">Status</th>
                            <th style="width: 130px; text-align: right;">Ticker Put</th>
                        </tr>
                    </thead>
                    <tbody>
                        {tabela_corpo}
                    </tbody>
                </table>
            </div>
            """

        display_style = "block" if idx == 0 else "none"
        containers_contratos.append(
            f'<div class="grade-contrato-container" id="grade-{cod}" style="display: {display_style};">'
            f'{kpi_bar}'
            f'{corpo_conteudo}'
            f'</div>'
        )

    nav_html = "\n".join(botoes_nav)
    containers_html = "\n".join(containers_contratos)

    card_html = f"""
    <div class="profit-card" id="card-grade-opcoes">
        <div class="profit-card-header">
            <div>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="display: inline-block; width: 10px; height: 10px; background: #58a6ff; border-radius: 50%; box-shadow: 0 0 8px #58a6ff;"></span>
                    <h3 class="profit-title-text">GRADE DE OPÇÕES — Posições Abertas de Calls e Puts por Contrato</h3>
                </div>
                <p class="profit-subtitle">
                    Posições reais em aberto de Calls e Puts registradas na B3 (BRAPI). Compare strikes, concentração de contratos (Open Interest), Call Wall, Put Wall, Max Pain e zonas de proteção por contrato.
                </p>
            </div>
            <div style="display: flex; align-items: center; gap: 12px;">
                <span style="background: rgba(88, 166, 255, 0.15); color: #58a6ff; border: 1px solid rgba(88, 166, 255, 0.4); padding: 5px 12px; border-radius: 6px; font-size: 12px; font-weight: 700; letter-spacing: 0.5px;">PROVENIÊNCIA: MEDIDO / B3</span>
            </div>
        </div>
        <div class="opcoes-nav">
            {nav_html}
        </div>
        <div class="opcoes-body">
            {containers_html}
        </div>
    </div>
    """

    css_opcoes = """
    <style>
        .opcoes-nav {
            display: flex;
            gap: 8px;
            padding: 12px 20px;
            background: #101217;
            border-bottom: 1px solid #232a38;
            overflow-x: auto;
        }
        .btn-contrato-opcoes {
            background: #181d28;
            color: #9ba7b7;
            border: 1px solid #2b3345;
            border-radius: 6px;
            padding: 8px 14px;
            font-family: Consolas, monospace;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            white-space: nowrap;
        }
        .btn-contrato-opcoes:hover {
            background: #232a38;
            color: #ffffff;
            border-color: #3b465c;
        }
        .btn-contrato-opcoes.active {
            background: #1f6feb;
            color: #ffffff;
            border-color: #58a6ff;
            box-shadow: 0 0 12px rgba(31, 111, 235, 0.4);
        }
        .btn-oi-badge {
            background: rgba(0, 0, 0, 0.35);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 11px;
            color: #cad5e2;
        }
        .grade-kpi-bar {
            display: flex;
            flex-wrap: wrap;
            gap: 18px;
            padding: 14px 20px;
            background: #12151d;
            border-bottom: 1px solid #1c222e;
        }
        .grade-kpi-item {
            display: flex;
            flex-direction: column;
            gap: 3px;
        }
        .grade-kpi-item .kpi-title {
            font-size: 11px;
            font-weight: 700;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .grade-kpi-item .kpi-val {
            font-family: Consolas, monospace;
            font-size: 14px;
            font-weight: 700;
            color: #ffffff;
        }
        .opcoes-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }
        .opcoes-table th {
            padding: 10px 12px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .th-call-group {
            background: rgba(0, 208, 96, 0.12) !important;
            color: #00d060 !important;
            text-align: center;
            border-bottom: 2px solid #232a38;
            border-right: 2px solid #232a38;
        }
        .th-strike-group {
            background: #181d28 !important;
            color: #ffffff !important;
            text-align: center;
            border-bottom: 2px solid #232a38;
            border-right: 2px solid #232a38;
        }
        .th-put-group {
            background: rgba(255, 59, 48, 0.12) !important;
            color: #ff3b30 !important;
            text-align: center;
            border-bottom: 2px solid #232a38;
        }
        .th-sub th {
            background: #141720;
            color: #8b949e;
            font-size: 10px;
            border-bottom: 1px solid #232a38;
            padding: 8px 12px;
        }
        .opcoes-table td {
            padding: 8px 12px;
            border-bottom: 1px solid #1c222e;
            vertical-align: middle;
        }
        .opcoes-table tr:nth-child(even) {
            background-color: #12151d;
        }
        .opcoes-table tr:nth-child(odd) {
            background-color: #141720;
        }
        .opcoes-table tr:hover {
            background-color: #1e2433;
        }
        .row-call-wall {
            background: rgba(255, 59, 48, 0.12) !important;
        }
        .row-put-wall {
            background: rgba(0, 208, 96, 0.12) !important;
        }
        .row-atm {
            box-shadow: inset 0 1px 0 #58a6ff, inset 0 -1px 0 #58a6ff;
        }
        .mini-bar-track {
            width: 80px;
            background: #1c222e;
            height: 7px;
            border-radius: 3px;
            overflow: hidden;
            display: flex;
        }
        .mini-bar-fill-call {
            background: #00d060;
            height: 100%;
            border-radius: 3px;
        }
        .mini-bar-fill-put {
            background: #ff3b30;
            height: 100%;
            border-radius: 3px;
        }
        .badge-wall-call {
            font-size: 10px;
            background: rgba(255, 59, 48, 0.25);
            color: #ff3b30;
            border: 1px solid #ff3b30;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 700;
        }
        .badge-wall-put {
            font-size: 10px;
            background: rgba(0, 208, 96, 0.25);
            color: #00d060;
            border: 1px solid #00d060;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 700;
        }
        .badge-itm {
            font-size: 10px;
            background: rgba(88, 166, 255, 0.15);
            color: #58a6ff;
            padding: 2px 5px;
            border-radius: 3px;
            font-weight: 600;
        }
        .badge-otm {
            font-size: 10px;
            color: #6e7681;
        }
        .badge-mp {
            font-size: 10px;
            background: rgba(210, 153, 34, 0.25);
            color: #e3b341;
            border: 1px solid #d29922;
            padding: 2px 5px;
            border-radius: 4px;
            font-weight: 700;
            margin-left: 6px;
        }
        .badge-atm {
            font-size: 10px;
            background: rgba(255, 255, 255, 0.15);
            color: #ffffff;
            border: 1px solid #8b949e;
            padding: 2px 5px;
            border-radius: 4px;
            font-weight: 700;
            margin-left: 6px;
        }
    </style>
    """

    js_opcoes = r"""
    <script>
    function alternarGradeOpcoes(cod, sincronizarPlotly) {
        var containers = document.querySelectorAll('.grade-contrato-container');
        for (var i = 0; i < containers.length; i++) {
            containers[i].style.display = 'none';
        }
        var alvo = document.getElementById('grade-' + cod);
        if (alvo) {
            alvo.style.display = 'block';
        }

        var botoes = document.querySelectorAll('.btn-contrato-opcoes');
        for (var j = 0; j < botoes.length; j++) {
            if (botoes[j].getAttribute('data-cod') === cod) {
                botoes[j].classList.add('active');
            } else {
                botoes[j].classList.remove('active');
            }
        }

        if (sincronizarPlotly) {
            var gd = document.getElementsByClassName('plotly-graph-div')[0];
            if (gd && gd._fullLayout && gd._fullLayout.updatemenus && gd._fullLayout.updatemenus[0]) {
                var menu = gd._fullLayout.updatemenus[0];
                for (var k = 0; k < menu.buttons.length; k++) {
                    if (menu.buttons[k].label.indexOf(cod) !== -1) {
                        Plotly.update(gd, menu.buttons[k].args[0], menu.buttons[k].args[1]);
                        break;
                    }
                }
            }
        }
    }

    // Sincronização quando o dropdown nativo do gráfico Plotly for alterado
    document.addEventListener('DOMContentLoaded', function() {
        var timerCheck = setInterval(function() {
            var gd = document.getElementsByClassName('plotly-graph-div')[0];
            if (gd && gd.on) {
                clearInterval(timerCheck);
                gd.on('plotly_restyle', function() {
                    if (gd.data) {
                        for (var i = 0; i < gd.data.length; i++) {
                            if (gd.data[i].visible === true && gd.data[i].name) {
                                var nome = gd.data[i].name;
                                var match = nome.match(/CCM[FHKNUX]\d{2}/);
                                if (match) {
                                    alternarGradeOpcoes(match[0], false);
                                    break;
                                }
                            }
                        }
                    }
                });
            }
        }, 200);
    });
    </script>
    """

    return card_html, css_opcoes, js_opcoes


# ══════════════════════════════════════════════════════════════════════════
# 6. GERADOR DO GRÁFICO INTERATIVO COM SELETOR (SEÇÃO 2.5 / MOCKUP VALIDADO)
# ══════════════════════════════════════════════════════════════════════════

def gerar_grafico_interativo(resultados: list, output_html: str = ARQUIVO_HTML, watchlist: list = None):
    """
    Gera gráfico interativo standalone em HTML utilizando Plotly,
    replicando com fidelidade visual o padrão de design Profit:
      - Estética escura profissional (dark terminal / trading desk).
      - Candlesticks desenhados SOMENTE para dias reais (is_sintetico == False).
      - Cor dos candles baseada no ESTADO (PaintBar NTSL: COMPRADO=verde Profit, VENDIDO=vermelho Profit, FLAT=cinza).
      - Linha única no painel de preço: SMA(100) / VTend em branco/prata nítido.
      - Linha pontilhada magenta (#ff00cc) para o RTCNI Físico (Cepea/Esalq).
      - Escala de preços no lado direito (side="right", padrão Profit).
      - Marcadores de Entrada COMPRA e Entrada VENDA.
      - Linhas horizontais destacadas para Call Wall, Put Wall e Max Pain.
      - Seletor de contrato via dropdown menu (updatemenus).
      - Tabela visual de Watchlist (Seção 2.6b) de alta legibilidade e contraste no rodapé.
    """
    validos = [r for r in resultados if r.get("sucesso")]
    if not validos:
        print("Nenhum contrato válido para gerar gráfico.")
        return

    # Carrega série do RTCNI para plotagem da linha de referência física (Estilo Profit)
    df_rtcni = None
    try:
        try:
            import ingestao_cepea
            ingestao_cepea.sincronizar_dados_cepea(PASTA_PROJETO)
        except Exception:
            pass
        df_rtcni = leitor_csv.ler_arquivo(PASTA_PROJETO, "RTCNI")
        df_rtcni["Data"] = pd.to_datetime(df_rtcni["Data"]).dt.normalize()
    except Exception:
        df_rtcni = None

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

        # Prepara série alinhada do RTCNI Físico
        serie_rtcni = None
        rtcni_val = None
        if watchlist:
            for w in watchlist:
                if w.get("contrato") == cod:
                    rtcni_val = w.get("rtcni_preco")
                    break
            if rtcni_val is None and len(watchlist) > 0:
                rtcni_val = watchlist[0].get("rtcni_preco")

        if df_rtcni is not None and not df_rtcni.empty:
            df_m = pd.merge(df_plot[["Data"]], df_rtcni[["Data", "Close"]], on="Data", how="left")
            df_m["Close"] = df_m["Close"].ffill().bfill()
            serie_rtcni = df_m["Close"]
        elif rtcni_val is not None:
            serie_rtcni = pd.Series([rtcni_val] * len(datas))

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

        # Trace 1: Candles COMPRADO (Verde Profit #00d060)
        t_comp = go.Candlestick(
            x=datas,
            open=df_plot["Open"].where(is_comprado),
            high=df_plot["High"].where(is_comprado),
            low=df_plot["Low"].where(is_comprado),
            close=df_plot["Close"].where(is_comprado),
            name="COMPRADO",
            increasing={"fillcolor": "#00d060", "line": {"color": "#00d060"}},
            decreasing={"fillcolor": "#00d060", "line": {"color": "#00d060"}},
            showlegend=True,
            visible=(idx_contrato == 0),
        )

        # Trace 2: Candles VENDIDO (Vermelho Profit #ff3b30)
        t_vend = go.Candlestick(
            x=datas,
            open=df_plot["Open"].where(is_vendido),
            high=df_plot["High"].where(is_vendido),
            low=df_plot["Low"].where(is_vendido),
            close=df_plot["Close"].where(is_vendido),
            name="VENDIDO",
            increasing={"fillcolor": "#ff3b30", "line": {"color": "#ff3b30"}},
            decreasing={"fillcolor": "#ff3b30", "line": {"color": "#ff3b30"}},
            showlegend=True,
            visible=(idx_contrato == 0),
        )

        # Trace 3: Candles FLAT (Cinza Neutro #8b949e)
        t_flat = go.Candlestick(
            x=datas,
            open=df_plot["Open"].where(is_flat),
            high=df_plot["High"].where(is_flat),
            low=df_plot["Low"].where(is_flat),
            close=df_plot["Close"].where(is_flat),
            name="FLAT",
            increasing={"fillcolor": "#8b949e", "line": {"color": "#8b949e"}},
            decreasing={"fillcolor": "#8b949e", "line": {"color": "#8b949e"}},
            showlegend=True,
            visible=(idx_contrato == 0),
        )

        # Trace 4: Linha sobreposta SMA(100) / VTend (Branco nítido)
        t_sma = go.Scatter(
            x=datas,
            y=df_plot[f"trend_sma{trix_v5.P_TREND}"],
            mode="lines",
            name="SMA(100) — VTend",
            line={"color": "#f0f6fc", "width": 1.5},
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
            marker={"symbol": "triangle-up", "color": "#00d060", "size": 13},
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
            marker={"symbol": "triangle-down", "color": "#ff3b30", "size": 13},
            showlegend=True,
            visible=(idx_contrato == 0),
        )

        contrato_traces = [t_base, t_comp, t_vend, t_flat, t_sma, t_ent_comp, t_ent_vend]

        # Trace 7: Linha do RTCNI Físico (Estilo Profit — magenta pontilhada #ff00cc)
        if serie_rtcni is not None and not serie_rtcni.empty:
            ult_rtcni = float(serie_rtcni.iloc[-1])
            lbl_rtcni = f"RTCNI (Físico) R$ {ult_rtcni:.2f}"
            t_rtcni = go.Scatter(
                x=datas,
                y=serie_rtcni,
                mode="lines",
                name=lbl_rtcni,
                line={"color": "#ff00cc", "dash": "dot", "width": 2.0},
                showlegend=True,
                visible=(idx_contrato == 0),
            )
            contrato_traces.append(t_rtcni)

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

        # Top 3 Calls e Top 3 Puts com maior volume a 2 desvios-padrão do fechamento
        top_calls, top_puts = selecionar_top_opcoes_desvio(
            df_plot, op, close_ref=float(df_plot["Close"].iloc[-1])
        )

        for c_i, c_opt in enumerate(top_calls):
            c_strike = c_opt["strike"]
            c_oi = c_opt["oi"]
            if op.get("call_wall") is not None and abs(c_strike - float(op["call_wall"])) < 0.001:
                continue
            c_lbl = f"Top {c_i + 1} Call R$ {c_strike:.2f} — {c_oi:,} contratos"
            t_c = go.Scatter(
                x=[datas.iloc[0], datas.iloc[-1]],
                y=[c_strike, c_strike],
                mode="lines",
                name=c_lbl,
                line={"color": "#38bdf8", "dash": "dashdot", "width": 1.1},
                showlegend=True,
                visible=(idx_contrato == 0),
            )
            contrato_traces.append(t_c)

        for p_i, p_opt in enumerate(top_puts):
            p_strike = p_opt["strike"]
            p_oi = p_opt["oi"]
            if op.get("put_wall") is not None and abs(p_strike - float(op["put_wall"])) < 0.001:
                continue
            p_lbl = f"Top {p_i + 1} Put R$ {p_strike:.2f} — {p_oi:,} contratos"
            t_p = go.Scatter(
                x=[datas.iloc[0], datas.iloc[-1]],
                y=[p_strike, p_strike],
                mode="lines",
                name=p_lbl,
                line={"color": "#f43f5e", "dash": "dashdot", "width": 1.1},
                showlegend=True,
                visible=(idx_contrato == 0),
            )
            contrato_traces.append(t_p)

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
                {"title": f"MILHO TRADER · TRIX v5 (PaintBar NTSL) · Contrato: {cod}"},
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
        title={
            "text": f"<b>CCM FUTURO · TRIX v5 (PaintBar NTSL)</b> · Contrato: {primeiro_cod}",
            "font": {"size": 16, "color": "#f0f6fc"},
            "x": 0.5,
            "xanchor": "center",
        },
        plot_bgcolor="#13161c",
        paper_bgcolor="#101216",
        font={"color": "#e6edf3", "family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"},
        height=720,
        xaxis={
            "rangeslider": {"visible": False},
            "title": {"text": ""},
            "gridcolor": "#20252e",
            "showgrid": True,
            "zeroline": False,
            "tickfont": {"size": 11, "color": "#8b949e"},
        },
        yaxis={
            "title": {"text": "Preço (R$ / saca)"},
            "side": "right",
            "gridcolor": "#20252e",
            "showgrid": True,
            "zeroline": False,
            "dtick": 1.0,
            "tickformat": ".2f",
            "tickfont": {"size": 12, "color": "#cad5e2"},
        },
        legend={
            "font": {"color": "#cad5e2", "size": 11},
            "orientation": "h",
            "y": 1.1,
            "x": 0.5,
            "xanchor": "center",
            "bgcolor": "rgba(19, 22, 28, 0.8)",
            "bordercolor": "#2a313d",
            "borderwidth": 1,
        },
        updatemenus=[{
            "buttons": buttons,
            "direction": "down",
            "bgcolor": "#1c212b",
            "bordercolor": "#384152",
            "font": {"color": "#ffffff", "size": 12},
            "x": 0.0,
            "xanchor": "left",
            "y": 1.16,
            "active": 0,
        }],
        annotations=[
            {
                "text": "<b>CCM FUTURO · 1D</b><br><span style='font-size:14px;'>Milho B3 · PaintBar NTSL</span>",
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 24, "color": "rgba(255, 255, 255, 0.04)"},
                "align": "center",
            },
            {
                "align": "left",
                "font": {"color": "#8b949e", "size": 10},
                "showarrow": False,
                "text": (
                    "Padrão validado NTSL: cor do candle = estado (verde=comprado, vermelho=vendido, cinza=flat). "
                    "Linha branca = SMA(100)/VTend. Linha magenta pontilhada = RTCNI Físico ESALQ. "
                    "O trecho sintético do seed (2008–2026) alimenta o cálculo do indicador mas não é plotado. "
                    "Barreiras de opções exibem contratos em aberto (OI) ou N/D se indisponíveis."
                ),
                "x": 0,
                "xref": "paper",
                "y": -0.12,
                "yref": "paper",
            }
        ],
    )

    fig = go.Figure(data=all_traces, layout=layout)
    fig.write_html(output_html, config={"responsive": True})

    # Injeta estilização visual Profit e tabela visual de Watchlist no HTML gerado
    if watchlist:
        linhas_tr = []
        for w in watchlist:
            ccm_str = f"R$ {w['ccm_close']:.2f}"
            rtcni_str = f"R$ {w['rtcni_preco']:.2f}" if w["rtcni_preco"] else "N/D"
            sp = w["spread_vs_rtcni"]
            cor_sp = "#00d060" if sp and sp > 0 else ("#ff3b30" if sp and sp < 0 else "#e6edf3")
            sp_str = f"{sp:+0.2f}" if sp is not None else "N/D"
            rtcni_badge_defasado = ""
            if w.get('aviso_defasado'):
                rtcni_badge_defasado = f'<span class="badge-defasado">{w["aviso_defasado"]}</span>'

            linhas_tr.append(
                f"<tr>"
                f"<td style='padding: 14px 20px; font-family: Consolas, monospace; font-size: 15px; font-weight: 700; color: #58a6ff;'>{w['contrato']}</td>"
                f"<td style='padding: 14px 16px; color: #e6edf3; font-weight: 500;'>{w['vencimento_iso']}</td>"
                f"<td style='padding: 14px 16px;'><span style='font-family: Consolas, monospace; font-size: 15px; font-weight: 700; color: #ffffff;'>{ccm_str}</span> <span class='badge-medido'>[{w['prov_ccm']}]</span></td>"
                f"<td style='padding: 14px 16px;'><span style='font-family: Consolas, monospace; font-size: 15px; font-weight: 700; color: #ffffff;'>{rtcni_str}</span> <span class='badge-medido'>[{w['prov_rtcni']}]</span>{rtcni_badge_defasado}</td>"
                f"<td style='padding: 14px 16px; font-family: Consolas, monospace; font-size: 15px; font-weight: 700; color: {cor_sp};'>{sp_str}</td>"
                f"<td style='padding: 14px 16px; color: #cad5e2; font-family: Consolas, monospace; font-size: 13px;'>{w['ccm_data']}</td>"
                f"<td style='padding: 14px 20px; color: #cad5e2; font-family: Consolas, monospace; font-size: 13px;'>{w['rtcni_data']}</td>"
                f"</tr>"
            )
        corpo_tabela = "\n".join(linhas_tr)

        css_profit = """
        <style>
            body {
                margin: 0 !important;
                padding: 16px 20px 40px 20px !important;
                background-color: #0b0d11 !important;
                color: #e6edf3 !important;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif !important;
            }
            .profit-card {
                max-width: 1440px;
                margin: 24px auto 40px auto;
                background: #141720;
                border: 1px solid #232a38;
                border-radius: 10px;
                box-shadow: 0 12px 36px rgba(0,0,0,0.55);
                overflow: hidden;
            }
            .profit-card-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 16px 24px;
                background: #181d28;
                border-bottom: 1px solid #232a38;
            }
            .profit-title-text {
                margin: 0;
                font-size: 16px;
                font-weight: 700;
                color: #ffffff;
                letter-spacing: 0.5px;
            }
            .profit-subtitle {
                margin: 4px 0 0 0;
                font-size: 13px;
                color: #9ba7b7;
            }
            .profit-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 14px;
                text-align: left;
            }
            .profit-table th {
                background: #12151d;
                color: #a0afc0;
                font-size: 12px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.6px;
                padding: 14px 18px;
                border-bottom: 2px solid #232a38;
            }
            .profit-table td {
                padding: 14px 18px;
                border-bottom: 1px solid #1c222e;
                vertical-align: middle;
            }
            .profit-table tr:nth-child(even) {
                background-color: #12151d;
            }
            .profit-table tr:nth-child(odd) {
                background-color: #141720;
            }
            .profit-table tr:hover {
                background-color: #1d2331;
            }
            .badge-medido {
                font-size: 11px;
                background: rgba(0, 208, 96, 0.15);
                color: #00d060;
                border: 1px solid rgba(0, 208, 96, 0.4);
                padding: 2px 7px;
                border-radius: 4px;
                font-weight: 700;
                letter-spacing: 0.3px;
                margin-left: 6px;
            }
            .badge-defasado {
                font-size: 11px;
                background: rgba(240, 136, 62, 0.2);
                color: #f0883e;
                border: 1px solid rgba(240, 136, 62, 0.55);
                padding: 3px 8px;
                border-radius: 4px;
                font-weight: 700;
                letter-spacing: 0.3px;
                margin-left: 8px;
            }
        </style>
        """

        tabela_html = f"""
        <div class="profit-card">
            <div class="profit-card-header">
                <div>
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="display: inline-block; width: 10px; height: 10px; background: #00d060; border-radius: 50%; box-shadow: 0 0 8px #00d060;"></span>
                        <h3 class="profit-title-text">WATCHLIST — Curva CCM vs Físico RTCNI (Seção 2.6b)</h3>
                    </div>
                    <p class="profit-subtitle">
                        Último fechamento real medido por contrato contra indicador físico CEPEA/ESALQ (convergencia.py). Todos os valores são classificados como MEDIDO. Caso a defasagem entre Data CCM e Data RTCNI exceda 7 dias corridos, exibe o aviso [DEFASADO — Xd].
                    </p>
                </div>
                <div style="display: flex; align-items: center; gap: 12px;">
                    <span style="background: #1f6feb; color: #ffffff; padding: 5px 12px; border-radius: 6px; font-size: 12px; font-weight: 700; letter-spacing: 0.5px;">PROVENIÊNCIA: MEDIDO</span>
                </div>
            </div>
            <div style="overflow-x: auto;">
                <table class="profit-table">
                    <thead>
                        <tr>
                            <th style="padding: 14px 20px;">Contrato</th>
                            <th style="padding: 14px 16px;">Vencimento</th>
                            <th style="padding: 14px 16px;">CCM Real (B3)</th>
                            <th style="padding: 14px 16px;">RTCNI (Físico ESALQ)</th>
                            <th style="padding: 14px 16px;">Spread (Fut - Fís)</th>
                            <th style="padding: 14px 16px;">Data CCM</th>
                            <th style="padding: 14px 20px;">Data RTCNI</th>
                        </tr>
                    </thead>
                    <tbody>
                        {corpo_tabela}
                    </tbody>
                </table>
            </div>
        </div>
        """
        grade_card_html, grade_css, grade_js = montar_html_grade_opcoes(validos)

        try:
            with open(output_html, "r", encoding="utf-8") as f:
                conteudo = f.read()

            # Integra Feed de Notícias (coluna esquerda do gráfico)
            sidebar_html, css_feed, js_feed = "", "", ""
            try:
                import feed_noticias
                sidebar_html, css_feed, js_feed = feed_noticias.montar_html_feed_noticias()
            except Exception:
                pass

            if sidebar_html:
                m_plotly = re.search(r'(<div[^>]*class=["\']plotly-graph-div["\'][^>]*>[\s\S]*?</script>\s*</div>)', conteudo)
                if m_plotly:
                    bloco_plotly = m_plotly.group(1)
                    bloco_com_feed = (
                        f'<div class="dashboard-outer-container">\n'
                        f'    <div class="chart-and-news-wrapper">\n'
                        f'        {sidebar_html}\n'
                        f'        <div class="chart-main-container">\n'
                        f'            {bloco_plotly}\n'
                        f'        </div>\n'
                        f'    </div>\n'
                        f'</div>'
                    )
                    conteudo = conteudo.replace(bloco_plotly, bloco_com_feed)

            if "</head>" in conteudo:
                conteudo = conteudo.replace("</head>", f"{css_profit}\n{grade_css}\n{css_feed}\n</head>")
            if "</body>" in conteudo:
                corpo_adicional = f"{tabela_html}\n{grade_card_html}\n{grade_js}\n{js_feed}"
                conteudo = conteudo.replace("</body>", f"{corpo_adicional}\n</body>")
            with open(output_html, "w", encoding="utf-8") as f:
                f.write(conteudo)
        except Exception as e:
            print(f"Aviso ao anexar watchlist e grade de opções ao HTML: {e}")

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
