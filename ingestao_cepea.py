# -*- coding: utf-8 -*-
"""
ingestao_cepea.py — Camada de ingestão online do Indicador Físico de Milho CEPEA/ESALQ (RTCNI).
Criado em 17/09/2026 para Milho Trader v1.0.

Responsabilidade:
  - Coletar cotações diárias reais do Indicador do Milho ESALQ/BM&FBOVESPA (Campinas/SP - RTCNI).
  - Fonte primária: Site oficial CEPEA/ESALQ (https://www.cepea.esalq.usp.br/br/indicador/milho.aspx).
  - Fonte secundária (fallback): Notícias Agrícolas (espelho oficial diário da CEPEA/ESALQ).
  - Sincronizar com a base local para garantir que tanto chamadas pontuais (Watchlist) quanto
    séries temporais históricas (traço RTCNI no gráfico) tenham dados atualizados diariamente
    (com defasagem máxima de 1 dia útil), sem necessidade de exportação manual.
  - Estritamente dados MEDIDOS do mercado à vista: zero simulação, zero interpolação.
"""

import glob
import os
import ssl
import urllib.request
from datetime import datetime, date
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
import pandas as pd

# Headers padrão de navegador moderno para evitar bloqueio por WAF/Cloudflare
HEADERS_PADRAO = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

URL_CEPEA = "https://www.cepea.esalq.usp.br/br/indicador/milho.aspx"
URL_NOTICIAS_AGRICOLAS = "https://www.noticiasagricolas.com.br/cotacoes/milho/indicador-cepea-esalq-milho"


def _criar_ssl_context():
    """Cria contexto SSL permissivo para conexões públicas informativas."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _parsear_tabela_cepea(html: str) -> List[Dict]:
    """Extrai registros da tabela de cotações do site da CEPEA/ESALQ."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "imagenet-indicador1"})
    if not table:
        return []

    registros = []
    for tr in table.find_all("tr")[1:]:
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) >= 2:
            data_str, preco_str = tds[0], tds[1]
            try:
                dt = datetime.strptime(data_str, "%d/%m/%Y").date()
                preco = float(preco_str.replace(".", "").replace(",", "."))
                if preco > 0:
                    registros.append({
                        "Data": dt,
                        "Close": preco,
                        "fonte": "CEPEA/ESALQ (oficial)",
                    })
            except (ValueError, TypeError):
                continue
    return registros


def _parsear_tabela_noticias_agricolas(html: str) -> List[Dict]:
    """Extrai registros do espelho oficial do Indicador CEPEA em Notícias Agrícolas."""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table", {"class": "cot-fisicas"})
    if not tables:
        # Fallback genérico para qualquer tabela com cabeçalho de cotação física
        tables = [t for t in soup.find_all("table") if "sc 60 kg" in t.get_text().lower()]

    registros = []
    for table in tables:
        for tr in table.find_all("tr")[1:]:
            tds = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(tds) >= 2:
                data_str, preco_str = tds[0], tds[1]
                try:
                    dt = datetime.strptime(data_str, "%d/%m/%Y").date()
                    preco = float(preco_str.replace(".", "").replace(",", "."))
                    if preco > 0:
                        registros.append({
                            "Data": dt,
                            "Close": preco,
                            "fonte": "Notícias Agrícolas (espelho CEPEA/ESALQ)",
                        })
                except (ValueError, TypeError):
                    continue
    return registros


def coletar_indicador_cepea_online(timeout: int = 8) -> List[Dict]:
    """
    Coleta dados recentes do Indicador CEPEA/ESALQ Milho via Web.
    Retorna lista de dicionários com chaves 'Data', 'Close' e 'fonte', ordenada por data crescente.
    """
    ctx = _criar_ssl_context()
    pontos = []

    # 1. Tenta fonte primária oficial (CEPEA/ESALQ)
    try:
        req = urllib.request.Request(URL_CEPEA, headers=HEADERS_PADRAO)
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        pontos = _parsear_tabela_cepea(html)
    except Exception:
        pontos = []

    # 2. Se falhar ou vier vazio, tenta espelho confiável (Notícias Agrícolas)
    if not pontos:
        try:
            req = urllib.request.Request(URL_NOTICIAS_AGRICOLAS, headers=HEADERS_PADRAO)
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            pontos = _parsear_tabela_noticias_agricolas(html)
        except Exception:
            pontos = []

    if pontos:
        # Remove eventuais datas duplicadas mantendo a primeira ocorrência
        vistos = set()
        dedup = []
        for p in pontos:
            if p["Data"] not in vistos:
                vistos.add(p["Data"])
                dedup.append(p)
        dedup.sort(key=lambda x: x["Data"])
        return dedup

    return []


