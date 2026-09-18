# -*- coding: utf-8 -*-
"""
empacotar_entrega_r3.py — Empacotador Oficial e Verificador de Integridade Git (r3)
==================================================================================
Gera o pacote ZIP de entrega garantindo a inclusão completa da pasta .git
(com HEAD, config, objects/, refs/, hooks/), ccm_trix_curva.html, ccmfut_seed_2008_2026.csv
e testa o desempacotamento e integridade dos comandos git antes de finalizar.
"""

import os
import sys
import zipfile
import subprocess
import tempfile
import shutil

PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_ZIP = os.path.join(PASTA_PROJETO, "milho_trader_r3_completo.zip")

def validar_git_local():
    print(">> 1. Validando comandos Git no repositório local...")
    cmds = [
        ("git status", "git status"),
        ("git log --oneline -n 3", "git log"),
        ("git show --stat HEAD", "git show HEAD")
    ]
    for cmd, desc in cmds:
        res = subprocess.run(cmd, cwd=PASTA_PROJETO, shell=True, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[ERRO] {desc} falhou no repositório local:\n{res.stderr}")
            sys.exit(1)
        print(f"   [OK] {desc} funcionou perfeitamente.")

def criar_pacote_zip():
    print(f"\n>> 2. Gerando arquivo {os.path.basename(ARQUIVO_ZIP)} com .git completo...")
    arquivos_incluidos = 0
    pastas_git_incluidas = 0

    if os.path.exists(ARQUIVO_ZIP):
        os.remove(ARQUIVO_ZIP)

    with zipfile.ZipFile(ARQUIVO_ZIP, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(PASTA_PROJETO):
            # Ignora o próprio zip que está sendo criado
            if os.path.abspath(root) == os.path.abspath(PASTA_PROJETO):
                files = [f for f in files if f != os.path.basename(ARQUIVO_ZIP)]
            
            # Ignora cache do pytest e virtualenvs
            if ".pytest_cache" in root or "__pycache__" in root:
                continue

            for file in files:
                if file.startswith("~$") or file.endswith(".tmp") or file.endswith(".zip"):
                    continue
                caminho_completo = os.path.join(root, file)
                caminho_relativo = os.path.relpath(caminho_completo, PASTA_PROJETO)
                zf.write(caminho_completo, caminho_relativo)
                arquivos_incluidos += 1
                if caminho_relativo.startswith(".git"):
                    pastas_git_incluidas += 1

    print(f"   [OK] Pacote ZIP criado com sucesso!")
    print(f"   Total de arquivos no ZIP: {arquivos_incluidos}")
    print(f"   Arquivos da pasta .git inclusos: {pastas_git_incluidas}")

def testar_desempacotamento():
    print("\n>> 3. Testando desempacotamento e comandos git no pacote gerado...")
    temp_dir = tempfile.mkdtemp(prefix="teste_auditoria_r3_")
    try:
        with zipfile.ZipFile(ARQUIVO_ZIP, 'r') as zf:
            zf.extractall(temp_dir)

        # Checa presença dos arquivos obrigatórios
        obrigatorios = [
            os.path.join(temp_dir, "ccm_trix_curva.html"),
            os.path.join(temp_dir, "ccmfut_seed_2008_2026.csv"),
            os.path.join(temp_dir, ".git", "HEAD"),
            os.path.join(temp_dir, ".git", "config"),
            os.path.join(temp_dir, ".git", "objects"),
            os.path.join(temp_dir, ".git", "refs"),
        ]

        for p in obrigatorios:
            if not os.path.exists(p):
                print(f"[ERRO] Item obrigatório não encontrado no ZIP extraído: {p}")
                sys.exit(1)
        print("   [OK] Todos os arquivos obrigatórios (ccm_trix_curva.html, seed e estrutura .git) existem no ZIP.")

        # Executa comandos git no diretório temporário extraído
        for cmd in ["git status", "git log --oneline -n 3", "git show --stat HEAD"]:
            res = subprocess.run(cmd, cwd=temp_dir, shell=True, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"[ERRO] Comando '{cmd}' falhou no repositório extraído do ZIP!")
                print(res.stderr)
                sys.exit(1)
            print(f"   [OK] '{cmd}' executou com sucesso no pacote extraído.")

        print("\n>> PARECER DO EMPACOTAMENTO: APROVADO.")
        print(f"Arquivo pronto para entrega: {ARQUIVO_ZIP}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    validar_git_local()
    criar_pacote_zip()
    testar_desempacotamento()
