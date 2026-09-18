# ccm_dados.py — Milho Trader v1.0
# Análise técnica do CCM: TRIX v5, ATR, curva de vencimentos
#
# MIGRAÇÃO 17/09/2026 — EMA 9/20 (Sistema 1) e Setup 9.1 (Sistema 2) foram
# descontinuados por decisão do usuário em 14/09/2026, substituídos pelo TRIX
# v5 (TRIX(7)/SMA(3) + filtro de tendência SMA(100)), validado em
# C:\Projetos Antigravity\backtest\ (Monte Carlo p=0,012, walk-forward 5/5,
# holdout PF 1,47). Ver trix_v5.py para a lógica portada e as ressalvas do
# sistema (sem stop técnico, sem alvo fixo — stop_atr15/alvo_rr2 abaixo são
# só referência de gestão de risco, não parte do sistema validado).
#
# Compatibilidade: os campos 'sinal_ema920' e 'sinal_91' foram MANTIDOS no
# dict de retorno (outros módulos do pipeline e o validador de qualidade
# gerar_resumo_analise.py leem essas chaves), mas o CONTEÚDO mudou:
#   sinal_ema920 -> direção da posição ATUAL do TRIX v5 (COMPRA/VENDA/NEUTRO,
#                   NEUTRO = sem posição aberta/FLAT)
#   sinal_91     -> 'COMPRA'/'VENDA' só no pregão exato do cruzamento (nova
#                   entrada); 'NEUTRO' nos demais dias, inclusive mantendo
#                   posição aberta. Ver 'posicao_trix_v5' para o estado bruto.
# Os campos 'ema9'/'ema20'/'ema9_slope' também foram reaproveitados para
# guardar trix/trix_sinal/(trix-trix_sinal) — mesma razão de compatibilidade.
# Use os campos novos ('trix', 'trix_sinal', 'trend_sma100',
# 'posicao_trix_v5') em qualquer código novo.

import pandas as pd
import numpy as np
import os
from datetime import date
from leitor_csv import (
    ler_arquivo, ler_csv, listar_contratos_ccm, extrair_vencimento,
    ultimo_valor, variacao_pct, _chave_vencimento
)
from trix_v5 import calc_sinais_trix_v5

# Mapa de código de mês CCM para nome
MESES_CCM = {
    'F': 'Jan', 'G': 'Fev', 'H': 'Mar', 'J': 'Abr',
    'K': 'Mai', 'M': 'Jun', 'N': 'Jul', 'Q': 'Ago',
    'U': 'Set', 'V': 'Out', 'X': 'Nov', 'Z': 'Dez',
}

# Meses em que o CCM (milho B3) efetivamente lista vencimento: Jan/Mar/Mai/
# Jul/Ago/Set/Nov (F, H, K, N, Q, U, X — confirmado na especificação B3 do
# contrato). Fev/Abr/Jun/Out/Dez (G, J, M, V, Z) NÃO têm contrato CCM
# próprio — não é lacuna de dado, é a grade real do produto. Usado para a
# coluna "Contrato Afetado" da tabela de sazonalidade (31/07/2026).
LETRA_POR_MES_VENCIMENTO = {1: 'F', 3: 'H', 5: 'K', 7: 'N', 8: 'Q', 9: 'U', 11: 'X'}


def contrato_vivo_do_mes(pasta, mes_num, hoje=None):
    """
    Dado um mês do calendário (1-12), retorna o código do contrato CCM vivo
    mais próximo cujo vencimento cai nesse mês (ex.: mes_num=1 -> 'CCMF27'),
    ou None se: (a) esse mês não tem vencimento próprio na grade do CCM
    (ver LETRA_POR_MES_VENCIMENTO), ou (b) o mês TEM vencimento próprio mas
    não há CSV desse contrato na pasta agora (sinaliza lacuna de dado, não
    característica do produto — o chamador deve distinguir os dois casos
    usando LETRA_POR_MES_VENCIMENTO).
    """
    letra = LETRA_POR_MES_VENCIMENTO.get(mes_num)
    if not letra:
        return None
    vivos = listar_vencimentos_vivos(pasta, hoje)
    candidatos = [c for c in vivos if len(c) >= 4 and c[3] == letra]
    if not candidatos:
        return None
    candidatos.sort(key=_chave_vencimento)
    return candidatos[0]


# ── INDICADORES ───────────────────────────────────────────────────────────────

def calc_ema(serie, periodo):
    return serie.ewm(span=periodo, adjust=False).mean()


