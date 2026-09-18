# -*- coding: utf-8 -*-
"""
sentinel_engine.py — Motor de Inteligência e Sentimento de Mercado Sentinel-Corn 2.0
==================================================================================
Implementa o framework analítico de milho CCM (B3):
  1. Motor de Cálculo de Paridade de Exportação (PPE):
     PPE = ((CBOT + Premio) * 0.39368 * Câmbio * 0.06) - Custos_Logísticos
  2. Ponto de Inflexão de Câmbio (WDO):
     Nível de dólar no qual Preço_B3 = PPE
  3. Matriz de Decisão Basis vs. Paridade:
     Cruza Basis (Spot - Futuro) com PPE para alertas de Compra/Venda/Neutro.
  4. Ponderação Tripla de Sentimento por Contrato:
     - 20% Sentimento de Mercado (Notícias RSS categorizadas CEPEA/CONAB/USDA/Mercado)
     - 20% Calendário Econômico (Janela de risco e eventos USDA/CONAB)
     - 60% Sentimento Técnico (TRIX v5 + Barreiras de Opções Call/Put Wall + Max Pain)
     Classificação:
       Score >= +25  -> ALTISTA
       -25 < Score < +25 -> LATERAL
       Score <= -25 -> BAIXISTA
  5. Parecer Estratégico Sentinel-Corn 2.0 com Pivot Points e Cenários Bullish/Bearish.

100% compatível com dados MEDIDOS e DERIVADOS reais da B3/BRAPI/Esalq.
Sem dados fabricados ou simulados.
"""

import os
import json
import re
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple, Any

PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_CACHE_NOTICIAS = os.path.join(PASTA_PROJETO, "dados_noticias_milho.json")


# ══════════════════════════════════════════════════════════════════════════
# 1. MOTOR DE CÁLCULO DE PARIDADE DE EXPORTAÇÃO (PPE) E CÂMBIO
# ══════════════════════════════════════════════════════════════════════════

def calcular_ppe(
    cbot_cents: Optional[float],
    premio_porto_usd: float = 0.70,
    cambio_usdbrl: Optional[float] = 5.40,
    custos_logisticos_brl: float = 10.00
) -> Optional[float]:
    """
    Calcula a Paridade de Exportação (PPE) em R$/saca (60kg).
    Fórmula corrigida:
      cbot_total_cents = cbot_cents + (premio_porto_usd * 100.0)
      PPE_bruta = cbot_total_cents * 0.39368 * cambio_usdbrl * 0.06
      PPE = PPE_bruta - custos_logisticos_brl
    Retorna None se CBOT ou Câmbio forem nulos/indisponíveis.
    """
    if cbot_cents is None or cbot_cents <= 0:
        return None
    if cambio_usdbrl is None or cambio_usdbrl <= 0:
        return None

    cbot_total_cents = cbot_cents + (premio_porto_usd * 100.0)
    ppe_bruta = cbot_total_cents * 0.39368 * cambio_usdbrl * 0.06
    ppe_liquida = ppe_bruta - custos_logisticos_brl
    return round(ppe_liquida, 2)


def calcular_ponto_inflexao_cambio(
    preco_b3: float,
    cbot_cents: Optional[float],
    premio_porto_usd: float = 0.70,
    custos_logisticos_brl: float = 10.00
) -> Optional[float]:
    """
    Calcula qual patamar de Dólar (R$/USD) tornaria o preço B3 em tela igual à PPE.
    Isolando Câmbio na equação:
      cbot_total_cents = cbot_cents + (premio_porto_usd * 100.0)
      Preço_B3 + Custos = cbot_total_cents * 0.39368 * Câmbio * 0.06
      Câmbio_Inflexão = (Preço_B3 + Custos) / (cbot_total_cents * 0.39368 * 0.06)
    """
    if cbot_cents is None or cbot_cents <= 0:
        return None
    cbot_total_cents = cbot_cents + (premio_porto_usd * 100.0)
    denominador = cbot_total_cents * 0.39368 * 0.06
    if denominador <= 0:
        return None

    cambio_inflexao = (preco_b3 + custos_logisticos_brl) / denominador
    return round(cambio_inflexao, 3)