def obter_ultimo_indicador_cepea(timeout: int = 8) -> Dict:
    """
    Retorna o fechamento físico mais recente obtido online via CEPEA/ESALQ.
    Retorno:
      dict com chaves 'sucesso', 'rtcni_preco', 'rtcni_data', 'fonte', 'erro'.
    """
    pontos = coletar_indicador_cepea_online(timeout=timeout)
    if not pontos:
        return {
            "sucesso": False,
            "rtcni_preco": None,
            "rtcni_data": "N/D",
            "fonte": "Indisponível",
            "erro": "Não foi possível obter dados online da CEPEA ou espelho.",
        }

    ult = pontos[-1]
    return {
        "sucesso": True,
        "rtcni_preco": round(float(ult["Close"]), 2),
        "rtcni_data": str(ult["Data"]),
        "fonte": ult["fonte"],
        "erro": None,
    }


def sincronizar_dados_cepea(pasta: str, timeout: int = 8) -> bool:
    """
    Verifica o arquivo local RTCNI_F_*.csv e adiciona os novos pregões medidos
    coletados online da CEPEA que ainda não estejam presentes no arquivo.
    Preserva estritamente o formato esperado pelo leitor_csv do projeto:
      RTCNI;DD/MM/YYYY;Open;High;Low;Close;Volume;Trades
    com ordenação decrescente por data (mais recente no topo).
    """
    padrao = os.path.join(pasta, "RTCNI*.csv")
    encontrados = glob.glob(padrao)
    if not encontrados:
        return False

    caminho_csv = sorted(encontrados)[-1]

    # Lê as datas já existentes no CSV para não duplicar
    datas_existentes = set()
    linhas_originais = []
    try:
        with open(caminho_csv, "r", encoding="latin1") as f:
            for linha in f:
                linha_limpa = linha.strip()
                if not linha_limpa:
                    continue
                linhas_originais.append(linha_limpa)
                partes = linha_limpa.split(";")
                if len(partes) >= 2:
                    try:
                        d_str = partes[1].strip()
                        dt_existente = datetime.strptime(d_str, "%d/%m/%Y").date()
                        datas_existentes.add(dt_existente)
                    except ValueError:
                        pass
    except Exception:
        return False

    # Coleta os pontos da CEPEA online
    pontos_online = coletar_indicador_cepea_online(timeout=timeout)
    if not pontos_online:
        return False

    novos_pontos = [p for p in pontos_online if p["Data"] not in datas_existentes]
    if not novos_pontos:
        return True  # Já estava atualizado

    # Formata novas linhas no padrão Profit/Genial para RTCNI
    # RTCNI;DD/MM/YYYY;Close;Close;Close;Close;0,00;0
    # Ordena decrescente por data para ficar no topo do arquivo
    novos_pontos.sort(key=lambda x: x["Data"], reverse=True)
    novas_linhas = []
    for p in novos_pontos:
        d_str = p["Data"].strftime("%d/%m/%Y")
        c_str = f"{p['Close']:.2f}".replace(".", ",")
        linha_formatada = f"RTCNI;{d_str};{c_str};{c_str};{c_str};{c_str};0,00;0"
        novas_linhas.append(linha_formatada)

    # Escreve de forma atômica
    todas_linhas = novas_linhas + linhas_originais
    caminho_tmp = caminho_csv + ".tmp"
    try:
        with open(caminho_tmp, "w", encoding="latin1", newline="\n") as f:
            for l in todas_linhas:
                f.write(l + "\n")
        os.replace(caminho_tmp, caminho_csv)
        return True
    except Exception:
        if os.path.exists(caminho_tmp):
            try:
                os.remove(caminho_tmp)
            except Exception:
                pass
        return False
