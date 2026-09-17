# -*- coding: utf-8 -*-
"""
sazonalidade_milho.py — Módulo de Sazonalidade Proprietária CCM B3
Milho Trader | GPM v2.0 | Fase 3B

Fonte: CCMFUT_F_0_Diário.csv (Profit/Genial)
Período base: Jul/2024 → Jun/2026 (497 observações)
Metodologia: desvio percentual relativo à média anual (elimina viés de nível de preço)

Uso standalone:
    python sazonalidade_milho.py

Uso como módulo (chamado pelo pipeline.py):
    from sazonalidade_milho import calcular_sazonalidade
    dados_saz = calcular_sazonalidade(pasta_dados, data_referencia)
"""

import os
import csv
import math
import json
import time
from datetime import datetime, date
from collections import defaultdict

# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────

NOME_CSV = "CCMFUT_F_0_Diário.csv"

MESES_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
            "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

# Fase agrícola por mês
FASES_AGRICOLAS = {
    1:  "PLANTIO_SAFRINHA",
    2:  "COLHEITA_VERAO",
    3:  "COLHEITA_VERAO",
    4:  "COLHEITA_VERAO",
    5:  "COLHEITA_SAFRINHA",
    6:  "COLHEITA_SAFRINHA",
    7:  "COLHEITA_SAFRINHA",
    8:  "ENTRESSAFRA",
    9:  "PLANTIO_VERAO",
    10: "PLANTIO_VERAO",
    11: "ALTA_SAZONAL",
    12: "ALTA_SAZONAL",
}

DESCRICAO_FASES = {
    "PLANTIO_SAFRINHA":  "Plantio safrinha (2ª safra) e crescimento do milho verão",
    "COLHEITA_VERAO":    "Colheita do milho verão (1ª safra) — oferta crescente",
    "COLHEITA_SAFRINHA": "Colheita da safrinha (2ª safra) — pressão máxima de oferta",
    "ENTRESSAFRA":       "Entressafra — estoques em normalização, preços em recuperação",
    "PLANTIO_VERAO":     "Plantio do milho verão — demanda cresce, preços sobem",
    "ALTA_SAZONAL":      "Alta sazonal pré-colheita — janela historicamente bullish",
}

# Viés esperado por fase
VIES_FASE = {
    "PLANTIO_SAFRINHA":  "NEUTRO",
    "COLHEITA_VERAO":    "BAIXISTA",
    "COLHEITA_SAFRINHA": "BAIXISTA",
    "ENTRESSAFRA":       "ALTISTA",
    "PLANTIO_VERAO":     "ALTISTA",
    "ALTA_SAZONAL":      "ALTISTA",
}

# ─────────────────────────────────────────────
# LEITURA E PROCESSAMENTO DO CSV
# ─────────────────────────────────────────────

_CAMPOS_PADRAO = ["Ativo", "Data", "Abertura", "Maximo", "Minimo", "Fechamento", "Volume", "Quantidade"]


def _ler_csv(caminho_csv: str) -> list:
    """
    Lê o CCMFUT CSV em Latin-1 com separador ';' e retorna lista de dicts.

    Defensivo: o export do Profit às vezes grava o arquivo SEM a linha de
    cabeçalho (mesma causa raiz tratada em leitor_csv.py). Se a primeira
    célula não for 'Ativo', assume que o arquivo já começa com dados e
    fornece os nomes de campo manualmente ao DictReader — senão o parser
    trata a primeira linha de dado como cabeçalho e perde tudo silenciosamente.
    """
    # O exportador do Profit deixa bytes NUL de sobra no final deste arquivo
    # (confirmado em produção em 10/07/2026 — 1.376 bytes NUL após a última
    # linha, provavelmente um buffer de escrita de tamanho fixo não truncado).
    # O parser csv da stdlib rejeita qualquer linha com NUL ("line contains
    # NUL"); removemos os bytes antes de parsear. Mantemos um retry curto por
    # baixo só para locks de I/O genuinamente transitórios.
    ultima_excecao = None
    for tentativa in range(3):
        try:
            registros = []
            with open(caminho_csv, encoding="latin-1") as f:
                conteudo = f.read().replace("\x00", "")
            linhas = conteudo.splitlines()
            primeira_celula = linhas[0].split(";")[0].strip() if linhas else ""
            tem_cabecalho = primeira_celula.lower() == "ativo"
            fieldnames = None if tem_cabecalho else _CAMPOS_PADRAO
            reader = csv.DictReader(linhas, delimiter=";", fieldnames=fieldnames)
            for row in reader:
                try:
                    data_d = datetime.strptime(row["Data"].strip(), "%d/%m/%Y")
                    preco  = float(row["Fechamento"].replace(".", "").replace(",", "."))
                    registros.append({
                        "data":     data_d,
                        "preco":    preco,
                        "ano":      data_d.year,
                        "mes":      data_d.month,
                        "quinzena": 1 if data_d.day <= 15 else 2,
                    })
                except (ValueError, KeyError):
                    continue
            break
        except Exception as e:
            ultima_excecao = e
            if tentativa < 2:
                time.sleep(0.5)
    else:
        raise ultima_excecao

    registros.sort(key=lambda x: x["data"])
    return registros


