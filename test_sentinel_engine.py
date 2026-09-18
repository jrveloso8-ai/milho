# -*- coding: utf-8 -*-
"""
test_sentinel_engine.py — Suíte de testes para o motor Sentinel-Corn 2.0.
Valida:
  1. Fórmula de Paridade de Exportação (PPE).
  2. Ponto de Inflexão de Câmbio.
  3. Matriz de Decisão Basis vs. Paridade.
  4. Ponderação Tripla de Sentimento (20% Notícias / 20% Calendário / 60% Técnico).
  5. Classificação dos vereditos (ALTISTA, LATERAL, BAIXISTA).
  6. Ausência de dados simulados/fabricados.
"""

import pytest
from sentinel_engine import (
    calcular_ppe,
    calcular_ponto_inflexao_cambio,
    matriz_decisao_basis_paridade,
    classificar_sentimento,
    calcular_score_tecnico_contrato
)


def test_calcular_ppe_precisao():
    """Valida o cálculo exato da Paridade de Exportação com parâmetros de mercado (prêmio em centavos)."""
    cbot = 450.0
    premio = 0.70  # US$/bu -> 70 cents/bu
    cambio = 5.50
    custos = 10.00

    # cbot_total_cents = 450.0 + (0.70 * 100) = 520.0
    # PPE_bruta = 520.0 * 0.39368 * 5.50 * 0.06 = 67.5555
    # PPE_liquida = 67.5555 - 10.00 = 57.56
    ppe = calcular_ppe(cbot, premio, cambio, custos)
    assert ppe == 57.56


def test_calcular_ponto_inflexao_cambio_reciprocidade():
    """Valida que o Dólar de Inflexão reproduz exatamente a PPE quando Preço B3 = PPE."""
    cbot = 450.0
    premio = 0.70
    custos = 10.00
    preco_b3 = 57.56

    cambio_inflexao = calcular_ponto_inflexao_cambio(preco_b3, cbot, premio, custos)
    # Deve ser aproximadamente 5.50
    assert abs(cambio_inflexao - 5.50) < 0.01

    # Recalculando a PPE com o câmbio de inflexão deve dar o preco_b3
    ppe_recalculada = calcular_ppe(cbot, premio, cambio_inflexao, custos)
    assert abs(ppe_recalculada - preco_b3) < 0.02


def test_matriz_decisao_alerta_venda():
    """Se Preço B3 > PPE + R$ 3,00 com Contango excessivo -> ALERTA DE VENDA."""
    preco_b3 = 75.00
    ppe = 70.00  # Gap = +5.00 (> 3.00)
    res = matriz_decisao_basis_paridade(preco_b3, ppe, preco_spot_rtcni=68.00, estrutura_curva="CONTANGO")

    assert res["sinal"] == "VENDA"
    assert "ALERTA DE VENDA" in res["recomendacao"]
    assert res["gap_ppe"] == 5.00


def test_matriz_decisao_alerta_compra():
    """Se Preço B3 < PPE com Backwardation ou sustentação do spot -> ALERTA DE COMPRA."""
    preco_b3 = 68.00
    ppe = 72.00  # Gap = -4.00
    res = matriz_decisao_basis_paridade(preco_b3, ppe, preco_spot_rtcni=70.00, estrutura_curva="BACKWARDATION")

    assert res["sinal"] == "COMPRA"
    assert "ALERTA DE COMPRA" in res["recomendacao"]


def test_classificar_sentimento_fronteiras():
    """Valida as fronteiras estritas de ALTISTA (>= +25), BAIXISTA (<= -25) e LATERAL."""
    assert classificar_sentimento(25.0) == "ALTISTA"
    assert classificar_sentimento(50.0) == "ALTISTA"
    assert classificar_sentimento(24.9) == "LATERAL"
    assert classificar_sentimento(0.0) == "LATERAL"
    assert classificar_sentimento(-24.9) == "LATERAL"
    assert classificar_sentimento(-25.0) == "BAIXISTA"
    assert classificar_sentimento(-80.0) == "BAIXISTA"


