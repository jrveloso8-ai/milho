# -*- coding: utf-8 -*-
"""
verificar_literais_plot.py — Barreira estrutural (AST) contra literais soltos no plot/render.
Atende ao item 6.3 do Portão de Auditoria.

Objetivo:
  Garantir que nenhuma função de plotagem ou renderização visual (ex: gerar_grafico_interativo)
  contenha números literais representando dados de mercado ou preços fabricados/hardcoded
  (ex: preços, strikes, walls, volumes fixos injetados diretamente no código).

Metodologia (AST):
  1. Identifica todas as funções de plotagem/renderização em ccm_trix_curva.py.
  2. Inspeciona a árvore sintática (ast.walk) de cada função.
  3. Bloqueia:
     - Atribuições diretas de números literais a variáveis com nomes de dados de mercado
       (ex: preco, close, open, high, low, strike, wall, pain, volume, saldo).
     - Parâmetros de dados de séries/traços (open, high, low, close, x, y) recebendo literais
       numéricos em vez de expressões/colunas de DataFrame.
     - Literais numéricos soltos que caiam na faixa típica de cotações/preços sem justificativa
       estrita de layout/estilo (dimensão, padding, opacidade, multiplicador de offset visual).

Retorna:
  Exit code 0 se APROVADO (nenhum literal espúrio de dados de mercado).
  Exit code 1 se REPROVADO (com arquivo, linha e contexto do literal detectado).
"""

import ast
import os
import sys

PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))

# Nomes de variáveis proibidas de receber atribuição literal de números
VARIAVEIS_DADOS_PROIBIDAS = {
    "preco", "preco_futuro", "preco_fisico", "close", "open", "high", "low",
    "call_wall", "put_wall", "max_pain", "strike", "volume", "trades",
    "saldo", "spread", "cotacao", "valor_mercado", "cbot", "cambio", "ppe", "ptax"
}

# Nomes de argumentos de traços proibidos de receber número literal direto
ARGUMENTOS_TRACO_PROIBIDOS = {"x", "y", "open", "high", "low", "close"}

# Literais de layout e estilização permitidos em funções de renderização
LITERAIS_LAYOUT_PERMITIDOS = {
    # Índices e flags
    0, 1, 2, -1,
    # Tamanhos de fonte e espessuras de linha
    10, 11, 12, 13, 14, 16, 20, 24,
    1.0, 1.1, 1.4, 1.5, 2.0, 2.5,
    # Coordenadas de domínio e layout (Paper coordinates / margins)
    0.0, 0.12, 0.2, 0.5, 0.8, 1.0, 1.16,
    # Dimensões de tela / container (px)
    720, 1200, 800, 600, 1000,
    # Multiplicadores de afastamento visual de marcadores (offsets não-sobrepostos)
    0.995, 1.005,
    # Frações de padding / margin
    4, 8, 12, 15, 16, 20, 24, 30, 40,
}


class PlotLiteralAuditor(ast.NodeVisitor):
    def __init__(self, filename: str):
        self.filename = filename
        self.erros = []
        self.em_funcao_plot = False
        self.funcao_atual = ""

    def visit_FunctionDef(self, node: ast.FunctionDef):
        anterior = self.em_funcao_plot
        anterior_fn = self.funcao_atual
        nome = node.name.lower()
        self.em_funcao_plot = any(term in nome for term in ("plot", "grafico", "render", "desenhar", "chart"))
        self.funcao_atual = node.name

        self.generic_visit(node)

        self.em_funcao_plot = anterior
        self.funcao_atual = anterior_fn

    def visit_Assign(self, node: ast.Assign):
        fn_nome = self.funcao_atual or "módulo"
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_name = target.id.lower()
                # Checa atribuição de literal a variável de dado de mercado (em qualquer função ou módulo)
                for termo in VARIAVEIS_DADOS_PROIBIDAS:
                    if termo in var_name:
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float)):
                            self.erros.append(
                                f"{self.filename}:{node.lineno} no escopo '{fn_nome}': "
                                f"Atribuição de número literal {node.value.value} à variável de mercado '{target.id}'."
                            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if self.em_funcao_plot:
            # Checa se é chamada de criação de traço do Plotly (ex: go.Scatter, go.Candlestick)
            is_trace = False
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in ("Scatter", "Candlestick", "Bar"):
                    is_trace = True

            if is_trace:
                for kw in node.keywords:
                    if kw.arg in ARGUMENTOS_TRACO_PROIBIDOS:
                        # Se x, y, open, high, low, close for passado diretamente como literal numérico ou lista de literais
                        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, (int, float)):
                            self.erros.append(
                                f"{self.filename}:{node.lineno} na função '{self.funcao_atual}': "
                                f"Traço Plotly '{node.func.attr}' recebe literal numérico direto no argumento '{kw.arg}'."
                            )
                        elif isinstance(kw.value, ast.List):
                            # Se for uma lista contendo constantes numéricas soltas
                            constantes_numericas = [
                                elt.value for elt in kw.value.elts
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, (int, float))
                            ]
                            if constantes_numericas:
                                self.erros.append(
                                    f"{self.filename}:{node.lineno} na função '{self.funcao_atual}': "
                                    f"Traço Plotly '{node.func.attr}' recebe lista de números literais em '{kw.arg}': {constantes_numericas}."
                                )

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant):
        if self.em_funcao_plot and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            val = node.value
            # Se for um número que não está na lista permitida de layout/estilo
            if val not in LITERAIS_LAYOUT_PERMITIDOS:
                # Se parecer um preço de milho ou dado de mercado (ex: entre 30 e 150 com decimais, ou número atípico)
                if 20.0 <= val <= 200.0:
                    self.erros.append(
                        f"{self.filename}:{node.lineno} na função '{self.funcao_atual}': "
                        f"Literal numérico suspeito de ser preço/dado solto ({val}) não está na lista de layout/estilo permitida."
                    )
        self.generic_visit(node)


ARQUIVOS_ALVO = [
    os.path.join(PASTA_PROJETO, "ccm_trix_curva.py"),
    os.path.join(PASTA_PROJETO, "sentinel_engine.py"),
]


def auditar_literais_plot():
    print("=" * 70)
    print("BARREIRA ESTRUTURAL (AST) CONTRA LITERAIS SOLTOS NO PLOT (Item 6.3)")
    print("=" * 70)

    erros_totais = []
    for arq in ARQUIVOS_ALVO:
        if not os.path.isfile(arq):
            print(f"ERRO: Arquivo {arq} não encontrado.")
            return 1

        with open(arq, "r", encoding="utf-8") as f:
            codigo = f.read()

        try:
            tree = ast.parse(codigo, filename=arq)
        except SyntaxError as e:
            print(f"ERRO de sintaxe ao fazer parse do AST em {arq}: {e}")
            return 1

        auditor = PlotLiteralAuditor(os.path.basename(arq))
        auditor.visit(tree)
        print(f"Análise AST concluída sobre: {os.path.basename(arq)}")
        erros_totais.extend(auditor.erros)

    if erros_totais:
        print(f"PARECER: REPROVADO — {len(erros_totais)} violação(ões) encontrada(s):")
        for err in erros_totais:
            print(f"  [VIOLAÇÃO] {err}")
        return 1
    else:
        print("PARECER: APROVADO — Nenhum número literal solto ou preço hardcoded detectado.")
        return 0


if __name__ == "__main__":
    sys.exit(auditar_literais_plot())