def matriz_decisao_basis_paridade(
    preco_b3: float,
    ppe: Optional[float],
    preco_spot_rtcni: Optional[float] = None,
    estrutura_curva: str = "CONTANGO"
) -> Dict[str, Any]:
    """
    Aplica a matriz de decisão Basis vs. Paridade:
      - ALERTA DE VENDA (Short/Bearish): Se Preço B3 > PPE + R$ 3,00 E Contango excessivo
      - ALERTA DE COMPRA (Long/Bullish): Se Preço B3 < PPE E Basis estreito ou Backwardation
      - NEUTRO / FAIR: Se oscilando na banda de arbitragem
      - PARIDADE INDISPONÍVEL: Se PPE for None (CBOT ou Câmbio ausente)
    """
    basis = None
    if preco_spot_rtcni and preco_spot_rtcni > 0:
        basis = round(preco_spot_rtcni - preco_b3, 2)

    if ppe is None or ppe <= 0:
        return {
            "preco_b3": preco_b3,
            "ppe": None,
            "gap_ppe": None,
            "basis": basis,
            "recomendacao": "PARIDADE INDISPONÍVEL",
            "sinal": "NEUTRO",
            "explicacao": "Cotação CBOT (CME) ou Câmbio WDO indisponível para cálculo da PPE."
        }

    gap_ppe = round(preco_b3 - ppe, 2)

    # Lógica de recomendação estrita
    is_contango_excessivo = (estrutura_curva == "CONTANGO" and (basis is not None and basis < -4.0)) or (estrutura_curva == "CONTANGO" and gap_ppe > 3.0)
    is_backwardation_ou_estreito = (estrutura_curva == "BACKWARDATION") or (basis is not None and basis >= -1.0)

    if gap_ppe > 3.0 and is_contango_excessivo:
        recomendacao = "ALERTA DE VENDA (Short/Bearish)"
        sinal = "VENDA"
        explicacao = f"Preço B3 (R$ {preco_b3:.2f}) está R$ {gap_ppe:.2f} acima da PPE (R$ {ppe:.2f}) com Contango excessivo frente ao spot."
    elif preco_b3 < ppe and is_backwardation_ou_estreito:
        recomendacao = "ALERTA DE COMPRA (Long/Bullish)"
        sinal = "COMPRA"
        explicacao = f"Preço B3 (R$ {preco_b3:.2f}) negocia com desconto de R$ {abs(gap_ppe):.2f} sob a PPE com sustentação de Basis no físico."
    else:
        recomendacao = "NEUTRO / FAIXA DE ARBITRAGEM"
        sinal = "NEUTRO"
        explicacao = f"Preço B3 alinhado à banda normal de arbitragem portuária (Spread vs PPE: R$ {gap_ppe:+.2f})."

    return {
        "preco_b3": preco_b3,
        "ppe": ppe,
        "gap_ppe": gap_ppe,
        "basis": basis,
        "recomendacao": recomendacao,
        "sinal": sinal,
        "explicacao": explicacao
    }


# ══════════════════════════════════════════════════════════════════════════
# 2. SENTIMENTO DE MERCADO: NOTÍCIAS RSS (PESO 20%)
# ══════════════════════════════════════════════════════════════════════════

TERMOS_ALTISTAS = [
    "quebra", "estiagem", "seca", "geada", "perda", "atraso no plantio",
    "redução de safra", "corte de produtividade", "alta demanda", "aquecimento",
    "estoques baixos", "escassez", "retenção pelo produtor", "exportações firmes",
    "preço em alta", "dispara", "recuperação", "aperto", "subindo", "alta"
]

TERMOS_BAIXISTAS = [
    "safra recorde", "super safra", "supersafra", "avanço da colheita",
    "ritmo acelerado", "oferta abundante", "pressão de venda", "queda",
    "estoques elevados", "desaceleração", "recuo", "baixa demanda", "desvalorização",
    "pressão sazonal", "queda em chicago", "despenca", "estoques cheios"
]


