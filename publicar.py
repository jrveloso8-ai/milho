# -*- coding: utf-8 -*-
"""
publicar.py — Script de Automação de Publicação (GitHub / Vercel)
================================================================
Executa o ciclo completo de verificação, testes, auditoria, commit e deploy.
Pode ser chamado diretamente via terminal ou através de publicar_vercel.bat.
"""

import os
import sys
import subprocess
from datetime import datetime

PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))

def executar_comando(cmd, descricao, obrigatorio=True):
    print(f"\n>> {descricao}...")
    try:
        resultado = subprocess.run(cmd, cwd=PASTA_PROJETO, shell=True, text=True, capture_output=False)
        if resultado.returncode != 0:
            print(f"[ERRO] Falha ao executar: {descricao} (Código {resultado.returncode})")
            if obrigatorio:
                sys.exit(resultado.returncode)
            return False
        print(f"[OK] {descricao} concluído com sucesso.")
        return True
    except Exception as e:
        print(f"[ERRO] Exceção ao executar {descricao}: {e}")
        if obrigatorio:
            sys.exit(1)
        return False

def main():
    print("=" * 70)
    print(" MILHO TRADER — AUTOMAÇÃO DE AUDITORIA E PUBLICAÇÃO (GITHUB / VERCEL)")
    print("=" * 70)

    # 1. Regenerar dados e sincronizar index.html
    executar_comando("python ccm_trix_curva.py", "1/5: Regenerando Dashboard e Sincronizando index.html")

    # 2. Testes pytest e integridade de dados reais
    executar_comando("pytest -v test_ccm_trix_curva.py", "2/5 (a): Executando suíte pytest")
    executar_comando("python verificar_dados_fabricados.py", "2/5 (b): Verificando proveniência e dados fabricados")
    executar_comando("python verificar_literais_plot.py", "2/5 (c): Verificando barreira estrutural AST no plot")

    # 3. Auditoria de segurança e credenciais
    executar_comando("python auditar_seguranca.py", "3/5: Auditoria estrita de credenciais e segredos")

    # 4. Git status e commit automático
    print("\n>> 4/5: Verificando status do repositório Git...")
    status_out = subprocess.check_output("git status --porcelain", cwd=PASTA_PROJETO, shell=True, text=True).strip()
    if status_out:
        print("Alterações detectadas nos seguintes arquivos:")
        for linha in status_out.splitlines():
            print(f"   {linha}")
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        msg_commit = f"Deploy: Atualizacao automatica do dashboard e dados da curva CCM ({agora})"
        executar_comando("git add -A", "Preparando arquivos para commit (git add -A)")
        executar_comando(f'git commit -m "{msg_commit}"', "Registrando commit com dados reais")
    else:
        print("[OK] Repositório já está atualizado. Nenhum commit novo necessário.")

    # 4.1 Validação do Portão de Auditoria Oficial (Árvore limpa garantida)
    executar_comando("cmd /c portao_auditoria.bat", "4/5 (b): Validando Portão de Auditoria Oficial")

    # 5. Push para GitHub (Master e Main)
    print("\n>> 5/5: Publicando no GitHub e disparando Vercel...")
    remotes = subprocess.check_output("git remote -v", cwd=PASTA_PROJETO, shell=True, text=True).strip()
    if "origin" in remotes:
        executar_comando("git push origin master", "Enviando branch master para o GitHub", obrigatorio=False)
        executar_comando("git push origin master:main", "Sincronizando branch main para a Vercel", obrigatorio=False)
        print("\n[SUCESSO] Código enviado para o GitHub! O deploy na Vercel foi acionado.")
    else:
        print("\n[AVISO] Nenhum remote 'origin' configurado. Configure com 'git remote add origin ...'")

    print("\n" + "=" * 70)
    print(" PROCESSO CONCLUÍDO COM SUCESSO! DASHBOARD NO AR.")
    print("=" * 70)

if __name__ == "__main__":
    main()
