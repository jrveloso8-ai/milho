# -*- coding: utf-8 -*-
"""
converter_seed_ccm.py — Conversão one-off do histórico contínuo CCMFUT.
Origem: CCM_HIST.xlsx (export manual do Profit/Genial, CCMFUT diário contínuo)
Data de corte: 17/09/2026

Gera o arquivo fixo e imutável ccmfut_seed_2008_2026.csv para servir como seed
de profundidade histórica ao módulo ccm_trix_curva.py.
"""

import os
import pandas as pd

def converter():
    caminho_xlsx = "CCM_HIST.xlsx"
    caminho_csv = "ccmfut_seed_2008_2026.csv"

    if not os.path.isfile(caminho_xlsx):
        raise FileNotFoundError(f"Arquivo de origem {caminho_xlsx} não encontrado.")

    print(f"Lendo {caminho_xlsx}...")
    df = pd.read_excel(caminho_xlsx)

    # Identificar colunas com tolerância a acentuação do Excel
    col_map = {}
    for col in df.columns:
        c_lower = col.lower()
        if "data" in c_lower:
            col_map[col] = "Data"
        elif "fech" in c_lower:
            col_map[col] = "Close"
        elif "abert" in c_lower:
            col_map[col] = "Open"
        elif "x" in c_lower:
            col_map[col] = "High"
        else:
            col_map[col] = "Low"

    df = df.rename(columns=col_map)
    cols_esperadas = ["Data", "Open", "High", "Low", "Close"]
    for c in cols_esperadas:
        if c not in df.columns:
            raise ValueError(f"Coluna esperada '{c}' não encontrada no arquivo.")

    df["Data"] = pd.to_datetime(df["Data"]).dt.strftime("%Y-%m-%d")
    df = df.sort_values("Data").reset_index(drop=True)

    header_comentario = (
        "# ccmfut_seed_2008_2026.csv — Histórico contínuo CCMFUT (Profit/Genial)\n"
        "# Data de corte: 17/09/2026 | Origem: export manual do Profit, CCMFUT contínuo\n"
        "# Entrada fixa read-only para viabilizar SMA(100) em contratos com histórico curto\n"
    )

    with open(caminho_csv, "w", encoding="utf-8", newline="") as f:
        f.write(header_comentario)
        df[cols_esperadas].to_csv(f, index=False)

    print(f"Sucesso: {caminho_csv} gerado com {len(df)} registros.")
    print(f"Período: {df['Data'].iloc[0]} a {df['Data'].iloc[-1]}")

if __name__ == "__main__":
    converter()
