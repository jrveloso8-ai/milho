@echo off
chcp 1252 > nul
setlocal enabledelayedexpansion

echo ======================================================================
echo  MILHO TRADER - AUTOMACAO DE AUDITORIA E PUBLICACAO (GITHUB / VERCEL)
echo ======================================================================
echo.

set "PASTA=C:\Projetos Phyton\Milho"
cd /d "%PASTA%"
if errorlevel 1 (
    echo [ERRO] Nao foi possivel acessar a pasta %PASTA%
    pause
    exit /b 1
)

echo [1/5] Regenerando Dashboard e Sincronizando index.html com dados reais...
python ccm_trix_curva.py
if errorlevel 1 (
    echo [ERRO] Falha ao executar ccm_trix_curva.py. Abortando publicacao.
    pause
    exit /b 1
)
echo [OK] Dashboard ccm_trix_curva.html e index.html regenerados com sucesso.
echo.

echo [2/5] Validando integridade tecnica (Testes pytest, AST e Proveniencia)...
echo   -> Executando suite pytest...
pytest -v test_ccm_trix_curva.py
if errorlevel 1 (
    echo [ERRO] Testes automatizados falharam. Abortando publicacao por seguranca.
    pause
    exit /b 1
)

echo   -> Verificando proveniencia e dados fabricados...
python verificar_dados_fabricados.py
if errorlevel 1 (
    echo [ERRO] Violacao de proveniencia detectada. Abortando publicacao.
    pause
    exit /b 1
)

echo   -> Verificando barreira estrutural AST contra literais no plot...
python verificar_literais_plot.py
if errorlevel 1 (
    echo [ERRO] Violacao AST detectada no plot. Abortando publicacao.
    pause
    exit /b 1
)
echo [OK] Todas as validacoes de dados reais foram aprovadas.
echo.

echo [3/5] Verificando seguranca de credenciais no repositorio...
python auditar_seguranca.py
if errorlevel 1 (
    echo [ERRO] Auditoria de seguranca reprovada. Abortando publicacao.
    pause
    exit /b 1
)
echo.

echo [4/5] Registrando commit das atualizacoes e validando Portao de Auditoria...
git status --porcelain > "%TEMP%\git_status_check.txt"
set "TEM_MUDANCAS="
for /f "tokens=*" %%i in ("%TEMP%\git_status_check.txt") do (
    set "TEM_MUDANCAS=1"
)
del "%TEMP%\git_status_check.txt" 2>nul

if defined TEM_MUDANCAS (
    echo Alteracoes detectadas. Preparando commit...
    git add -A
    for /f "tokens=1-4 delims=/ " %%a in ("%date%") do set "DATA_HOJE=%%a-%%b-%%c"
    for /f "tokens=1-2 delims=: " %%a in ("%time%") do set "HORA_HOJE=%%a:%%b"
    git commit -m "Deploy: Atualizacao automatica do dashboard e dados da curva CCM (!DATA_HOJE! !HORA_HOJE!)"
    if errorlevel 1 (
        echo [ERRO] Falha ao criar commit (verifique o pre-commit hook).
        pause
        exit /b 1
    )
    echo [OK] Novo commit registrado com sucesso.
) else (
    echo [OK] Nenhuma nova alteracao para commitar.
)

echo   -> Validando Portao de Auditoria Final (arvore limpa)...
call portao_auditoria.bat
if errorlevel 1 (
    echo [ERRO] Portao de auditoria reprovado. Abortando envio.
    pause
    exit /b 1
)
echo.

echo [5/5] Publicando no GitHub e acionando Vercel...
git remote -v > "%TEMP%\git_remotes.txt" 2>nul
set "TEM_REMOTE="
for /f "tokens=*" %%i in ("%TEMP%\git_remotes.txt") do (
    set "TEM_REMOTE=1"
)
del "%TEMP%\git_remotes.txt" 2>nul

if defined TEM_REMOTE (
    echo Enviando branch master para o GitHub...
    git push origin master
    if errorlevel 1 (
        echo [AVISO] O comando git push origin master retornou codigo de erro.
    ) else (
        echo [OK] Branch master enviada com sucesso!
    )
    
    echo Sincronizando branch main no GitHub...
    git push origin master:main
    if errorlevel 1 (
        echo [AVISO] Nao foi possivel atualizar a branch main.
    ) else (
        echo [OK] Branch main sincronizada com sucesso!
    )
    echo [OK] Deploy na Vercel disparado automaticamente!
) else (
    echo [AVISO] Nenhum remote configurado no Git.
)
echo.

echo ======================================================================
echo  PROCESSO CONCLUIDO COM SUCESSO!
echo  Dashboard publicado no GitHub e pronto para Vercel.
echo ======================================================================
pause
exit /b 0
