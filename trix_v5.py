# trix_v5.py — Milho Trader
# ==============================================================================
# TRIX(7)/SMA(3) + Filtro de Tendência SMA(100) — MIGRAÇÃO 17/09/2026
#
# Sistema ATIVO ÚNICO do projeto Milho desde a decisão do usuário em
# 14/09/2026 (ver /areas/milho-trader.md e /areas/trix-reversal.md). Substitui
# EMA9/20 (Sistema 1) e Setup 9.1 (Sistema 2), formalmente descontinuados —
# ORB 60min e Donchian também descontinuados, mas nunca fizeram parte deste
# arquivo (viviam em sistemas separados de 60min).
#
# Esta é uma RÉPLICA LITERAL da lógica validada em
# C:\Projetos Antigravity\backtest\strategy\trix_trend_v5.py e
# C:\Projetos Antigravity\backtest\indicators\trix.py — portada linha a linha,
# não uma reimplementação por analogia. Validação de referência (ver README
# daquele projeto): paridade Python vs. NTSL (229 vs 233 trades, WR 51,09% vs
# 51,07%, PF 2,84 vs 2,86), Monte Carlo Permutation p=0,012, walk-forward 5/5
# folds positivos, holdout travado 2024-03-08 a 2026-09-14 com PF 1,47 líquido
# de custos.
#
# IMPORTANTE — o sistema validado é stop-and-reverse SEM stop técnico e SEM
# alvo fixo: uma vez que entra, permanece na posição até o cruzamento oposto
# do TRIX (USAR_STOP_TECNICO=False no backtest de referência). Os campos
# stop_atr15/alvo_rr2 calculados em ccm_dados.py a partir daqui são só
# REFERÊNCIA DE GESTÃO DE RISCO (dimensionamento, margem) — não fazem parte
# do sistema validado e NÃO devem ser lidos como "onde o sistema sai".
# ==============================================================================

import numpy as np
import pandas as pd

P_TRIX = 7
P_SINAL = 3
P_TREND = 100


def calc_trix(close: pd.Series, period: int = P_TRIX) -> pd.Series:
    """TRIX: taxa de variação percentual de uma tripla EMA suavizada."""
    ema1 = close.ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    ema3 = ema2.ewm(span=period, adjust=False).mean()
    return (ema3 - ema3.shift(1)) / ema3.shift(1) * 100


def calc_sinais_trix_v5(
    df: pd.DataFrame,
    p_trix: int = P_TRIX,
    p_sinal: int = P_SINAL,
    p_trend: int = P_TREND,
) -> pd.DataFrame:
    """
    Simula bar-a-bar a lógica EXATA do TRIX v5 validado (réplica de
    simulate_trix_trend_v5 em backtest/strategy/trix_trend_v5.py). Precisa da
    série completa (não só os últimos N candles) porque é um sistema com
    estado — a posição de hoje depende de toda a história de cruzamentos
    desde o início dos dados, não é recalculável olhando só a janela recente.

    Regras (idênticas ao NTSL v5 portado):
      - cruzamento SIMÉTRICO do TRIX contra sua SMA(p_sinal)
      - filtro de tendência SÓ NA ENTRADA (Close vs SMA(p_trend))
      - saída é o cruzamento oposto PURO, sem o filtro de tendência
      - sem stop técnico (réplica do padrão validado, UsarStopTecnico=False)

    Adiciona ao df:
      - trix, trix_sinal, trend_sma{p_trend}
      - posicao_trix_v5 ∈ {'COMPRADO','VENDIDO','FLAT'} — estado ao fim do bar
      - entrada_hoje ∈ {'COMPRA','VENDA', None} — só preenchido no bar exato
        do cruzamento que abriu a posição
      - saida_hoje ∈ {'COMPRA','VENDA', None} — idem, no bar do cruzamento
        que fechou a posição
    """
    df = df.copy()
    df['trix'] = calc_trix(df['Close'], p_trix)
    df['trix_sinal'] = df['trix'].rolling(p_sinal).mean()
    df[f'trend_sma{p_trend}'] = df['Close'].rolling(p_trend).mean()

    n = len(df)
    close_v = df['Close'].values
    trix_v = df['trix'].values
    sig_v = df['trix_sinal'].values
    trend_v = df[f'trend_sma{p_trend}'].values

    posicao = np.empty(n, dtype=object)
    posicao[:] = 'FLAT'
    entrada_hoje = np.array([None] * n, dtype=object)
    saida_hoje = np.array([None] * n, dtype=object)

    is_bought = False
    is_sold = False

    for t in range(1, n):
        if (
            np.isnan(trix_v[t - 1]) or np.isnan(trix_v[t])
            or np.isnan(sig_v[t - 1]) or np.isnan(sig_v[t])
            or np.isnan(trend_v[t]) or np.isnan(close_v[t])
        ):
            posicao[t] = posicao[t - 1]
            continue

        cross_up = (trix_v[t - 1] <= sig_v[t - 1]) and (trix_v[t] > sig_v[t])
        cross_down = (trix_v[t - 1] >= sig_v[t - 1]) and (trix_v[t] < sig_v[t])

        tend_alta_ok = close_v[t] > trend_v[t]
        tend_baixa_ok = close_v[t] < trend_v[t]

        sinal_c = cross_up and tend_alta_ok
        sinal_v = cross_down and tend_baixa_ok
        saida_c = cross_down
        saida_v = cross_up

        if sinal_c and not is_bought and not is_sold:
            is_bought = True
            entrada_hoje[t] = 'COMPRA'
        if sinal_v and not is_bought and not is_sold:
            is_sold = True
            entrada_hoje[t] = 'VENDA'

        if is_bought and saida_c:
            is_bought = False
            saida_hoje[t] = 'COMPRA'
        if is_sold and saida_v:
            is_sold = False
            saida_hoje[t] = 'VENDA'

        posicao[t] = 'COMPRADO' if is_bought else ('VENDIDO' if is_sold else 'FLAT')

    df['posicao_trix_v5'] = posicao
    df['entrada_hoje'] = entrada_hoje
    df['saida_hoje'] = saida_hoje
    return df


# ── TESTE ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    sys.path.insert(0, '.')
    from leitor_csv import ler_arquivo

    pasta = sys.argv[1] if len(sys.argv) > 1 else r'C:\Projetos Phyton\Milho'
    df = ler_arquivo(pasta, 'CCMFUT')
    df = calc_sinais_trix_v5(df)
    ult = df.iloc[-1]
    print(f"Data: {ult['Data'].date()} | Close: {ult['Close']:.2f}")
    print(f"TRIX: {ult['trix']:.4f} | Sinal: {ult['trix_sinal']:.4f} | SMA100: {ult['trend_sma100']:.2f}")
    print(f"Posição: {ult['posicao_trix_v5']} | Entrada hoje: {ult['entrada_hoje']} | Saída hoje: {ult['saida_hoje']}")
