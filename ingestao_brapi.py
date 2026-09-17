# -*- coding: utf-8 -*-
"""
ingestao_brapi.py — Camada de ingestão via BRAPI para o pipeline Milho Trader.
Criado em 01/09/2026 — Etapa 1 da reestruturação de dados (seção 4.1 do
documento Agro Intelligence B2B).

Biblioteca pura: nenhuma função faz I/O de arquivo, imprime menu ou chama
input() (ao contrário de brapi_milho.py, que é um script manual de
conferência e NÃO é importado aqui — ele verifica BRAPI_TOKEN no nível do
módulo e derruba o processo com sys.exit(1) se ausente, o que é incompatível
com o padrão defensivo do pipeline). Cada função de coleta retorna dict/tupla
ou None em falha — dado ausente não trava a rodada, mesma convenção do resto
do projeto.

Escopo confirmado com o usuário (sessão de 01/09/2026):
  - Câmbio (WDOFUT), DI futuro (DI1F27/DI1F29), curva de vencimentos CCM:
    MODO SOMBRA por enquanto — pipeline.py roda isso em paralelo ao legado
    (leitor_csv/cambio_macro) e só LOGA divergência, não substitui.
  - Open Interest de opções (Call Wall/Put Wall/Max Pain): SUBSTITUIÇÃO
    DIRETA do CCM_OP.xlsx manual. Decidido pelo usuário porque a grade
    manual tinha ~53% dos tickers mal interpretados por fórmula quebrada no
    Excel (ver cabeçalho de oi_opcoes.py) — a BRAPI fornece OI real por
    strike, dado estritamente melhor. Reaproveita calcular_wall() e
    calcular_max_pain() de oi_opcoes.py sem alteração (são funções puras,
    agnósticas de fonte) — só a origem do dado de entrada muda.

NÃO cobre (fora do escopo da BRAPI, confirmado em sessão anterior): RTCNI,
DXY, ZC Chicago, Brent, WASDE, CONAB. Continuam via cambio_macro.py /
leitor_csv.py manual — permanente, não é fallback temporário (a BRAPI não
tem esses dados em nenhum plano).

Profundidade histórica: confirmado em sessão anterior que a BRAPI não cobre
a janela de 2 anos usada no backtest atual (~14-15 meses de teto, testado ao
vivo). Este módulo cobre só a coleta do dia corrente — não serve para
reconstruir série histórica de validação.
"""

import os
from datetime import datetime

import requests

from oi_opcoes import calcular_wall, calcular_max_pain, OI_VAZIO

BASE_URL = "https://brapi.dev/api"


def token_disponivel() -> bool:
    """Permite ao pipeline logar 'BRAPI_TOKEN ausente' uma vez, de forma
    explícita, em vez de deduzir isso de uma cascata de None."""
    return bool(os.environ.get("BRAPI_TOKEN"))