def _media_anual(registros: list) -> dict:
    """Calcula média de fechamento por ano."""
    por_ano = defaultdict(list)
    for r in registros:
        por_ano[r["ano"]].append(r["preco"])
    return {ano: sum(v) / len(v) for ano, v in por_ano.items()}


def _sazonalidade_quinzenal(registros: list, medias_anuais: dict) -> dict:
    """
    Calcula desvio percentual médio por quinzena (mês, 1 ou 2).
    Retorna dict com chave (mes, quinzena) → {avg_pct, std_pct, n_obs}.
    """
    acum = defaultdict(list)
    for r in registros:
        ma = medias_anuais.get(r["ano"])
        if ma and ma > 0:
            desvio = (r["preco"] / ma - 1) * 100
            acum[(r["mes"], r["quinzena"])].append(desvio)

    resultado = {}
    for (mes, qz), vals in acum.items():
        avg = sum(vals) / len(vals)
        var = sum((v - avg) ** 2 for v in vals) / len(vals)
        resultado[(mes, qz)] = {
            "avg_pct": round(avg, 4),
            "std_pct": round(math.sqrt(var), 4),
            "n_obs":   len(vals),
        }
    return resultado


def _sazonalidade_mensal(registros: list, medias_anuais: dict) -> dict:
    """Calcula desvio percentual médio por mês."""
    acum = defaultdict(list)
    for r in registros:
        ma = medias_anuais.get(r["ano"])
        if ma and ma > 0:
            desvio = (r["preco"] / ma - 1) * 100
            acum[r["mes"]].append(desvio)

    resultado = {}
    for mes, vals in acum.items():
        avg = sum(vals) / len(vals)
        var = sum((v - avg) ** 2 for v in vals) / len(vals)
        resultado[mes] = {
            "avg_pct": round(avg, 4),
            "std_pct": round(math.sqrt(var), 4),
            "n_obs":   len(vals),
            "min_pct": round(min(vals), 4),
            "max_pct": round(max(vals), 4),
        }
    return resultado

# ─────────────────────────────────────────────
# CONTEXTO DO MOMENTO ATUAL
# ─────────────────────────────────────────────

