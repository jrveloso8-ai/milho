# -*- coding: utf-8 -*-
"""
test_ccm_trix_curva.py — Suíte de testes automatizados (pytest) para o módulo TRIX v5 por contrato (curva CCM).
Atende ao item 6.1 do Portão de Auditoria.

Coberturas obrigatórias:
  1. montar_serie_ajustada():
     - Cálculo exato do offset aditivo (primeiro_close_real - ultimo_close_seed).
     - Marcação correta de is_sintetico (True para seed, False para real em ambos os lados da costura).
     - Truncamento do seed antes do primeiro pregão real.
  2. classificar_proveniencia():
     - Fronteira exata dos 100 pregões reais (caso de borda: 99º pregão é ESTIMADO, 100º pregão é DERIVADO).
     - Open proxy no 1º pregão real classificado como ESTIMADO (Opção a) e 2º pregão real como MEDIDO.
     - OHLC em pregão real classificado como MEDIDO, em sintético como ESTIMADO.
  3. coletar_historico_ccm() (em ingestao_brapi.py):
     - Open nulo tratado via proxy (Close anterior).
     - Descarte de linha de calendário sem negócio real (Close nulo ou não positivo).
     - Erro de rede / timeout (RequestException) tratado defensivamente sem quebrar.
     - Erro de autorização / token ausente / HTTP 401 tratado defensivamente sem quebrar.
     * TODAS as chamadas à API são 100% mockadas — a suíte NUNCA bate na API real.
"""

from unittest.mock import MagicMock, patch
import numpy as np
import pandas as pd
import pytest
import requests

from ccm_trix_curva import (
    montar_serie_ajustada,
    classificar_proveniencia,
    calcular_transicao_derivado,
)
import ingestao_brapi as ib


# ══════════════════════════════════════════════════════════════════════════
# 1. TESTES DE montar_serie_ajustada()
# ══════════════════════════════════════════════════════════════════════════

def test_montar_serie_ajustada_offset_e_is_sintetico():
    """Valida o offset aditivo e a marcação de is_sintetico em ambos os lados da costura."""
    datas_seed = pd.date_range("2026-01-01", periods=5, freq="D")
    df_seed = pd.DataFrame({
        "Data": datas_seed,
        "Open": [50.0, 51.0, 52.0, 53.0, 54.0],
        "High": [51.0, 52.0, 53.0, 54.0, 55.0],
        "Low": [49.0, 50.0, 51.0, 52.0, 53.0],
        "Close": [50.5, 51.5, 52.5, 53.5, 54.5],
        "Volume": [100.0] * 5,
        "Qtd": [10.0] * 5,
    })

    # O contrato real inicia em 2026-01-04 (sobrepondo 2026-01-04 e 2026-01-05 do seed)
    datas_real = pd.date_range("2026-01-04", periods=4, freq="D")
    df_real = pd.DataFrame({
        "Data": datas_real,
        "Open": [60.0, 61.0, 62.0, 63.0],
        "High": [61.0, 62.0, 63.0, 64.0],
        "Low": [59.0, 60.0, 61.0, 62.0],
        "Close": [60.5, 61.5, 62.5, 63.5],
        "Volume": [200.0] * 4,
        "Qtd": [20.0] * 4,
    })

    # Executa a costura
    df_adj = montar_serie_ajustada("CCMZ26", df_real, df_seed)

    # 1. Truncamento: O seed deve ter sido truncado antes de 2026-01-04 (apenas 01, 02 e 03)
    # Total de registros: 3 do seed + 4 do real = 7
    assert len(df_adj) == 7

    # 2. Offset aditivo:
    # Último Close do seed truncado (2026-01-03) era 52.5
    # Primeiro Close do real (2026-01-04) é 60.5
    # Offset esperado = 60.5 - 52.5 = 8.0
    # O Close ajustado do seed em 2026-01-03 deve ser 52.5 + 8.0 = 60.5
    assert np.isclose(df_adj.loc[df_adj["Data"] == "2026-01-03", "Close"].iloc[0], 60.5)
    assert np.isclose(df_adj.loc[df_adj["Data"] == "2026-01-01", "Close"].iloc[0], 50.5 + 8.0)
    assert np.isclose(df_adj.loc[df_adj["Data"] == "2026-01-01", "High"].iloc[0], 51.0 + 8.0)

    # 3. Marcação de is_sintetico em ambos os lados da costura:
    seed_part = df_adj[df_adj["Data"] < "2026-01-04"]
    real_part = df_adj[df_adj["Data"] >= "2026-01-04"]

    assert len(seed_part) == 3
    assert seed_part["is_sintetico"].all() == True

    assert len(real_part) == 4
    assert (real_part["is_sintetico"] == False).all()