def _headers():
    token = os.environ.get("BRAPI_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else None


def _get(path, params=None):
    """GET genérico. Retorna None (nunca lança) se token ausente, erro HTTP
    ou erro de conexão."""
    headers = _headers()
    if headers is None:
        return None
    try:
        resp = requests.get(f"{BASE_URL}{path}", headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException:
        return None


# ══════════════════════════════════════════════════════════════════════════
# CÂMBIO E DI — MODO SOMBRA (pipeline.py compara contra o legado, não substitui)
# ══════════════════════════════════════════════════════════════════════════

def coletar_cambio() -> dict:
    """
    WDOFUT — contrato vigente (mais próximo do vencimento, primeiro item da
    curva). Settlement já vem em R$/1000 USD, mesmo formato do CSV legado
    (confirmado em sessão anterior com dado real: WDOU26 settlement 5.158,22).
    Retorna None se a BRAPI não responder ou não tiver contrato WDO ativo.
    """
    data = _get("/v2/futures/term-structure", params={"asset": "WDO", "includeExpired": "false"})
    contratos = (data or {}).get("contracts") or []
    if not contratos:
        return None
    c = contratos[0]
    settlement = c.get("settlement")
    return {
        "wdofut": settlement,
        "wdofut_symbol": c.get("symbol"),
        "wdofut_usdbrl": round(settlement / 1000, 4) if settlement else None,
        "variacao_semanal_pct": c.get("oscillationPct"),
    }


def coletar_di() -> dict:
    """
    DI1F27 e DI1F29 — settlementRate já em %a.a., mesma unidade do
    Close do CSV legado (confirmado empiricamente em 01/09/2026: BRAPI
    retornou 13,613 vs. 13,71 do CSV alguns dias antes — mesma ordem de
    grandeza, sem fator de conversão pendente).
    """
    data = _get("/v2/futures/quote", params={"symbols": "DI1F27,DI1F29"})
    quotes = (data or {}).get("quotes") or (data or {}).get("results") or []
    if not quotes:
        return None
    resultado = {"di1f27_taxa": None, "di1f29_taxa": None}
    for item in quotes:
        if item.get("symbol") == "DI1F27":
            resultado["di1f27_taxa"] = item.get("settlementRate")
        elif item.get("symbol") == "DI1F29":
            resultado["di1f29_taxa"] = item.get("settlementRate")
    return resultado


def coletar_curva_ccm() -> dict:
    """
    Curva completa de vencimentos vivos do CCM.

    ATENÇÃO — 'vencimento_ativo' aqui é escolhido por MAIOR VOLUME do dia,
    critério DIFERENTE do legado (que segue o contrato mais recente ainda
    não vencido no CCMFUT contínuo exportado do Profit). Os dois podem
    apontar para contratos diferentes perto do rollover — pipeline.py deve
    logar os dois lado a lado no modo sombra, não tratar divergência de
    contrato-ativo como erro de dado.

    Retorna {"vencimento_ativo": str, "curva": [...]} ou None.
    """
    data = _get("/v2/futures/term-structure", params={"asset": "CCM", "includeExpired": "false"})
    contratos = (data or {}).get("contracts") or []
    if not contratos:
        return None

    curva = []
    anterior = None
    for c in contratos:
        preco = c.get("close") if c.get("close") is not None else c.get("settlement")
        spread = round(preco - anterior, 2) if (anterior is not None and preco is not None) else None
        curva.append({
            "contrato":           c["symbol"],
            "vencimento_iso":     c.get("expirationDate", ""),
            "preco":              preco,
            "volume":             c.get("volume"),
            "spread_vs_anterior": spread,
        })
        anterior = preco

    com_volume = [c for c in curva if c.get("volume") is not None]
    if com_volume:
        vencimento_ativo = max(com_volume, key=lambda c: c["volume"])["contrato"]
    else:
        vencimento_ativo = curva[0]["contrato"] if curva else None

    return {"vencimento_ativo": vencimento_ativo, "curva": curva}


# ══════════════════════════════════════════════════════════════════════════
# OPEN INTEREST DE OPÇÕES — SUBSTITUIÇÃO DIRETA do CCM_OP.xlsx
# ══════════════════════════════════════════════════════════════════════════

def _oi_bruto_por_vencimento(expiration_date_iso: str, max_dias_defasagem: int = 5):
    """
    Busca OI real por strike para um vencimento (a expiração das opções
    acompanha a do futuro subjacente — mesmo padrão validado em sessão
    anterior). Filtra séries com apuração (openInterestDate) mais velha que
    max_dias_defasagem em relação à data mais recente do lote — evita OI
    zumbi de série desatualizada (regra de qualidade obrigatória, seção 4.3
    do documento de arquitetura).

    Retorna (calls: {strike: oi}, puts: {strike: oi}, meta: dict) ou None
    se a BRAPI não retornar posições para esse vencimento.
    """
    data = _get("/v2/futures/options/positions", params={
        "underlying": "CCM",
        "expirationDate": expiration_date_iso,
    })
    posicoes = (data or {}).get("positions") or []
    if not posicoes:
        return None

    datas_validas = [p["openInterestDate"] for p in posicoes if p.get("openInterestDate")]
    if not datas_validas:
        return None
    data_ref = max(datas_validas)
    data_ref_dt = datetime.strptime(data_ref, "%Y-%m-%d")

    def recente(p):
        d = p.get("openInterestDate")
        if not d:
            return False
        return (data_ref_dt - datetime.strptime(d, "%Y-%m-%d")).days <= max_dias_defasagem

    validas = [p for p in posicoes if recente(p)]
    calls, puts = {}, {}
    for p in validas:
        alvo = calls if p.get("optionType") == "call" else puts
        strike = p["strike"]
        alvo[strike] = alvo.get(strike, 0) + p["openInterest"]

    meta = {
        "data_referencia_lote": data_ref,
        "series_total":         len(posicoes),
        "series_validas":       len(validas),
    }
    return calls, puts, meta


def coletar_oi_todos_vencimentos(curva: list) -> dict:
    """
    Busca OI bruto (calls/puts por strike) para CADA contrato vivo da curva,
    UMA vez só por contrato — resultado reaproveitado por montar_oi_opcoes()
    e montar_oi_por_contrato() para não duplicar chamada de API entre os
    dois blocos do pipeline (Etapa 3 e Etapa 3B).

    curva = saída de coletar_curva_ccm()['curva'].
    Retorna {codigo_contrato: {"calls": {...}, "puts": {...}, "meta": {...}}}
    — contratos sem dado de OI disponível ficam com calls/puts vazios, não
    são omitidos da chave (facilita o consumidor saber que a tentativa
    ocorreu e não teve retorno, distinto de 'nunca tentou').
    """
    saida = {}
    for c in curva:
        venc_iso = c.get("vencimento_iso")
        bruto = _oi_bruto_por_vencimento(venc_iso) if venc_iso else None
        if bruto is None:
            saida[c["contrato"]] = {"calls": {}, "puts": {}, "meta": None}
        else:
            calls, puts, meta = bruto
            saida[c["contrato"]] = {"calls": calls, "puts": puts, "meta": meta}
    return saida


def _wall_seguro(dic_oi: dict, preco: float, lado: str):
    """calcular_wall() de oi_opcoes.py assume preco numérico quando dic_oi
    não é vazio — guarda explícita aqui porque este módulo agora é chamado
    de mais de um ponto do pipeline, alguns podendo ter preco_referencia
    ausente (contrato sem candle do dia)."""
    if not dic_oi or preco is None:
        return None
    return calcular_wall(dic_oi, preco, lado)


def montar_oi_opcoes(oi_todos: dict, curva: list, vencimento_ativo: str, preco_atual: float) -> dict:
    """
    Substitui oi_opcoes.analisar_oi_opcoes() — MESMO FORMATO DE SAÍDA
    (drop-in: milho_dashboard.html e o restante do pipeline não precisam
    mudar), mas o OI vem da BRAPI (real, por strike) em vez do CCM_OP.xlsx
    manual. Função pura — não faz I/O; consome o resultado já coletado por
    coletar_oi_todos_vencimentos().

    'grade' = strikes do vencimento ativo (equivalente ao 'vencimento
    exato' do legado). 'grade_agregada' = soma de OI de TODOS os
    vencimentos vivos da curva (equivalente ao 'agregado, todas as
    expirações do arquivo' do legado) — mesma semântica, fonte diferente.
    """
    if not curva or vencimento_ativo not in oi_todos:
        return dict(OI_VAZIO, fonte='BRAPI (vencimento ativo indisponível)')

    contrato_ativo = next((c for c in curva if c["contrato"] == vencimento_ativo), None)
    dado_ativo = oi_todos.get(vencimento_ativo) or {"calls": {}, "puts": {}}
    calls_ativo, puts_ativo = dado_ativo["calls"], dado_ativo["puts"]
    strikes_ativo = sorted(set(list(calls_ativo) + list(puts_ativo)))
    grade = [{'strike': s, 'oi_call': calls_ativo.get(s, 0), 'oi_put': puts_ativo.get(s, 0)} for s in strikes_ativo]

    calls_agg, puts_agg = {}, {}
    expiracoes_com_dado = []
    for codigo, dado in oi_todos.items():
        if not dado["calls"] and not dado["puts"]:
            continue
        expiracoes_com_dado.append(codigo)
        for s, oi in dado["calls"].items():
            calls_agg[s] = calls_agg.get(s, 0) + oi
        for s, oi in dado["puts"].items():
            puts_agg[s] = puts_agg.get(s, 0) + oi
    strikes_agg = sorted(set(list(calls_agg) + list(puts_agg)))
    grade_agregada = [{'strike': s, 'oi_call': calls_agg.get(s, 0), 'oi_put': puts_agg.get(s, 0)} for s in strikes_agg]

    return {
        'call_wall':            _wall_seguro(calls_ativo, preco_atual, 'call'),
        'put_wall':             _wall_seguro(puts_ativo, preco_atual, 'put'),
        'max_pain':             calcular_max_pain(calls_ativo, puts_ativo),
        'call_wall_agregado':   _wall_seguro(calls_agg, preco_atual, 'call'),
        'put_wall_agregado':    _wall_seguro(puts_agg, preco_atual, 'put'),
        'grade_agregada':       grade_agregada,
        'expiracoes_agregadas': expiracoes_com_dado,
        'fonte':                'BRAPI (Open Interest real por strike)',
        'vencimento_opcoes':    contrato_ativo.get("vencimento_iso") if contrato_ativo else None,
        'total_oi_calls':       int(sum(calls_ativo.values())),
        'total_oi_puts':        int(sum(puts_ativo.values())),
        'arquivo':              None,
        'grade':                grade,
    }


def montar_oi_por_contrato(oi_todos: dict, curva: list) -> dict:
    """
    Substitui oi_opcoes.analisar_todas_expiracoes() — uma entrada por
    vencimento vivo, para o seletor de contrato no dashboard. Função pura,
    reaproveita coletar_oi_todos_vencimentos() já executado.

    preco_referencia vem da própria curva da BRAPI (settlement/close do
    dia) — nunca precisa do proxy 'strike central' que o legado usava
    quando faltava o CSV do contrato, porque aqui, se o contrato está na
    curva, o preço já veio junto.
    """
    saida = {}
    for c in curva:
        codigo = c["contrato"]
        preco_ref = c.get("preco")
        dado = oi_todos.get(codigo) or {"calls": {}, "puts": {}}
        calls, puts = dado["calls"], dado["puts"]
        strikes = sorted(set(list(calls) + list(puts)))
        grade = [{'strike': s, 'oi_call': calls.get(s, 0), 'oi_put': puts.get(s, 0)} for s in strikes]

        saida[codigo] = {
            'contrato':          codigo,
            'vencimento_opcoes': c.get("vencimento_iso"),
            'preco_referencia':  preco_ref,
            'preco_estimado':    False,
            'call_wall':         _wall_seguro(calls, preco_ref, 'call'),
            'put_wall':          _wall_seguro(puts, preco_ref, 'put'),
            'max_pain':          calcular_max_pain(calls, puts),
            'total_oi_calls':    int(sum(calls.values())),
            'total_oi_puts':     int(sum(puts.values())),
            'grade':             grade,
        }
    return saida