def _contexto_atual(data_ref: date, saz_mensal: dict, saz_qz: dict) -> dict:
    """
    Dado a data de referência, retorna:
    - fase agrícola atual
    - desvio sazonal atual (quinzena)
    - desvio sazonal próxima quinzena
    - tendência sazonal (ALTISTA / BAIXISTA / NEUTRO)
    - janela de alta sazonalidade (mai→nov histórico)
    """
    mes  = data_ref.month
    qz   = 1 if data_ref.day <= 15 else 2

    # Quinzena atual
    atual = saz_qz.get((mes, qz), {})

    # Próxima quinzena
    if qz == 1:
        prox_mes, prox_qz = mes, 2
    else:
        prox_mes = mes % 12 + 1
        prox_qz  = 1
    proxima = saz_qz.get((prox_mes, prox_qz), {})

    # Tendência: compara próxima quinzena com atual
    delta_qz = None
    tendencia = "NEUTRO"
    if atual.get("avg_pct") is not None and proxima.get("avg_pct") is not None:
        delta_qz = round(proxima["avg_pct"] - atual["avg_pct"], 4)
        if delta_qz > 0.5:
            tendencia = "ALTISTA"
        elif delta_qz < -0.5:
            tendencia = "BAIXISTA"

    # Fase agrícola
    fase  = FASES_AGRICOLAS.get(mes, "INDEFINIDA")
    vies  = VIES_FASE.get(fase, "NEUTRO")
    descr = DESCRICAO_FASES.get(fase, "")

    # Recuperação sazonal: jul-Q2 em diante é virada histórica
    virada_sazonal = (mes == 7 and qz == 2) or mes >= 8

    # Meses até pico sazonal (março)
    mes_pico = 3
    meses_ate_pico = (mes_pico - mes) % 12
    if meses_ate_pico == 0:
        meses_ate_pico = 12

    return {
        "fase_agricola":       fase,
        "descricao_fase":      descr,
        "vies_sazonal":        vies,
        "quinzena_atual":      f"{MESES_PT[mes-1]}-Q{qz}",
        "desvio_atual_pct":    atual.get("avg_pct"),
        "desvio_std_pct":      atual.get("std_pct"),
        "n_obs_atual":         atual.get("n_obs"),
        "proxima_quinzena":    f"{MESES_PT[prox_mes-1]}-Q{prox_qz}",
        "desvio_proxima_pct":  proxima.get("avg_pct"),
        "delta_quinzenal_pct": delta_qz,
        "tendencia_sazonal":   tendencia,
        "virada_sazonal":      virada_sazonal,
        "meses_ate_pico_mar":  meses_ate_pico,
    }


def _calendario_sazonal(saz_mensal: dict) -> list:
    """Retorna tabela mensal ordenada para exibição no relatório."""
    tabela = []
    for mes in range(1, 13):
        info = saz_mensal.get(mes, {})
        tabela.append({
            "mes":      MESES_PT[mes - 1],
            "mes_num":  mes,
            "avg_pct":  info.get("avg_pct"),
            "std_pct":  info.get("std_pct"),
            "min_pct":  info.get("min_pct"),
            "max_pct":  info.get("max_pct"),
            "n_obs":    info.get("n_obs"),
            "fase":     FASES_AGRICOLAS.get(mes, ""),
            "vies":     VIES_FASE.get(FASES_AGRICOLAS.get(mes, ""), "NEUTRO"),
        })
    return tabela

# ─────────────────────────────────────────────
# FUNÇÃO PRINCIPAL — EXPORTADA PARA O PIPELINE
# ─────────────────────────────────────────────

def calcular_sazonalidade(pasta_dados: str, data_referencia=None) -> dict:
    """
    Função principal. Chamada pelo pipeline.py.

    Parâmetros:
        pasta_dados     : str — caminho da pasta com os CSVs (C:\\Projetos Phyton\\Milho)
        data_referencia : date ou None — se None, usa date.today()

    Retorna:
        dict com toda a análise de sazonalidade, pronto para inserção no dados_milho.json
    """
    if data_referencia is None:
        data_referencia = date.today()

    caminho_csv = os.path.join(pasta_dados, NOME_CSV)

    if not os.path.exists(caminho_csv):
        return {
            "erro":    f"Arquivo não encontrado: {caminho_csv}",
            "status":  "FALHA",
        }

    try:
        registros      = _ler_csv(caminho_csv)
        medias_anuais  = _media_anual(registros)
        saz_mensal     = _sazonalidade_mensal(registros, medias_anuais)
        saz_qz         = _sazonalidade_quinzenal(registros, medias_anuais)
        contexto       = _contexto_atual(data_referencia, saz_mensal, saz_qz)
        calendario     = _calendario_sazonal(saz_mensal)

        periodo_inicio = registros[0]["data"].strftime("%d/%m/%Y")
        periodo_fim    = registros[-1]["data"].strftime("%d/%m/%Y")
        anos_base      = sorted(medias_anuais.keys())
        total_obs      = len(registros)

        return {
            "status":          "OK",
            "fonte":           NOME_CSV,
            "periodo_base":    f"{periodo_inicio} a {periodo_fim}",
            "anos_base":       anos_base,
            "total_obs":       total_obs,
            "aviso_historico": (
                "BASE CURTA (2 anos) — padrões direcionais confiáveis; amplitudes com incerteza."
                if len(anos_base) < 3 else
                f"Base com {len(anos_base)} anos — sazonalidade robusta."
            ),
            "contexto_atual":  contexto,
            "calendario_mensal": calendario,
        }

    except Exception as e:
        return {
            "erro":   str(e),
            "status": "FALHA",
        }

