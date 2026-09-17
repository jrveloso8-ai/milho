# -*- coding: utf-8 -*-
"""
brapi_milho.py — Módulo de coleta via API BRAPI (plano Pro)
Projeto: Milho Trader (GPM v2.0) — Fase 3B

SUBSTITUI, quando integrado ao pipeline.py:
  - CCMFUT_F_0_Diário.csv (contrato contínuo)
  - CCM*.csv (contratos por vencimento — curva)
  - DI1F27_F_0_Diário.csv
  - DI1F29_F_0_Diário.csv
  - WDOFUT_F_0_Diário.csv
  - Cálculo manual/estimado de Call Wall, Put Wall (oi_opcoes) — agora com
    Open Interest REAL por strike, confirmado via e-mail da BRAPI em
    27/Ago/2026 (endpoint /v2/futures/options/positions entrou em produção).

NÃO SUBSTITUI (continuam na fonte atual):
  - RTCNI (ESALQ) — índice físico, fora do escopo da BRAPI
  - DOLINDEX (DXY), ZC Chicago, Brent — mercado americano, fora do escopo da BRAPI
  - Frete ESALQ-LOG, COT CFTC, CONAB, WASDE
  - Max Pain — NÃO implementado ainda (requer somar valor intrínseco de
    todas as séries por strike hipotético; deixado como próximo passo)

✅ VALIDAÇÃO CONFIRMADA (via requests puro, rodado por Duda em 27/Ago/2026):
- /v2/futures/term-structure?asset=CCM — chave real "contracts", já com
  cotação EOD embutida (close/settlement/volume/expirationDate).
- /v2/futures/term-structure?asset=WDO — mesmo formato, usado pro câmbio.
- /v2/futures/quote?symbols=DI1F27,DI1F29 — chave real "quotes"/"results",
  settlementRate correto pros dois.
- /v2/futures/list?asset=CCM|WDO — chave real "futures" (NÃO "contracts"
  nem "results" como eu tinha assumido antes). Esse endpoint não é mais
  usado neste módulo (term-structure é mais direto), mas fica documentado
  aqui caso seja útil depois.
- /v2/futures/options/positions?underlying=CCM — confirmado por e-mail
  oficial da BRAPI e testado ao vivo (82 séries CCMU26 com OI real).

ATENÇÃO — pontos que NÃO são bug, são características do dado real:
- openInterestDate pode ficar defasado por série (vi séries com apuração
  de até 50 dias atrás dentro do mesmo lote). O filtro max_dias_defasagem
  em coletar_open_interest_ccm() descarta séries velhas antes de calcular
  as walls — não remova esse filtro.
- Como o milho tem baixa liquidez em opções, Call Wall/Put Wall por OI
  GLOBAL pode cair muito longe do preço (hedge estrutural de exportador).
  Por isso o cálculo de curto prazo considera só as N strikes mais
  próximas do preço atual (n_proximos, default 3) — ver ressalva sobre
  espaçamento desigual de strikes no código de coletar_open_interest_ccm().

Uso:
    export BRAPI_TOKEN="seu_token_aqui"
    python brapi_milho.py
"""

import os
import sys
import json
import requests
from datetime import datetime

DEBUG = True
BASE_URL = "https://brapi.dev/api"
TOKEN = os.environ.get("BRAPI_TOKEN")

if not TOKEN:
    print("ERRO: variável de ambiente BRAPI_TOKEN não definida.")
    print('Rode: export BRAPI_TOKEN="seu_token_aqui" (Linux/Mac)')
    print('  ou: set BRAPI_TOKEN=seu_token_aqui (Windows CMD)')
    sys.exit(1)

HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def _get(path, params=None):
    """GET genérico com tratamento de erro e log de debug."""
    url = f"{BASE_URL}{path}"
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if DEBUG:
            print(f"[GET] {resp.url} -> {resp.status_code}")
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        print(f"ERRO HTTP em {url}: {e}")
        print(f"Resposta: {resp.text[:500]}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"ERRO DE CONEXÃO em {url}: {e}")
        return None


def estrutura_a_termo(asset, incluir_expirados=False):
    """
    Endpoint CONFIRMADO em 27/Ago/2026 via diag_brapi.py rodado por Duda:
    GET /v2/futures/term-structure?asset=CCM
    Resposta real: {"asset": "CCM", "contracts": [ {..., "close":, "settlement":,
    "volume":, "expirationDate":, ...} ]}, já ordenado por vencimento ascendente
    e já com cotação EOD embutida — dispensa chamada separada de /quote e /specs.

    NOTA: /v2/futures/list também foi confirmado, mas sua chave real é
    "futures" (não "contracts" nem "results" como eu tinha assumido antes).
    Usamos term-structure aqui porque entrega tudo em 1 chamada só.
    """
    data = _get("/v2/futures/term-structure", params={
        "asset": asset,
        "includeExpired": "true" if incluir_expirados else "false",
    })
    if not data:
        return []
    return data.get("contracts") or []


def montar_curva_ccm():
    """
    Monta o bloco 'curva_vencimentos' + 'ccm' (contrato mais próximo do
    vencimento) do schema dados_milho.json, direto da BRAPI — 1 chamada.
    """
    contratos = estrutura_a_termo("CCM")
    if not contratos:
        print("AVISO: nenhum contrato CCM ativo retornado pela BRAPI.")
        return None, []

    curva = []
    anterior = None
    for c in contratos:
        preco = c.get("close") if c.get("close") is not None else c.get("settlement")
        spread = round(preco - anterior, 2) if (anterior is not None and preco is not None) else None
        curva.append({
            "contrato": c["symbol"],
            "vencimento": c.get("expirationDate", ""),
            "preco": preco,
            "volume": c.get("volume"),
            "spread_vs_anterior": spread,
        })
        anterior = preco

    # Contrato ativo = MAIOR VOLUME na curva, não necessariamente o mais
    # próximo do vencimento. Corrigido em 27/Ago/2026 com base em dado real:
    # CCMU26 (vencimento mais próximo) teve volume 5.975, enquanto CCMX26
    # (segundo vencimento) teve 7.927 — mais líquido, provavelmente por
    # estarmos perto do rollover do primeiro contrato. Escolher por
    # vencimento mais próximo estaria pegando o contrato errado agora.
    contratos_com_volume = [c for c in curva if c.get("volume") is not None]
    if contratos_com_volume:
        contrato_mais_liquido = max(contratos_com_volume, key=lambda c: c["volume"])
        vencimento_ativo = contrato_mais_liquido["contrato"]
    else:
        vencimento_ativo = curva[0]["contrato"] if curva else None

    return vencimento_ativo, curva


def cotacao_futuros(symbols):
    """
    Cotação EOD para uma lista de símbolos específicos (máx 20 por chamada).
    CONFIRMADO funcionando em produção (testado por Duda com DI1F27,DI1F29
    em 27/Ago/2026 — retornou settlementRate correto pros dois).
    """
    if not symbols:
        return []
    data = _get("/v2/futures/quote", params={"symbols": ",".join(symbols)})
    if not data:
        return []
    return data.get("quotes") or data.get("results") or []


def coletar_di():
    """DI1F27 e DI1F29 — custo de carrego e estrutura a termo."""
    data = cotacao_futuros(["DI1F27", "DI1F29"])
    resultado = {}
    for item in data:
        if item["symbol"] == "DI1F27":
            resultado["di1f27_taxa"] = item.get("settlementRate")
        elif item["symbol"] == "DI1F29":
            resultado["di1f29_taxa"] = item.get("settlementRate")
    return resultado


def coletar_cambio():
    """
    WDOFUT — usa o mesmo endpoint term-structure já confirmado para CCM.
    O contrato vigente (mais próximo do vencimento) vem em contratos[0].
    Settlement já vem no formato R$/1000 USD, igual ao CSV atual —
    confirmado no lote de dados reais coletado em 27/Ago/2026 (WDOU26
    settlement 5.158,22).
    """
    contratos = estrutura_a_termo("WDO")
    if not contratos:
        print("AVISO: nenhum contrato WDO retornado pela BRAPI.")
        return {}
    c = contratos[0]
    settlement = c.get("settlement")
    return {
        "wdofut": settlement,
        "wdofut_symbol": c.get("symbol"),
        "wdofut_usdbrl": round(settlement / 1000, 4) if settlement else None,
        "variacao_semanal_pct": c.get("oscillationPct"),
    }


def coletar_open_interest_ccm(vencimento, preco_atual, max_dias_defasagem=5,
                               n_proximos=3, largura_janela_reais=3.0):
    """
    Busca Open Interest real por strike (endpoint confirmado por e-mail da BRAPI
    em 27/Ago/2026: /v2/futures/options/positions?underlying=CCM).

    Filtra séries com apuração (openInterestDate) mais antiga que
    max_dias_defasagem dias em relação à data mais recente do lote — evita
    contaminar o cálculo com OI zumbi de séries não atualizadas.

    MUDANÇA DE MÉTODO (27/Ago/2026, com base em teste real):
    O critério original de "N strikes mais próximas por contagem" (n_proximos)
    foi testado ao vivo e se mostrou pouco informativo: como o milho tem baixa
    liquidez em opções e strikes desigualmente espaçados, o resultado quase
    sempre cai no strike ATM (que está sempre entre os N mais próximos),
    escondendo concentrações reais de OI um pouco mais distantes. Exemplo real
    do primeiro teste: janela por contagem escolheu Put Wall em 72,00 (130
    contratos) enquanto o strike 71,00, fora da janela por 1 posição, tinha
    2.923 contratos.

    Por isso o método PRINCIPAL agora é janela por DISTÂNCIA EM R$/sc
    (largura_janela_reais, default ±3,00) — mais robusto a espaçamento
    desigual. O critério por contagem (n_proximos) é mantido apenas como
    informação secundária para comparação, não como wall principal.

    Retorna:
    1. 'visao_geral' — todas as séries válidas, para contexto completo.
    2. 'call_wall_janela' / 'put_wall_janela' — MÉTODO PRINCIPAL: maior OI
       dentro de ±largura_janela_reais do preço atual.
    3. 'call_wall_n_proximos' / 'put_wall_n_proximos' — método por contagem
       fixa, mantido só para comparação/diagnóstico.
    4. 'call_wall_global' / 'put_wall_global' — maior OI absoluto,
       independente da distância (leitura estrutural, ex. hedge de
       exportador muito OTM — não confundir com curto prazo).
    """
    data = _get("/v2/futures/options/positions", params={
        "underlying": "CCM",
        "expirationDate": vencimento,
    })
    if not data:
        return None

    posicoes = data.get("positions") or []
    if not posicoes:
        return None

    datas_validas = [p["openInterestDate"] for p in posicoes if p.get("openInterestDate")]
    if not datas_validas:
        return None
    data_referencia = max(datas_validas)
    data_ref_dt = datetime.strptime(data_referencia, "%Y-%m-%d")

    def defasagem_ok(p):
        d = p.get("openInterestDate")
        if not d:
            return False
        dt = datetime.strptime(d, "%Y-%m-%d")
        return (data_ref_dt - dt).days <= max_dias_defasagem

    posicoes_validas = [p for p in posicoes if defasagem_ok(p)]

    calls = sorted(
        [p for p in posicoes_validas if p["optionType"] == "call"],
        key=lambda p: p["strike"]
    )
    puts = sorted(
        [p for p in posicoes_validas if p["optionType"] == "put"],
        key=lambda p: p["strike"]
    )

    def resumo_serie(p):
        dist_pct = round((p["strike"] - preco_atual) / preco_atual * 100, 1) if preco_atual else None
        return {
            "strike": p["strike"],
            "open_interest": p["openInterest"],
            "distancia_pct": dist_pct,
            "data_apuracao": p["openInterestDate"],
        }

    visao_geral = {
        "calls": [resumo_serie(p) for p in calls],
        "puts": [resumo_serie(p) for p in puts],
    }

    # --- Global (maior OI absoluto, qualquer distância) ---
    call_wall_global = max(calls, key=lambda p: p["openInterest"], default=None)
    put_wall_global = max(puts, key=lambda p: p["openInterest"], default=None)

    # --- MÉTODO PRINCIPAL: janela por distância em R$/sc ---
    def dentro_da_janela(lista):
        if not preco_atual:
            return []
        return [p for p in lista if abs(p["strike"] - preco_atual) <= largura_janela_reais]

    calls_janela = dentro_da_janela(calls)
    puts_janela = dentro_da_janela(puts)

    call_wall_janela = max(calls_janela, key=lambda p: p["openInterest"], default=None)
    put_wall_janela = max(puts_janela, key=lambda p: p["openInterest"], default=None)

    # Sinalizador de confiança: janela com poucos strikes ou OI total baixo
    # não deve ser lida como "wall" com a mesma força que uma janela densa.
    # Limiares abaixo são um primeiro corte razoável, não uma verdade
    # absoluta — ajustar se, na prática, gerar falso-positivo/negativo.
    def avaliar_confianca(strikes_na_janela, min_strikes=5, min_oi_total=1000):
        oi_total = sum(p["openInterest"] for p in strikes_na_janela)
        motivos = []
        if len(strikes_na_janela) < min_strikes:
            motivos.append(f"apenas {len(strikes_na_janela)} strikes na janela (mínimo esperado: {min_strikes})")
        if oi_total < min_oi_total:
            motivos.append(f"OI total na janela é {oi_total} (mínimo esperado: {min_oi_total})")
        return {
            "confiavel": len(motivos) == 0,
            "oi_total_janela": oi_total,
            "motivos": motivos,
        }

    confianca_call = avaliar_confianca(calls_janela)
    confianca_put = avaliar_confianca(puts_janela)

    def montar_leitura_final(wall_janela, confianca, wall_global, lado):
        """
        Decide o que o relatório deve reportar como referência de curto prazo:
        - Se a janela é confiável: usa a wall da janela, status 'tatico_confiavel'.
        - Se não é confiável: NÃO promove a wall fraca da janela como se fosse
          um nível forte. Cai para o global como contexto, mas com status
          'inconclusivo_curto_prazo' e a ressalva explícita de distância —
          isso deve ser reportado como "sem nível tático claro", não omitido
          nem apresentado com a mesma confiança de um caso normal.
        """
        if confianca["confiavel"]:
            return {
                "status": "tatico_confiavel",
                "referencia": wall_janela,
                "nota": None,
            }
        else:
            return {
                "status": "inconclusivo_curto_prazo",
                "referencia": wall_global,
                "nota": (
                    f"Sem concentração de OI confiável perto do preço para {lado} "
                    f"(motivos: {'; '.join(confianca['motivos'])}). "
                    f"Referência mais próxima disponível é o nível global "
                    f"({wall_global['strike'] if wall_global else 'N/A'}, "
                    f"a {wall_global['distancia_pct'] if wall_global else '?'}% do preço) "
                    f"— tratar como contexto estrutural, não como nível tático de curto prazo."
                ),
            }

    leitura_call = montar_leitura_final(
        resumo_serie(call_wall_janela) if call_wall_janela else None,
        confianca_call,
        resumo_serie(call_wall_global) if call_wall_global else None,
        "calls",
    )
    leitura_put = montar_leitura_final(
        resumo_serie(put_wall_janela) if put_wall_janela else None,
        confianca_put,
        resumo_serie(put_wall_global) if put_wall_global else None,
        "puts",
    )

    # --- Secundário: N mais próximos por contagem (mantido para comparação) ---
    def n_mais_proximos(lista, n):
        if not preco_atual:
            return []
        return sorted(lista, key=lambda p: abs(p["strike"] - preco_atual))[:n]

    calls_proximos = n_mais_proximos(calls, n_proximos)
    puts_proximos = n_mais_proximos(puts, n_proximos)
    call_wall_n = max(calls_proximos, key=lambda p: p["openInterest"], default=None)
    put_wall_n = max(puts_proximos, key=lambda p: p["openInterest"], default=None)

    return {
        "data_referencia_lote": data_referencia,
        "series_total": len(posicoes),
        "series_validas": len(posicoes_validas),
        "visao_geral": visao_geral,
        "leitura_final_call": leitura_call,
        "leitura_final_put": leitura_put,
        "call_wall_global": resumo_serie(call_wall_global) if call_wall_global else None,
        "put_wall_global": resumo_serie(put_wall_global) if put_wall_global else None,
        "call_wall_janela": {
            "largura_reais": largura_janela_reais,
            "strikes_considerados": [resumo_serie(p) for p in calls_janela],
            "wall": resumo_serie(call_wall_janela) if call_wall_janela else None,
            "confianca": confianca_call,
        },
        "put_wall_janela": {
            "largura_reais": largura_janela_reais,
            "strikes_considerados": [resumo_serie(p) for p in puts_janela],
            "wall": resumo_serie(put_wall_janela) if put_wall_janela else None,
            "confianca": confianca_put,
        },
        "call_wall_n_proximos": {
            "n": n_proximos,
            "strikes_considerados": [resumo_serie(p) for p in calls_proximos],
            "wall": resumo_serie(call_wall_n) if call_wall_n else None,
        },
        "put_wall_n_proximos": {
            "n": n_proximos,
            "strikes_considerados": [resumo_serie(p) for p in puts_proximos],
            "wall": resumo_serie(put_wall_n) if put_wall_n else None,
        },
    }


def montar_bloco_brapi():
    """Monta o subconjunto do schema dados_milho.json coberto pela BRAPI."""
    vencimento_ativo, curva = montar_curva_ccm()
    carrego = coletar_di()
    cambio = coletar_cambio()

    ccm_atual = next((c for c in curva if c["contrato"] == vencimento_ativo), {})

    # Vencimento de opções correspondente ao contrato ativo (mesma data, padrão B3)
    vencimento_opcoes = ccm_atual.get("vencimento")
    oi_opcoes = None
    if vencimento_opcoes and ccm_atual.get("preco"):
        oi_opcoes = coletar_open_interest_ccm(vencimento_opcoes, ccm_atual["preco"])

    bloco = {
        "data_coleta": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "fonte": "BRAPI (plano Pro)",
        "ccm": {
            "vencimento_ativo": vencimento_ativo,
            "ultimo_preco": ccm_atual.get("preco"),
        },
        "curva_vencimentos": curva,
        "carrego": carrego,
        "cambio": cambio,
        "oi_opcoes": oi_opcoes,
    }
    return bloco


def mesclar_com_dados_milho_json(bloco, caminho_json):
    """
    Mescla o bloco coletado da BRAPI com o dados_milho.json existente,
    SEM sobrescrever os campos vindos de outras fontes (RTCNI, ZC, Brent, DXY,
    fundamentos, sazonalidade, etc.) que continuam alimentados manualmente.
    """
    if os.path.exists(caminho_json):
        with open(caminho_json, "r", encoding="utf-8") as f:
            dados = json.load(f)
    else:
        dados = {}

    # Merge raso por chave de topo — ajustar conforme necessidade de nested merge
    dados.setdefault("ccm", {}).update(bloco["ccm"])
    dados["curva_vencimentos"] = bloco["curva_vencimentos"]
    dados.setdefault("carrego", {}).update(bloco["carrego"])
    dados.setdefault("cambio", {}).update(bloco["cambio"])
    if bloco.get("oi_opcoes"):
        dados.setdefault("oi_opcoes", {}).update(bloco["oi_opcoes"])
    dados["_brapi_ultima_coleta"] = bloco["data_coleta"]

    with open(caminho_json, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    print(f"dados_milho.json atualizado com bloco BRAPI em {caminho_json}")


if __name__ == "__main__":
    # PASTA_DADOS deve ser importado/definido igual ao resto do pipeline
    PASTA_DADOS = os.environ.get("PASTA_DADOS", r"C:\Projetos Phyton\Milho")
    caminho_saida = os.path.join(PASTA_DADOS, "dados_milho.json")

    print("=== Coletando dados via BRAPI ===")
    bloco = montar_bloco_brapi()
    print(json.dumps(bloco, ensure_ascii=False, indent=2))

    resposta = input(f"\nMesclar com {caminho_saida}? (s/n): ")
    if resposta.strip().lower() == "s":
        mesclar_com_dados_milho_json(bloco, caminho_saida)
    else:
        print("Não mesclado. Bloco impresso acima para conferência manual.")
