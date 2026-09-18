# calendario_economico.py — Milho Trader v1.0 (Fase 3B)
#
# Calendário de divulgações que movem o preço do milho — WASDE/Estoques
# Trimestrais (USDA) e Boletim da Safra de Grãos (CONAB) — com alerta de
# "não operar" no dia da divulgação. Decidido com o usuário em 11/07/2026.
#
# ESCOPO — por que só USDA e CONAB, e por que CEPEA fica de fora:
# WASDE e o Boletim CONAB são divulgações DISCRETAS e AGENDADAS: o mercado
# não sabe o número até a hora H, e a reação de preço costuma ser abrupta
# (gap ou vela fora do padrão) no minuto da divulgação — exatamente o tipo
# de risco que um stop técnico normal (ATR×1,5) não foi desenhado para
# absorver. CEPEA, ao contrário, publica um índice de preço físico DIÁRIO,
# construído a partir de transações já realizadas — não é uma "surpresa"
# pontual, é o mesmo tipo de dado contínuo que já entra no projeto via
# RTCNI. Por isso CEPEA não tem "dia de divulgação" para bloquear; incluí-lo
# aqui seria simular um evento que não existe.
#
# Datas verificadas via web search em 11/07/2026 (não vêm do conhecimento
# de treinamento, que tem corte em mai/2025):
#   - WASDE 2026: calendário oficial USDA/CME Group, sempre 12:00 ET.
#   - Estoques Trimestrais (Grain Stocks) 2026: USDA/NASS, 12:00 ET. Duas
#     datas coincidem com outras divulgações de altíssimo impacto — 12/jan
#     (mesmo dia do WASDE de janeiro + Crop Production anual) e 30/jun
#     (mesmo dia do relatório de Acreage/Área Plantada) — marcadas abaixo
#     com impacto "MAXIMO".
#   - CONAB Boletim da Safra de Grãos 2026: a Conab publica no dia 15 de
#     cada mês (12 levantamentos/ano, confirmado para jan/2026, set/2026 e
#     out/2026 no comunicado oficial). Não consegui abrir o PDF do
#     calendário completo (só o link de download, sem o conteúdo) para
#     confirmar TODAS as 12 datas individualmente — assumi a regra "dia 15,
#     ou o próximo dia útil se cair em fim de semana" para os meses não
#     confirmados. Reconferir contra o calendário oficial da Conab
#     periodicamente (github.com/gov.br/conab) — ver `_CONAB_DIAS_CONFIRMADOS`.

from datetime import date, timedelta

# ── USDA — WASDE (World Agricultural Supply and Demand Estimates) ─────────
# Fonte: CME Group ("Understanding Major USDA Reports in 2026") + calendário
# oficial USDA/NASS. Todos às 12:00 ET.
EVENTOS_WASDE_2026 = [
    date(2026, 1, 12), date(2026, 2, 10), date(2026, 3, 10), date(2026, 4, 9),
    date(2026, 5, 12), date(2026, 6, 11), date(2026, 7, 10), date(2026, 8, 12),
    date(2026, 9, 11), date(2026, 10, 9), date(2026, 11, 10), date(2026, 12, 10),
]

# ── USDA — Grain Stocks (Estoques Trimestrais) ─────────────────────────────
# Fonte: USDA/NASS. 12:00 ET. jan/12 e jun/30 coincidem com outra divulgação
# de altíssimo impacto (Crop Production anual / Acreage) no mesmo dia.
EVENTOS_GRAIN_STOCKS_2026 = {
    date(2026, 1, 12):  'Estoques Trimestrais + Crop Production Anual',
    date(2026, 3, 31):  'Estoques Trimestrais',
    date(2026, 6, 30):  'Estoques Trimestrais + Acreage (Área Plantada)',
    date(2026, 9, 30):  'Estoques Trimestrais',
}

# ── CONAB — Boletim da Safra de Grãos ──────────────────────────────────────
# Regra: dia 15 de cada mês, ajustado para o próximo dia útil se cair em
# fim de semana (mesmo padrão de ajuste usado em convergencia.py e
# spread_calendario.py para vencimento B3). Datas confirmadas via
# comunicado oficial Conab (02/01/2026): jan=15, set=15 (fecha safra
# 2025/26), out=15 (abre safra 2026/27). As demais seguem a mesma regra
# mensal, não confirmadas individualmente.
_CONAB_DIAS_CONFIRMADOS = {1: 15, 9: 15, 10: 15}

# Último ano com WASDE/Estoques Trimestrais cadastrados manualmente. USDA não
# publica essas datas por regra fixa (tipo "toda segunda terça do mês") —
# muda ano a ano, exige nova busca manual. Sem esse controle, rodar o
# pipeline em 2027+ silenciosamente devolve "sem eventos" para o lado USDA
# (a lista simplesmente não tem nada daquele ano) — um gate de "não operar"
# que fica quieto por falta de dado é pior que não ter gate: passa a
# impressão de que está tudo limpo. `usda_desatualizado` existe para isso
# não passar batido. CONAB não tem esse problema — é gerado por regra para
# qualquer ano (ver _gerar_calendario_conab), só a precisão mês a mês que é
# limitada (ver cabeçalho do arquivo).
_ULTIMO_ANO_USDA_CONFIRMADO = 2026


def _dia_util_seguinte(d: date) -> date:
    while d.weekday() >= 5:  # 5=sábado, 6=domingo
        d += timedelta(days=1)
    return d


