# zc_cme.py — Coleta ZC Chicago via yfinance
# Milho Trader v1.0 — Fase 1
# Nota: yfinance é a única fonte gratuita disponível para ZC.
# Brent migrado para CSV local (BBR_X_0_Diário.csv) em macrodata.py

import yfinance as yf
from datetime import datetime, timedelta


def obter_zc_chicago() -> dict:
    """
    Coleta ZC Chicago (milho CME) via yfinance.
    Retorna dict com preco_cents_bu e variacao_semanal_pct.
    Em caso de falha, retorna valores None com flag de erro.
    """
    resultado = {
        "preco_cents_bu": None,
        "variacao_semanal_pct": None,
        "fonte": "yfinance",
        "erro": None
    }

    try:
        fim = datetime.today()
        inicio = fim - timedelta(days=14)  # 14 dias para garantir 2 pregões completos

        ticker = yf.Ticker("ZC=F")
        hist = ticker.history(start=inicio.strftime("%Y-%m-%d"),
                              end=fim.strftime("%Y-%m-%d"))

        if hist.empty or len(hist) < 2:
            resultado["erro"] = "Dados ZC insuficientes — menos de 2 pregões retornados"
            return resultado

        hist = hist.sort_index()

        preco_atual = float(hist["Close"].iloc[-1])
        preco_semana_anterior = float(hist["Close"].iloc[-6]) if len(hist) >= 6 else float(hist["Close"].iloc[0])

        variacao = ((preco_atual - preco_semana_anterior) / preco_semana_anterior) * 100

        resultado["preco_cents_bu"] = round(preco_atual, 2)
        resultado["variacao_semanal_pct"] = round(variacao, 2)

    except Exception as e:
        resultado["erro"] = f"Falha yfinance ZC: {str(e)}"

    return resultado


if __name__ == "__main__":
    dados = obter_zc_chicago()
    print("=== ZC Chicago ===")
    if dados["erro"]:
        print(f"ERRO: {dados['erro']}")
        print("ZC indisponível — pipeline continua sem este dado")
    else:
        print(f"ZC último: {dados['preco_cents_bu']} cents/bu")
        print(f"Variação semanal: {dados['variacao_semanal_pct']:+.2f}%")