def test_montar_serie_ajustada_validacoes_defensivas():
    """Valida casos de borda e exceções de montar_serie_ajustada()."""
    df_seed = pd.DataFrame({
        "Data": pd.date_range("2026-01-01", periods=3),
        "Close": [50.0, 51.0, 52.0],
    })

    # Contrato nulo ou vazio levanta ValueError
    with pytest.raises(ValueError):
        montar_serie_ajustada("CCMZ26", None, df_seed)

    with pytest.raises(ValueError):
        montar_serie_ajustada("CCMZ26", pd.DataFrame(), df_seed)


# ══════════════════════════════════════════════════════════════════════════
# 2. TESTES DE classificar_proveniencia()
# ══════════════════════════════════════════════════════════════════════════

def test_classificar_proveniencia_fronteira_100_pregoes_reais():
    """
    Testa o caso de borda exato da fronteira dos 100 pregões reais:
      - Pregão 99 (índice 98 dos reais): janela de 100 barras toca o seed -> ESTIMADO.
      - Pregão 100 (índice 99 dos reais): janela de 100 barras é 100% real -> DERIVADO.
    """
    # Cria série com 20 pregões sintéticos + 120 pregões reais
    datas = pd.date_range("2025-01-01", periods=140, freq="B")
    is_sint = [True] * 20 + [False] * 120

    df = pd.DataFrame({
        "Data": datas,
        "Open": [70.0] * 140,
        "High": [72.0] * 140,
        "Low": [69.0] * 140,
        "Close": [71.0] * 140,
        "Volume": [1000.0] * 140,
        "Qtd": [100.0] * 140,
        "is_sintetico": is_sint,
    })

    # O primeiro dia real é o índice 20.
    # O 99º dia real é o índice 20 + 99 - 1 = 118.
    # A janela de 100 barras para o índice 118 vai de (118 - 100 + 1) = 19 até 118.
    # O índice 19 tem is_sintetico = True -> CONTAGIADO -> ESTIMADO!
    idx_99 = 118
    dt_99 = df.iloc[idx_99]["Data"]
    assert classificar_proveniencia(df, "trend_sma100", dt_99) == "ESTIMADO"
    assert classificar_proveniencia(df, "trix", dt_99) == "ESTIMADO"
    assert classificar_proveniencia(df, "trix_sinal", dt_99) == "ESTIMADO"
    assert classificar_proveniencia(df, "posicao_trix_v5", dt_99) == "ESTIMADO"

    # O 100º dia real é o índice 20 + 100 - 1 = 119.
    # A janela de 100 barras para o índice 119 vai de (119 - 100 + 1) = 20 até 119.
    # Todos os índices de 20 a 119 têm is_sintetico = False -> NÃO CONTAGIADO -> DERIVADO!
    idx_100 = 119
    dt_100 = df.iloc[idx_100]["Data"]
    assert classificar_proveniencia(df, "trend_sma100", dt_100) == "DERIVADO"
    assert classificar_proveniencia(df, "trix", dt_100) == "DERIVADO"
    assert classificar_proveniencia(df, "trix_sinal", dt_100) == "DERIVADO"
    assert classificar_proveniencia(df, "posicao_trix_v5", dt_100) == "DERIVADO"

    # Valida também a função de transição auxiliar
    trans = calcular_transicao_derivado(df)
    assert trans["sma100_suficiente"] == True
    assert trans["total_pregoes_reais"] == 120
    assert trans["data_transicao"] == dt_100.strftime("%Y-%m-%d")
    assert trans["classificacao_atual"] == "DERIVADO"


