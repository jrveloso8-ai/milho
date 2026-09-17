# macrodata.py — Dados macro: câmbio, juros, RTCNI, paridade, Brent
# Milho Trader v1.0 — Fase 1
# Fontes: todos CSV locais (Profit/Genial)
# Brent: BBR_X_0_Diário.csv (cotação ÷ 10 = USD/barril)

import os
import glob
import pandas as pd
from datetime import datetime


# ── Configurações ────────────────────────────────────────────────────────────
PASTA = r"C:\Projetos Python\Milho"

SPREAD_MEDIO_HISTORICO = 6.51   # R$/sc — referência Jun/2024→Jun/2026
SPREAD_DESVIO_PADRAO   = 3.50   # R$/sc


# ── Funções auxiliares ───────────────────────────────────────────────────────

def _ler_csv(caminho: str, nome: str) -> pd.DataFrame:
    """Lê CSV padrão Profit: Latin-1, ponto-e-vírgula, decimal vírgula, data decrescente."""
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"CSV não encontrado: {caminho} ({nome})")

    df = pd.read_csv(
        caminho,
        encoding="latin-1",
        sep=";",
        decimal=",",
        thousands="."
    )
    df.columns = [c.strip() for c in df.columns]

    # Normalizar coluna de data
    col_data = next((c for c in df.columns if c.lower() == "data"), None)
    if col_data is None:
        raise ValueError(f"Coluna 'Data' não encontrada em {nome}")

    df[col_data] = pd.to_datetime(df[col_data], dayfirst=True)
    df = df.sort_values(col_data).reset_index(drop=True)
    return df


def _variacao_semanal(df: pd.DataFrame, col_fechamento: str) -> float:
    """Calcula variação percentual entre o último e o 6º pregão anterior (≈1 semana)."""
    if len(df) < 2:
        return 0.0
    atual = df[col_fechamento].iloc[-1]
    anterior = df[col_fechamento].iloc[-6] if len(df) >= 6 else df[col_fechamento].iloc[0]
    return round(((atual - anterior) / anterior) * 100, 2)


def _col_fechamento(df: pd.DataFrame) -> str:
    """Localiza coluna de fechamento independente de maiúsculas."""
    for c in df.columns:
        if c.lower() == "fechamento":
            return c
    raise ValueError(f"Coluna 'Fechamento' não encontrada. Colunas: {list(df.columns)}")


# ── Módulos de leitura ───────────────────────────────────────────────────────

def obter_wdofut(pasta: str) -> dict:
    caminho = os.path.join(pasta, "WDOFUT_F_0_Diário.csv")
    df = _ler_csv(caminho, "WDOFUT")
    col = _col_fechamento(df)

    ultimo = float(df[col].iloc[-1])          # R$/1.000 USD
    usdbrl = round(ultimo / 1000, 4)          # R$/USD
    var = _variacao_semanal(df, col)

    return {
        "wdofut": round(ultimo, 2),
        "wdofut_usdbrl": usdbrl,
        "variacao_semanal_pct": var
    }


def obter_dolindex(pasta: str) -> dict:
    caminho = os.path.join(pasta, "DOLINDEX_O_0_Diário.csv")
    df = _ler_csv(caminho, "DOLINDEX")
    col = _col_fechamento(df)

    ultimo = float(df[col].iloc[-1])
    var = _variacao_semanal(df, col)

    return {
        "dolindex_dxy": round(ultimo, 2),
        "dxy_variacao_pct": var
    }


def obter_di(pasta: str) -> dict:
    """Lê DI1F27 e DI1F29. Converte PU para taxa a.a."""

    def pu_para_taxa(pu: float) -> float:
        # PU base 100.000 → taxa a.a. = (100.000/PU)^(252/du) - 1
        # Aproximação direta usada pelo mercado para leitura rápida:
        # taxa = (100.000 / PU - 1) * 100  (não anualizada, mas convencional no Profit)
        # Profit exporta a taxa diretamente em % a.a. no campo Fechamento
        return round(pu, 3)

    resultado = {}

    for ticker, chave in [("DI1F27", "di1f27_taxa"), ("DI1F29", "di1f29_taxa")]:
        caminho = os.path.join(pasta, f"{ticker}_F_0_Diário.csv")
        try:
            df = _ler_csv(caminho, ticker)
            col = _col_fechamento(df)
            taxa = float(df[col].iloc[-1])
            resultado[chave] = pu_para_taxa(taxa)
        except FileNotFoundError:
            resultado[chave] = None

    return resultado