def calc_atr(df, periodo=14):
    tr = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - df['Close'].shift(1)).abs(),
        (df['Low']  - df['Close'].shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(periodo).mean()


# DESCONTINUADAS 17/09/2026 — mantidas só para referência histórica /
# depuração manual. Não são mais chamadas por _analisar_serie_ohlc(), que usa
# calc_sinais_trix_v5() (trix_v5.py). Ver decisão do usuário de 14/09/2026.
def calc_sinais_ema920(df):
    df = df.copy()
    df['ema9']  = calc_ema(df['Close'], 9)
    df['ema20'] = calc_ema(df['Close'], 20)
    cruzou_alta  = (df['ema9'].shift(1) <= df['ema20'].shift(1)) & (df['ema9'] > df['ema20'])
    cruzou_baixa = (df['ema9'].shift(1) >= df['ema20'].shift(1)) & (df['ema9'] < df['ema20'])
    df['sinal_ema920'] = 'NEUTRO'
    df.loc[cruzou_alta,  'sinal_ema920'] = 'COMPRA'
    df.loc[cruzou_baixa, 'sinal_ema920'] = 'VENDA'
    return df


def calc_sinais_91(df):
    df = df.copy()
    if 'ema9' not in df.columns:
        df['ema9'] = calc_ema(df['Close'], 9)
    slope = df['ema9'] - df['ema9'].shift(1)
    virou_alta  = (slope > 0) & (slope.shift(1) <= 0)
    virou_baixa = (slope < 0) & (slope.shift(1) >= 0)
    df['sinal_91'] = 'NEUTRO'
    df.loc[virou_alta,  'sinal_91'] = 'COMPRA'
    df.loc[virou_baixa, 'sinal_91'] = 'VENDA'
    df['ema9_slope'] = slope
    return df


def calc_suporte_resistencia(df, janela=20):
    recente = df.tail(janela)
    return float(recente['Low'].min()), float(recente['High'].max())


# ── ANÁLISE CCMFUT ────────────────────────────────────────────────────────────

def _analisar_serie_ohlc(df, vencimento_label):
    """
    Núcleo do critério técnico — TRIX v5 (TRIX(7)/SMA(3) + filtro de
    tendência SMA(100)) + ATR + stop/alvo de REFERÊNCIA — extraído de
    analisar_ccmfut() para ser reutilizado tanto pelo CCMFUT contínuo quanto
    por qualquer contrato específico (analisar_contrato), com o MESMO
    critério em ambos os casos (pedido do usuário, 31/07/2026).

    MIGRAÇÃO 17/09/2026: EMA9/20 + Setup 9.1 substituídos pelo TRIX v5. Ver
    cabeçalho do arquivo e trix_v5.py para o mapeamento de compatibilidade
    dos campos de retorno.
    """
    df = df.copy()
    df['atr14'] = calc_atr(df, 14)
    df = calc_sinais_trix_v5(df)

    ult      = df.iloc[-1]
    preco    = float(ult['Close'])
    atr14    = float(ult['atr14'])       if not pd.isna(ult['atr14'])       else 0.0
    trix_val = float(ult['trix'])        if not pd.isna(ult['trix'])        else 0.0
    trix_sig = float(ult['trix_sinal'])  if not pd.isna(ult['trix_sinal'])  else 0.0
    trend100 = float(ult['trend_sma100']) if not pd.isna(ult['trend_sma100']) else 0.0

    posicao_atual = ult['posicao_trix_v5']  # 'COMPRADO' | 'VENDIDO' | 'FLAT'
    sinal_direcional = {'COMPRADO': 'COMPRA', 'VENDIDO': 'VENDA', 'FLAT': 'NEUTRO'}[posicao_atual]
    # NOTA: colunas object com None misturado a strings podem virar NaN
    # (float) na leitura via .iloc dependendo da versão do pandas — nunca
    # usar teste de truthiness/`is None` direto aqui, sempre isinstance(str).
    entrada_raw  = ult['entrada_hoje']
    entrada_hoje = entrada_raw if isinstance(entrada_raw, str) else 'NEUTRO'  # 'COMPRA'/'VENDA' só no dia do cruzamento

    # ATENÇÃO: o sistema TRIX v5 validado NÃO usa stop técnico nem alvo fixo
    # (é stop-and-reverse — sai só no cruzamento oposto). Isto aqui é
    # referência de gestão de risco/dimensionamento, não parte do sistema
    # testado — não confundir com "onde o TRIX v5 sai".
    stop_dist  = round(atr14 * 1.5, 2)
    alvo_dist  = round(stop_dist * 2.0, 2)
    suporte, resistencia = calc_suporte_resistencia(df, 20)

    return {
        'ultimo_preco':         round(preco, 2),
        'variacao_semanal_pct': variacao_pct(df, 'Close', 5),
        'vencimento_ativo':     vencimento_label,
        # Campos legados mantidos por compatibilidade (ver nota no topo do
        # arquivo) — conteúdo agora vem do TRIX v5, não mais de EMA9/20:
        'ema9':                 round(trix_val, 4),               # valor do TRIX(7)
        'ema20':                round(trix_sig, 4),               # valor da SMA(3) do TRIX
        'sinal_ema920':         sinal_direcional,                 # direção da posição ATUAL do TRIX v5
        'ema9_slope':           round(trix_val - trix_sig, 4),    # distância TRIX - sinal
        'sinal_91':             entrada_hoje,                     # 'COMPRA'/'VENDA' só no dia da nova entrada
        # Campos novos (TRIX v5) — usar em código novo:
        'trix':                 round(trix_val, 4),
        'trix_sinal':           round(trix_sig, 4),
        'trend_sma100':         round(trend100, 2),
        'posicao_trix_v5':      posicao_atual,
        'entrada_hoje':         entrada_raw if isinstance(entrada_raw, str) else None,
        'atr14':                round(atr14, 2),
        'stop_atr15_dist':      stop_dist,
        'alvo_rr2_dist':        alvo_dist,
        'stop_atr15':           round(preco - stop_dist, 2),
        'alvo_rr2':             round(preco + alvo_dist, 2),
        'volume_medio':         int(df['Qtd'].tail(20).mean()) if 'Qtd' in df.columns else 0,
        'suporte':              round(suporte, 2),
        'resistencia':          round(resistencia, 2),
        'data_ultimo':          str(df['Data'].iloc[-1].date()),
        'n_pregoes':            int(len(df)),
    }


def analisar_ccmfut(pasta):
    """Analisa o contrato contínuo CCMFUT (usado como proxy do vencimento
    mais líquido)."""
    df = ler_arquivo(pasta, 'CCMFUT')  # usa glob — sem hardcode de acento
    return _analisar_serie_ohlc(df, _identificar_vencimento_ativo(pasta))


def analisar_contrato(pasta, codigo_contrato):
    """
    Roda o MESMO critério técnico de analisar_ccmfut() (EMA 9/20 + Setup 9.1
    + ATR14 + stop/alvo R:R 2:1), mas sobre o CSV do contrato específico
    informado (ex.: 'CCMU26'), em vez do CCMFUT contínuo. Permite comparar
    todos os vencimentos vivos pelo mesmo critério, não só o mais líquido.
    Levanta FileNotFoundError se o contrato não tiver CSV na pasta.
    """
    df = ler_arquivo(pasta, codigo_contrato)
    return _analisar_serie_ohlc(df, codigo_contrato)


def listar_vencimentos_vivos(pasta, hoje=None):
    """
    Lista os códigos de contrato CCM (ex.: 'CCMU26') ainda não vencidos,
    em ordem cronológica — mesma regra de exclusão de analisar_curva_vencimentos
    (mês/ano do contrato >= mês/ano de 'hoje'), para não desperdiçar análise
    técnica em contratos mortos que pararam de ser atualizados.
    """
    hoje = hoje or date.today()
    chave_atual = (hoje.year, hoje.month)
    contratos = listar_contratos_ccm(pasta)
    contratos = [p for p in contratos if _chave_vencimento(p) >= chave_atual]
    return [extrair_vencimento(p) for p in contratos]


def _ultimo_sinal_ativo(df, coluna, janela=5):
    recente   = df[coluna].tail(janela)
    nao_neutro = recente[recente != 'NEUTRO']
    return nao_neutro.iloc[-1] if len(nao_neutro) > 0 else 'NEUTRO'


def _identificar_vencimento_ativo(pasta):
    contratos = listar_contratos_ccm(pasta)
    if not contratos:
        return 'N/A'
    melhor, maior_vol = None, 0
    for path in contratos:
        try:
            df  = ler_csv(path)
            vol = df['Qtd'].tail(5).mean() if 'Qtd' in df.columns else 0
            if vol > maior_vol:
                maior_vol = vol
                melhor    = extrair_vencimento(path)
        except Exception:
            continue
    return melhor or 'N/A'


# ── CANDLES DO CONTRATO ATIVO ─────────────────────────────────────────────────

def obter_candles(pasta, vencimento_ativo, n=40):
    """
    OHLC dos últimos N pregões do CONTRATO ESPECÍFICO (ex.: CCMU26), não do
    CCMFUT contínuo — para o gráfico de candles é o preço realmente
    negociado naquele ticker que importa, igual ao que aparece no Profit.
    Retorna lista vazia se o contrato não for encontrado (não deve
    interromper o pipeline por isso).
    """
    try:
        df = ler_arquivo(pasta, vencimento_ativo)
    except FileNotFoundError:
        return []

    df = df.tail(n)
    candles = []
    for _, row in df.iterrows():
        try:
            candles.append({
                'data':  str(row['Data'].date()),
                'open':  round(float(row['Open']), 2),
                'high':  round(float(row['High']), 2),
                'low':   round(float(row['Low']), 2),
                'close': round(float(row['Close']), 2),
            })
        except (TypeError, ValueError):
            continue
    return candles


# ── CURVA DE VENCIMENTOS ──────────────────────────────────────────────────────

def analisar_curva_vencimentos(pasta, hoje=None):
    """
    Monta a curva de vencimentos a partir dos contratos específicos CCM.

    Exclui contratos já vencidos (mês/ano de vencimento anterior ao mês/ano
    de 'hoje'). Sem esse filtro, contratos mortos (ex.: CCMH26 vencido em
    Mar/2026) continuavam entrando no cálculo de spread ponta-a-ponta e na
    classificação CONTANGO/BACKWARDATION/FLAT mesmo depois que o arquivo
    parou de ser atualizado — distorcendo os dois (confirmado em produção
    em 10/07/2026: 'Spread Ponta a Ponta' comparava CCMH26 vencido contra
    CCMU27, e a curva era classificada como FLAT quando, olhando só os
    contratos vivos, era CONTANGO).
    """
    hoje = hoje or date.today()
    chave_atual = (hoje.year, hoje.month)

    contratos = listar_contratos_ccm(pasta)
    contratos = [p for p in contratos if _chave_vencimento(p) >= chave_atual]
    curva = []
    preco_anterior = None

    for path in contratos:
        codigo = extrair_vencimento(path)
        try:
            df    = ler_csv(path)
            preco = ultimo_valor(df, 'Close')
            if preco is None:
                continue

            letra_mes      = codigo[3]
            ano            = '20' + codigo[4:6]
            nome_mes       = MESES_CCM.get(letra_mes, '?')
            vencimento_str = f'{nome_mes}/{ano}'
            spread         = round(preco - preco_anterior, 2) if preco_anterior else None

            curva.append({
                'contrato':           codigo,
                'vencimento':         vencimento_str,
                'preco':              round(preco, 2),
                'spread_vs_anterior': spread,
                'data_referencia':    str(df['Data'].iloc[-1].date()),
            })
            preco_anterior = preco
        except Exception:
            continue

    return {
        'contratos':         curva,
        'estrutura':         _classificar_estrutura(curva),
        'total_vencimentos': len(curva),
    }


def _classificar_estrutura(curva):
    if len(curva) < 2:
        return 'N/A'
    spreads   = [c['spread_vs_anterior'] for c in curva if c['spread_vs_anterior'] is not None]
    positivos = sum(1 for s in spreads if s > 0.5)
    negativos = sum(1 for s in spreads if s < -0.5)
    if positivos > negativos:   return 'CONTANGO'
    elif negativos > positivos: return 'BACKWARDATION'
    else:                       return 'FLAT'


# ── SIZING ────────────────────────────────────────────────────────────────────

def calcular_sizing(preco, margem_pct=0.0549):
    SACAS         = 450
    valor         = round(preco * SACAS, 2)
    margem        = round(valor * margem_pct, 2)
    return {
        'sacas_por_contrato': SACAS,
        'valor_contrato':     valor,
        'margem_estimada':    margem,
        'stop_mensal':        {'conservador': 2000, 'moderado': 4000, 'arrojado': 8000},
        'contratos':          {'conservador': 2,    'moderado': 4,    'arrojado': 8},
    }


# ── TESTE ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    pasta = sys.argv[1] if len(sys.argv) > 1 else r'C:\Projetos Python\Milho'

    print('=' * 60)
    print('TESTE ccm_dados.py')
    print('=' * 60)

    dados = analisar_ccmfut(pasta)
    print(f"\n✅ CCMFUT:")
    print(f"   Preço:         R$ {dados['ultimo_preco']}/sc")
    print(f"   EMA9/EMA20:    {dados['ema9']} / {dados['ema20']}")
    print(f"   Sinal EMA9/20: {dados['sinal_ema920']}")
    print(f"   Sinal 9.1:     {dados['sinal_91']}")
    print(f"   ATR14:         R$ {dados['atr14']}/sc")
    print(f"   Stop ATR×1.5:  R$ {dados['stop_atr15_dist']}/sc")
    print(f"   Alvo R:R 2:1:  R$ {dados['alvo_rr2_dist']}/sc")
    print(f"   Suporte:       R$ {dados['suporte']}")
    print(f"   Resistência:   R$ {dados['resistencia']}")
    print(f"   Vencimento:    {dados['vencimento_ativo']}")

    curva = analisar_curva_vencimentos(pasta)
    print(f"\n✅ Curva ({curva['total_vencimentos']} contratos — {curva['estrutura']}):")
    for c in curva['contratos']:
        s = f" Δ{c['spread_vs_anterior']:+.2f}" if c['spread_vs_anterior'] else ""
        print(f"   {c['contrato']} ({c['vencimento']}): R$ {c['preco']:.2f}{s}")