def test_classificar_proveniencia_open_proxy_opcao_a():
    """
    Testa a Opção a para o Open Proxy:
      - 1º pregão real: Open é ESTIMADO (pois decorre do último Close sintético).
      - 2º pregão real em diante: Open é MEDIDO.
      - Close, High, Low no pregão real são MEDIDO.
      - Qualquer preço no pregão sintético é ESTIMADO.
    """
    datas = pd.date_range("2026-01-01", periods=5, freq="B")
    is_sint = [True, True, False, False, False]

    df = pd.DataFrame({
        "Data": datas,
        "Open": [70.0, 70.5, 71.0, 71.5, 72.0],
        "High": [71.0, 71.5, 72.0, 72.5, 73.0],
        "Low": [69.0, 69.5, 70.0, 70.5, 71.0],
        "Close": [70.5, 71.0, 71.5, 72.0, 72.5],
        "Volume": [500.0] * 5,
        "Qtd": [50.0] * 5,
        "is_sintetico": is_sint,
    })

    # Dia sintético (índice 1)
    assert classificar_proveniencia(df, "Close", datas[1]) == "ESTIMADO"
    assert classificar_proveniencia(df, "Open", datas[1]) == "ESTIMADO"

    # 1º pregão real (índice 2)
    assert classificar_proveniencia(df, "Close", datas[2]) == "MEDIDO"
    assert classificar_proveniencia(df, "High", datas[2]) == "MEDIDO"
    assert classificar_proveniencia(df, "Low", datas[2]) == "MEDIDO"
    assert classificar_proveniencia(df, "Open", datas[2]) == "ESTIMADO"  # Exceção da Opção a

    # 2º pregão real (índice 3)
    assert classificar_proveniencia(df, "Close", datas[3]) == "MEDIDO"
    assert classificar_proveniencia(df, "Open", datas[3]) == "MEDIDO"    # Já é MEDIDO


# ══════════════════════════════════════════════════════════════════════════
# 3. TESTES DE coletar_historico_ccm() (MOCK BRAPI)
# ══════════════════════════════════════════════════════════════════════════

def test_coletar_historico_ccm_open_nulo_e_proxy():
    """Valida tratamento defensivo quando o Open vem nulo da BRAPI (aplica proxy)."""
    mock_payload = {
        "future": {
            "symbol": "CCMX26",
            "history": [
                {
                    "date": 1726000000,
                    "open": None,       # Open nulo!
                    "high": 75.0,
                    "low": 73.0,
                    "close": 74.0,
                    "volume": 100,
                    "trades": 10,
                },
                {
                    "date": 1726086400,
                    "open": None,       # Open nulo!
                    "high": 76.0,
                    "low": 74.0,
                    "close": 75.5,
                    "volume": 150,
                    "trades": 15,
                }
            ]
        }
    }

    with patch("ingestao_brapi._get", return_value=mock_payload):
        df = ib.coletar_historico_ccm("CCMX26")

        assert df is not None
        assert len(df) == 2
        # Primeiro bar usa o próprio Close como proxy (74.0)
        assert df["Open"].iloc[0] == 74.0
        # Segundo bar usa o Close anterior como proxy (74.0)
        assert df["Open"].iloc[1] == 74.0
        assert df["Close"].iloc[1] == 75.5


def test_coletar_historico_ccm_descarte_linha_sem_negocio():
    """Valida descarte de linhas sem negócio (Close nulo ou menor igual a zero)."""
    mock_payload = {
        "future": {
            "symbol": "CCMX26",
            "history": [
                {
                    "date": 1726000000,
                    "open": 74.0,
                    "high": 75.0,
                    "low": 73.0,
                    "close": 74.0,
                    "volume": 100,
                    "trades": 10,
                },
                {
                    "date": 1726086400,
                    "open": None,
                    "high": None,
                    "low": None,
                    "close": None,      # Sem negócio / feriado
                    "volume": 0,
                    "trades": 0,
                },
                {
                    "date": 1726172800,
                    "open": 0,
                    "high": 0,
                    "low": 0,
                    "close": 0,         # Close zero (descartar)
                    "volume": 0,
                    "trades": 0,
                },
                {
                    "date": 1726259200,
                    "open": 74.5,
                    "high": 75.0,
                    "low": 74.0,
                    "close": 74.8,
                    "volume": 50,
                    "trades": 5,
                }
            ]
        }
    }

    with patch("ingestao_brapi._get", return_value=mock_payload):
        df = ib.coletar_historico_ccm("CCMX26")

        assert df is not None
        # Deve ter descartado as duas linhas sem negócio
        assert len(df) == 2
        assert list(df["Close"]) == [74.0, 74.8]


def test_coletar_historico_ccm_erro_rede_ou_token():
    """Valida que erros de rede ou token ausente retornam None sem lançar exceção."""
    # 1. Simula token ausente ou _get retornando None
    with patch("ingestao_brapi._get", return_value=None):
        res = ib.coletar_historico_ccm("CCMX26")
        assert res is None

    # 2. Simula exceção de conexão do requests dentro de _get
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Falha de DNS")):
        # _get trata internamente e retorna None
        res = ib._get("/v2/futures/historical", params={"symbol": "CCMX26"})
        assert res is None

    # 3. Simula HTTP 401 Unauthorized
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("401 Client Error: Unauthorized")
    with patch("requests.get", return_value=mock_resp):
        res = ib._get("/v2/futures/historical", params={"symbol": "CCMX26"})
        assert res is None
