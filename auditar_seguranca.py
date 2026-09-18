# -*- coding: utf-8 -*-
"""
auditar_seguranca.py — Auditoria Estrita de Seguranca e Credenciais (Git e Repositorio)
======================================================================================
Verifica se existem chaves de API, senhas, tokens hardcoded ou arquivos sensiveis (.env)
rastreados no controle de versao git antes de publicar no GitHub / Vercel.
"""

import os
import sys
import re
import subprocess

def main():
    print("======================================================================")
    print("AUDITORIA DE SEGURANCA E CREDENCIAIS (DEPLOY GITHUB / VERCEL)")
    print("======================================================================")

    # 1. Checa arquivos rastreados no git
    try:
        arquivos_git = subprocess.check_output(['git', 'ls-files'], text=True).splitlines()
    except Exception as e:
        print(f"[ERRO] Falha ao listar arquivos no git: {e}")
        sys.exit(1)

    padroes_sensiveis = [
        r'\.env$',
        r'\.env\..+$',
        r'token\.txt$',
        r'secret.*\.json$',
        r'credentials.*\.json$',
        r'id_rsa',
    ]

    arquivos_suspeitos = []
    for a in arquivos_git:
        for p in padroes_sensiveis:
            if re.search(p, a, re.IGNORECASE):
                arquivos_suspeitos.append((a, p))

    if arquivos_suspeitos:
        print("[ALERTA] Arquivos sensíveis detectados no Git:")
        for a, p in arquivos_suspeitos:
            print(f"  -> {a}")
        sys.exit(1)
    else:
        print(f"[1/3] Nomes de arquivos no Git ({len(arquivos_git)} arquivos): OK (nenhum .env ou arquivo de credencial)")

    # 2. Varre conteudo de todos os arquivos de texto rastreados
    padroes_conteudo = [
        (r'(?i)brapi[_-]?token\s*=\s*["\']([a-zA-Z0-9_\-\.]{12,})["\']', 'BRAPI_TOKEN hardcoded'),
        (r'(?i)api[_-]?key\s*=\s*["\']([a-zA-Z0-9_\-\.]{16,})["\']', 'API_KEY hardcoded'),
        (r'(?i)secret\s*=\s*["\']([a-zA-Z0-9_\-\.]{16,})["\']', 'SECRET hardcoded'),
        (r'(?i)bearer\s+([a-zA-Z0-9_\-\.]{25,})', 'Bearer token hardcoded')
    ]

    achados = []
    for a in arquivos_git:
        if os.path.isfile(a):
            if a.endswith(('.xlsx', '.docx', '.zip', '.pdf', '.png', '.jpg', '.ico', '.parquet')):
                continue
            try:
                with open(a, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                for regex, desc in padroes_conteudo:
                    matches = re.findall(regex, content)
                    for m in matches:
                        # Ignora placeholders de documentacao e testes
                        if m.lower() in ('your_token_here', 'none', 'default', 'password', 'secret', 'changeme', 'seu_token_aqui'):
                            continue
                        achados.append((a, desc, m[:4] + '****' if len(m) > 4 else '****'))
            except Exception:
                pass

    if achados:
        print("[ALERTA] Segredos potenciais detectados no código:")
        for ac in achados:
            print(f"  -> {ac[0]}: {ac[1]} (amostra: {ac[2]})")
        sys.exit(1)
    else:
        print("[2/3] Varredura profunda de conteúdo no Git: OK (zero segredos ou tokens hardcoded)")

    # 3. Checa proteção no .gitignore
    itens_obrigatorios_gitignore = ['.env', '.env.local', '.pytest_cache', '*.tmp']
    gitignore_path = os.path.join(os.path.dirname(__file__), '.gitignore')
    if os.path.exists(gitignore_path):
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            ign_text = f.read()
        faltantes = [it for it in itens_obrigatorios_gitignore if it not in ign_text]
        if faltantes:
            print(f"[AVISO] Itens ausentes no .gitignore: {faltantes}")
        else:
            print("[3/3] Proteção do .gitignore: OK (.env, caches e temporários blindados)")
    else:
        print("[ERRO] Arquivo .gitignore não encontrado!")
        sys.exit(1)

    print("----------------------------------------------------------------------")
    print("PARECER DE SEGURANCA: APROVADO — Nenhum padrão conhecido de segredo ou credencial detectado nos arquivos rastreados.")
    sys.exit(0)

if __name__ == '__main__':
    main()
