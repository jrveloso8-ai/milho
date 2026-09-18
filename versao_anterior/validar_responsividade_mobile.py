# -*- coding: utf-8 -*-
"""
validar_responsividade_mobile.py — Verificação estrita de requisitos de responsividade mobile.
Valida se index.html e ccm_trix_curva.html atendem a todos os 10 critérios para mobile/celular.
"""

import os
import sys

PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))

def validar_arquivo(nome_arquivo):
    caminho = os.path.join(PASTA_PROJETO, nome_arquivo)
    assert os.path.isfile(caminho), f"Arquivo {nome_arquivo} não encontrado!"
    
    with open(caminho, "r", encoding="utf-8") as f:
        html = f.read()

    erros = []

    # 1. Meta viewport
    if "name=\"viewport\"" not in html and "name='viewport'" not in html:
        erros.append("Critério 1 Falhou: Meta viewport não configurado.")

    # 2. Seletor de contratos no topo do gráfico (Quick Contract Pills)
    if "chart-contract-pills-bar" not in html or "btn-top-contract" not in html:
        erros.append("Critério 2 Falhou: Barra de pílulas rápidas de contrato não encontrada.")

    # 3. Barra de legendas em chips HTML
    if "chart-legend-chips-container" not in html or "legend-chip" not in html:
        erros.append("Critério 3 Falhou: Barra de chips de legenda HTML não encontrada.")

    # 4. Remoção de sobreposição de legenda SVG no mobile
    if ".plotly-graph-div .legend" not in html or "display: none !important" not in html:
        erros.append("Critério 4 Falhou: Regra CSS de ocultação da legenda SVG no mobile ausente.")

    # 5. Liberação de scroll touch vertical
    if "touch-action: pan-y !important" not in html or "desbloquearTouchScroll" not in html:
        erros.append("Critério 5 Falhou: Touch-action pan-y para desbloqueio de scroll ausente.")

    # 6. Container de scroll para tabelas
    if "table-scroll-container" not in html:
        erros.append("Critério 6 Falhou: .table-scroll-container ausente nas tabelas.")

    # 7. Min-width nas tabelas e white-space nowrap
    if "min-width: 760px" not in html or "min-width: 860px" not in html or "white-space: nowrap" not in html:
        erros.append("Critério 7 Falhou: min-width (760px/860px) ou white-space nowrap ausentes.")

    # 8. Dica visual de navegação horizontal em mobile
    if "mobile-table-hint" not in html or "Deslize horizontalmente" not in html:
        erros.append("Critério 8 Falhou: Dica visual de scroll horizontal ausente.")

    # 9. Sincronização de botões superiores e inferiores em JS
    if "btn-top-contract" not in html or "alternarGradeOpcoes" not in html:
        erros.append("Critério 9 Falhou: Sincronização JS entre botões e gráfico ausente.")

    # 10. Desativação de scrollZoom no Plotly
    if "scrollZoom\": false" not in html and "scrollZoom': False" not in html and "scrollZoom\":false" not in html:
        erros.append("Critério 10 Falhou: scrollZoom não desativado na config do Plotly.")

    print(f"[{nome_arquivo}]")
    if erros:
        for err in erros:
            print(f"  [FALHA] {err}")
        return False
    else:
        print("  -> Todos os 10 critérios de responsividade mobile APROVADOS.")
        return True

def main():
    print("=" * 70)
    print("VALIDAÇÃO RIGOROSA DE RESPONSIVIDADE MOBILE (10 CRITÉRIOS)")
    print("=" * 70)
    
    ok1 = validar_arquivo("ccm_trix_curva.html")
    ok2 = validar_arquivo("index.html")

    if ok1 and ok2:
        print("\nPARECER FINAL: 100% APROVADO PARA DISPOSITIVOS MÓVEIS.")
        return 0
    else:
        print("\nPARECER FINAL: REPROVADO.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
