# ==============================================================================
# pipeline.py — Milho Trader v1.0 + ETAPA 6E (Bias Estrutural) + ETAPA 6F
# (Veredito Consolidado)
# ==============================================================================
# ETAPA 6E: Structural Bias Score v1.0 — agrega Sazonalidade + Físico + Macro
# + Técnico num score único.
# ETAPA 6F: Veredito Consolidado (20/07/2026) — funde o sinal técnico com o
# Bias Estrutural num ÚNICO veredito, substituindo os dois banners separados
# que existiam antes (Decisão e Bias Estrutural). Ver comentário na definição
# de calcular_veredito_consolidado() para a regra completa.
# ==============================================================================

import json
import os
import sys
from datetime import datetime, date

from leitor_csv           import ler_csv, ultimo_valor
from ccm_dados            import (analisar_ccmfut, analisar_curva_vencimentos, calcular_sizing,
                                   obter_candles, analisar_contrato, listar_vencimentos_vivos,
                                   contrato_vivo_do_mes, LETRA_POR_MES_VENCIMENTO)
from convergencia         import analisar_convergencia
from cambio_macro         import analisar_macro_completo
from sazonalidade_milho   import calcular_sazonalidade
from oi_opcoes            import analisar_oi_opcoes, analisar_todas_expiracoes
from spread_calendario    import analisar_spreads_calendario
from calendario_economico import verificar_calendario_economico
import ingestao_brapi


# ── CONFIGURAÇÕES ─────────────────────────────────────────────────────────────
PASTA_DADOS  = r'C:\Projetos Phyton\Milho'
PASTA_SAIDA  = r'C:\Projetos Phyton\Milho'
ARQUIVO_JSON = 'dados_milho.json'

# OI de opções — fallback quando a grade CCM_OP*.xlsx não é encontrada
# (analisar_oi_opcoes() substitui isso quando o arquivo existe)
OI_OPCOES_DEFAULT = {
    'call_wall': None,
    'put_wall':  None,
    'max_pain':  None,
    'fonte':     'manual',
    'grade':     [],
}

# Fundamentos — preencher manualmente (CONAB/WASDE mais recentes)
FUNDAMENTOS_DEFAULT = {
    'safra_br_estimativa_mt': 140.5,
    'colheita_safrinha_pct':  None,
    'estoques_globais_mt':    281.2,
    'vies_fundamental':       'BAIXISTA',
    'fonte':                  'CONAB/WASDE Jun-2026',
}


# ══════════════════════════════════════════════════════════════════════════
# STRUCTURAL BIAS SCORE v1.0 (Fase 3B)
#
# Agrega Sazonalidade + Físico (RTCNI/convergência + curva) + Macro + Técnico
# num score único de -100 a +100, com veto duro por calendário econômico.
# NÃO recalcula nada que sazonalidade_milho.py, convergencia.py, ccm_dados.py,
# cambio_macro.py ou spread_calendario.py já fazem — só consome o resultado.
#
# v1.0 (lido direto do código-fonte real dos módulos, não mais heurística):
#   - ccm_dados.py confirma sinal_ema920 / sinal_91 ∈ {'COMPRA', 'VENDA',
#     'NEUTRO'} — mapeamento exato, sem heurística de texto. MIGRAÇÃO
#     17/09/2026: esses dois campos agora vêm do TRIX v5 (trix_v5.py), não
#     mais de EMA9/20 + Setup 9.1 — ver cabeçalho de ccm_dados.py. A dimensão
#     Técnico do Bias (_bias_score_tecnico) usa só sinal_ema920 (a direção
#     ATUAL da posição do TRIX v5) — não faz mais média com sinal_91, que
#     agora só marca "há cruzamento novo hoje?" e não é uma segunda leitura
#     técnica independente.
#   - sazonalidade_milho.py (VIES_FASE) e FUNDAMENTOS_DEFAULT confirmam
#     vies_sazonal / vies_fundamental ∈ {'ALTISTA', 'BAIXISTA', 'NEUTRO'}.
#   - cambio_macro.py (analisar_cambio) mostra que 'diagnostico' NÃO é um
#     rótulo direcional altista/baixista — é uma tag de ATRIBUIÇÃO
#     ('MILHO' | 'CAMBIO' | 'MISTO') que diz qual fator explica um desvio
#     >5% entre o câmbio implícito no CCM e o USDBRL real, sem dizer se
#     isso é bom ou ruim pro preço. Por isso NÃO entra no Macro — usá-lo
#     como se fosse ALTA/BAIXA era um erro de leitura da v0.1, não uma
#     lacuna de dado. Macro roda só com fundamentos.vies_fundamental por
#     enquanto. (Candidato futuro, não implementado: dif_pct entre
#     cambio_implicito e wdofut_usdbrl como proxy de prêmio doméstico —
#     precisa decidir com Duda a direção do sinal antes de entrar no score.)
#
# Frete/paridade de exportação NÃO entra aqui — decidido em sessão anterior
# que é enriquecimento de relatório, não sinal do Bias Score.
# ══════════════════════════════════════════════════════════════════════════

BIAS_PESOS = {
    'sazonalidade': 0.30,
    'fisico':       0.30,
    'macro':        0.20,
    'tecnico':      0.20,
}

BIAS_FAIXAS = [
    (50, 'Bias forte / Go'),
    (20, 'Bias moderado'),
    (0,  'Neutro / No-Go'),
]


def _bias_clip(x, lo=-100, hi=100):
    return max(lo, min(hi, x))


_BIAS_MAPA_DIRECIONAL = {
    # sazonalidade_milho.VIES_FASE / FUNDAMENTOS_DEFAULT.vies_fundamental
    'ALTISTA':  60,
    'BAIXISTA': -60,
    # ccm_dados.calc_sinais_ema920 / calc_sinais_91
    'COMPRA':   60,
    'VENDA':    -60,
    'NEUTRO':   0,
}


def _bias_rotulo_para_score(rotulo):
    """Mapeamento EXATO (v1.0) — confirmado lendo ccm_dados.py e
    sazonalidade_milho.py direto na pasta do projeto, não mais heurística
    de texto. Retorna None para qualquer valor fora do vocabulário
    conhecido (ex.: 'N/A', 'DADOS AUSENTES — ...') — a dimensão fica sem
    essa contribuição em vez de arriscar uma leitura errada."""
    if not rotulo:
        return None
    return _BIAS_MAPA_DIRECIONAL.get(str(rotulo).strip().upper())


def _bias_score_sazonalidade(saz: dict):
    desvio = saz.get('desvio_atual_pct')
    desvio_std = saz.get('desvio_std_pct')
    if desvio is None or not desvio_std:
        return None, 'sem dado (desvio_atual_pct ou desvio_std_pct ausente)'
    score = _bias_clip((desvio / desvio_std) * 33)
    return score, f'desvio={desvio:+.1f}% / std={desvio_std:.1f}% -> {score:+.0f}'


def _bias_score_fisico(convergencia: dict, curva_leitura_sazonal: dict, spread_calendario: dict):
    z = convergencia.get('spread_zscore')
    if z is None:
        return None, 'sem dado (convergencia.spread_zscore ausente)'
    score = _bias_clip(z * 25)
    nota = f'spread_zscore={z:+.2f} -> {score:+.0f}'
    if curva_leitura_sazonal.get('avaliavel') and curva_leitura_sazonal.get('consistente') is False:
        score *= 0.7
        nota += ' | curva destoa da sazonalidade -> confiança reduzida (x0.7)'
    n_alertas = sum(1 for p in (spread_calendario.get('pares') or []) if p.get('alerta'))
    if n_alertas:
        nota += f' | {n_alertas} par(es) de spread calendário com alerta'
    return score, nota


