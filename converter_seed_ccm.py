# -*- coding: utf-8 -*-
"""
converter_seed_ccm.py — Conversão one-off do histórico contínuo CCMFUT.
Origem: CCM_HIST.xlsx (export manual do Profit/Genial, CCMFUT diário contínuo)
Data de corte: 17/09/2026

Gera o arquivo fixo e imutável ccmfut_seed_2008_2026.csv para servir como seed
de profundidade histórica ao módulo ccm_trix_curva.py.
Possui mapeamento estrito e tolerante de colunas e validação programática de 100%
das linhas contra inconsistências OHLC.
"""

import os
import unicodedata
import pandas as pd


def _normalizar_nome(nome: str) -> str:
    """Normaliza nome de coluna removendo acentos e caracteres de substituição."""
    nfkd = unicodedata.normalize("NFKD", str(nome))
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return sem_acento.replace("", "").strip().lower()


def converter():
    caminho_xlsx = "CCM_HIST.xlsx"
    caminho_csv = "ccmfut_seed_2008_2026.csv"

    if not os.path.isfile(caminho_xlsx):
        raise FileNotFoundError(f"Arquivo de origem {caminho_xlsx} não encontrado.")

    print(f"Lendo {caminho_xlsx}...")
    df = pd.read_excel(caminho_xlsx)

    # a) Mapeamento estrito por nome canônico esperado
    col_map = {}
    for col in df.columns:
        norm = _normalizar_nome(col)
        if norm == "data":
            col_map[col] = "Data"
        elif norm in ("abertura", "open"):
            col_map[col] = "Open"
        elif norm in ("maxima", "maximo", "high"):
            col_map[col] = "High"
        elif norm in ("minima", "minimo", "low"):
            col_map[col] = "Low"
        elif norm in ("fechamento", "close"):
            col_map[col] = "Close"

    df = df.rename(columns=col_map)
    cols_esperadas = ["Data", "Open", "High", "Low", "Close"]

    # c) Falha explícita se cabeçalho mudar e coluna faltar
    for c in cols_esperadas:
        if c not in df.columns:
            raise ValueError(
                f"Coluna esperada '{c}' não encontrada no arquivo {caminho_xlsx}. "
                f"Colunas disponíveis: {list(df.columns)}"
            )

    df["Data"] = pd.to_datetime(df["Data"]).dt.strftime("%Y-%m-%d")
    df = df.sort_values("Data").reset_index(drop=True)

    for col_preco in ["Open", "High", "Low", "Close"]:
        df[col_preco] = df[col_preco].astype(float)

    # b) Validação programática de consistência OHLC em 100% das linhas
    # Permite tolerância numérica de float (1e-6)
    tol = 1e-6
    linhas_high_invalidas = df[
        (df["High"] < df["Open"] - tol)
        | (df["High"] < df["Close"] - tol)
        | (df["High"] < df["Low"] - tol)
    ]
    linhas_low_invalidas = df[
        (df["Low"] > df["Open"] + tol)
        | (df["Low"] > df["Close"] + tol)
    ]

    if not linhas_high_invalidas.empty:
        idx_primeiro = linhas_high_invalidas.index[0]
        linha_err = linhas_high_invalidas.iloc[0]
        raise ValueError(
            f"Erro de consistência OHLC: High < Open/Close/Low na linha {idx_primeiro} "
            f"(Data: {linha_err['Data']}, O:{linha_err['Open']}, H:{linha_err['High']}, "
            f"L:{linha_err['Low']}, C:{linha_err['Close']})"
        )

    if not linhas_low_invalidas.empty:
        idx_primeiro = linhas_low_invalidas.index[0]
        linha_err = linhas_low_invalidas.iloc[0]
        raise ValueError(
            f"Erro de consistência OHLC: Low > Open/Close na linha {idx_primeiro} "
            f"(Data: {linha_err['Data']}, O:{linha_err['Open']}, H:{linha_err['High']}, "
            f"L:{linha_err['Low']}, C:{linha_err['Close']})"
        )

    print(f"Validação OHLC concluída com sucesso em 100% das {len(df)} linhas.")

    header_comentario = (
        "# ccmfut_seed_2008_2026.csv — Histórico contínuo CCMFUT (Profit/Genial)\n"
        "# Data de corte: 17/09/2026 | Origem: export manual do Profit, CCMFUT contínuo\n"
        "# Entrada fixa read-only para viabilizar SMA(100) em contratos com histórico curto\n"
    )

    with open(caminho_csv, "w", encoding="utf-8", newline="") as f:
        f.write(header_comentario)
        df[cols_esperadas].to_csv(f, index=False)

    print(f"Sucesso: {caminho_csv} gerado e validado com {len(df)} registros.")
    print(f"Período: {df['Data'].iloc[0]} a {df['Data'].iloc[-1]}")


if __name__ == "__main__":
    converter()
