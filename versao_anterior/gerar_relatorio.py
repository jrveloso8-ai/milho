# gerar_relatorio.py — Motor de Análise Claude
# Milho Trader v1.0 — Fase 2
# Lê dados_milho.json e chama API Claude para gerar relatório semanal
# Chave de API: variável de ambiente ANTHROPIC_API_KEY

import os
import json
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ── Configurações ─────────────────────────────────────────────────────────────
PASTA          = r"C:\Projetos Phyton\Milho"
ARQUIVO_JSON   = os.path.join(PASTA, "dados_milho.json")
PASTA_RELATORIO = os.path.join(PASTA, "relatorios")
MODELO         = "claude-sonnet-4-6"
MAX_TOKENS     = 8000
API_URL        = "https://api.anthropic.com/v1/messages"

# ── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Você é um analista sênior especializado em mercado futuro de milho (CCM B3), com profundo conhecimento do ecossistema brasileiro: sazonalidade, Basis regional, paridade de exportação, convergência futuro×físico (RTCNI), custo de carrego (DI futuro), estrutura da curva de vencimentos, relação com ZC Chicago, câmbio (WDOFUT/DXY), clima e fundamentos de oferta e demanda.

Seu mandato é produzir um relatório semanal educacional sobre o contrato futuro de milho CCM na B3, consumindo dados estruturados em JSON e entregando análise objetiva, fundamentada e acionável.

IMPORTANTE — ENQUADRAMENTO REGULATÓRIO:
Todo o conteúdo produzido é de natureza exclusivamente educacional e informativa. Não constitui recomendação de investimento, consultoria financeira ou sugestão personalizada de compra ou venda de ativos. O leitor é o único responsável por suas decisões de investimento. Mercado futuro envolve risco de perda superior ao capital investido.

ESTRUTURA OBRIGATÓRIA DO RELATÓRIO (nesta ordem exata):

### 🌽 MILHO TRADER — RELATÓRIO SEMANAL
**Data:** {data_referencia} | **Vencimento ativo:** {vencimento_ativo}

---

### 📋 RESUMO EXECUTIVO
Máximo 6 linhas. Linguagem simples, acessível ao produtor rural. Sem jargão técnico.
Responde: o que está acontecendo no mercado de milho esta semana, para onde aponta o preço, e o que o produtor ou investidor deve observar. Nunca use termos como EMA, ATR, spread, DI.

---

### 🌍 CENÁRIO MACRO E FUNDAMENTOS
Análise em prosa cobrindo: ZC Chicago, WDOFUT (câmbio e diagnóstico), DXY, DI Futuro, paridade de exportação, Brent/etanol, safra Brasil, estoques globais.

---

### 📊 ANÁLISE TÉCNICA
Análise em prosa cobrindo: estrutura de preço CCM, EMA 9 vs EMA 20, ATR14, curva de vencimentos (contango/backwardation), barreiras de opções, calendário de eventos.

---

### ⚖️ PARIDADE, BASIS E CONVERGÊNCIA
Paridade internacional (fórmula: ZC × 0,3937 × USDBRL / 100), câmbio implícito, diagnóstico milho/câmbio/misto.
Convergência Futuro×Físico: RTCNI, spread, Z-Score, alerta se zscore > 1,5.
Custo de Carrego: DI Jan/27, preço justo teórico, avaliação do contrato.

---

### 📅 CALENDÁRIO DE RISCO
Eventos críticos: WASDE, CONAB, vencimentos CCM, dados macro, alertas sazonais.

---

### 🎯 SEÇÃO TÉCNICA — OPERADORES
Linguagem técnica de mercado.
Sistema Principal EMA 9/20: sinal, valores, inclinação, contexto.
Sistema Secundário Setup 9.1: sinal, contexto.
Alerta de convergência se zscore > 1,5.
Tabela de parâmetros operacionais (preço referência, stop ATR×1,5, alvo R:R 2:1, risco/contrato, valor contrato, margem estimada).
Tabela de sizing por perfil (conservador/moderado/arrojado).

---

### ⚡ DESTAQUE DA SEMANA
Aprofundamento no tema mais relevante definido pelo campo destaque_semana do JSON. Não repetir outras seções — agregar perspectiva nova.

---

### ⚠️ DISCLAIMER
Este relatório tem caráter exclusivamente educacional e informativo. Não constitui recomendação de investimento, consultoria financeira ou sugestão de compra e venda de ativos financeiros. O mercado futuro envolve risco elevado de perda, podendo superar o capital investido. Rentabilidade passada não garante resultados futuros. Antes de operar, consulte um profissional habilitado pela CVM/ANBIMA. Duda Veloso — Milho Trader Educação.

---

