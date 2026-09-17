@echo off
chcp 1252 > nul
setlocal enabledelayedexpansion

echo ======================================================================
echo  MILHO TRADER - PORTAO DE AUDITORIA (Modulo TRIX v5 Curva CCM)
echo ======================================================================
echo.

set "PASTA=C:\Projetos Phyton\Milho"
cd /d "%PASTA%"
if errorlevel 1 (
    echo [ERRO] Nao foi possivel acessar a pasta %PASTA%
    exit /b 1
)

set "FALHA_ITEM="

echo ----------------------------------------------------------------------
echo [6.1] Executando suite de testes automatizados (pytest)...
echo ----------------------------------------------------------------------
pytest -v test_ccm_trix_curva.py
if errorlevel 1 (
    set "FALHA_ITEM=6.1 (Suite pytest falhou)"
    goto REPROVADO
)
echo [OK] 6.1: Testes automatizados passaram com sucesso.
echo.

echo ----------------------------------------------------------------------
echo [6.2] Verificando dados fabricados e proveniencia...
echo ----------------------------------------------------------------------
python verificar_dados_fabricados.py
if errorlevel 1 (
    set "FALHA_ITEM=6.2 (Verificacao contra dados fabricados falhou)"
    goto REPROVADO
)
echo [OK] 6.2: Verificacao de dados fabricados e proveniencia passou com sucesso.
echo.

echo ----------------------------------------------------------------------
echo [6.3] Verificando barreira estrutural AST contra literais soltos no plot...
echo ----------------------------------------------------------------------
python verificar_literais_plot.py
if errorlevel 1 (
    set "FALHA_ITEM=6.3 (Barreira estrutural AST detectou violacao)"
    goto REPROVADO
)
echo [OK] 6.3: Barreira estrutural AST passou com sucesso.
echo.

echo ----------------------------------------------------------------------
echo [6.4] Executando mypy (recomendado, nao bloqueante)...
echo ----------------------------------------------------------------------
python -m mypy ccm_trix_curva.py 2>nul
if errorlevel 1 (
    echo [AVISO] mypy retornou apontamentos ou nao esta instalado - etapa nao bloqueante.
) else (
    echo [OK] 6.4: mypy executado com sucesso.
)
echo.

echo ----------------------------------------------------------------------
echo [6.5] Verificando status do repositorio git (git status --porcelain)...
echo ----------------------------------------------------------------------
set "GIT_SUJO="
for /f "tokens=*" %%i in ('git status --porcelain') do (
    set "GIT_SUJO=1"
    echo Arquivo modificado/nao commitado: %%i
)
if defined GIT_SUJO (
    set "FALHA_ITEM=6.5 (git status --porcelain nao esta limpo)"
    goto REPROVADO
)
echo [OK] 6.5: Repositorio git perfeitamente limpo.
echo.

echo ----------------------------------------------------------------------
echo [6.6] Verificando seguranca de credenciais no repositorio (auditar_seguranca.py)...
echo ----------------------------------------------------------------------
python auditar_seguranca.py
if errorlevel 1 (
    set "FALHA_ITEM=6.6 (Auditoria de seguranca de credenciais reprovada)"
    goto REPROVADO
)
echo [OK] 6.6: Auditoria de seguranca passou com sucesso.
echo.

echo ======================================================================
echo PARECER FINAL: APROVADO
echo Todos os portoes de auditoria (6.1 a 6.6) foram atendidos com sucesso!
echo ======================================================================
exit /b 0

:REPROVADO
echo.
echo ======================================================================
echo PARECER FINAL: REPROVADO
echo Falha detectada no item: !FALHA_ITEM!
echo ======================================================================
exit /b 1
