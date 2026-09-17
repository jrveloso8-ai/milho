# cambio_macro.py — Milho Trader v1.0
# Câmbio (WDOFUT), DI futuro, DXY (DOLINDEX), ZC CME e Brent via yfinance

import os
from datetime import datetime
from leitor_csv import ler_arquivo, ler_wdofut, ler_di, ultimo_valor, variacao_pct

SACAS_POR_BUSHEL = 2.3621  # 1 saca = 60kg = 2.3621 bushels

try:
    import yfinance as yf
    YFINANCE_OK = True
except ImportError:
    YFINANCE_OK = False


# ── HELPER SEGURO PARA YFINANCE ───────────────────────────────────────────────

def _safe_close(df_yf, idx=-1):
    """
    Extrai valor de fechamento do DataFrame do yfinance de forma segura.
    Compatível com versões antigas (Series) e novas (MultiIndex DataFrame).
    """
    import pandas as pd
    col = df_yf['Close']
    # Se MultiIndex retornou DataFrame em vez de Series
    if isinstance(col, pd.DataFrame):
        col = col.iloc[:, 0]  # pega a primeira coluna (único ticker)
    return float(col.values[idx])


# ── CÂMBIO ────────────────────────────────────────────────────────────────────

def analisar_cambio(pasta, preco_ccm, preco_zc):
    """
    Lê WDOFUT e calcula câmbio implícito no CCM.
    Paridade: (ZC_cents/100) × 2.3621 × USDBRL = R$/saca FOB (ex-custos)
    """
    try:
        df = ler_wdofut(pasta)
    except FileNotFoundError:
        return _cambio_vazio('WDOFUT não encontrado')

    usdbrl      = ultimo_valor(df, 'USDBRL')
    var5d       = variacao_pct(df, 'USDBRL', 5)
    paridade    = None
    cambio_impl = None
    diagnostico = 'N/A'

    if usdbrl and preco_zc:
        paridade = round((preco_zc / 100) * SACAS_POR_BUSHEL * usdbrl, 2)

    if usdbrl and preco_zc and preco_ccm:
        cambio_impl = round(preco_ccm / ((preco_zc / 100) * SACAS_POR_BUSHEL), 4)
        dif_pct     = (cambio_impl - usdbrl) / usdbrl * 100
        if abs(dif_pct) < 5.0:  diagnostico = 'MISTO'
        elif dif_pct > 5.0:     diagnostico = 'MILHO'
        else:                   diagnostico = 'CAMBIO'

    return {
        'wdofut':               round(df['Close'].iloc[-1], 3),
        'wdofut_usdbrl':        round(usdbrl, 4) if usdbrl else None,
        'variacao_semanal_pct': var5d,
        'ccm_paridade':         paridade,
        'cambio_implicito':     cambio_impl,
        'diagnostico':          diagnostico,
        'data_ultimo':          str(df['Data'].iloc[-1].date()),
    }


# ── DI FUTURO ─────────────────────────────────────────────────────────────────

def analisar_di(pasta, preco_fisico, preco_futuro=None):
    result = {
        'di1f27_taxa':             None,
        'di1f29_taxa':             None,
        'preco_justo_jan27':       None,
        'spread_justo_vs_mercado': None,  # exigido por gerar_resumo_analise.py (CAMPOS_OBRIGATORIOS)
    }

    try:
        df27   = ler_di(pasta, 'DI1F27')
        taxa27 = ultimo_valor(df27, 'Close')
        result['di1f27_taxa'] = round(taxa27, 3) if taxa27 else None
        if taxa27 and preco_fisico:
            dias_uteis = max(1, int((datetime(2027, 1, 2) - datetime.now()).days * 252 / 365))
            result['preco_justo_jan27'] = round(
                preco_fisico * ((1 + taxa27 / 100) ** (dias_uteis / 252)), 2
            )
            # Spread do preço de mercado (CCM) contra o preço justo teórico
            # (físico + carrego DI até jan/27) — mesmo conceito da Convergência
            # (futuro - físico), mas aqui é futuro - físico_corrigido_pelo_carrego.
            # É o campo que gerar_resumo_analise.py espera e nunca recebia.
            if preco_futuro:
                result['spread_justo_vs_mercado'] = round(preco_futuro - result['preco_justo_jan27'], 2)
    except FileNotFoundError:
        pass

    try:
        df29   = ler_di(pasta, 'DI1F29')
        taxa29 = ultimo_valor(df29, 'Close')
        result['di1f29_taxa'] = round(taxa29, 3) if taxa29 else None
    except FileNotFoundError:
        pass

    return result


# ── DOLINDEX ──────────────────────────────────────────────────────────────────