# ─────────────────────────────────────────────
# EXECUÇÃO STANDALONE (python sazonalidade_milho.py)
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Detecta pasta: argumento CLI ou padrão do projeto
    if len(sys.argv) > 1:
        pasta = sys.argv[1]
    else:
        pasta = r"C:\Projetos Phyton\Milho"

    # Para teste no ambiente de desenvolvimento, aceita caminho Unix também
    if not os.path.exists(pasta):
        pasta = os.path.dirname(os.path.abspath(__file__))

    print("=" * 60)
    print("  MILHO TRADER — Sazonalidade Proprietária CCMFUT")
    print("=" * 60)

    resultado = calcular_sazonalidade(pasta, date.today())

    if resultado.get("status") != "OK":
        print(f"❌ ERRO: {resultado.get('erro')}")
        sys.exit(1)

    ctx = resultado["contexto_atual"]
    print(f"\n📅 Data referência : {date.today().strftime('%d/%m/%Y')}")
    print(f"📊 Base histórica  : {resultado['periodo_base']} ({resultado['total_obs']} obs)")
    print(f"⚠️  {resultado['aviso_historico']}")
    print()
    print(f"🌱 Fase agrícola   : {ctx['fase_agricola']}")
    print(f"   Descrição       : {ctx['descricao_fase']}")
    print(f"   Viés sazonal    : {ctx['vies_sazonal']}")
    print()
    print(f"📍 Quinzena atual  : {ctx['quinzena_atual']}")
    print(f"   Desvio médio    : {ctx['desvio_atual_pct']:+.1f}% (±{ctx['desvio_std_pct']:.1f}%) | {ctx['n_obs_atual']} obs")
    print(f"   Próxima quinzena: {ctx['proxima_quinzena']} → {ctx['desvio_proxima_pct']:+.1f}%")
    print(f"   Delta quinzenal : {ctx['delta_quinzenal_pct']:+.2f}% ({ctx['tendencia_sazonal']})")
    print(f"   Virada sazonal  : {'✅ SIM — Jul-Q2 é historicamente a virada de baixa para alta' if ctx['virada_sazonal'] else '❌ NÃO — ainda em zona de pressão'}")
    print(f"   Meses até pico  : {ctx['meses_ate_pico_mar']} meses (pico histórico: Março)")
    print()
    print("📆 CALENDÁRIO SAZONAL COMPLETO:")
    print(f"   {'Mês':5s} | {'Desvio':>8s} | {'±':>6s} | {'Min':>7s} | {'Max':>7s} | {'Obs':>4s} | Fase")
    print("   " + "-" * 72)
    for m in resultado["calendario_mensal"]:
        sinal = "▲" if (m["avg_pct"] or 0) > 0 else "▼"
        print(f"   {m['mes']:5s} | {m['avg_pct']:+7.1f}% | {m['std_pct']:5.1f}% | "
              f"{m['min_pct']:+6.1f}% | {m['max_pct']:+6.1f}% | {m['n_obs']:4d} | "
              f"{sinal} {m['fase']}")

    # Salva JSON de debug
    out_path = os.path.join(pasta, "sazonalidade_debug.json")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n✅ JSON de debug salvo em: {out_path}")
    except Exception:
        print("\n⚠️  Não foi possível salvar o JSON de debug.")

    print("=" * 60)