def obter_rtcni(pasta: str) -> dict:
    caminho = os.path.join(pasta, "RTCNI_F_0_Diário.csv")
    df = _ler_csv(caminho, "RTCNI")
    col = _col_fechamento(df)

    preco = float(df[col].iloc[-1])
    return {"rtcni_preco": round(preco, 2)}


def obter_brent(pasta: str) -> dict:
    """
    Lê Brent do CSV local BBR_X_0_Diário.csv.
    Profit exporta cotação × 10 — dividir por 10 para obter USD/barril.
    """
    caminho = os.path.join(pasta, "BBR_X_0_Diário.csv")
    df = _ler_csv(caminho, "BBR Brent")
    col = _col_fechamento(df)

    preco_raw = float(df[col].iloc[-1])
    preco = round(preco_raw / 10, 2)          # ÷10: cotação real em USD/barril

    # Variação semanal sobre valor já convertido
    df["_preco"] = df[col] / 10
    var = _variacao_semanal(df, "_preco")

    return {
        "brent": preco,
        "brent_variacao_pct": var
    }


# ── Cálculos derivados ───────────────────────────────────────────────────────

def calcular_paridade(ccm_preco: float, zc_cents_bu: float, wdofut_usdbrl: float) -> dict:
    """
    Paridade de exportação: ZC (cents/bu) → R$/sc
    Fórmula: ZC × 0,3937 × (USDBRL) / 100
    Câmbio implícito: CCM / (ZC × 0,3937 / 100)
    Diagnóstico: compara variação relativa CCM vs câmbio para dissocia movimento
    """
    if zc_cents_bu is None or zc_cents_bu == 0:
        return {
            "ccm_paridade": None,
            "cambio_implicito": None,
            "diagnostico": "INDISPONIVEL"
        }

    paridade = round(zc_cents_bu * 0.3937 * wdofut_usdbrl / 100, 2)
    cambio_implicito = round(ccm_preco / (zc_cents_bu * 0.3937 / 100), 4)

    # Diagnóstico simplificado — refinado no relatório pelo agente
    diferenca_pct = abs((ccm_preco - paridade) / paridade * 100) if paridade > 0 else 0
    if diferenca_pct < 2:
        diagnostico = "MISTO"
    elif ccm_preco > paridade:
        diagnostico = "MILHO"
    else:
        diagnostico = "CAMBIO"

    return {
        "ccm_paridade": paridade,
        "cambio_implicito": cambio_implicito,
        "diagnostico": diagnostico
    }


def calcular_carrego(ccm_preco: float, di1f27_taxa: float) -> dict:
    """
    Preço justo Jan/27 via custo de carrego DI.
    Aproximação: preco_atual × (1 + taxa/100)^(dias/252)
    Usa 126 dias úteis como proxy para ~6 meses.
    """
    if di1f27_taxa is None:
        return {"preco_justo_jan27": None, "spread_justo_vs_mercado": None}

    du = 126  # dias úteis aproximados até Jan/27
    preco_justo = round(ccm_preco * ((1 + di1f27_taxa / 100) ** (du / 252)), 2)

    return {
        "preco_justo_jan27": preco_justo,
        "spread_justo_vs_mercado": None  # preenchido pelo pipeline com preço do vencimento F27
    }


def calcular_zscore_spread(spread_atual: float) -> float:
    """Z-Score do spread futuro×físico vs histórico."""
    return round((spread_atual - SPREAD_MEDIO_HISTORICO) / SPREAD_DESVIO_PADRAO, 2)