def _gerar_calendario_conab(ano: int) -> dict:
    eventos = {}
    for mes in range(1, 13):
        dia = _CONAB_DIAS_CONFIRMADOS.get(mes, 15)
        d = _dia_util_seguinte(date(ano, mes, dia))
        eventos[d] = 'Boletim da Safra de Grãos (CONAB)'
    return eventos


def _montar_todos_eventos(ano: int) -> list:
    eventos = []
    for d in EVENTOS_WASDE_2026:
        if d.year != ano:
            continue
        impacto = 'MAXIMO' if d in EVENTOS_GRAIN_STOCKS_2026 else 'ALTO'
        nome = 'WASDE'
        if d in EVENTOS_GRAIN_STOCKS_2026:
            nome = f'WASDE + {EVENTOS_GRAIN_STOCKS_2026[d]}'
        eventos.append({'data': d, 'orgao': 'USDA', 'evento': nome, 'horario_et': '12:00', 'impacto': impacto})

    for d, nome in EVENTOS_GRAIN_STOCKS_2026.items():
        if d.year != ano or d in EVENTOS_WASDE_2026:
            continue  # já coberto acima (mesmo dia do WASDE)
        eventos.append({'data': d, 'orgao': 'USDA', 'evento': nome, 'horario_et': '12:00', 'impacto': 'MAXIMO'})

    for d, nome in _gerar_calendario_conab(ano).items():
        eventos.append({'data': d, 'orgao': 'CONAB', 'evento': nome, 'horario_et': None, 'impacto': 'ALTO'})

    eventos.sort(key=lambda e: e['data'])
    return eventos


def verificar_calendario_economico(hoje: date = None) -> dict:
    """
    Ponto de entrada. Devolve se HOJE é dia de divulgação (gate de "não
    operar") e o próximo evento agendado, para os anos presentes no
    calendário (atualmente só 2026 — ver limitação no manual).
    """
    hoje = hoje or date.today()
    todos = _montar_todos_eventos(hoje.year)

    eventos_hoje = [e for e in todos if e['data'] == hoje]
    eventos_futuros = sorted([e for e in todos if e['data'] > hoje], key=lambda e: e['data'])
    proximo = eventos_futuros[0] if eventos_futuros else None
    dias_ate_proximo = (proximo['data'] - hoje).days if proximo else None

    def _serializar(e):
        return {**e, 'data': e['data'].strftime('%Y-%m-%d'), 'data_br': e['data'].strftime('%d/%m/%Y')}

    # Sinaliza quando não há mais nenhuma data USDA cadastrada para o resto
    # do ano corrente — bloqueio duro do gate fica sem sentido nesses dias
    # porque o dado simplesmente acabou, não porque não há evento real.
    usda_restante = any(
        e['orgao'] == 'USDA' and e['data'] >= hoje for e in _montar_todos_eventos(hoje.year)
    )
    usda_desatualizado = (hoje.year > _ULTIMO_ANO_USDA_CONFIRMADO) or not usda_restante

    return {
        'bloquear_hoje':            len(eventos_hoje) > 0,
        'eventos_hoje':             [_serializar(e) for e in eventos_hoje],
        'proximo_evento':           _serializar(proximo) if proximo else None,
        'dias_ate_proximo_evento':  dias_ate_proximo,
        'aviso_amanha':             dias_ate_proximo == 1,
        'proximos_eventos':        [_serializar(e) for e in eventos_futuros[:5]],
        'usda_desatualizado':      usda_desatualizado,
    }


def obter_eventos_proximos(data_ref: date = None, dias_a_frente: int = 15) -> list:
    """
    Retorna a lista de eventos agendados (USDA e CONAB) dentro da janela de dias_a_frente,
    calculando a quantidade de dias restantes (dias_ate).
    Usado pelo motor Sentinel-Corn 2.0 para determinacao de risco de volatilidade pre-relatorio.
    """
    data_ref = data_ref or date.today()
    todos = _montar_todos_eventos(data_ref.year)
    if data_ref.month >= 11:
        todos += _montar_todos_eventos(data_ref.year + 1)

    eventos = []
    for e in todos:
        diff = (e['data'] - data_ref).days
        if 0 <= diff <= dias_a_frente:
            d_val = e['data']
            eventos.append({
                'data': d_val.isoformat() if hasattr(d_val, 'isoformat') else str(d_val),
                'dias_ate': diff,
                'evento': e['evento'],
                'orgao': e['orgao'],
                'impacto': e['impacto']
            })
    eventos.sort(key=lambda x: x['dias_ate'])
    return eventos


# ── TESTE ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        y, m, d = map(int, sys.argv[1].split('-'))
        hoje = date(y, m, d)
    else:
        hoje = date.today()

    r = verificar_calendario_economico(hoje)
    print(f'Data testada: {hoje}')
    print(f'Bloquear hoje: {r["bloquear_hoje"]}')
    if r['eventos_hoje']:
        for e in r['eventos_hoje']:
            print(f"  HOJE: {e['orgao']} — {e['evento']}")
    if r['proximo_evento']:
        pe = r['proximo_evento']
        print(f"Próximo evento: {pe['orgao']} — {pe['evento']} em {pe['data_br']} ({r['dias_ate_proximo_evento']} dias)")
    print('Aviso amanhã:', r['aviso_amanha'])
    print(f"\nPróximos {len(r['proximos_eventos'])} eventos:")
    for e in r['proximos_eventos']:
        print(f"  {e['data_br']} | {e['orgao']} | {e['evento']} | impacto {e['impacto']}")
