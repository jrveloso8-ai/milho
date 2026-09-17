# spread_calendario.py — Milho Trader v1.0 (Fase 3B)
#
# Spread trade entre pares de contratos CCM específicos ("comprar um vencimento,
# vender outro"). Trata o spread entre duas pernas como sua PRÓPRIA série
# histórica, com média/desvio/Z-score reais — não clona o sistema EMA 9/20 +
# Setup 9.1 em cada contrato individualmente. Esse sistema só foi validado
# (backtest WR/Payoff) no CCMFUT contínuo; rodar ele em contratos específicos,
# muitos com liquidez bem menor, seria estatística emprestada sem validação.
# Decidido com o usuário em 11/07/2026.

import os
from datetime import date, timedelta
import pandas as pd
from leitor_csv import (
    listar_contratos_ccm, extrair_vencimento, _chave_vencimento,
    ler_csv, ler_arquivo,
)

_MIN_OBS_HISTORICO = 10
_LIMIAR_Z = 1.5

# Janela móvel (não expansível) para média/desvio-padrão do spread — mudança
# de 11/07/2026, motivada por cross-check real: o indicador nativo da
# plataforma do usuário (Bandas de Bollinger, 113 períodos, no par
# CCMU26/CCMX26) deu Z=-1,27σ no fechamento contra Z=-1,89σ do cálculo por
# janela expansível deste módulo — mesma direção, magnitude bem diferente.
# Causa: janela expansível pondera dados de ~1 ano atrás com o mesmo peso do
# pregão de ontem; se o spread está em tendência estrutural (não só ruído
# ao redor de uma média estável), a janela expansível fica "presa" a um
# nível antigo e superestima o quão extremo o spread atual é. Janela móvel
# de 113 pregões (~5,5 meses) se adapta a mudança de regime e também
# aproxima o Z-score deste módulo do que o operador já vê na tela de
# execução — reduz a chance de dois sinais do mesmo par discordarem sem
# explicação clara.
_JANELA_ROLLING = 113

_MES_ORDEM = {
    'F': 1, 'G': 2, 'H': 3, 'J': 4, 'K': 5, 'M': 6,
    'N': 7, 'Q': 8, 'U': 9, 'V': 10, 'X': 11, 'Z': 12,
}


def _data_vencimento(codigo_vencimento: str):
    """Mesma regra B3 usada em convergencia.py: dia 15 do mês, ajustado para
    o próximo dia útil se cair em fim de semana."""
    try:
        letra = codigo_vencimento[3]
        ano   = 2000 + int(codigo_vencimento[4:6])
        mes   = _MES_ORDEM.get(letra)
        if mes is None:
            return None
        d = date(ano, mes, 15)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d
    except (IndexError, ValueError):
        return None


_DIAS_MIN_ATE_VENCIMENTO = 15  # mesmo limiar do gate "acionável" da Convergência


def identificar_contratos_liquidos(pasta: str, hoje=None, top_n: int = 3, janela_volume: int = 10) -> list:
    """
    Retorna os `top_n` contratos VIVOS com maior volume médio dos últimos
    `janela_volume` pregões, ordenados CRONOLOGICAMENTE — para formar pares
    de spread com convenção de sinal consistente (perna mais próxima primeiro).

    Exclui contratos a `_DIAS_MIN_ATE_VENCIMENTO` dias ou menos do próprio
    vencimento. Motivo: achado em produção (11/07/2026) — sem esse filtro,
    CCMN26 (a 4 dias do vencimento) entrava como perna de spread. Um
    contrato tão perto do vencimento já está sob o mesmo mecanismo de
    convergência forçada futuro×físico (liquidação financeira do CCM) que
    justifica o gate de Convergência; seu spread contra outro vencimento
    passa a refletir essa convergência, não uma distorção de calendário
    genuína — e não sobra tempo útil para abrir/segurar a posição antes do
    vencimento de qualquer forma.
    """
    hoje = hoje or date.today()
    chave_atual = (hoje.year, hoje.month)
    caminhos = [p for p in listar_contratos_ccm(pasta) if _chave_vencimento(p) >= chave_atual]

    candidatos = []
    for path in caminhos:
        codigo = extrair_vencimento(path)
        dv = _data_vencimento(codigo)
        if dv is not None and (dv - hoje).days <= _DIAS_MIN_ATE_VENCIMENTO:
            continue
        try:
            df = ler_csv(path)
            vol = float(df['Qtd'].tail(janela_volume).mean()) if 'Qtd' in df.columns and len(df) > 0 else 0.0
            candidatos.append((codigo, vol, path))
        except Exception:
            continue

    candidatos.sort(key=lambda t: t[1], reverse=True)
    top = candidatos[:top_n]
    top.sort(key=lambda t: _chave_vencimento(t[2]))
    return [codigo for codigo, _vol, _path in top]


def _serie_spread(pasta: str, cod_a: str, cod_b: str) -> pd.DataFrame:
    df_a = ler_arquivo(pasta, cod_a)[['Data', 'Close']].rename(columns={'Close': 'a'})
    df_b = ler_arquivo(pasta, cod_b)[['Data', 'Close']].rename(columns={'Close': 'b'})
    m = pd.merge(df_a, df_b, on='Data', how='inner').sort_values('Data')
    m['spread'] = m['a'] - m['b']
    return m


