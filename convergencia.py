# convergencia.py — Milho Trader v1.0
# Análise de convergência futuro×físico via RTCNI
#
# Reescrito em 11/07/2026: média/desvio-padrão do spread agora vêm do
# histórico real (todas as datas onde CCMFUT e RTCNI têm pregão em comum —
# hoje ~2 anos, cresce a cada rodada do pipeline), substituindo as constantes
# fixas SPREAD_MEDIA/SPREAD_DESVPAD que ficam só como fallback defensivo para
# quando não há histórico pareado suficiente. O gráfico da aba Convergência
# também passa a receber pontos semanais reais (`historico_semanal`) em vez
# de ruído aleatório gerado no navegador.

import os
from datetime import date, timedelta
import pandas as pd
from leitor_csv import ler_arquivo, ultimo_valor

# Fallback apenas — usado quando o histórico pareado tem menos de 10 pontos
# (ex.: RTCNI ou CCMFUT recém-adicionados, sem sobreposição de datas ainda).
SPREAD_MEDIA   = 6.51
SPREAD_DESVPAD = 3.50

_MIN_OBS_HISTORICO = 10

_MES_ORDEM = {
    'F': 1, 'G': 2, 'H': 3, 'J': 4, 'K': 5, 'M': 6,
    'N': 7, 'Q': 8, 'U': 9, 'V': 10, 'X': 11, 'Z': 12,
}


def _data_vencimento(codigo_vencimento: str):
    """
    Regra B3 para CCM: vencimento no dia 15 do mês de vencimento; se não
    houver sessão de negociação nesse dia, vai para a próxima sessão.
    Aproximação: só ajusta fim de semana (sáb/dom) — não há calendário de
    feriados B3 no projeto, então feriados no meio da semana não são
    tratados. Fonte: especificação do contrato futuro de milho B3.
    """
    try:
        letra = codigo_vencimento[3]
        ano   = 2000 + int(codigo_vencimento[4:6])
        mes   = _MES_ORDEM.get(letra)
        if mes is None:
            return None
        d = date(ano, mes, 15)
        while d.weekday() >= 5:  # 5=sábado, 6=domingo
            d += timedelta(days=1)
        return d
    except (IndexError, ValueError):
        return None


def obter_rtcni_atual(pasta: str) -> dict:
    """
    Obtém o último preço físico medido do RTCNI (Indicador CEPEA/ESALQ Milho)
    e sua data de referência. Prioriza busca online direta na fonte oficial
    (CEPEA/ESALQ ou espelho Notícias Agrícolas) para eliminar a dependência
    de exportação manual. Em caso de indisponibilidade de rede, recorre
    ao cache/série local de forma defensiva.
    Atende à Watchlist da curva CCM (Seção 2.6b).
    """
    # 1. Tenta coleta online via ingestao_cepea
    try:
        import ingestao_cepea
        res_online = ingestao_cepea.obter_ultimo_indicador_cepea()
        if res_online.get("sucesso") and res_online.get("rtcni_preco") is not None:
            # Sincroniza defensivamente com a base local
            try:
                ingestao_cepea.sincronizar_dados_cepea(pasta)
            except Exception:
                pass
            return {
                'rtcni_preco': res_online["rtcni_preco"],
                'rtcni_data': res_online["rtcni_data"],
                'fonte': res_online.get("fonte", "CEPEA/ESALQ (online)"),
            }
    except Exception:
        pass

    # 2. Fallback defensivo: lê o CSV do RTCNI localmente
    try:
        df_rtcni = ler_arquivo(pasta, 'RTCNI')
    except FileNotFoundError:
        return {'rtcni_preco': None, 'rtcni_data': 'N/D', 'erro': 'RTCNI não encontrado'}

    preco_fisico = ultimo_valor(df_rtcni, 'Close')
    if preco_fisico is None:
        return {'rtcni_preco': None, 'rtcni_data': 'N/D', 'erro': 'RTCNI sem fechamento'}

    data_rtcni = str(df_rtcni['Data'].iloc[-1].date())
    return {
        'rtcni_preco': round(preco_fisico, 2),
        'rtcni_data': data_rtcni,
        'fonte': 'Base local (fallback)',
    }


