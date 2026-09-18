# leitor_csv.py — Milho Trader v1.0
# Leitura padronizada de todos os CSVs exportados do Profit/Genial
# Formato: separador=; | encoding=latin1 | decimal=, | milhar=. | header na linha 1
# IMPORTANTE: usa glob com wildcard para evitar problema de encoding no nome do arquivo

import pandas as pd
import numpy as np
import os
import glob
import time
import io


def _encontrar_arquivo(pasta: str, prefixo: str) -> str:
    """
    Localiza arquivo CSV pelo prefixo usando glob.
    Evita hardcode do acento em 'Diário' — funciona em qualquer encoding do SO.
    Ex: prefixo='CCMFUT' → encontra 'CCMFUT_F_0_Diário.csv'
    """
    padrao = os.path.join(pasta, f'{prefixo}*.csv')
    encontrados = glob.glob(padrao)
    # Ignora arquivos de seed contínuo como ccmfut_seed_*.csv
    encontrados = [f for f in encontrados if 'seed' not in os.path.basename(f).lower()]
    if not encontrados:
        return None
    # Retorna o mais recente se houver múltiplos
    return sorted(encontrados)[-1]


COLUNAS_PADRAO = ['Ativo', 'Data', 'Abertura', 'Máximo', 'Mínimo', 'Fechamento', 'Volume', 'Quantidade']


def ler_csv(path: str) -> pd.DataFrame:
    """
    Lê qualquer CSV do Profit/Genial e retorna DataFrame padronizado.
    Colunas: Ativo, Data, Open, High, Low, Close, Volume, Qtd
    Ordenado por Data crescente (mais antigo primeiro).

    Defensivo: o export do Profit às vezes grava o arquivo SEM a linha de
    cabeçalho (observado em produção em 10/07/2026 — mesmo CCMFUT, mesma
    sessão, apareceu com e sem cabeçalho entre uma leitura e outra). Detecta
    pela primeira célula da primeira linha: se não for 'Ativo', assume que
    já é dado e aplica os nomes de coluna padrão manualmente, em vez de
    estourar KeyError na hora de ler 'Data'.
    """
    # O exportador do Profit deixa bytes NUL de sobra em vários CSVs do projeto
    # (confirmado em produção em 10/07/2026: WDOFUT, DOLINDEX, DI1F27/29 e
    # alguns contratos CCM tinham de dezenas a ~20 mil bytes NUL no final do
    # arquivo — provavelmente um buffer de escrita de tamanho fixo que não é
    # truncado). O parser C do pandas tolera isso silenciosamente na maioria
    # dos casos, mas removemos os NUL explicitamente para não depender desse
    # comportamento implícito. Mantemos um retry curto por baixo só para
    # locks de I/O genuinamente transitórios (arquivo aberto por outro
    # processo no instante exato da leitura).
    ultima_excecao = None
    for tentativa in range(3):
        try:
            with open(path, encoding='latin1') as f:
                conteudo = f.read().replace('\x00', '')
            primeira_celula = conteudo.split('\n', 1)[0].split(';')[0].strip()
            tem_cabecalho = primeira_celula.lower() == 'ativo'

            df = pd.read_csv(
                io.StringIO(conteudo),
                sep=';',
                decimal=',',
                thousands='.',
                header=0 if tem_cabecalho else None,
                names=None if tem_cabecalho else COLUNAS_PADRAO,
            )
            break
        except Exception as e:
            ultima_excecao = e
            if tentativa < 2:
                time.sleep(0.5)
    else:
        raise ultima_excecao

    df = df.rename(columns={
        'Fechamento': 'Close',
        'Máximo':     'High',
        'Mínimo':     'Low',
        'Abertura':   'Open',
        'Volume':     'Volume',
        'Quantidade': 'Qtd',
    })

    df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
    df = df.dropna(subset=['Data'])
    df = df.sort_values('Data').reset_index(drop=True)

    return df


def ler_arquivo(pasta: str, prefixo: str) -> pd.DataFrame:
    """
    Localiza e lê um CSV pelo prefixo. Lança FileNotFoundError se não encontrar.
    """
    path = _encontrar_arquivo(pasta, prefixo)
    if path is None:
        raise FileNotFoundError(f'Arquivo com prefixo "{prefixo}" não encontrado em: {pasta}')
    return ler_csv(path)


def ler_wdofut(pasta: str) -> pd.DataFrame:
    """
    Lê WDOFUT e converte cotação de R$/1000 USD para R$/USD.
    """
    df = ler_arquivo(pasta, 'WDOFUT')
    df['USDBRL'] = df['Close'] / 1000.0
    return df