def _bias_score_macro(cambio: dict, fundamentos: dict):
    """cambio.diagnostico NÃO entra aqui — ver nota no cabeçalho da seção:
    é uma tag de atribuição ('MILHO'/'CAMBIO'/'MISTO'), não um rótulo
    altista/baixista. Macro roda só com o fundamento manual CONAB/WASDE."""
    s_fund = _bias_rotulo_para_score(fundamentos.get('vies_fundamental'))
    if s_fund is None:
        return None, f"sem rótulo reconhecido em fundamentos.vies_fundamental (valor bruto: {fundamentos.get('vies_fundamental')!r})"
    nota = f"fundamentos.vies_fundamental='{fundamentos.get('vies_fundamental')}' -> {s_fund:+d}"
    return float(s_fund), nota


def _bias_score_tecnico(ccm: dict):
    """MIGRAÇÃO 17/09/2026: usa só sinal_ema920 (direção ATUAL da posição do
    TRIX v5 — COMPRA/VENDA/NEUTRO, NEUTRO=FLAT). Antes fazia média com
    sinal_91 (Setup 9.1), que era uma segunda leitura técnica independente;
    agora sinal_91 só marca "cruzamento novo hoje" (ver ccm_dados.py) e não
    é mais uma dimensão técnica própria — usá-lo aqui diluiria o score nos
    dias em que o TRIX v5 está mantendo uma posição real sem cruzar hoje."""
    s_tec = _bias_rotulo_para_score(ccm.get('sinal_ema920'))
    if s_tec is None:
        return None, f"sem rótulo reconhecido em sinal_ema920 (valor bruto: {ccm.get('sinal_ema920')!r})"
    return float(s_tec), f"TRIX v5 (posição atual)='{ccm.get('sinal_ema920')}' -> {s_tec:+d}"


def calcular_bias_estrutural(payload: dict) -> dict:
    """Structural Bias Score v1.0. Ver cabeçalho da seção para contexto."""
    cal_econ = payload.get('calendario_economico', {}) or {}
    if cal_econ.get('bloquear_hoje'):
        eventos = ', '.join(e.get('evento', '?') for e in cal_econ.get('eventos_hoje', []))
        return {
            'versao': '1.0',
            'decisao': 'NO-GO por calendário econômico',
            'motivo_veto': eventos,
            'score_ajustado': None,
        }

    saz        = payload.get('sazonalidade', {}) or {}
    conv       = payload.get('convergencia', {}) or {}
    curva_saz  = payload.get('curva_leitura_sazonal', {}) or {}
    spread_cal = payload.get('spread_calendario', {}) or {}
    cambio     = payload.get('cambio', {}) or {}
    fundamentos = payload.get('fundamentos', {}) or {}
    ccm        = payload.get('ccm', {}) or {}

    score_saz, nota_saz = _bias_score_sazonalidade(saz)
    score_fis, nota_fis = _bias_score_fisico(conv, curva_saz, spread_cal)
    score_mac, nota_mac = _bias_score_macro(cambio, fundamentos)
    score_tec, nota_tec = _bias_score_tecnico(ccm)

    dimensoes = {'sazonalidade': score_saz, 'fisico': score_fis, 'macro': score_mac, 'tecnico': score_tec}
    validadas = {k: v for k, v in dimensoes.items() if v is not None}
    n_validadas = len(validadas)
    detalhes = {'sazonalidade': nota_saz, 'fisico': nota_fis, 'macro': nota_mac, 'tecnico': nota_tec}

    if n_validadas == 0:
        return {'versao': '1.0', 'decisao': 'sem dado suficiente', 'detalhes': detalhes}

    peso_total = sum(BIAS_PESOS[k] for k in validadas)
    score_bruto = sum(validadas[k] * BIAS_PESOS[k] for k in validadas) / peso_total
    fator_confianca = n_validadas / 4
    score_ajustado = score_bruto * fator_confianca
    decisao = next(rotulo for limite, rotulo in BIAS_FAIXAS if abs(score_ajustado) >= limite)

    return {
        'versao': '1.0',
        'score_bruto': round(score_bruto, 1),
        'score_ajustado': round(score_ajustado, 1),
        'confianca': f'{n_validadas}/4 dimensões validadas',
        'decisao': decisao,
        'dimensoes': {k: (round(v, 1) if v is not None else None) for k, v in dimensoes.items()},
        'detalhes': detalhes,
    }


# ══════════════════════════════════════════════════════════════════════════
# VEREDITO CONSOLIDADO (Fase 3B; reescrito 17/09/2026 na migração p/ TRIX v5)
#
# Decidido com o usuário em 20/07/2026: não manter Decisão e Bias Estrutural
# como dois veredictos separados que o operador precisa reconciliar na
# cabeça. Este é o ÚNICO módulo de decisão — funde o sinal técnico com o
# Bias Estrutural num consenso só.
#
# MIGRAÇÃO 17/09/2026 — mudança de modelo, não só de indicador: EMA9/20 +
# Setup 9.1 eram dois sinais de CRUZAMENTO independentes que precisavam
# concordar. O TRIX v5 validado é stop-and-reverse: uma vez que entra, FICA
# na posição até o cruzamento oposto (sem stop técnico, sem alvo fixo — ver
# trix_v5.py). Isso muda o que "operar" significa no dia a dia: na maioria
# dos pregões não há cruzamento novo nenhum — o sistema simplesmente
# continua na posição que já tinha. Tratar todo dia sem cruzamento como
# "AGUARDAR" (como fazia o modelo antigo) esconderia do operador que ele
# JÁ TEM uma posição aberta que o sistema recomenda manter. Por isso o
# veredito agora distingue três estados, não dois:
#   - ENTRAR [direção]: há cruzamento HOJE que abre posição nova.
#   - MANTER [direção]: já existe posição aberta do TRIX v5, sem cruzamento
#     hoje — não é uma ordem nova, é "continue como está".
#   - AGUARDAR: sistema está FLAT (sem posição) e não houve cruzamento hoje.
#
# Regra (nessa ordem, a primeira que bater decide):
#   1. Calendário econômico bloqueando hoje -> NÃO OPERAR (veto duro).
#   2. Sem posição aberta e sem cruzamento hoje -> AGUARDAR.
#   3. Cruzamento hoje (nova entrada) e Bias Estrutural FORTE (|score|>=50)
#      na direção CONTRÁRIA -> AGUARDAR (estrutura pesa mais que timing de
#      entrada nova). Importante: este veto só se aplica a ENTRADAS novas —
#      nunca força o fechamento de uma posição já aberta, porque isso
#      alteraria a regra de saída do sistema validado (só sai no cruzamento
#      oposto). Um Bias forte contra uma posição já aberta aparece como
#      atrito/alerta no motivo, não como ordem de fechar.
#   4. Cruzamento hoje sem veto -> ENTRAR na direção do cruzamento, com
#      convicção ALTA/MODERADA conforme o Bias Estrutural (moderado contra
#      reduz a convicção, não veta).
#   5. Sem cruzamento hoje mas com posição aberta -> MANTER na direção da
#      posição, sinalizando como atrito se o Bias Estrutural estiver forte
#      contra (alerta para o operador considerar redução manual — decisão
#      dele, o sistema não fecha sozinho fora da regra validada).
# ══════════════════════════════════════════════════════════════════════════