# ── Função principal ─────────────────────────────────────────────────────────

def obter_macrodata(pasta: str, ccm_preco: float, zc_cents_bu: float = None) -> dict:
    """
    Consolida todos os dados macro em um único dict.
    ccm_preco: último preço CCM (R$/sc) — vem do dados_acao_milho
    zc_cents_bu: preço ZC Chicago (cents/bu) — vem do zc_cme
    """
    wdo   = obter_wdofut(pasta)
    dxy   = obter_dolindex(pasta)
    di    = obter_di(pasta)
    rtcni = obter_rtcni(pasta)
    brent = obter_brent(pasta)

    # Paridade
    paridade = calcular_paridade(ccm_preco, zc_cents_bu, wdo["wdofut_usdbrl"])

    # Spread futuro×físico
    spread = round(ccm_preco - rtcni["rtcni_preco"], 2)
    zscore = calcular_zscore_spread(spread)
    alerta = abs(zscore) > 1.5

    # Carrego
    carrego = calcular_carrego(ccm_preco, di.get("di1f27_taxa"))

    return {
        "cambio": {
            "wdofut":              wdo["wdofut"],
            "wdofut_usdbrl":       wdo["wdofut_usdbrl"],
            "variacao_semanal_pct": wdo["variacao_semanal_pct"],
            "dolindex_dxy":        dxy["dolindex_dxy"],
            "dxy_variacao_pct":    dxy["dxy_variacao_pct"],
            "ccm_paridade":        paridade["ccm_paridade"],
            "cambio_implicito":    paridade["cambio_implicito"],
            "diagnostico":         paridade["diagnostico"]
        },
        "convergencia": {
            "rtcni_preco":           rtcni["rtcni_preco"],
            "spread_futuro_fisico":  spread,
            "spread_media_historica": SPREAD_MEDIO_HISTORICO,
            "spread_desvio_padrao":  SPREAD_DESVIO_PADRAO,
            "spread_zscore":         zscore,
            "alerta_convergencia":   alerta
        },
        "carrego": {
            "di1f27_taxa":            di.get("di1f27_taxa"),
            "di1f29_taxa":            di.get("di1f29_taxa"),
            "preco_justo_jan27":      carrego["preco_justo_jan27"],
            "spread_justo_vs_mercado": carrego["spread_justo_vs_mercado"]
        },
        "macro": {
            "brent":              brent["brent"],
            "brent_variacao_pct": brent["brent_variacao_pct"],
            "wasde_proximo":      "N/A",
            "conab_proximo":      "N/A"
        }
    }


if __name__ == "__main__":
    import sys
    pasta = sys.argv[1] if len(sys.argv) > 1 else PASTA
    dados = obter_macrodata(pasta, ccm_preco=66.82, zc_cents_bu=435.0)

    print("=== MACRO DATA ===")
    print(f"WDOFUT:        R$ {dados['cambio']['wdofut']}/1.000 USD")
    print(f"USD/BRL:       R$ {dados['cambio']['wdofut_usdbrl']}")
    print(f"DXY:           {dados['cambio']['dolindex_dxy']}")
    print(f"Brent:         USD {dados['macro']['brent']}/barril")
    print(f"Var Brent:     {dados['macro']['brent_variacao_pct']:+.2f}%")
    print(f"DI Jan/27:     {dados['carrego']['di1f27_taxa']}% a.a.")
    print(f"DI Jan/29:     {dados['carrego']['di1f29_taxa']}% a.a.")
    print(f"RTCNI:         R$ {dados['convergencia']['rtcni_preco']}/sc")
    print(f"Spread fut×fís: R$ {dados['convergencia']['spread_futuro_fisico']}/sc")
    print(f"Z-Score:       {dados['convergencia']['spread_zscore']}")
    print(f"Alerta:        {dados['convergencia']['alerta_convergencia']}")
    print(f"Paridade:      R$ {dados['cambio']['ccm_paridade']}/sc")
    print(f"Diagnóstico:   {dados['cambio']['diagnostico']}")