REGRAS DE CONDUTA:
1. Nunca emita viés sem fundamento nos dados recebidos.
2. Sempre dissocia câmbio de milho usando o campo cambio.diagnostico.
3. Se spread_zscore > 1,5 → emitir alerta na Seção Técnica.
4. DI sempre contextualizado — spread entre vencimentos acima do custo de carrego = distorção real.
5. Sinal de COMPRA com viés fundamental BAIXISTA = declarar divergência explicitamente.
6. Consistência entre seções — Resumo Executivo e Seção Técnica não podem ter vieses opostos sem justificativa.
7. Projeções são probabilísticas — nunca use "vai subir" ou "vai cair".
8. Tom duplo obrigatório: Resumo Executivo = produtor rural; Seção Técnica = operador.
9. Disclaimer sempre ao final, sem exceção.
10. Seção variável deve ser substantiva — agregar perspectiva nova.

ESTATÍSTICAS DE REFERÊNCIA:
Sistema EMA 9/20 (Jun/2024→Jun/2026): 9 trades, WR 66,7%, Payoff 2,52, Fat.Rec 10,1x, resultado R$9.246, MaxDD -R$915.
Sistema Setup 9.1 (mesmo período): 29 trades, WR 37,9%, Payoff 4,03, Fat.Rec 5,6x, resultado R$10.467, MaxDD -R$1.868.
Convergência histórica: spread médio R$6,51/sc, máx R$18,22/sc, mín -R$5,38/sc."""


# ── Funções auxiliares ────────────────────────────────────────────────────────

def carregar_json(caminho: str) -> dict:
    if not os.path.exists(caminho):
        raise FileNotFoundError(
            f"dados_milho.json não encontrado em: {caminho}\n"
            f"Execute rodar_pipeline.bat antes de gerar o relatório."
        )
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def obter_api_key() -> str:
    chave = os.environ.get("ANTHROPIC_API_KEY", "")
    if not chave or not chave.startswith("sk-"):
        raise EnvironmentError(
            "Variável de ambiente ANTHROPIC_API_KEY não definida ou inválida.\n"
            "Configure com: setx ANTHROPIC_API_KEY \"sk-ant-...\"\n"
            "Depois feche e reabra o terminal."
        )
    return chave


def chamar_api_claude(dados_json: dict, api_key: str) -> str:
    """
    Chama API Claude via urllib (sem dependências externas).
    Envia o JSON completo como contexto e solicita o relatório.
    """
    payload = {
        "model": MODELO,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Gere o relatório semanal completo do Milho Trader com base nos dados abaixo.\n\n"
                    f"```json\n{json.dumps(dados_json, ensure_ascii=False, indent=2)}\n```"
                )
            }
        ]
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resposta = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Erro HTTP {e.code} na API Claude:\n{corpo}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Erro de conexão com API Claude: {e.reason}")

    # Extrair texto da resposta
    blocos = resposta.get("content", [])
    textos = [b["text"] for b in blocos if b.get("type") == "text"]
    if not textos:
        raise RuntimeError(f"Resposta inesperada da API: {json.dumps(resposta, indent=2)}")

    return "\n".join(textos)


def salvar_relatorio(texto: str, pasta: str) -> str:
    """Salva relatório em markdown com timestamp no nome do arquivo."""
    Path(pasta).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    nome = f"relatorio_milho_{timestamp}.md"
    caminho = os.path.join(pasta, nome)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)
    return caminho


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  MILHO TRADER — GERADOR DE RELATÓRIO SEMANAL")
    print("=" * 60)

    # 1. Carregar JSON
    print(f"\n[1/3] Carregando dados: {ARQUIVO_JSON}")
    try:
        dados = carregar_json(ARQUIVO_JSON)
        data_ref = dados.get("data_referencia", "N/A")
        ccm = dados.get("ccm", {}).get("ultimo_preco", "N/A")
        print(f"      ✅ JSON carregado | Data: {data_ref} | CCM: R$ {ccm}/sc")
    except FileNotFoundError as e:
        print(f"\n❌ ERRO: {e}")
        return

    # 2. Verificar API key
    print("\n[2/3] Verificando chave de API...")
    try:
        api_key = obter_api_key()
        print("      ✅ ANTHROPIC_API_KEY encontrada")
    except EnvironmentError as e:
        print(f"\n❌ ERRO: {e}")
        return

    # 3. Chamar API e gerar relatório
    print("\n[3/3] Gerando relatório via API Claude...")
    print("      (pode levar até 60 segundos)")
    try:
        relatorio = chamar_api_claude(dados, api_key)
    except RuntimeError as e:
        print(f"\n❌ ERRO na API: {e}")
        return

    # 4. Salvar
    caminho_salvo = salvar_relatorio(relatorio, PASTA_RELATORIO)
    print(f"\n✅ Relatório gerado e salvo em:")
    print(f"   {caminho_salvo}")
    print("\n" + "=" * 60)
    print("  SUCESSO — relatório pronto para revisão")
    print("=" * 60)
    print("\nPróximos passos:")
    print("  1. Abra o arquivo .md em qualquer editor de texto")
    print("  2. Revise o conteúdo antes de distribuir")
    print("  3. Aplique o disclaimer obrigatório em toda distribuição")
    print()


if __name__ == "__main__":
    main()