def calcular_veredito_consolidado(dados_ccm: dict, bias_estrutural: dict, calendario_economico: dict) -> dict:
    posicao = dados_ccm.get('posicao_trix_v5', 'FLAT')  # 'COMPRADO'/'VENDIDO'/'FLAT'
    entrada_hoje = dados_ccm.get('entrada_hoje')          # 'COMPRA'/'VENDA'/None
    direcao_posicao = {'COMPRADO': 'COMPRA', 'VENDIDO': 'VENDA', 'FLAT': None}[posicao]

    if (calendario_economico or {}).get('bloquear_hoje'):
        eventos = ', '.join(e.get('evento', '?') for e in (calendario_economico or {}).get('eventos_hoje', []))
        return {
            'veredito': 'NÃO OPERAR', 'direcao': direcao_posicao, 'convicao': None,
            'motivo': f'Divulgação hoje: {eventos or "evento de calendário econômico"}. '
                      f'TRIX v5 e Bias Estrutural suspensos — volatilidade de divulgação domina.',
        }

    score = (bias_estrutural or {}).get('score_ajustado')
    direcao_estrutural = None
    if score is not None:
        if score >= 20:
            direcao_estrutural = 'COMPRA'
        elif score <= -20:
            direcao_estrutural = 'VENDA'

    if entrada_hoje is None and direcao_posicao is None:
        return {
            'veredito': 'AGUARDAR', 'direcao': None, 'convicao': None,
            'motivo': 'TRIX v5 sem posição aberta (FLAT) e sem cruzamento hoje.',
        }

    if entrada_hoje is not None:
        concordancia = 'neutro'
        if direcao_estrutural == entrada_hoje:
            concordancia = 'concorda'
        elif direcao_estrutural is not None and direcao_estrutural != entrada_hoje:
            concordancia = 'discorda'

        if concordancia == 'discorda' and score is not None and abs(score) >= 50:
            return {
                'veredito': 'AGUARDAR', 'direcao': entrada_hoje, 'convicao': None,
                'motivo': f'TRIX v5 cruzou para {entrada_hoje} hoje, mas Bias Estrutural forte contra '
                          f'({score:+.1f}) — estrutura pesa mais que uma entrada nova.',
            }

        convicao = 'MODERADA' if concordancia == 'discorda' else 'ALTA'
        veredito = f'ENTRAR {entrada_hoje}' + ('' if convicao == 'ALTA' else ' — TAMANHO REDUZIDO')
        motivo = (f'Bias Estrutural moderado contra ({score:+.1f})' if concordancia == 'discorda'
                  else 'Cruzamento TRIX v5 confirmado' + (f' e Bias Estrutural concorda ({score:+.1f})' if concordancia == 'concorda' else '.'))
        return {
            'veredito': veredito, 'direcao': entrada_hoje, 'convicao': convicao,
            'concordancia_bias': concordancia, 'motivo': motivo,
        }

    # Sem cruzamento hoje, mas com posição aberta -> MANTER.
    concordancia = 'neutro'
    if direcao_estrutural == direcao_posicao:
        concordancia = 'concorda'
    elif direcao_estrutural is not None and direcao_estrutural != direcao_posicao:
        concordancia = 'discorda'

    atrito = f' Bias Estrutural forte contra a posição aberta ({score:+.1f}) — considere reduzir manualmente; o sistema só sai no cruzamento oposto.' \
        if (concordancia == 'discorda' and score is not None and abs(score) >= 50) else ''

    return {
        'veredito': f'MANTER {direcao_posicao}',
        'direcao': direcao_posicao,
        'convicao': None,
        'concordancia_bias': concordancia,
        'motivo': f'Posição aberta desde cruzamento anterior, sem cruzamento novo hoje.{atrito}',
    }


# ══════════════════════════════════════════════════════════════════════════
# RESUMO EXECUTIVO (Fase 3B, 20/07/2026)
#
# Pedido do usuário: separar a recomendação por público, porque "operar o
# CCM" (trader/especulador), "vender a safra" (produtor) e "comprar milho
# físico" (indústria/consumidor) são decisões diferentes mesmo olhando o
# mesmo mercado. NÃO introduz dado novo — é uma camada de tradução sobre o
# que já foi calculado (veredito_consolidado, Bias Estrutural, sazonalidade,
# convergência).
#
# Trader: usa o veredito_consolidado direto (timing tático já resolvido).
# Vendedor/Comprador: usam o Bias Estrutural (médio prazo) + sazonalidade,
# não o timing técnico diário — para quem vende/compra fisicamente, o
# ruído técnico de curto prazo não é o que importa, o contexto estrutural
# sim. Convergência entra como complemento: spread futuro×físico muito
# esticado é sinal de bom momento para travar preço via CCM (hedge), em
# qualquer direção.
#
# Isto é conteúdo educacional, não recomendação de investimento
# personalizada — precisa do disclaimer regulatório no relatório final.
# ══════════════════════════════════════════════════════════════════════════

def gerar_resumo_executivo(veredito_consolidado: dict, bias_estrutural: dict,
                            convergencia: dict, calendario_economico: dict) -> dict:
    cal = calendario_economico or {}
    if cal.get('bloquear_hoje'):
        eventos = ', '.join(e.get('evento', '?') for e in cal.get('eventos_hoje', []))
        msg = (f'Divulgação hoje ({eventos or "evento de calendário econômico"}) — '
               f'aguardar o mercado assimilar antes de qualquer decisão de preço.')
        return {'trader': msg, 'comprador': msg, 'vendedor': msg}

    vc = veredito_consolidado or {}
    trader_txt = f"{vc.get('veredito', '—')}" + (f" (convicção {vc['convicao']})" if vc.get('convicao') else '') + f". {vc.get('motivo', '')}"

    score = (bias_estrutural or {}).get('score_ajustado')
    if score is None:
        faixa = None
    elif score >= 50:
        faixa = 'altista_forte'
    elif score >= 20:
        faixa = 'altista_moderado'
    elif score <= -50:
        faixa = 'baixista_forte'
    elif score <= -20:
        faixa = 'baixista_moderado'
    else:
        faixa = 'neutro'

    textos_vendedor = {
        None: 'Bias Estrutural indisponível nesta rodada — sem base para recomendação de venda.',
        'altista_forte': f'Contexto estrutural fortemente altista (score {score:+.1f}) — considere AGUARDAR para vender, preços tendem a melhorar. Se precisar de caixa, venda só o necessário agora.',
        'altista_moderado': f'Contexto moderadamente altista (score {score:+.1f}) — leve vantagem em aguardar, sem urgência de esperar muito.',
        'neutro': 'Sem viés estrutural relevante — decisão de venda deve seguir seu fluxo de caixa/logística, não timing de mercado.',
        'baixista_moderado': f'Contexto moderadamente baixista (score {score:+.1f}) — considere fixar/vender parte da safra agora.',
        'baixista_forte': f'Contexto fortemente baixista (score {score:+.1f}) — considere fixar/vender agora ou travar via CCM; risco real de preços piores à frente.',
    }
    textos_comprador = {
        None: 'Bias Estrutural indisponível nesta rodada — sem base para recomendação de compra.',
        'altista_forte': f'Contexto fortemente altista (score {score:+.1f}) — considere travar/comprar agora antes de preços subirem mais.',
        'altista_moderado': f'Contexto moderadamente altista (score {score:+.1f}) — leve vantagem em comprar/travar logo.',
        'neutro': 'Sem viés estrutural relevante — decisão de compra deve seguir sua necessidade operacional, não timing de mercado.',
        'baixista_moderado': f'Contexto moderadamente baixista (score {score:+.1f}) — pode aguardar, preços tendem a ceder.',
        'baixista_forte': f'Contexto fortemente baixista (score {score:+.1f}) — aguardar tende a compensar; risco de pagar caro agora é maior.',
    }

    vendedor_txt  = textos_vendedor[faixa]
    comprador_txt = textos_comprador[faixa]

    conv = convergencia or {}
    z = conv.get('spread_zscore')
    if isinstance(z, (int, float)):
        if z >= 1.5:
            vendedor_txt += f' Prêmio do futuro sobre o físico está historicamente esticado (Z={z:+.1f}σ) — bom momento para travar preço via CCM.'
        elif z <= -1.5:
            comprador_txt += f' Futuro com desconto historicamente esticado sobre o físico (Z={z:+.1f}σ) — bom momento para travar compra via CCM.'

    return {'trader': trader_txt, 'comprador': comprador_txt, 'vendedor': vendedor_txt}