def ler_di(pasta: str, contrato: str) -> pd.DataFrame:
    """
    Lê contrato DI futuro (ex: contrato='DI1F27').
    Fechamento em % a.a. Adiciona taxa_decimal.
    """
    df = ler_arquivo(pasta, contrato)
    df['taxa_decimal'] = df['Close'] / 100.0
    return df


# Código de mês do contrato futuro (padrão B3/CME) → número do mês (1-12).
# Usado para ordenar contratos CRONOLOGICAMENTE, não alfabeticamente pelo nome do arquivo
# (ex.: CCMF27/Jan-2027 vem alfabeticamente antes de CCMH26/Mar-2026, mas é cronologicamente depois).
_MES_ORDEM = {
    'F': 1, 'G': 2, 'H': 3, 'J': 4, 'K': 5, 'M': 6,
    'N': 7, 'Q': 8, 'U': 9, 'V': 10, 'X': 11, 'Z': 12,
}


def extrair_vencimento(nome_arquivo: str) -> str:
    """
    Extrai o código de vencimento do nome do arquivo.
    Ex: CCMN26_F_0_Diário.csv → CCMN26
    """
    return os.path.basename(nome_arquivo).split('_')[0]


def _chave_vencimento(path: str) -> tuple:
    """
    Converte o código do contrato (ex: 'CCMN26') em uma chave (ano, mes)
    ordenável cronologicamente. Códigos com formato inesperado vão para o final.
    """
    codigo = extrair_vencimento(path)
    try:
        letra_mes = codigo[3]
        ano       = 2000 + int(codigo[4:6])
        mes       = _MES_ORDEM.get(letra_mes, 99)
        return (ano, mes)
    except (IndexError, ValueError):
        return (9999, 99)


def listar_contratos_ccm(pasta: str) -> list:
    """
    Varre a pasta e retorna lista ordenada de arquivos CCM por vencimento
    CRONOLÓGICO real (ano, mês) — não ordem alfabética do nome do arquivo.
    Exclui CCMFUT (contrato contínuo).
    """
    padrao = os.path.join(pasta, 'CCM*.csv')
    arquivos = glob.glob(padrao)
    arquivos = [a for a in arquivos if 'CCMFUT' not in os.path.basename(a).upper()]
    arquivos.sort(key=_chave_vencimento)
    return arquivos


def ultimo_valor(df: pd.DataFrame, coluna: str = 'Close') -> float:
    """Retorna o último valor não-nulo de uma coluna."""
    serie = df[coluna].dropna()
    return float(serie.iloc[-1]) if len(serie) > 0 else None


def variacao_pct(df: pd.DataFrame, coluna: str = 'Close', periodos: int = 5) -> float:
    """Calcula variação percentual dos últimos N períodos."""
    serie = df[coluna].dropna()
    if len(serie) < periodos + 1:
        return None
    atual    = serie.iloc[-1]
    anterior = serie.iloc[-periodos - 1]
    return round((atual - anterior) / anterior * 100, 2) if anterior != 0 else None


# ── TESTE ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    pasta = sys.argv[1] if len(sys.argv) > 1 else r'C:\Projetos Python\Milho'

    print('=' * 60)
    print('TESTE leitor_csv.py')
    print('=' * 60)

    # CCMFUT
    try:
        df = ler_arquivo(pasta, 'CCMFUT')
        print(f'\n✅ CCMFUT: {len(df)} pregões | Último: R$ {ultimo_valor(df):.2f}/sc')
    except FileNotFoundError as e:
        print(f'\n❌ {e}')

    # WDOFUT
    try:
        df = ler_wdofut(pasta)
        print(f'✅ WDOFUT: {len(df)} pregões | USDBRL: R$ {ultimo_valor(df, "USDBRL"):.4f}')
    except FileNotFoundError as e:
        print(f'❌ {e}')

    # RTCNI
    try:
        df = ler_arquivo(pasta, 'RTCNI')
        print(f'✅ RTCNI: {len(df)} pregões | Físico: R$ {ultimo_valor(df):.2f}/sc')
    except FileNotFoundError as e:
        print(f'❌ {e}')

    # DI1F27
    try:
        df = ler_di(pasta, 'DI1F27')
        print(f'✅ DI1F27: {len(df)} pregões | Taxa: {ultimo_valor(df):.3f}% a.a.')
    except FileNotFoundError as e:
        print(f'❌ {e}')

    # Contratos CCM
    contratos = listar_contratos_ccm(pasta)
    print(f'\n✅ Contratos CCM encontrados: {len(contratos)}')
    for c in contratos:
        print(f'   → {extrair_vencimento(c)}')