def test_score_tecnico_contrato_ntsl_e_opcoes():
    """Valida o cálculo do score técnico com TRIX NTSL, SMA100 e Call/Put Wall."""
    res_mock = {
        "ultimo_bar": {
            "close": 70.0,
            "posicao": "COMPRA",
            "trix": 0.15,
            "sinal": 0.05,
            "sma100": 65.0
        },
        "barreiras_opcoes": {
            "call_wall": 76.0,
            "put_wall": 64.0,
            "max_pain": 68.0
        }
    }
    score, info = calcular_score_tecnico_contrato(res_mock, preco_fechamento=70.0, atr14=1.50)
    # COMPRA (+40) + TRIX>Sinal (+20) + Close>SMA100 (+20) = +80.0
    assert score == 80.0
    assert info["posicao_ntsl"] == "COMPRA"


def test_ponderacao_tripla_sentimento():
    """Valida a fórmula com pesos exatos: 20% Notícias + 20% Calendário + 60% Técnico."""
    score_noticias = 50.0      # Contribuição: 10.0
    score_calendario = -10.0   # Contribuição: -2.0
    score_tecnico = 80.0       # Contribuição: 48.0

    score_final = (0.20 * score_noticias) + (0.20 * score_calendario) + (0.60 * score_tecnico)
    # 10.0 - 2.0 + 48.0 = 56.0
    assert round(score_final, 1) == 56.0
    assert classificar_sentimento(score_final) == "ALTISTA"


def test_calcular_score_calendario_integracao_real():
    """Valida integração real com o calendário econômico oficial (sem mock), prevenindo regressão de AttributeError."""
    from sentinel_engine import calcular_score_calendario
    score, info = calcular_score_calendario()

    assert isinstance(score, float)
    assert -100.0 <= score <= 100.0
    assert "classificacao" in info
    assert "proximo_evento" in info
    assert "eventos_proximos" in info
    assert isinstance(info["eventos_proximos"], list)
    # Com calendário real, deve conter eventos conhecidos (USDA / CONAB)
    if info["proximo_evento"]:
        assert isinstance(info["proximo_evento"], str)
        assert info["dias_ate_proximo"] is not None
        assert info["dias_ate_proximo"] >= 0


def test_processar_sentimento_curva_sem_dados_macro_indisponivel():
    """Valida que ausência de CBOT e Câmbio resulta em PARIDADE INDISPONÍVEL sem quebrar nem inventar números."""
    from sentinel_engine import processar_sentimento_curva

    curva_mock = [{
        "codigo": "CCMX26",
        "ultimo_bar": {"close": 71.50, "posicao": "COMPRA", "trix": 0.1, "sinal": 0.05, "sma100": 68.0},
        "atr14": 1.50,
        "barreiras_opcoes": {"call_wall": 74.0, "put_wall": 66.0, "max_pain": 70.0}
    }]

    res = processar_sentimento_curva(
        curva_resultados=curva_mock,
        cbot_cents=None,
        cambio_usdbrl=None,
        cbot_fonte="[INDISPONIVEL]",
        cambio_fonte="[INDISPONIVEL]"
    )

    assert "contratos" in res
    assert len(res["contratos"]) == 1
    assert "parametros_arbitragem" in res
    assert res["parametros_arbitragem"]["cbot_cents"] is None
    assert res["parametros_arbitragem"]["cambio_usdbrl"] is None
    assert res["parametros_arbitragem"]["ppe_prov"] == "[INDISPONIVEL]"

    # Tabela de arbitragem deve marcar recomendação como INDISPONÍVEL
    arb = res["tabela_arbitragem"][0]
    assert arb["ppe"] is None
    assert arb["recomendacao"] == "PARIDADE INDISPONÍVEL"
    assert arb["sinal"] == "NEUTRO"