# ══════════════════════════════ FIM DO BLOCO NOVO ═══════════════════════════


# ── PIPELINE PRINCIPAL ────────────────────────────────────────────────────────

def rodar_pipeline(pasta_dados: str, pasta_saida: str) -> dict:
    """
    Executa todas as etapas do pipeline e retorna o JSON completo.
    """
    log = []
    erros = []

    def ok(msg):
        log.append(f'✅ {msg}')
        try:
            print(f'✅ {msg}')
        except UnicodeEncodeError:
            try:
                print(f'[OK] {msg}')
            except UnicodeEncodeError:
                print(f'[OK] {msg.encode("ascii", errors="replace").decode("ascii")}')

    def err(msg):
        erros.append(f'❌ {msg}')
        try:
            print(f'❌ {msg}')
        except UnicodeEncodeError:
            try:
                print(f'[ERRO] {msg}')
            except UnicodeEncodeError:
                print(f'[ERRO] {msg.encode("ascii", errors="replace").decode("ascii")}')

    print('=' * 60)
    print(f'MILHO TRADER — PIPELINE v1.0')
    print(f'Data/hora: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}')
    print(f'Pasta dados: {pasta_dados}')
    print('=' * 60)

    # ── ETAPA 1: CCM FUTURO ───────────────────────────────────────────────────
    dados_ccm = None
    try:
        dados_ccm = analisar_ccmfut(pasta_dados)
        ok(f'CCMFUT | Preço: R$ {dados_ccm["ultimo_preco"]}/sc | '
           f'EMA9/20: {dados_ccm["sinal_ema920"]} | '
           f'9.1: {dados_ccm["sinal_91"]}')
    except Exception as e:
        err(f'CCMFUT falhou: {e}')
        dados_ccm = _ccm_vazio()

    candles = []
    try:
        candles = obter_candles(pasta_dados, dados_ccm['vencimento_ativo'], 40)
        if candles:
            ok(f'Candles | {len(candles)} pregões de {dados_ccm["vencimento_ativo"]}')
    except Exception as e:
        err(f'Candles falhou: {e}')

    # ── ETAPA 2: CURVA DE VENCIMENTOS ─────────────────────────────────────────
    curva = {'contratos': [], 'estrutura': 'N/A', 'total_vencimentos': 0}
    try:
        curva = analisar_curva_vencimentos(pasta_dados, date.today())
        ok(f'Curva | {curva["total_vencimentos"]} contratos | {curva["estrutura"]}')
    except Exception as e:
        err(f'Curva de vencimentos falhou: {e}')

    # ── ETAPA 3: OI OPÇÕES (Call Wall / Put Wall / Max Pain) ──────────────────
    # Substituído por BRAPI (OI real por strike) em 01/09/2026 — decisão do
    # usuário: a grade manual CCM_OP.xlsx tinha ~53% dos tickers mal
    # interpretados por fórmula quebrada no Excel (ver cabeçalho de
    # oi_opcoes.py). O caminho antigo (analisar_oi_opcoes/
    # analisar_todas_expiracoes, ainda importados acima) só roda como
    # fallback se a BRAPI estiver indisponível nesta rodada (token ausente
    # ou API fora do ar) — nunca como primeira escolha.
    oi_opcoes = dict(OI_OPCOES_DEFAULT)
    oi_por_contrato = {}
    curva_brapi = None
    try:
        if not ingestao_brapi.token_disponivel():
            err('BRAPI_TOKEN não configurado — OI Opções cai no fallback CCM_OP.xlsx')
        else:
            curva_brapi = ingestao_brapi.coletar_curva_ccm()
            if curva_brapi is None:
                err('BRAPI indisponível (curva CCM) — OI Opções cai no fallback CCM_OP.xlsx')
    except Exception as e:
        err(f'BRAPI (curva CCM) falhou: {e}')

    if curva_brapi:
        try:
            oi_todos = ingestao_brapi.coletar_oi_todos_vencimentos(curva_brapi['curva'])
            oi_opcoes = ingestao_brapi.montar_oi_opcoes(
                oi_todos, curva_brapi['curva'], dados_ccm['vencimento_ativo'], dados_ccm['ultimo_preco']
            )
            if oi_opcoes.get('max_pain') is not None:
                ok(f'OI Opções (BRAPI) | Venc. {oi_opcoes.get("vencimento_opcoes")} | '
                   f'Call Wall: R$ {oi_opcoes.get("call_wall")} | Put Wall: R$ {oi_opcoes.get("put_wall")} | '
                   f'Max Pain: R$ {oi_opcoes.get("max_pain")}')
            else:
                ok('OI Opções (BRAPI) | sem posições retornadas para o vencimento ativo')

            oi_por_contrato = ingestao_brapi.montar_oi_por_contrato(oi_todos, curva_brapi['curva'])
            for cod, info in oi_por_contrato.items():
                info['candles'] = obter_candles(pasta_dados, cod, 40)
            if oi_por_contrato:
                ok(f'OI por Contrato (BRAPI) | {len(oi_por_contrato)} expirações disponíveis para seleção')
        except Exception as e:
            err(f'OI Opções via BRAPI falhou: {e} — caindo no fallback CCM_OP.xlsx')
            curva_brapi = None  # força o bloco de fallback abaixo

    if not curva_brapi:
        try:
            oi_opcoes = analisar_oi_opcoes(pasta_dados, dados_ccm['vencimento_ativo'], dados_ccm['ultimo_preco'])
            if oi_opcoes.get('max_pain') is not None:
                ok(f'OI Opções (fallback Excel) | Venc. {oi_opcoes.get("vencimento_opcoes")} | '
                   f'Call Wall: R$ {oi_opcoes.get("call_wall")} | Put Wall: R$ {oi_opcoes.get("put_wall")} | '
                   f'Max Pain: R$ {oi_opcoes.get("max_pain")}')
            else:
                ok('OI Opções (fallback Excel) | grade não encontrada (CCM_OP*.xlsx)')

            oi_por_contrato = analisar_todas_expiracoes(pasta_dados)
            for cod, info in oi_por_contrato.items():
                info['candles'] = obter_candles(pasta_dados, cod, 40)
            if oi_por_contrato:
                ok(f'OI por Contrato (fallback Excel) | {len(oi_por_contrato)} expirações disponíveis')
        except Exception as e:
            err(f'OI Opções (fallback Excel) falhou: {e}')

    # ── ETAPA 4: CONVERGÊNCIA (RTCNI) ─────────────────────────────────────────
    convergencia = {}
    try:
        convergencia = analisar_convergencia(
            pasta_dados, dados_ccm['ultimo_preco'], dados_ccm['vencimento_ativo'], date.today()
        )
        alerta_str = '⚠️ ALERTA' if convergencia.get('alerta_convergencia') else 'normal'
        ok(f'RTCNI | Físico: R$ {convergencia.get("rtcni_preco")}/sc | '
           f'Spread: R$ {convergencia.get("spread_futuro_fisico")}/sc | '
           f'Z={convergencia.get("spread_zscore")}σ | {alerta_str}')
    except Exception as e:
        err(f'Convergência falhou: {e}')

    # ── ETAPA 5: CÂMBIO, DI, ZC E BRENT ──────────────────────────────────────
    macro_completo = {}
    try:
        preco_fisico = convergencia.get('rtcni_preco') or 0.0
        macro_completo = analisar_macro_completo(
            pasta_dados,
            dados_ccm['ultimo_preco'],
            preco_fisico,
        )
        cam = macro_completo['cambio']
        zc  = macro_completo['zc_cme']
        ok(f'Câmbio | USDBRL: {cam.get("wdofut_usdbrl")} | Diagnóstico: {cam.get("diagnostico")}')
        ok(f'ZC CME | {zc.get("preco_cents_bu")} c/bu | Fonte: {macro_completo.get("fonte_zc")}')
    except Exception as e:
        err(f'Macro falhou: {e}')

    # ── ETAPA 5B: INGESTÃO BRAPI EM MODO SOMBRA (câmbio, DI, curva) ───────────
    # Criada em 01/09/2026 — seção 4.1 do documento Agro Intelligence B2B.
    # NÃO substitui nada aqui: só coleta o mesmo dado via BRAPI e compara
    # contra o valor já obtido pela via legada (CSV manual), gravando a
    # divergência no payload para acompanhamento. Decisão de substituir
    # fica para depois de medir a divergência por algumas rodadas reais —
    # mitigação de risco "modo sombra" pedida no documento de arquitetura.
    ingestao_brapi_sombra = {'token_disponivel': ingestao_brapi.token_disponivel()}
    if ingestao_brapi_sombra['token_disponivel']:
        try:
            cambio_brapi = ingestao_brapi.coletar_cambio()
            di_brapi     = ingestao_brapi.coletar_di()
            curva_ccm_brapi = curva_brapi if curva_brapi else ingestao_brapi.coletar_curva_ccm()

            def _divergencia_pct(legado, novo):
                if legado in (None, 0) or novo is None:
                    return None
                return round((novo - legado) / legado * 100, 2)

            cam_legado = macro_completo.get('cambio', {}) or {}
            di_legado  = macro_completo.get('carrego', {}) or {}

            ingestao_brapi_sombra['cambio'] = {
                'legado': {'wdofut': cam_legado.get('wdofut'), 'wdofut_usdbrl': cam_legado.get('wdofut_usdbrl')},
                'brapi':  cambio_brapi,
                'divergencia_wdofut_pct': _divergencia_pct(
                    cam_legado.get('wdofut'), (cambio_brapi or {}).get('wdofut')
                ),
            }
            ingestao_brapi_sombra['di'] = {
                'legado': {'di1f27_taxa': di_legado.get('di1f27_taxa'), 'di1f29_taxa': di_legado.get('di1f29_taxa')},
                'brapi':  di_brapi,
                'divergencia_di1f27_pct': _divergencia_pct(
                    di_legado.get('di1f27_taxa'), (di_brapi or {}).get('di1f27_taxa')
                ),
            }
            ingestao_brapi_sombra['curva'] = {
                'vencimento_ativo_legado': curva.get('estrutura') and dados_ccm.get('vencimento_ativo'),
                'vencimento_ativo_brapi':  (curva_ccm_brapi or {}).get('vencimento_ativo'),
                'contratos_concordam':     (
                    dados_ccm.get('vencimento_ativo') == (curva_ccm_brapi or {}).get('vencimento_ativo')
                    if curva_ccm_brapi else None
                ),
            }
            ok(f"Ingestão BRAPI (sombra) | câmbio div. {ingestao_brapi_sombra['cambio']['divergencia_wdofut_pct']}% | "
               f"DI div. {ingestao_brapi_sombra['di']['divergencia_di1f27_pct']}% | "
               f"contrato ativo concorda: {ingestao_brapi_sombra['curva']['contratos_concordam']}")
        except Exception as e:
            err(f'Ingestão BRAPI (sombra) falhou: {e}')
    else:
        ok('Ingestão BRAPI (sombra) | BRAPI_TOKEN não configurado — só a via legada roda nesta rodada')

    # ── ETAPA 6: SAZONALIDADE (Fase 3B) ──────────────────────────────────────
    sazonalidade = {}
    try:
        saz = calcular_sazonalidade(pasta_dados, date.today())
        if saz.get('status') == 'OK':
            ctx = saz['contexto_atual']
            ok(f'Sazonalidade | Fase: {ctx["fase_agricola"]} | '
               f'Desvio atual: {ctx["desvio_atual_pct"]:+.1f}% | '
               f'Viés: {ctx["vies_sazonal"]}')
        else:
            err(f'Sazonalidade falhou: {saz.get("erro", "erro desconhecido")}')

        sazonalidade = {
            'status':             saz.get('status'),
            'periodo_base':       saz.get('periodo_base'),
            'aviso_historico':    saz.get('aviso_historico'),
            'fase_agricola':      saz.get('contexto_atual', {}).get('fase_agricola'),
            'descricao_fase':     saz.get('contexto_atual', {}).get('descricao_fase'),
            'vies_sazonal':       saz.get('contexto_atual', {}).get('vies_sazonal'),
            'quinzena_atual':     saz.get('contexto_atual', {}).get('quinzena_atual'),
            'desvio_atual_pct':   saz.get('contexto_atual', {}).get('desvio_atual_pct'),
            'desvio_std_pct':     saz.get('contexto_atual', {}).get('desvio_std_pct'),
            'proxima_quinzena':   saz.get('contexto_atual', {}).get('proxima_quinzena'),
            'desvio_proxima_pct': saz.get('contexto_atual', {}).get('desvio_proxima_pct'),
            'delta_quinzenal_pct':saz.get('contexto_atual', {}).get('delta_quinzenal_pct'),
            'tendencia_sazonal':  saz.get('contexto_atual', {}).get('tendencia_sazonal'),
            'virada_sazonal':     saz.get('contexto_atual', {}).get('virada_sazonal'),
            'meses_ate_pico_mar': saz.get('contexto_atual', {}).get('meses_ate_pico_mar'),
            'calendario_mensal':  saz.get('calendario_mensal', []),
        }

        # Contrato Afetado por mês (pedido do usuário, 31/07/2026): liga o
        # viés sazonal de cada mês ao código do contrato CCM que de fato
        # vence naquele mês (ex.: viés BAIXISTA em Jan -> alerta em CCMF).
        # O CCM só lista vencimento em Jan/Mar/Mai/Jul/Ago/Set/Nov (F, H, K,
        # N, Q, U, X) — os outros 5 meses não têm contrato próprio, isso não
        # é lacuna de dado. Distingue os dois casos explicitamente para não
        # confundir "mês sem vencimento no produto" com "vencimento existe
        # mas falta o CSV na pasta".
        try:
            for linha in sazonalidade['calendario_mensal']:
                mes_num = linha.get('mes_num')
                tem_vencimento = mes_num in LETRA_POR_MES_VENCIMENTO
                contrato = contrato_vivo_do_mes(pasta_dados, mes_num, date.today()) if tem_vencimento else None
                linha['tem_vencimento_ccm'] = tem_vencimento
                linha['contrato_letra'] = f'CCM{LETRA_POR_MES_VENCIMENTO[mes_num]}' if tem_vencimento else None
                linha['contrato_afetado'] = contrato
            ok('Contrato Afetado por mês | calendário sazonal ligado aos vencimentos CCM')
        except Exception as e:
            err(f'Contrato Afetado por mês falhou: {e}')
    except Exception as e:
        err(f'Sazonalidade falhou: {e}')

    # ── ETAPA 6B: CURVA × SAZONALIDADE ────────────────────────────────────────
    # Sem custo de carrego confiável ponto-a-ponto na curva inteira (só temos
    # 2 vencimentos de DI — DI1F27 e DI1F29 — insuficiente para os ~8 pares
    # de vencimentos do milho sem extrapolar). Em vez disso, cruza a
    # ESTRUTURA observada (contango/backwardation) contra o viés sazonal
    # esperado: fase de colheita/alta oferta (viés BAIXISTA) deveria mostrar
    # contango normal; fase de aperto/baixo estoque (viés ALTISTA) deveria
    # mostrar achatamento ou backwardation. Decidido com o usuário em
    # 11/07/2026.
    curva_leitura_sazonal = _leitura_curva_vs_sazonalidade(curva['estrutura'], sazonalidade)
    if curva_leitura_sazonal['avaliavel']:
        ok(f'Curva×Sazonalidade | {"consistente" if curva_leitura_sazonal["consistente"] else "DESTOA"}')

    # ── ETAPA 6C: SPREAD CALENDÁRIO (Fase 3B) ─────────────────────────────────
    # Trata o spread entre pares dos 3 contratos CCM mais líquidos (vivos)
    # como uma série própria, com média/desvio/Z-score reais — não roda o
    # sistema EMA/Setup 9.1 (validado só no CCMFUT contínuo) em cada
    # vencimento individual, que teria liquidez muito menor. Cobre o caso de
    # o operador comprar um vencimento e vender outro. Decidido com o
    # usuário em 11/07/2026 ("Só spread trade").
    spread_calendario = {'contratos_considerados': [], 'pares': []}
    try:
        spread_calendario = analisar_spreads_calendario(pasta_dados, date.today())
        n_alertas = sum(1 for p in spread_calendario['pares'] if p.get('alerta'))
        ok(f'Spread Calendário | {len(spread_calendario["pares"])} pares '
           f'({", ".join(spread_calendario["contratos_considerados"])}) | {n_alertas} com alerta')
    except Exception as e:
        err(f'Spread Calendário falhou: {e}')

    # ── ETAPA 6D: CALENDÁRIO ECONÔMICO (Fase 3B) ──────────────────────────────
    # Bloqueio duro (não soft) no dia de divulgação WASDE/Estoques
    # Trimestrais (USDA) ou Boletim da Safra de Grãos (CONAB) — volatilidade
    # de divulgação pode passar por cima de qualquer stop técnico. Decidido
    # com o usuário em 11/07/2026: "alerta para o operador não operar em
    # dias de divulgação".
    calendario_economico = {'bloquear_hoje': False, 'eventos_hoje': [], 'proximo_evento': None}
    try:
        calendario_economico = verificar_calendario_economico(date.today())
        if calendario_economico['bloquear_hoje']:
            nomes = ', '.join(e['evento'] for e in calendario_economico['eventos_hoje'])
            ok(f'Calendário Econômico | ⚠️ HOJE: {nomes}')
        elif calendario_economico.get('proximo_evento'):
            pe = calendario_economico['proximo_evento']
            ok(f'Calendário Econômico | próximo: {pe["evento"]} em {calendario_economico["dias_ate_proximo_evento"]}d ({pe["data_br"]})')
        if calendario_economico.get('usda_desatualizado'):
            err('Calendário Econômico | ⚠️ dados WASDE/Estoques (USDA) esgotados para o ano corrente — reconfira '
                'e atualize calendario_economico.py manualmente (busca as datas do próximo ano)')
    except Exception as e:
        err(f'Calendário Econômico falhou: {e}')

    # ── ETAPA 6E: STRUCTURAL BIAS SCORE (Fase 3B, v1.0) ───────────────────────
    # Agrega sazonalidade + físico (RTCNI/convergência + curva) + macro +
    # técnico num score único, com veto duro se houver bloqueio de
    # calendário econômico hoje. Mapeamento categórico exato (COMPRA/VENDA/
    # NEUTRO, ALTISTA/BAIXISTA/NEUTRO) confirmado lendo ccm_dados.py e
    # sazonalidade_milho.py — ver comentário no topo do arquivo.
    bias_estrutural = {}
    try:
        _payload_parcial_bias = {
            'sazonalidade':          sazonalidade,
            'convergencia':          convergencia,
            'curva_leitura_sazonal': curva_leitura_sazonal,
            'spread_calendario':     spread_calendario,
            'cambio':                macro_completo.get('cambio', {}),
            'fundamentos':           FUNDAMENTOS_DEFAULT,
            'ccm':                   dados_ccm,
            'calendario_economico':  calendario_economico,
        }
        bias_estrutural = calcular_bias_estrutural(_payload_parcial_bias)
        ok(f"Bias Estrutural | {bias_estrutural.get('decisao')} | "
           f"score={bias_estrutural.get('score_ajustado')} | "
           f"{bias_estrutural.get('confianca', '')}")
        for dim, nota in bias_estrutural.get('detalhes', {}).items():
            print(f'    - {dim}: {nota}')
    except Exception as e:
        err(f'Bias Estrutural falhou: {e}')

    # ── ETAPA 6F: VEREDITO CONSOLIDADO (Fase 3B) ──────────────────────────────
    # Único módulo de decisão — funde sinal técnico + Bias Estrutural (ver
    # comentário na definição da função). Substitui os dois banners
    # separados que existiam antes (Decisão e Bias Estrutural).
    veredito_consolidado = {}
    try:
        veredito_consolidado = calcular_veredito_consolidado(dados_ccm, bias_estrutural, calendario_economico)
        ok(f"Veredito Consolidado | {veredito_consolidado.get('veredito')} | "
           f"convicção: {veredito_consolidado.get('convicao')} | {veredito_consolidado.get('motivo')}")
    except Exception as e:
        err(f'Veredito Consolidado falhou: {e}')

    # ── ETAPA 6G: RESUMO EXECUTIVO POR PÚBLICO (Fase 3B) ──────────────────────
    # Traduz o mesmo veredito/Bias em recomendação separada para trader,
    # comprador e vendedor de milho físico. Ver comentário na definição de
    # gerar_resumo_executivo().
    resumo_executivo = {}
    try:
        resumo_executivo = gerar_resumo_executivo(veredito_consolidado, bias_estrutural, convergencia, calendario_economico)
        ok('Resumo Executivo | gerado para trader / comprador / vendedor')
    except Exception as e:
        err(f'Resumo Executivo falhou: {e}')

    # ── ETAPA 6H: ANÁLISE POR CONTRATO (Fase 4, 31/07/2026) ───────────────────
    # Pedido do usuário: o pipeline só analisava o contrato mais líquido
    # (via CCMFUT contínuo, usado como proxy — hoje CCMU26). Agora roda o
    # MESMO critério (EMA9/20 + Setup 9.1 + ATR + Bias Estrutural + Veredito
    # Consolidado) em CADA vencimento vivo individualmente, para o operador
    # escolher qual contrato de fato atende aos requisitos — não fica preso
    # ao mais líquido se outro vencimento tiver sinal melhor. Reaproveita as
    # 3 dimensões de Bias que não dependem do contrato específico
    # (sazonalidade/físico/macro, calculadas uma vez em _payload_parcial_bias
    # acima) e só recalcula a dimensão Técnico e o Veredito por contrato.
    contratos_analise = {}
    resumo_contratos  = []
    try:
        vivos = listar_vencimentos_vivos(pasta_dados, date.today())
        for codigo in vivos:
            try:
                ccm_c = analisar_contrato(pasta_dados, codigo)
            except Exception as e:
                err(f'Contrato {codigo} | análise técnica falhou: {e}')
                continue

            payload_bias_c = dict(_payload_parcial_bias)
            payload_bias_c['ccm'] = ccm_c
            bias_c     = calcular_bias_estrutural(payload_bias_c)
            veredito_c = calcular_veredito_consolidado(ccm_c, bias_c, calendario_economico)
            risco_c    = round(ccm_c.get('stop_atr15_dist', 0) * 450, 2)

            contratos_analise[codigo] = {
                'ccm':                 {**ccm_c, 'risco_por_contrato': risco_c},
                'bias_estrutural':     bias_c,
                'veredito_consolidado': veredito_c,
            }
            resumo_contratos.append({
                'contrato':      codigo,
                'preco':         ccm_c.get('ultimo_preco'),
                'sinal_ema920':  ccm_c.get('sinal_ema920'),
                'sinal_91':      ccm_c.get('sinal_91'),
                'veredito':      veredito_c.get('veredito'),
                'direcao':       veredito_c.get('direcao'),
                'convicao':      veredito_c.get('convicao'),
                'motivo':        veredito_c.get('motivo'),
                'score_bias':    bias_c.get('score_ajustado'),
                'volume_medio':  ccm_c.get('volume_medio'),
                'n_pregoes':     ccm_c.get('n_pregoes'),
                'e_mais_liquido': (codigo == dados_ccm.get('vencimento_ativo')),
            })
        n_operar = sum(1 for r in resumo_contratos if (r.get('veredito') or '').startswith(('ENTRAR', 'MANTER')))
        ok(f'Análise por Contrato | {len(contratos_analise)} vencimento(s) vivo(s) analisados | {n_operar} com veredito OPERAR')
    except Exception as e:
        err(f'Análise por Contrato falhou: {e}')

    # ── ETAPA 7: SIZING ───────────────────────────────────────────────────────
    sizing = calcular_sizing(dados_ccm['ultimo_preco'])
    risco_por_contrato = round(dados_ccm.get('stop_atr15_dist', 0) * 450, 2)

    # ── MONTA JSON ────────────────────────────────────────────────────────────
    cam  = macro_completo.get('cambio', {})
    di   = macro_completo.get('carrego', {})
    zc   = macro_completo.get('zc_cme', {})
    mac  = macro_completo.get('macro', {})

    payload = {
        'meta': {
            'versao':          '1.0',
            'gerado_em':       datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'pasta_dados':     pasta_dados,
            'erros':           erros,
            'log':             log,
        },
        'data_referencia': dados_ccm.get('data_ultimo', datetime.now().strftime('%d/%m/%Y')),

        # CCM — análise técnica
        'ccm': {
            'ultimo_preco':        dados_ccm['ultimo_preco'],
            'variacao_semanal_pct': dados_ccm['variacao_semanal_pct'],
            'vencimento_ativo':    dados_ccm['vencimento_ativo'],
            'ema9':                dados_ccm['ema9'],
            'ema20':               dados_ccm['ema20'],
            'sinal_ema920':        dados_ccm['sinal_ema920'],
            'ema9_slope':          dados_ccm['ema9_slope'],
            'sinal_91':            dados_ccm['sinal_91'],
            'atr14':               dados_ccm['atr14'],
            'stop_atr15':          dados_ccm['stop_atr15'],
            'stop_atr15_dist':     dados_ccm['stop_atr15_dist'],
            'alvo_rr2_dist':       dados_ccm['alvo_rr2_dist'],
            'alvo_rr2':            dados_ccm.get('alvo_rr2', 0.0),
            'risco_por_contrato':  risco_por_contrato,
            'volume_medio':        dados_ccm['volume_medio'],
            'suporte':             dados_ccm['suporte'],
            'resistencia':         dados_ccm['resistencia'],
            'candles':             candles,
        },

        # Curva de vencimentos
        'curva_vencimentos':      curva['contratos'],
        'estrutura_curva':        curva['estrutura'],
        'curva_leitura_sazonal':  curva_leitura_sazonal,

        # Convergência futuro×físico
        'convergencia': convergencia,

        # Custo de carrego (DI)
        'carrego': di,

        # Câmbio
        'cambio': cam,

        # ZC CME
        'zc_cme': zc,

        # Macro
        'macro': mac,

        # Fundamentos (manual — atualizar conforme CONAB/WASDE)
        'fundamentos': FUNDAMENTOS_DEFAULT,

        # OI Opções — Call Wall / Put Wall / Max Pain (grade CCM_OP.xlsx)
        'oi_opcoes': oi_opcoes,

        # OI por contrato — cada expiração com sua própria grade/paredes/candles,
        # para o seletor de contrato na aba Opções (Fase 3B)
        'oi_por_contrato': oi_por_contrato,

        # Sazonalidade proprietária (Fase 3B)
        'sazonalidade': sazonalidade,

        # Spread calendário — pares dos 3 contratos mais líquidos (Fase 3B)
        'spread_calendario': spread_calendario,

        # Calendário econômico — WASDE/Estoques (USDA) e Boletim (CONAB) (Fase 3B)
        'calendario_economico': calendario_economico,

        # Ingestão BRAPI em modo sombra — câmbio/DI/curva ainda não substituem
        # o legado, só medem divergência (seção 4.1, Agro Intelligence B2B)
        'ingestao_brapi_sombra': ingestao_brapi_sombra,

        # Structural Bias Score — v1.0 (Fase 3B)
        'bias_estrutural': bias_estrutural,

        # Veredito consolidado — funde técnico + Bias Estrutural num único
        # consenso (Fase 3B, 20/07/2026)
        'veredito_consolidado': veredito_consolidado,

        # Resumo executivo por público — trader / comprador / vendedor de
        # milho físico (Fase 3B, 20/07/2026)
        'resumo_executivo': resumo_executivo,

        # Análise por contrato — mesmo critério técnico rodado em CADA
        # vencimento vivo individualmente, para o seletor de contrato no
        # dashboard e o resumo comparativo (Fase 4, 31/07/2026)
        'contratos_analise': contratos_analise,
        'resumo_contratos':  resumo_contratos,

        # Sizing por perfil
        'sizing': {
            **sizing,
            'risco_por_contrato': risco_por_contrato,
        },
    }

    # ── ETAPA 8: CONSULTOR SENTINEL-CORN 2.0 (Fase 5, 18/09/2026) ─────────────
    sentinel_dados = {}
    try:
        import sentinel_engine
        curva_para_sentinel = []
        cbot_val = float((zc or {}).get('ultimo_preco') or 450.0)
        cambio_val = float((cam or {}).get('wdofut_usdbrl') or 5.40)
        spot_val = (convergencia or {}).get('rtcni_preco')
        est_curva = (curva or {}).get('estrutura', 'CONTANGO')

        for r_c in resumo_contratos:
            cod_c = r_c['contrato']
            c_info = contratos_analise.get(cod_c, {}).get('ccm', {})
            op_c = (oi_por_contrato or {}).get(cod_c, {})
            cw_c = op_c.get('call_wall') or (oi_opcoes.get('call_wall') if cod_c == dados_ccm.get('vencimento_ativo') else None)
            pw_c = op_c.get('put_wall') or (oi_opcoes.get('put_wall') if cod_c == dados_ccm.get('vencimento_ativo') else None)
            mp_c = op_c.get('max_pain') or (oi_opcoes.get('max_pain') if cod_c == dados_ccm.get('vencimento_ativo') else None)

            curva_para_sentinel.append({
                'codigo': cod_c,
                'ultimo_bar': {
                    'close': r_c.get('preco', 0.0),
                    'posicao': r_c.get('sinal_ema920', 'NEUTRO'),
                    'trix': 0.15 if r_c.get('sinal_ema920') == 'COMPRA' else (-0.15 if r_c.get('sinal_ema920') == 'VENDA' else 0.0),
                    'sinal': 0.0,
                    'sma100': c_info.get('suporte', 0.0),
                },
                'atr14': c_info.get('atr14', 1.50) or 1.50,
                'barreiras_opcoes': {
                    'call_wall': cw_c,
                    'put_wall': pw_c,
                    'max_pain': mp_c
                }
            })

        sentinel_dados = sentinel_engine.processar_sentimento_curva(
            curva_resultados=curva_para_sentinel,
            cbot_cents=cbot_val,
            cambio_usdbrl=cambio_val,
            preco_spot_rtcni=spot_val,
            estrutura_curva=est_curva
        )
        ok(f'Sentinel-Corn 2.0 | Sentimento calculado para {len(sentinel_dados.get("contratos", []))} contratos')
    except Exception as e:
        err(f'Sentinel-Corn 2.0 falhou: {e}')

    payload['sentinel_corn'] = sentinel_dados

    # ── SALVA JSON ────────────────────────────────────────────────────────────
    path_json = os.path.join(pasta_saida, ARQUIVO_JSON)
    with open(path_json, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    try:
        print()
        print('=' * 60)
        if erros:
            print(f'Pipeline concluido com {len(erros)} erro(s)')
            for e in erros:
                print(f'   {e.encode("ascii", errors="replace").decode("ascii")}')
        else:
            print('Pipeline concluido sem erros')
        print(f'JSON salvo em: {path_json}')
        print('=' * 60)
    except Exception:
        pass

    return payload


# ── FUNÇÕES DE FALLBACK ───────────────────────────────────────────────────────

def _leitura_curva_vs_sazonalidade(estrutura_curva: str, sazonalidade: dict) -> dict:
    """
    Cruza a estrutura observada da curva (CONTANGO/BACKWARDATION/FLAT) com o
    viés sazonal esperado. Regra: viés BAIXISTA (tipicamente colheita, oferta
    alta) → contango é o normal esperado; viés ALTISTA (tipicamente
    entressafra/aperto, estoque baixo) → achatamento/backwardation é o normal
    esperado. Quando a curva observada não bate com essa expectativa, é sinal
    de que algo fora do padrão sazonal típico pode estar em jogo (quebra de
    safra, demanda atípica, distorção de carrego) — não é uma regra formal
    validada estatisticamente, é uma leitura de consistência para o operador
    investigar, não um veredito de operação.
    """
    vies = (sazonalidade or {}).get('vies_sazonal')
    fase = (sazonalidade or {}).get('fase_agricola')

    if not sazonalidade or sazonalidade.get('status') != 'OK':
        return {'avaliavel': False, 'consistente': None, 'esperado': None,
                'leitura': 'Sazonalidade indisponível — sem cruzamento possível.'}

    if vies not in ('ALTISTA', 'BAIXISTA') or estrutura_curva not in ('CONTANGO', 'BACKWARDATION'):
        return {'avaliavel': False, 'consistente': None, 'esperado': None,
                'leitura': f'Viés sazonal ({vies}) ou estrutura da curva ({estrutura_curva}) neutros — sem leitura direcional a cruzar.'}

    esperado = 'CONTANGO' if vies == 'BAIXISTA' else 'BACKWARDATION'
    consistente = (estrutura_curva == esperado)

    if consistente:
        leitura = (
            f'Curva em {estrutura_curva} é consistente com a fase agrícola atual '
            f'({fase}, viés {vies}) — padrão sazonal normal, sem sinal de distorção adicional.'
        )
    else:
        leitura = (
            f'Curva em {estrutura_curva} DESTOA da fase agrícola atual '
            f'({fase}, viés {vies} esperaria {esperado}) — pode indicar fator fora do padrão '
            f'sazonal típico (quebra de safra, demanda atípica, distorção de carrego). '
            f'Vale investigar antes de assumir que é contango/backwardation normal.'
        )

    return {'avaliavel': True, 'consistente': consistente, 'esperado': esperado, 'leitura': leitura}


def _ccm_vazio() -> dict:
    return {
        'ultimo_preco': 0.0, 'variacao_semanal_pct': None,
        'vencimento_ativo': 'N/A', 'ema9': 0.0, 'ema20': 0.0,
        'sinal_ema920': 'N/A', 'ema9_slope': 0.0, 'sinal_91': 'N/A',
        'atr14': 0.0, 'stop_atr15': 0.0, 'stop_atr15_dist': 0.0,
        'alvo_rr2_dist': 0.0, 'alvo_rr2': 0.0, 'volume_medio': 0,
        'suporte': 0.0, 'resistencia': 0.0, 'data_ultimo': 'N/A',
    }


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    pasta_d = sys.argv[1] if len(sys.argv) > 1 else PASTA_DADOS
    pasta_s = sys.argv[2] if len(sys.argv) > 2 else PASTA_SAIDA
    rodar_pipeline(pasta_d, pasta_s)

import gerar_resumo_analise as resumo
resumo.gerar(caminho_json="dados_milho.json", pasta_saida=".")