def analisar_par(pasta: str, cod_a: str, cod_b: str, hoje=None) -> dict:
    """
    spread = preço(cod_a) - preço(cod_b). Z-score positivo = cod_a caro em
    relação a cod_b (vs. o histórico real desse par específico, não uma
    constante). |Z| > 1,5 é o mesmo limiar usado no resto do projeto
    (Convergência). Não há gate de "dias até o vencimento" aqui como em
    Convergência — ali o gatilho é o mecanismo de liquidação financeira do
    CCM forçando convergência futuro×físico; aqui as duas pernas são
    futuros negociáveis, o racional é reversão à média do spread, não
    convergência forçada por liquidação. `dias_vencimento_perna_a` é só
    informativo (avisa se a perna mais próxima precisa de rolagem em breve).
    """
    hoje = hoje or date.today()
    try:
        m = _serie_spread(pasta, cod_a, cod_b)
    except FileNotFoundError as e:
        return {'par': f'{cod_a}-{cod_b}', 'contrato_a': cod_a, 'contrato_b': cod_b, 'erro': str(e)}

    if len(m) < _MIN_OBS_HISTORICO:
        return {
            'par': f'{cod_a}-{cod_b}', 'contrato_a': cod_a, 'contrato_b': cod_b,
            'erro': f'histórico pareado insuficiente ({len(m)} pontos, mínimo {_MIN_OBS_HISTORICO})',
        }

    # Janela móvel — ver comentário em _JANELA_ROLLING. Usa os últimos
    # min(len(m), 113) pregões pareados, não a série inteira. Com menos de
    # 113 pontos disponíveis (par recém-formado), usa o que houver — ainda
    # sujeito ao piso de _MIN_OBS_HISTORICO acima.
    janela_df = m.tail(min(len(m), _JANELA_ROLLING))
    media  = round(float(janela_df['spread'].mean()), 2)
    desvio = round(float(janela_df['spread'].std(ddof=1)), 2)
    n_obs  = int(len(janela_df))
    periodo_base = f"{janela_df['Data'].min().date().strftime('%d/%m/%Y')} a {janela_df['Data'].max().date().strftime('%d/%m/%Y')}"
    spread_hoje = round(float(m['spread'].iloc[-1]), 2)

    zscore = round((spread_hoje - media) / desvio, 2) if desvio else None
    alerta = zscore is not None and abs(zscore) > _LIMIAR_Z
    direcao, leitura = None, None
    if alerta:
        if zscore > _LIMIAR_Z:
            direcao = f'{cod_a}_CARO'
            leitura = f'{cod_a} está caro em relação a {cod_b} (Z={zscore:.1f}σ) — considerar vender {cod_a} / comprar {cod_b} (tese: spread reverte à média).'
        else:
            direcao = f'{cod_a}_BARATO'
            leitura = f'{cod_a} está barato em relação a {cod_b} (Z={zscore:.1f}σ) — considerar comprar {cod_a} / vender {cod_b} (tese: spread reverte à média).'

    semanal = janela_df.set_index('Data')['spread'].resample('W').last().dropna().tail(20)
    historico_semanal = [round(float(v), 2) for v in semanal.values]

    dv_a = _data_vencimento(cod_a)
    dias_vencimento_perna_a = (dv_a - hoje).days if dv_a else None

    return {
        'par':                      f'{cod_a}-{cod_b}',
        'contrato_a':               cod_a,
        'contrato_b':               cod_b,
        'spread_hoje':              spread_hoje,
        'spread_media_historica':   media,
        'spread_desvio_padrao':     desvio,
        'spread_zscore':            zscore,
        'alerta':                   alerta,
        'direcao':                  direcao,
        'leitura':                  leitura,
        'periodo_base':             periodo_base,
        'n_obs_historico':          n_obs,
        'historico_semanal':        historico_semanal,
        'dias_vencimento_perna_a':  dias_vencimento_perna_a,
    }


def analisar_spreads_calendario(pasta: str, hoje=None, top_n: int = 3) -> dict:
    """
    Ponto de entrada. Identifica os `top_n` contratos mais líquidos vivos e
    devolve a análise de TODOS os pares entre eles (C(top_n,2) pares — com
    top_n=3, são 3 pares).
    """
    hoje = hoje or date.today()
    contratos = identificar_contratos_liquidos(pasta, hoje, top_n)
    if len(contratos) < 2:
        return {'contratos_considerados': contratos, 'pares': []}

    pares = []
    for i in range(len(contratos)):
        for j in range(i + 1, len(contratos)):
            pares.append(analisar_par(pasta, contratos[i], contratos[j], hoje))

    return {'contratos_considerados': contratos, 'pares': pares}


# ── TESTE ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    import json
    pasta = sys.argv[1] if len(sys.argv) > 1 else r'C:\Projetos Phyton\Milho'
    r = analisar_spreads_calendario(pasta, date(2026, 7, 11))
    print('Contratos considerados:', r['contratos_considerados'])
    for p in r['pares']:
        if 'erro' in p:
            print(f"  {p['par']}: ERRO — {p['erro']}")
        else:
            print(f"  {p['par']}: spread={p['spread_hoje']} média={p['spread_media_historica']} "
                  f"desvio={p['spread_desvio_padrao']} Z={p['spread_zscore']} alerta={p['alerta']}")
            if p['leitura']:
                print(f"    → {p['leitura']}")