def analisar_convergencia(pasta, preco_futuro, vencimento_ativo=None, hoje=None):
    hoje = hoje or date.today()

    try:
        df_rtcni = ler_arquivo(pasta, 'RTCNI')
    except FileNotFoundError:
        return _vazio('RTCNI não encontrado')

    preco_fisico = ultimo_valor(df_rtcni, 'Close')
    if preco_fisico is None:
        return _vazio('RTCNI sem fechamento')

    # Spread "de hoje" continua usando o RTCNI mais recente disponível vs o
    # preço futuro passado pelo chamador (CCMFUT do dia) — mantém o
    # comportamento já documentado no manual sobre o RTCNI poder estar
    # alguns dias defasado do CCMFUT.
    spread_hoje = round(preco_futuro - preco_fisico, 2)

    media, desvio, n_obs, periodo_base, historico_semanal = _stats_historicas(pasta)

    zscore = round((spread_hoje - media) / desvio, 2) if desvio else None
    alerta = zscore is not None and abs(zscore) > 1.5
    direcao = None
    if alerta:
        direcao = 'FUTURO_CARO' if zscore > 1.5 else 'FUTURO_BARATO'

    vencimento_proximo_dias = None
    if vencimento_ativo:
        data_venc = _data_vencimento(vencimento_ativo)
        if data_venc:
            vencimento_proximo_dias = (data_venc - hoje).days

    # Só vira tese de operação (não só "monitorar") quando a distorção é
    # real E o vencimento está perto o suficiente para o mecanismo de
    # convergência (liquidação financeira do CCM) forçar o ajuste. Limiar
    # de 15 dias definido com o usuário em 11/07/2026.
    acionavel = bool(
        alerta and vencimento_proximo_dias is not None and 0 <= vencimento_proximo_dias <= 15
    )
    leitura_acionavel = None
    if acionavel:
        if direcao == 'FUTURO_CARO':
            leitura_acionavel = (
                f'Convergência forçada em {vencimento_proximo_dias} dia(s) — futuro caro '
                f'(Z={zscore:.1f}σ) sugere pressão de queda em direção ao físico (R${preco_fisico:.2f}/sc).'
            )
        else:
            leitura_acionavel = (
                f'Convergência forçada em {vencimento_proximo_dias} dia(s) — futuro barato '
                f'(Z={zscore:.1f}σ) sugere pressão de alta em direção ao físico (R${preco_fisico:.2f}/sc).'
            )
    elif alerta:
        leitura_acionavel = (
            f'Distorção real (Z={zscore:.1f}σ) mas vencimento ainda a {vencimento_proximo_dias} dia(s) — '
            f'monitorar, não é tese de convergência ainda; o spread pode persistir ou alargar.'
        ) if vencimento_proximo_dias is not None else (
            f'Distorção real (Z={zscore:.1f}σ), mas sem vencimento_ativo para calcular prazo — monitorar.'
        )

    return {
        'rtcni_preco':              round(preco_fisico, 2),
        'rtcni_data':               str(df_rtcni['Data'].iloc[-1].date()),
        'spread_futuro_fisico':     spread_hoje,
        'spread_media_historica':   media,
        'spread_desvio_padrao':     desvio,
        'spread_zscore':            zscore,
        'alerta_convergencia':      alerta,
        'direcao_alerta':           direcao,
        'interpretacao':            _interpretar(zscore, spread_hoje) if zscore is not None else 'Z-score indisponível — histórico pareado insuficiente.',
        'periodo_base':             periodo_base,
        'n_obs_historico':          n_obs,
        'historico_semanal':        historico_semanal,
        'vencimento_proximo_dias':  vencimento_proximo_dias,
        'acionavel':                acionavel,
        'leitura_acionavel':        leitura_acionavel,
    }