def analisar_dolindex(pasta):
    for prefixo in ['DOLINDEX_O', 'DOLINDEX_F', 'DOLINDEX']:
        try:
            df    = ler_arquivo(pasta, prefixo)
            dxy   = ultimo_valor(df, 'Close')
            var5d = variacao_pct(df, 'Close', 5)
            return {
                'dolindex_dxy':     round(dxy, 2) if dxy else None,
                'dxy_variacao_pct': var5d,
            }
        except FileNotFoundError:
            continue
    return {'dolindex_dxy': None, 'dxy_variacao_pct': None}


# ── ZC CME e BRENT (yfinance) ─────────────────────────────────────────────────

def buscar_zc_brent():
    result = {
        'zc_preco_cents_bu':  None,
        'zc_variacao_pct':    None,
        'brent_preco':        None,
        'brent_variacao_pct': None,
        'fonte':              'N/A',
    }

    if not YFINANCE_OK:
        result['fonte'] = 'yfinance não instalado — pip install yfinance'
        return result

    try:
        # ZC=F — milho Chicago front month
        zc = yf.download('ZC=F', period='15d', interval='1d',
                         progress=False, auto_adjust=True)
        zc = zc.dropna()
        if len(zc) >= 2:
            pz  = _safe_close(zc, -1)
            pza = _safe_close(zc, -6) if len(zc) >= 6 else _safe_close(zc, 0)
            result['zc_preco_cents_bu'] = round(pz, 2)
            result['zc_variacao_pct']   = round((pz - pza) / pza * 100, 2)

        # BZ=F — Brent
        brent = yf.download('BZ=F', period='15d', interval='1d',
                             progress=False, auto_adjust=True)
        brent = brent.dropna()
        if len(brent) >= 2:
            pb  = _safe_close(brent, -1)
            pba = _safe_close(brent, -6) if len(brent) >= 6 else _safe_close(brent, 0)
            result['brent_preco']        = round(pb, 2)
            result['brent_variacao_pct'] = round((pb - pba) / pba * 100, 2)

        result['fonte'] = 'yfinance'

    except Exception as e:
        result['fonte'] = f'yfinance erro: {str(e)[:120]}'

    return result


# ── MACRO COMPLETO ────────────────────────────────────────────────────────────

def analisar_macro_completo(pasta, preco_ccm, preco_fisico):
    zc_brent = buscar_zc_brent()
    preco_zc  = zc_brent.get('zc_preco_cents_bu')
    dolindex  = analisar_dolindex(pasta)

    # DXY pertence ao bloco 'cambio' (schema do SYSTEM_PROMPT_v1.0.md) — o dashboard
    # lê cambio.dolindex_dxy, não macro.dolindex_dxy. Mesclar aqui evita o campo
    # "sumir" (aparecer como "—") no dashboard por estar no bloco errado.
    cambio = analisar_cambio(pasta, preco_ccm, preco_zc)
    cambio['dolindex_dxy']     = dolindex['dolindex_dxy']
    cambio['dxy_variacao_pct'] = dolindex['dxy_variacao_pct']

    return {
        'cambio':   cambio,
        'carrego':  analisar_di(pasta, preco_fisico, preco_ccm),
        'zc_cme': {
            'preco_cents_bu':       zc_brent['zc_preco_cents_bu'],
            'variacao_semanal_pct': zc_brent['zc_variacao_pct'],
        },
        'macro': {
            'brent':              zc_brent['brent_preco'],
            'brent_variacao_pct': zc_brent['brent_variacao_pct'],
            'wasde_proximo':      'N/A',
            'conab_proximo':      'N/A',
        },
        'fonte_zc': zc_brent['fonte'],
    }


def _cambio_vazio(motivo):
    return {
        'wdofut': None, 'wdofut_usdbrl': None,
        'variacao_semanal_pct': None, 'ccm_paridade': None,
        'cambio_implicito': None,
        'diagnostico': f'DADOS AUSENTES — {motivo}',
        'data_ultimo': None,
    }


if __name__ == '__main__':
    import sys
    pasta = sys.argv[1] if len(sys.argv) > 1 else r'C:\Projetos Phyton\Milho'
    r = analisar_macro_completo(pasta, 66.88, 62.99)
    c = r['cambio']
    print(f"USDBRL:   R${c['wdofut_usdbrl']} | Paridade: R${c['ccm_paridade']}/sc | {c['diagnostico']}")
    print(f"DI Jan27: {r['carrego']['di1f27_taxa']}% | Justo: R${r['carrego']['preco_justo_jan27']}/sc")
    print(f"ZC:       {r['zc_cme']['preco_cents_bu']} c/bu | Fonte: {r['fonte_zc']}")
    print(f"Brent:    USD {r['macro']['brent']}")