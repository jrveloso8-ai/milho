"""
gerar_resumo_analise.py
------------------------
Milho Trader (GPM v2.0) - Modulo de exportacao/QA do resumo de analise.

O QUE FAZ
Le o dados_milho.json (saida do pipeline.py, schema definido em SYSTEM_PROMPT_v1.0.md),
roda uma bateria de checagens de qualidade/consistencia sobre os dados, e grava um novo
arquivo milho_resumo_AAAAMMDD_HHMM.json contendo:
  1) meta          - quando foi exportado, idade dos dados, versao
  2) dados_originais - o dados_milho.json inalterado (auditoria)
  3) diagnostico_qualidade - status geral + lista de alertas encontrados
  4) resumo_consolidado - os poucos numeros/sinais que mais importam para decisao rapida

COMO INTEGRAR NO PIPELINE (C:\\Projetos Phyton\\Milho\\)
  1. Copie este arquivo para a pasta do projeto (junto de pipeline.py).
  2. No final de pipeline.py, apos gravar dados_milho.json, adicione:

        import gerar_resumo_analise as resumo
        resumo.gerar(caminho_json="dados_milho.json", pasta_saida=".")

  3. Rode o pipeline normalmente. Vai aparecer um arquivo
     milho_resumo_AAAAMMDD_HHMM.json na mesma pasta.
  4. Suba esse arquivo aqui na conversa com o Claude para eu validar os dados
     e te dar recomendacao (Go/No-Go, sizing, alertas de divergencia etc.).

Os nomes de campos abaixo seguem exatamente o schema do SYSTEM_PROMPT_v1.0.md.
Se o pipeline.py usa nomes diferentes internamente, ajuste o dicionario antes
de chamar gerar(), ou adapte os "getters" (funcao _get) abaixo.

Nao ha dependencias externas - so biblioteca padrao do Python 3.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Optional


VERSAO_EXPORT = "1.0"

# ---------------------------------------------------------------------------
# Helpers de acesso seguro (evita KeyError quando o pipeline ainda nao
# preencheu algum campo opcional)
# ---------------------------------------------------------------------------

def _get(d: dict, path: str, default: Any = None) -> Any:
    """Acessa d['a']['b']['c'] via path='a.b.c', sem estourar excecao."""
    cur: Any = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _parse_data_ref(data_str: Optional[str]) -> Optional[datetime]:
    if not data_str:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(data_str, fmt)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Checagens de qualidade / consistencia
# ---------------------------------------------------------------------------

CAMPOS_OBRIGATORIOS = [
    "data_referencia",
    "ccm.ultimo_preco",
    "ccm.variacao_semanal_pct",
    "ccm.vencimento_ativo",
    "ccm.ema9",
    "ccm.ema20",
    "ccm.sinal_ema920",
    "ccm.sinal_91",
    "ccm.atr14",
    "estrutura_curva",
    "convergencia.rtcni_preco",
    "convergencia.spread_futuro_fisico",
    "convergencia.spread_zscore",
    "carrego.di1f27_taxa",
    "carrego.spread_justo_vs_mercado",
    "cambio.wdofut_usdbrl",
    "cambio.diagnostico",
    "zc_cme.preco_cents_bu",
    "fundamentos.vies_fundamental",
    "sizing.contratos.conservador",
    "sizing.contratos.moderado",
    "sizing.contratos.arrojado",
]

ENUMS_VALIDOS = {
    "ccm.sinal_ema920": {"COMPRA", "VENDA", "NEUTRO"},
    "ccm.sinal_91": {"COMPRA", "VENDA", "NEUTRO", "AGUARDANDO"},
    "estrutura_curva": {"CONTANGO", "BACKWARDATION", "FLAT"},
    "cambio.diagnostico": {"MILHO", "CAMBIO", "MISTO"},
    "fundamentos.vies_fundamental": {"ALTISTA", "BAIXISTA", "NEUTRO"},
}

# Limiares ajustaveis - calibrados a partir do SYSTEM_PROMPT_v1.0.md e do
# historico de backtest (spread medio R$6,51/sc, desvio R$3,50/sc)
LIMIAR_STALENESS_DIAS = 2          # pipeline roda diario -> dado com mais de X dias e suspeito
LIMIAR_VARIACAO_SEMANAL_PCT = 15   # variacao semanal acima disso (modulo) e incomum p/ milho
LIMIAR_ZSCORE_ALERTA = 1.5         # regra 3 do SYSTEM_PROMPT: gatilho obrigatorio de alerta
LIMIAR_ZSCORE_EXTREMO = 3.0        # acima disso, tratar como outlier / possivel erro de dado
LIMIAR_SPREAD_JUSTO_DISTORCAO = 3.0  # R$/sc de diferenca entre preco justo (DI) e mercado


def validar(dados: dict) -> dict:
    """Roda todas as checagens e devolve o bloco diagnostico_qualidade."""
    alertas: list[dict] = []
    campos_faltantes: list[str] = []

    # 1. completude -----------------------------------------------------
    for campo in CAMPOS_OBRIGATORIOS:
        if _get(dados, campo) in (None, ""):
            campos_faltantes.append(campo)

    score_completude = round(
        100 * (1 - len(campos_faltantes) / len(CAMPOS_OBRIGATORIOS)), 1
    )

    # 2. enums validos ----------------------------------------------------
    for campo, validos in ENUMS_VALIDOS.items():
        valor = _get(dados, campo)
        if valor is not None and valor not in validos:
            alertas.append({
                "nivel": "ERRO",
                "regra": "enum_invalido",
                "campo": campo,
                "detalhe": f"Valor '{valor}' fora do conjunto esperado {sorted(validos)}",
            })

    # 3. staleness dos dados ----------------------------------------------
    data_ref = _parse_data_ref(_get(dados, "data_referencia"))
    if data_ref is None:
        alertas.append({
            "nivel": "ERRO",
            "regra": "staleness",
            "campo": "data_referencia",
            "detalhe": "Nao foi possivel interpretar data_referencia (esperado DD/MM/AAAA)",
        })
    else:
        idade_dias = (datetime.now() - data_ref).days
        if idade_dias > LIMIAR_STALENESS_DIAS:
            alertas.append({
                "nivel": "ATENCAO",
                "regra": "staleness",
                "campo": "data_referencia",
                "detalhe": f"Dado tem {idade_dias} dia(s), acima do limiar de {LIMIAR_STALENESS_DIAS} dia(s). Confirme se o pipeline rodou hoje.",
            })

    # 4. variacao semanal fora do comum ------------------------------------
    var_ccm = _get(dados, "ccm.variacao_semanal_pct")
    if isinstance(var_ccm, (int, float)) and abs(var_ccm) > LIMIAR_VARIACAO_SEMANAL_PCT:
        alertas.append({
            "nivel": "ATENCAO",
            "regra": "variacao_incomum",
            "campo": "ccm.variacao_semanal_pct",
            "detalhe": f"Variacao semanal de {var_ccm:+.2f}% excede limiar de {LIMIAR_VARIACAO_SEMANAL_PCT}%. Verificar se e evento real (WASDE, cambio) ou erro de captura.",
        })

    # 5. convergencia futuro x fisico (regra 3 do SYSTEM_PROMPT) -----------
    zscore = _get(dados, "convergencia.spread_zscore")
    if isinstance(zscore, (int, float)):
        if abs(zscore) >= LIMIAR_ZSCORE_EXTREMO:
            alertas.append({
                "nivel": "ATENCAO",
                "regra": "convergencia_zscore",
                "campo": "convergencia.spread_zscore",
                "detalhe": f"Z-score {zscore:+.2f} extremo (>= {LIMIAR_ZSCORE_EXTREMO}). Checar se RTCNI/CCM foram capturados corretamente antes de confiar no alerta.",
            })
        elif abs(zscore) >= LIMIAR_ZSCORE_ALERTA:
            alertas.append({
                "nivel": "INFO",
                "regra": "convergencia_zscore",
                "campo": "convergencia.spread_zscore",
                "detalhe": f"Z-score {zscore:+.2f} >= {LIMIAR_ZSCORE_ALERTA}: alerta de convergencia deve constar na Secao Tecnica (regra 3 do SYSTEM_PROMPT).",
            })

    # 6. custo de carrego / DI ---------------------------------------------
    spread_justo = _get(dados, "carrego.spread_justo_vs_mercado")
    if isinstance(spread_justo, (int, float)) and abs(spread_justo) >= LIMIAR_SPREAD_JUSTO_DISTORCAO:
        alertas.append({
            "nivel": "INFO",
            "regra": "carrego_di",
            "campo": "carrego.spread_justo_vs_mercado",
            "detalhe": f"Contrato futuro {'acima' if spread_justo > 0 else 'abaixo'} do preco justo teorico (DI) em R$ {abs(spread_justo):.2f}/sc. Distorcao real ou contango/backwardation normal? Contextualizar (regra 4).",
        })

    # 7. divergencia sinal tecnico vs vies fundamental (regra 5) -----------
    sinal = _get(dados, "ccm.sinal_ema920")
    vies = _get(dados, "fundamentos.vies_fundamental")
    if sinal == "COMPRA" and vies == "BAIXISTA":
        alertas.append({
            "nivel": "ATENCAO",
            "regra": "divergencia_sinal_fundamento",
            "campo": "ccm.sinal_ema920 / fundamentos.vies_fundamental",
            "detalhe": "Sinal tecnico de COMPRA com vies fundamental BAIXISTA. Regra 5 exige declarar a divergencia explicitamente no relatorio.",
        })
    elif sinal == "VENDA" and vies == "ALTISTA":
        alertas.append({
            "nivel": "ATENCAO",
            "regra": "divergencia_sinal_fundamento",
            "campo": "ccm.sinal_ema920 / fundamentos.vies_fundamental",
            "detalhe": "Sinal tecnico de VENDA com vies fundamental ALTISTA. Regra 5 exige declarar a divergencia explicitamente no relatorio.",
        })

    # 8. sizing coerente entre perfis --------------------------------------
    stop_cons = _get(dados, "sizing.stop_mensal.conservador")
    stop_mod = _get(dados, "sizing.stop_mensal.moderado")
    stop_arr = _get(dados, "sizing.stop_mensal.arrojado")
    if all(isinstance(v, (int, float)) for v in (stop_cons, stop_mod, stop_arr)):
        if not (stop_mod == 2 * stop_cons and stop_arr == 4 * stop_cons):
            alertas.append({
                "nivel": "INFO",
                "regra": "sizing_consistencia",
                "campo": "sizing.stop_mensal",
                "detalhe": f"Proporcao fora do padrao 1x/2x/4x entre perfis (conservador={stop_cons}, moderado={stop_mod}, arrojado={stop_arr}). Confirmar se foi intencional.",
            })

    # 9. dissociacao cambio x milho (regra 2) -------------------------------
    var_cambio = _get(dados, "cambio.variacao_semanal_pct")
    diagnostico_cambio = _get(dados, "cambio.diagnostico")
    if isinstance(var_ccm, (int, float)) and isinstance(var_cambio, (int, float)):
        # heuristica simples: se cambio se moveu muito mais que o CCM, o
        # diagnostico deveria apontar CAMBIO ou MISTO, nao MILHO isolado.
        if abs(var_cambio) > 2 * max(abs(var_ccm), 0.01) and diagnostico_cambio == "MILHO":
            alertas.append({
                "nivel": "ATENCAO",
                "regra": "dissociacao_cambio",
                "campo": "cambio.diagnostico",
                "detalhe": f"WDOFUT variou {var_cambio:+.2f}% (bem mais que o CCM, {var_ccm:+.2f}%), mas diagnostico esta como MILHO. Revisar classificacao (regra 2).",
            })

    # status geral ----------------------------------------------------------
    if campos_faltantes or any(a["nivel"] == "ERRO" for a in alertas):
        status_geral = "CRITICO"
    elif any(a["nivel"] == "ATENCAO" for a in alertas):
        status_geral = "ATENCAO"
    else:
        status_geral = "OK"

    return {
        "status_geral": status_geral,
        "score_completude_pct": score_completude,
        "campos_faltantes": campos_faltantes,
        "alertas": alertas,
    }


def montar_resumo_consolidado(dados: dict) -> dict:
    """Os poucos campos que mais importam para uma decisao rapida."""
    return {
        "data_referencia": _get(dados, "data_referencia"),
        "vencimento_ativo": _get(dados, "ccm.vencimento_ativo"),
        "ultimo_preco": _get(dados, "ccm.ultimo_preco"),
        "sinal_ema920": _get(dados, "ccm.sinal_ema920"),
        "sinal_91": _get(dados, "ccm.sinal_91"),
        "estrutura_curva": _get(dados, "estrutura_curva"),
        "spread_zscore_convergencia": _get(dados, "convergencia.spread_zscore"),
        "diagnostico_cambio": _get(dados, "cambio.diagnostico"),
        "vies_fundamental": _get(dados, "fundamentos.vies_fundamental"),
        "destaque_semana": _get(dados, "destaque_semana"),
    }


# ---------------------------------------------------------------------------
# Entrada principal
# ---------------------------------------------------------------------------

def gerar(caminho_json: str = "dados_milho.json", pasta_saida: str = ".") -> str:
    """Le dados_milho.json, valida e grava milho_resumo_AAAAMMDD_HHMM.json.

    Retorna o caminho do arquivo gerado.
    """
    with open(caminho_json, "r", encoding="utf-8") as f:
        dados = json.load(f)

    diagnostico = validar(dados)
    resumo_consolidado = montar_resumo_consolidado(dados)

    agora = datetime.now()
    saida = {
        "meta": {
            "exportado_em": agora.isoformat(timespec="seconds"),
            "fonte": os.path.basename(caminho_json),
            "versao_export": VERSAO_EXPORT,
        },
        "resumo_consolidado": resumo_consolidado,
        "diagnostico_qualidade": diagnostico,
        "dados_originais": dados,
    }

    nome_arquivo = f"milho_resumo_{agora.strftime('%Y%m%d_%H%M')}.json"
    caminho_saida = os.path.join(pasta_saida, nome_arquivo)
    with open(caminho_saida, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)

    print(f"[gerar_resumo_analise] Status geral: {diagnostico['status_geral']}")
    print(f"[gerar_resumo_analise] Completude: {diagnostico['score_completude_pct']}%")
    print(f"[gerar_resumo_analise] Alertas: {len(diagnostico['alertas'])}")
    print(f"[gerar_resumo_analise] Arquivo gerado: {caminho_saida}")
    return caminho_saida


if __name__ == "__main__":
    import sys
    caminho = sys.argv[1] if len(sys.argv) > 1 else "dados_milho.json"
    gerar(caminho_json=caminho)