def _stats_historicas(pasta):
    """
    Casa CCMFUT e RTCNI pelas datas em comum e calcula média/desvio-padrão
    reais do spread em todo o histórico disponível (janela expansível — a
    cada rodada do pipeline entra mais um dia). Também devolve os últimos
    20 pontos semanais para o gráfico da aba Convergência.

    Se o histórico pareado tiver menos de _MIN_OBS_HISTORICO pontos (ex.:
    um dos dois arquivos muito mais curto que o outro), cai para as
    constantes fixas em vez de calcular estatística instável com poucos
    pontos.
    """
    try:
        df_fut = ler_arquivo(pasta, 'CCMFUT')
    except FileNotFoundError:
        return SPREAD_MEDIA, SPREAD_DESVPAD, 0, None, []

    try:
        df_rtcni = ler_arquivo(pasta, 'RTCNI')
    except FileNotFoundError:
        return SPREAD_MEDIA, SPREAD_DESVPAD, 0, None, []

    m = pd.merge(
        df_fut[['Data', 'Close']].rename(columns={'Close': 'futuro'}),
        df_rtcni[['Data', 'Close']].rename(columns={'Close': 'fisico'}),
        on='Data', how='inner',
    ).sort_values('Data')

    if len(m) < _MIN_OBS_HISTORICO:
        return SPREAD_MEDIA, SPREAD_DESVPAD, int(len(m)), None, []

    m['spread'] = m['futuro'] - m['fisico']

    media  = round(float(m['spread'].mean()), 2)
    desvio = round(float(m['spread'].std(ddof=1)), 2)
    n_obs  = int(len(m))
    periodo_base = f"{m['Data'].min().date().strftime('%d/%m/%Y')} a {m['Data'].max().date().strftime('%d/%m/%Y')}"

    semanal = m.set_index('Data')['spread'].resample('W').last().dropna().tail(20)
    historico_semanal = [round(float(v), 2) for v in semanal.values]

    return media, desvio, n_obs, periodo_base, historico_semanal


def _interpretar(zscore, spread):
    if zscore > 2.0:
        return f'Spread MUITO ELEVADO (Z={zscore:.1f}σ, R${spread:.2f}/sc) — candidato a venda por convergência.'
    elif zscore > 1.5:
        return f'Spread ELEVADO (Z={zscore:.1f}σ, R${spread:.2f}/sc) — monitorar; aguardar catalisador.'
    elif zscore < -1.5:
        return f'Spread NEGATIVO ATÍPICO (Z={zscore:.1f}σ, R${spread:.2f}/sc) — backwardation, escassez real.'
    else:
        return f'Spread normal (Z={zscore:.1f}σ, R${spread:.2f}/sc) — sem distorção de convergência.'


def _vazio(motivo):
    return {
        'rtcni_preco': None, 'rtcni_data': None,
        'spread_futuro_fisico': None,
        'spread_media_historica': SPREAD_MEDIA,
        'spread_desvio_padrao': SPREAD_DESVPAD,
        'spread_zscore': None, 'alerta_convergencia': False,
        'direcao_alerta': None, 'interpretacao': f'DADOS AUSENTES — {motivo}',
        'periodo_base': None, 'n_obs_historico': 0,
        'historico_semanal': [], 'vencimento_proximo_dias': None,
        'acionavel': False, 'leitura_acionavel': None,
    }


# ── TESTE ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    pasta = sys.argv[1] if len(sys.argv) > 1 else r'C:\Projetos Phyton\Milho'
    vencimento = sys.argv[2] if len(sys.argv) > 2 else 'CCMU26'
    r = analisar_convergencia(pasta, 66.90, vencimento_ativo=vencimento)
    print(f"RTCNI: R${r['rtcni_preco']}/sc | Spread: R${r['spread_futuro_fisico']}/sc | Z={r['spread_zscore']}σ")
    print(f"Média real: R${r['spread_media_historica']} | Desvio real: R${r['spread_desvio_padrao']} | n_obs={r['n_obs_historico']} | período: {r['periodo_base']}")
    print(f"Alerta: {'SIM — ' + r['direcao_alerta'] if r['alerta_convergencia'] else 'Não'}")
    print(f"Interpretação: {r['interpretacao']}")
    print(f"Vencimento em {r['vencimento_proximo_dias']} dias")
    print(f"Acionável: {r['acionavel']} | {r['leitura_acionavel']}")
    print(f"Histórico semanal ({len(r['historico_semanal'])} pontos): {r['historico_semanal']}")
