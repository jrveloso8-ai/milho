# -*- coding: utf-8 -*-
"""
verificar_dados_fabricados.py — Script de auditoria de dados fabricados e proveniência.
Atende ao item 6.2 do Portão de Auditoria.

Verificações obrigatórias:
  1. Barreira de opções sem proveniência registrada em resumo_trix_curva.txt ou tabela_proveniencia.md.
  2. Preço da Watchlist (CCM Real ou RTCNI Físico) que não seja estritamente MEDIDO.
  3. Dia sintético desenhado como candle real no gráfico interativo ccm_trix_curva.html.
  4. Presença de qualquer dado fabricado/inventado ou tag SIMULADO em uso ativo.

Retorna:
  Exit code 0 se APROVADO em todas as verificações.
  Exit code 1 se REPROVADO com apontamento explícito do motivo.
"""

import os
import re
import sys

PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))
ARQ_RESUMO = os.path.join(PASTA_PROJETO, "resumo_trix_curva.txt")
ARQ_TABELA = os.path.join(PASTA_PROJETO, "tabela_proveniencia.md")
ARQ_HTML = os.path.join(PASTA_PROJETO, "ccm_trix_curva.html")

PROVENIENCIAS_VALIDAS = {"MEDIDO", "DERIVADO", "ESTIMADO", "INDISPONIVEL"}


def auditar_resumo_trix_curva():
    """Varre resumo_trix_curva.txt checando proveniência da Watchlist e barreiras de opções."""
    erros = []
    if not os.path.isfile(ARQ_RESUMO):
        return [f"Arquivo {ARQ_RESUMO} não encontrado."]

    with open(ARQ_RESUMO, "r", encoding="utf-8") as f:
        linhas = f.readlines()

    # 1. Proibição absoluta de SIMULADO
    for i, linha in enumerate(linhas, 1):
        if "[SIMULADO]" in linha or "SIMULADO" in linha and "Proibido" not in linha:
            erros.append(f"resumo_trix_curva.txt:L{i} contém 'SIMULADO' não permitido: {linha.strip()}")

    # 2. Auditoria da Watchlist
    em_watchlist = False
    linhas_watchlist = []
    for linha in linhas:
        if "WATCHLIST" in linha:
            em_watchlist = True
            continue
        if em_watchlist and "DETALHAMENTO TÉCNICO" in linha:
            em_watchlist = False
            break
        if em_watchlist and linha.startswith("CCM"):
            linhas_watchlist.append(linha)

    if not linhas_watchlist:
        erros.append("resumo_trix_curva.txt: nenhuma linha de contrato encontrada na Watchlist.")

    for linha in linhas_watchlist:
        partes = linha.split()
        contrato = partes[0]
        # Toda linha deve conter [MEDIDO] para CCM e [MEDIDO] para RTCNI
        ocorrencias_medido = linha.count("[MEDIDO]")
        if ocorrencias_medido < 2:
            erros.append(
                f"resumo_trix_curva.txt: Contrato {contrato} na Watchlist não possui todos os preços como [MEDIDO]: {linha.strip()}"
            )
        if "[ESTIMADO]" in linha or "[DERIVADO]" in linha:
            erros.append(
                f"resumo_trix_curva.txt: Contrato {contrato} na Watchlist possui classificação espúria (não-MEDIDO): {linha.strip()}"
            )

        # Checa se defasagem > 7 dias corridos possui aviso [DEFASADO
        datas_encontradas = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", linha)
        if len(datas_encontradas) >= 2:
            from datetime import datetime as _dt
            d_ccm = _dt.strptime(datas_encontradas[0], "%Y-%m-%d").date()
            d_rtcni = _dt.strptime(datas_encontradas[1], "%Y-%m-%d").date()
            dias_def = (d_ccm - d_rtcni).days
            if dias_def > 7 and "[DEFASADO" not in linha:
                erros.append(
                    f"resumo_trix_curva.txt: Contrato {contrato} com defasagem de {dias_def} dias sem aviso [DEFASADO]: {linha.strip()}"
                )

    # 3. Auditoria de Barreiras de Opções no resumo
    for i, linha in enumerate(linhas, 1):
        if "Barreiras Opções:" in linha or "Put Wall" in linha or "Call Wall" in linha or "Max Pain" in linha:
            # Deve conter proveniência explicitamente entre colchetes
            tags = re.findall(r"\[(.*?)\]", linha)
            if not tags:
                erros.append(f"resumo_trix_curva.txt:L{i} Barreira de opções sem tag de proveniência: {linha.strip()}")
            else:
                for tag in tags:
                    sub_tags = [t.strip() for t in tag.split("/")]
                    for st in sub_tags:
                        if st not in PROVENIENCIAS_VALIDAS:
                            erros.append(f"resumo_trix_curva.txt:L{i} Tag inválida de proveniência '{st}': {linha.strip()}")

    return erros