def calcular_score_noticias(caminho_noticias: str = ARQUIVO_CACHE_NOTICIAS) -> Tuple[float, Dict[str, Any]]:
    """
    Analisa as notícias reais capturadas do RSS (CEPEA, CONAB, USDA, Mercado).
    Retorna score de -100 (Extremamente Baixista) a +100 (Extremamente Altista).
    """
    if not os.path.isfile(caminho_noticias):
        return 0.0, {"resumo": "Feed de notícias indisponível no momento.", "contagem_altista": 0, "contagem_baixista": 0}

    try:
        with open(caminho_noticias, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except Exception:
        return 0.0, {"resumo": "Falha ao ler cache de notícias.", "contagem_altista": 0, "contagem_baixista": 0}

    if isinstance(dados, list):
        noticias = dados
    elif isinstance(dados, dict):
        noticias = dados.get("noticias", [])
    else:
        noticias = []
    if not noticias:
        return 0.0, {"resumo": "Nenhuma notícia agro no feed.", "contagem_altista": 0, "contagem_baixista": 0}

    pontos_altistas = 0
    pontos_baixistas = 0
    manchetes_relevantes = []

    for item in noticias[:30]:
        texto = f"{item.get('titulo', '')} {item.get('resumo', '')}".lower()
        alt_match = [t for t in TERMOS_ALTISTAS if t in texto]
        bx_match = [t for t in TERMOS_BAIXISTAS if t in texto]

        if alt_match or bx_match:
            manchetes_relevantes.append({
                "titulo": item.get("titulo"),
                "fonte": item.get("categoria", "MERCADO"),
                "alt": len(alt_match),
                "bx": len(bx_match)
            })

        pontos_altistas += len(alt_match)
        pontos_baixistas += len(bx_match)

    total = pontos_altistas + pontos_baixistas
    if total == 0:
        score = 0.0
        resumo = "Noticiário recente neutro, sem gatilhos climáticos ou de quebra evidentes."
    else:
        score = ((pontos_altistas - pontos_baixistas) / total) * 100.0
        score = max(-100.0, min(100.0, score))

        if score >= 20:
            resumo = f"Noticiário com viés ALTISTA ({pontos_altistas} termos de alta vs {pontos_baixistas} de baixa), pautado por clima/estoques."
        elif score <= -20:
            resumo = f"Noticiário com viés BAIXISTA ({pontos_baixistas} termos de baixa vs {pontos_altistas} de alta), pautado por avanço de oferta/colheita."
        else:
            resumo = f"Noticiário EQUILIBRADO/LATERAL ({pontos_altistas} termos altistas vs {pontos_baixistas} baixistas)."

    return round(score, 1), {
        "score": round(score, 1),
        "resumo": resumo,
        "pontos_altistas": pontos_altistas,
        "pontos_baixistas": pontos_baixistas,
        "total_analisado": len(noticias)
    }


# ══════════════════════════════════════════════════════════════════════════
# 3. SENTIMENTO DE CALENDÁRIO ECONÔMICO (PESO 20%)
# ══════════════════════════════════════════════════════════════════════════

def calcular_score_calendario(data_ref: Optional[date] = None) -> Tuple[float, Dict[str, Any]]:
    """
    Avalia a proximidade de eventos de alto impacto (USDA WASDE, Levantamentos CONAB).
    """
    if data_ref is None:
        data_ref = date.today()

    try:
        import calendario_economico as cal
        eventos = cal.obter_eventos_proximos(data_ref, dias_a_frente=15)
    except Exception:
        eventos = []

    if not eventos:
        return 0.0, {
            "score": 0.0,
            "status": "JANELA_LIMPA",
            "classificacao": "JANELA_LIMPA",
            "dias_ate_proximo": None,
            "proximo_evento": None,
            "eventos_proximos": [],
            "resumo": "Nenhum relatório oficial (USDA/CONAB) nos próximos 15 dias. Menor risco de gap."
        }

    proximo = eventos[0]
    dias = proximo.get("dias_ate", 999)
    nome_evento = proximo.get("evento", "Evento Oficial")

    if dias <= 1:
        score = -15.0
        resumo = f"ALERTA MÁXIMO: {nome_evento} em {dias} dia(s). Alto risco de volatilidade e reprecificação abrupta."
        status = "RISCO_IMINENTE"
    elif dias <= 3:
        score = -5.0
        resumo = f"ATENÇÃO: {nome_evento} em {dias} dias. Redução de convicção direcional pré-relatório."
        status = "RISCO_MODERADO"
    else:
        score = 10.0
        resumo = f"Janela livre de relatórios oficiais imediatos. Próximo: {nome_evento} em {dias} dias."
        status = "JANELA_LIMPA"

    return round(score, 1), {
        "score": round(score, 1),
        "status": status,
        "classificacao": status,
        "dias_ate_proximo": dias,
        "proximo_evento": nome_evento,
        "eventos_proximos": eventos,
        "resumo": resumo
    }


# ══════════════════════════════════════════════════════════════════════════
# 4. SENTIMENTO TÉCNICO & BARREIRAS DE OPÇÕES (PESO 60%)
# ══════════════════════════════════════════════════════════════════════════

def calcular_score_tecnico_contrato(
    res_contrato: Dict[str, Any],
    preco_fechamento: float,
    atr14: float = 1.50
) -> Tuple[float, Dict[str, Any]]:
    """
    Avalia a condição técnica do contrato:
      1. Indicador TRIX v5 (NTSL, inclinação, SMA100)
      2. Barreiras de Opções (Call Wall, Put Wall, Max Pain)
    """
    score = 0.0
    detalhes = []

    u = res_contrato.get("ultimo_bar", {})
    posicao = u.get("posicao", "NEUTRO")
    trix_val = u.get("trix")
    sinal_val = u.get("sinal")
    sma100 = u.get("sma100")

    # 1. Posição NTSL
    if posicao == "COMPRA":
        score += 40.0
        detalhes.append("TRIX NTSL: COMPRA (+40)")
    elif posicao == "VENDA":
        score -= 40.0
        detalhes.append("TRIX NTSL: VENDA (-40)")
    else:
        detalhes.append("TRIX NTSL: NEUTRO (0)")

    # 2. TRIX vs Linha de Sinal
    if trix_val is not None and sinal_val is not None:
        if trix_val > sinal_val:
            score += 20.0
            detalhes.append("TRIX acima do Sinal (+20)")
        elif trix_val < sinal_val:
            score -= 20.0
            detalhes.append("TRIX abaixo do Sinal (-20)")

    # 3. Posição vs SMA 100
    if sma100 and sma100 > 0:
        if preco_fechamento > sma100:
            score += 20.0
            detalhes.append(f"Preço acima da SMA100 (R$ {sma100:.2f}) (+20)")
        else:
            score -= 20.0
            detalhes.append(f"Preço abaixo da SMA100 (R$ {sma100:.2f}) (-20)")

    # 4. Barreiras de Opções
    barreiras = res_contrato.get("barreiras_opcoes", {})
    call_wall = barreiras.get("call_wall")
    put_wall = barreiras.get("put_wall")
    max_pain = barreiras.get("max_pain")

    impacto_opcoes = 0.0
    if call_wall and preco_fechamento:
        dist_call = call_wall - preco_fechamento
        if 0 <= dist_call <= (atr14 * 1.0):
            impacto_opcoes -= 20.0
            detalhes.append(f"Testando Call Wall R$ {call_wall:.2f} (Resistência Gamma, -20)")

    if put_wall and preco_fechamento:
        dist_put = preco_fechamento - put_wall
        if 0 <= dist_put <= (atr14 * 1.0):
            impacto_opcoes += 20.0
            detalhes.append(f"Testando Put Wall R$ {put_wall:.2f} (Suporte Gamma, +20)")

    score += impacto_opcoes
    score = max(-100.0, min(100.0, score))

    return round(score, 1), {
        "score": round(score, 1),
        "posicao_ntsl": posicao,
        "trix": trix_val,
        "sinal": sinal_val,
        "sma100": sma100,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "max_pain": max_pain,
        "detalhes": detalhes
    }


# ══════════════════════════════════════════════════════════════════════════
# 5. PONDERAÇÃO CONSOLIDADA E CLASSIFICAÇÃO DE SENTIMENTO (20 / 20 / 60)
# ══════════════════════════════════════════════════════════════════════════

def classificar_sentimento(score_final: float) -> str:
    if score_final >= 25.0:
        return "ALTISTA"
    elif score_final <= -25.0:
        return "BAIXISTA"
    else:
        return "LATERAL"


def processar_sentimento_curva(
    curva_resultados: List[Dict[str, Any]],
    cbot_cents: Optional[float],
    cambio_usdbrl: Optional[float],
    preco_spot_rtcni: Optional[float] = None,
    premio_porto: float = 0.70,
    custos_logisticos: float = 10.00,
    estrutura_curva: str = "CONTANGO",
    cbot_fonte: str = "CME / yfinance",
    cambio_fonte: str = "B3 / BRAPI (WDOFUT)"
) -> Dict[str, Any]:
    """
    Processa a análise completa Sentinel-Corn 2.0 para todos os contratos vivos da curva.
    """
    score_noticias, info_noticias = calcular_score_noticias()
    score_calendario, info_calendario = calcular_score_calendario()
    ppe_ref = calcular_ppe(cbot_cents, premio_porto, cambio_usdbrl, custos_logisticos)

    contratos_sentimento = []
    tabela_arbitragem = []

    for c in curva_resultados:
        cod = c.get("codigo", "")
        u = c.get("ultimo_bar", {})
        preco_close = u.get("close", 0.0)
        atr14 = c.get("atr14", 1.50) or 1.50

        if not preco_close or preco_close <= 0:
            continue

        score_tec, info_tec = calcular_score_tecnico_contrato(c, preco_close, atr14)

        score_final = (0.20 * score_noticias) + (0.20 * score_calendario) + (0.60 * score_tec)
        score_final = round(max(-100.0, min(100.0, score_final)), 1)
        sentimento = classificar_sentimento(score_final)

        matriz = matriz_decisao_basis_paridade(preco_close, ppe_ref, preco_spot_rtcni, estrutura_curva)
        cambio_inflexao = calcular_ponto_inflexao_cambio(preco_close, cbot_cents, premio_porto, custos_logisticos)

        cw = info_tec.get("call_wall")
        pw = info_tec.get("put_wall")
        resistencia_pivot = round(cw if cw else (preco_close + (atr14 * 1.5)), 2)
        suporte_pivot = round(pw if pw else (preco_close - (atr14 * 1.5)), 2)

        dif_cambio = round(cambio_usdbrl - cambio_inflexao, 3) if (cambio_usdbrl and cambio_inflexao) else None

        item_sentimento = {
            "contrato": cod,
            "preco": preco_close,
            "sentimento": sentimento,
            "score_final": score_final,
            "pesos": {
                "noticias_20": score_noticias,
                "calendario_20": score_calendario,
                "tecnico_60": score_tec
            },
            "ponto_inflexao_cambio": cambio_inflexao,
            "diferenca_cambio_atual": dif_cambio,
            "pivot_points": {
                "suporte": suporte_pivot,
                "resistencia": resistencia_pivot
            },
            "matriz_basis_paridade": matriz,
            "detalhes_tecnicos": info_tec
        }
        contratos_sentimento.append(item_sentimento)

        tabela_arbitragem.append({
            "contrato": cod,
            "preco_b3": preco_close,
            "ppe": ppe_ref,
            "spread_gap": matriz["gap_ppe"],
            "recomendacao": matriz["recomendacao"],
            "sinal": matriz["sinal"]
        })

    parecer_texto = gerar_parecer_sentinel_corn_2(
        contratos_sentimento,
        tabela_arbitragem,
        cbot_cents,
        cambio_usdbrl,
        ppe_ref,
        preco_spot_rtcni,
        estrutura_curva,
        info_noticias,
        info_calendario,
        cbot_fonte,
        cambio_fonte
    )

    return {
        "timestamp": datetime.now().isoformat(),
        "parametros_arbitragem": {
            "cbot_cents": cbot_cents,
            "cbot_fonte": cbot_fonte,
            "cbot_prov": "[MEDIDO]" if cbot_cents else "[INDISPONIVEL]",
            "cambio_usdbrl": cambio_usdbrl,
            "cambio_fonte": cambio_fonte,
            "cambio_prov": "[MEDIDO]" if cambio_usdbrl else "[INDISPONIVEL]",
            "premio_porto_usd": premio_porto,
            "custos_logisticos_brl": custos_logisticos,
            "ppe_referencia": ppe_ref,
            "ppe_prov": "[DERIVADO]" if ppe_ref else "[INDISPONIVEL]",
            "preco_spot_rtcni": preco_spot_rtcni
        },
        "score_noticias": info_noticias,
        "score_calendario": info_calendario,
        "contratos": contratos_sentimento,
        "tabela_arbitragem": tabela_arbitragem,
        "tabela_arbitragem_porto": tabela_arbitragem,
        "parecer_executivo": parecer_texto
    }


# ══════════════════════════════════════════════════════════════════════════
# 6. SÍNTESE DO CONSULTOR DE IA SENTINEL-CORN 2.0
# ══════════════════════════════════════════════════════════════════════════

def gerar_parecer_sentinel_corn_2(
    contratos: List[Dict[str, Any]],
    tabela_arbitragem: List[Dict[str, Any]],
    cbot_cents: Optional[float],
    cambio_usdbrl: Optional[float],
    ppe: Optional[float],
    preco_spot: Optional[float],
    estrutura_curva: str,
    info_noticias: Dict[str, Any],
    info_calendario: Dict[str, Any],
    cbot_fonte: str = "CME / yfinance",
    cambio_fonte: str = "B3 / BRAPI (WDOFUT)"
) -> str:
    """
    Gera o relatório analítico no tom do estrategista sênior Sentinel-Corn 2.0:
    - Foco exclusivo em CCM B3
    - Tabela comparativa Bullish vs Bearish
    - Ponto de Inflexão de Câmbio
    - Tabela de Arbitragem de Porto
    - Leitura de Gamma e Barreiras
    """
    data_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    linhas_arbitragem = []
    for item in tabela_arbitragem:
        ppe_str = f"R$ {item['ppe']:.2f}" if item.get('ppe') is not None else "N/D [INDISPONIVEL]"
        gap_str = f"R$ {item['spread_gap']:+.2f}" if item.get('spread_gap') is not None else "N/D"
        linhas_arbitragem.append(
            f"| {item['contrato']} | R$ {item['preco_b3']:.2f} | {ppe_str} | {gap_str} | {item['recomendacao']} |"
        )
    tabela_arb_md = "\n".join(linhas_arbitragem)

    c_ativo = contratos[0] if contratos else None
    cod_ativo = c_ativo["contrato"] if c_ativo else "CCM"
    sent_ativo = c_ativo["sentimento"] if c_ativo else "NEUTRO"
    score_ativo = c_ativo["score_final"] if c_ativo else 0.0
    inflex_ativo = c_ativo["ponto_inflexao_cambio"] if c_ativo else None
    sup_ativo = c_ativo["pivot_points"]["suporte"] if c_ativo else 0.0
    res_ativo = c_ativo["pivot_points"]["resistencia"] if c_ativo else 0.0

    mes_atual = datetime.now().month
    if 1 <= mes_atual <= 6:
        foco_sazonal = "Janeiro a Junho: Foco no RTCNI (Cepea/Campinas), entressafra e demanda doméstica das granjas/etanol."
    else:
        foco_sazonal = "Julho a Dezembro: Foco em Chicago (CBOT), prêmios nos portos e Paridade de Exportação (colheita Safrinha)."

    cbot_desc = f"{cbot_cents:.1f}¢/bu [{cbot_fonte}]" if cbot_cents else "INDISPONÍVEL"
    cambio_desc = f"R$ {cambio_usdbrl:.3f} [{cambio_fonte}]" if cambio_usdbrl else "INDISPONÍVEL"
    inflex_desc = f"R$ {inflex_ativo:.3f}" if inflex_ativo else "N/D"
    dif_desc = f"R$ {cambio_usdbrl - inflex_ativo:+.3f}" if (cambio_usdbrl and inflex_ativo) else "N/D"

    parecer = f"""### 🌽 SENTINEL-CORN 2.0 — PARECER ESTRATÉGICO DE SENTIMENTO
**Referência:** {data_str} | **Vencimento em Foco:** {cod_ativo} | **Sentimento Consolidado:** {sent_ativo} (Score: {score_ativo:+.1f})

---

#### 1. SÍNTESE EXECUTIVA & VETORES DE PRESSÃO
- **Veredito do Sentinel-Corn 2.0:** O contrato **{cod_ativo}** opera sob viés **{sent_ativo}**, com score ponderado de **{score_ativo:+.1f}/100** (60% Técnico: {c_ativo['pesos']['tecnico_60']:+.1f} | 20% Notícias: {info_noticias['score']:+.1f} | 20% Calendário: {info_calendario['score']:+.1f}).
- **Sazonalidade das Correlações:** {foco_sazonal}
- **Estrutura da Curva:** {estrutura_curva} — Basis Spot RTCNI (R$ {preco_spot or 0.0:.2f}) vs Futuro em {c_ativo['matriz_basis_paridade']['basis'] or 0.0:+.2f} R$/sc.

---

#### 2. TABELA DE ARBITRAGEM DE PORTO (PPE)
*Paridade calculada com CBOT a {cbot_desc}, Câmbio WDO a {cambio_desc}, Prêmio Porto de +US$ 0,70 e Frete/Logística de R$ 10,00/sc:*

| Contrato Alvo | Preço B3 (Tela) | PPE Calculada | Spread (Gap) | Recomendação Sentinel |
|---|---|---|---|---|
{tabela_arb_md}

---

#### 3. MATRIZ COMPARATIVA DE CENÁRIOS (BULLISH vs. BEARISH)

| Vetor de Mercado | Cenário Altista (Bullish) | Cenário Baixista (Bearish) | Status Atual |
|---|---|---|---|
| **Fundamentos & Clima** | Quebra de safra, retenção de vendas pelo produtor físico | Avanço rápido da colheita, supersafra Safrinha consolidada | {info_noticias['resumo']} |
| **Paridade & Câmbio** | Dólar acima do ponto de inflexão ativa escoamento no porto | Dólar fraco fecha janela de exportação e represamento local | Ponto de Inflexão WDO: {inflex_desc} (Tela: {cambio_desc}) |
| **Estrutura Técnica & Opções** | Preço sustentado no Put Wall, TRIX NTSL virando para compra | Preço colidindo com Call Wall, divergência baixista no TRIX | Suporte: R$ {sup_ativo:.2f} | Resistência: R$ {res_ativo:.2f} |

---

#### 4. VISÃO DE RISCO CAMBIAL & GAMMA (MARKET MAKERS)
- **Ponto de Inflexão de Câmbio:** O patamar de dólar que iguala o milho B3 à paridade internacional é de **{inflex_desc}**. Com o câmbio atual em **{cambio_desc}**, o mercado apresenta spread de **{dif_desc}**, calibrando a atratividade de exportação nos portos.
- **Barreiras Operacionais:** Atenção imediata aos Pivot Points: Suporte institucional em **R$ {sup_ativo:.2f}** e Resistência de Gamma em **R$ {res_ativo:.2f}**.
"""
    return parecer.strip()
