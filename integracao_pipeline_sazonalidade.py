# ─────────────────────────────────────────────────────────────────
# INTEGRAÇÃO: sazonalidade_milho.py → pipeline.py
# Milho Trader | GPM v2.0 | Fase 3B
#
# INSTRUÇÕES:
# 1. Copiar sazonalidade_milho.py para C:\Projetos Phyton\Milho\
# 2. Adicionar o import abaixo no topo do pipeline.py
# 3. Adicionar o bloco de chamada dentro de gerar_json()
# 4. Adicionar a chave "sazonalidade" no JSON de saída
# ─────────────────────────────────────────────────────────────────

# ── ADICIONAR NO TOPO DO pipeline.py (junto dos outros imports) ──
from sazonalidade_milho import calcular_sazonalidade

# ── ADICIONAR DENTRO DE gerar_json() ou equivalente ──────────────
# (substituir PASTA_DADOS pela variável que já existe no pipeline)

from datetime import date

saz = calcular_sazonalidade(PASTA_DADOS, date.today())

if saz.get("status") == "OK":
    ctx = saz["contexto_atual"]
    print(f"✅ Sazonalidade | Fase: {ctx['fase_agricola']} | "
          f"Desvio atual: {ctx['desvio_atual_pct']:+.1f}% | "
          f"Viés: {ctx['vies_sazonal']}")
else:
    print(f"⚠️  Sazonalidade | FALHA: {saz.get('erro', 'erro desconhecido')}")

# ── ADICIONAR NO DICT DO JSON DE SAÍDA ───────────────────────────
# Dentro do dict principal que é serializado em dados_milho.json:

sazonalidade_output = {
    "status":            saz.get("status"),
    "periodo_base":      saz.get("periodo_base"),
    "aviso_historico":   saz.get("aviso_historico"),
    "fase_agricola":     saz.get("contexto_atual", {}).get("fase_agricola"),
    "descricao_fase":    saz.get("contexto_atual", {}).get("descricao_fase"),
    "vies_sazonal":      saz.get("contexto_atual", {}).get("vies_sazonal"),
    "quinzena_atual":    saz.get("contexto_atual", {}).get("quinzena_atual"),
    "desvio_atual_pct":  saz.get("contexto_atual", {}).get("desvio_atual_pct"),
    "desvio_std_pct":    saz.get("contexto_atual", {}).get("desvio_std_pct"),
    "proxima_quinzena":  saz.get("contexto_atual", {}).get("proxima_quinzena"),
    "desvio_proxima_pct":saz.get("contexto_atual", {}).get("desvio_proxima_pct"),
    "delta_quinzenal_pct":saz.get("contexto_atual", {}).get("delta_quinzenal_pct"),
    "tendencia_sazonal": saz.get("contexto_atual", {}).get("tendencia_sazonal"),
    "virada_sazonal":    saz.get("contexto_atual", {}).get("virada_sazonal"),
    "meses_ate_pico_mar":saz.get("contexto_atual", {}).get("meses_ate_pico_mar"),
    "calendario_mensal": saz.get("calendario_mensal", []),
}

# No dict principal do JSON:
# dados["sazonalidade"] = sazonalidade_output

# ── RESULTADO ESPERADO NO LOG DO PIPELINE ────────────────────────
# ✅ Sazonalidade | Fase: COLHEITA_SAFRINHA | Desvio atual: -5.0% | Viés: BAIXISTA