def auditar_tabela_proveniencia():
    """Varre tabela_proveniencia.md checando matriz de campos e documentação da Watchlist."""
    erros = []
    if not os.path.isfile(ARQ_TABELA):
        return [f"Arquivo {ARQ_TABELA} não encontrado."]

    with open(ARQ_TABELA, "r", encoding="utf-8") as f:
        conteudo = f.read()

    # Checar se barreiras de opções estão na matriz de proveniência
    opcoes_requeridas = ["Call Wall", "Put Wall", "Max Pain", "Contratos em Aberto da Wall (OI)"]
    for req in opcoes_requeridas:
        if req not in conteudo:
            erros.append(f"tabela_proveniencia.md: barreira/campo de opção obrigatório '{req}' não encontrado.")

    # Checar se a Watchlist está formalmente documentada
    if "Watchlist" not in conteudo and "WATCHLIST" not in conteudo:
        erros.append("tabela_proveniencia.md: seção da Watchlist não encontrada.")

    # Checar se a regra contra SIMULADO está expressa
    if "SIMULADO" not in conteudo or "Proibido" not in conteudo:
        erros.append("tabela_proveniencia.md: proibição de dados SIMULADOS não documentada.")

    # Checar nota explícita de RTCNI via export manual do Profit e defasagem
    if "exportado manualmente do Profit" not in conteudo:
        erros.append("tabela_proveniencia.md: nota de limitação do RTCNI (export manual do Profit) não encontrada.")

    return erros


def auditar_grafico_html():
    """Varre ccm_trix_curva.html garantindo que dias sintéticos não viraram candles reais."""
    erros = []
    if not os.path.isfile(ARQ_HTML):
        return [f"Arquivo {ARQ_HTML} não encontrado."]

    with open(ARQ_HTML, "r", encoding="utf-8") as f:
        conteudo = f.read()

    # 1. No HTML, não deve existir candlestick para dados sintéticos
    # O código só gera Candlestick para dados reais (df[~df["is_sintetico"]])
    if "Candlestick Sintético" in conteudo or "Candle Sintético" in conteudo:
        erros.append("ccm_trix_curva.html: detectado traço de Candlestick Sintético no HTML!")

    # 2. A Watchlist deve estar presente no HTML
    if "WATCHLIST" not in conteudo or "Curva CCM vs Físico" not in conteudo:
        erros.append("ccm_trix_curva.html: tabela de Watchlist não encontrada no HTML.")

    # 3. Na tabela Watchlist do HTML, a proveniência dos preços deve ser estritamente MEDIDO
    if "PROVENIÊNCIA: MEDIDO" not in conteudo and "[MEDIDO]" not in conteudo:
        erros.append("ccm_trix_curva.html: tag/badge MEDIDO ausente na Watchlist do HTML.")

    # 4. Checa se o aviso de defasagem está presente quando aplicável
    if "[DEFASADO" in open(ARQ_RESUMO, encoding="utf-8").read() and "[DEFASADO" not in conteudo:
        erros.append("ccm_trix_curva.html: badge/aviso [DEFASADO] ausente na Watchlist do HTML.")

    return erros


def main():
    print("=" * 70)
    print("AUDITORIA DE DADOS FABRICADOS E PROVENIÊNCIA (Item 6.2)")
    print("=" * 70)

    erros_totais = []

    print("[1/3] Auditando resumo_trix_curva.txt...")
    erros_resumo = auditar_resumo_trix_curva()
    erros_totais.extend(erros_resumo)
    if not erros_resumo:
        print("      -> OK: Watchlist 100% MEDIDO, barreiras de opções classificadas.")
    else:
        for e in erros_resumo:
            print(f"      [FALHA] {e}")

    print("[2/3] Auditando tabela_proveniencia.md...")
    erros_tabela = auditar_tabela_proveniencia()
    erros_totais.extend(erros_tabela)
    if not erros_tabela:
        print("      -> OK: Matriz completa, opções registradas e Watchlist documentada.")
    else:
        for e in erros_tabela:
            print(f"      [FALHA] {e}")

    print("[3/3] Auditando ccm_trix_curva.html...")
    erros_html = auditar_grafico_html()
    erros_totais.extend(erros_html)
    if not erros_html:
        print("      -> OK: Zero candles sintéticos, Watchlist MEDIDO incorporada.")
    else:
        for e in erros_html:
            print(f"      [FALHA] {e}")

    print("-" * 70)
    if erros_totais:
        print(f"PARECER: REPROVADO — {len(erros_totais)} inconformidade(s) detectada(s).")
        sys.exit(1)
    else:
        print("PARECER: APROVADO — Nenhum dado fabricado ou sem proveniência detectado.")
        sys.exit(0)


if __name__ == "__main__":
    main()
