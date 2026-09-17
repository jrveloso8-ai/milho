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

echo [1/5] Regenerando Dashboard e Sincronizando index.html...
python ccm_trix_curva.py
if errorlevel 1 (
    echo [ERRO] Falha ao executar ccm_trix_curva.py. Abortando publicacao.
    pause
    exit /b 1
)
echo [OK] Dashboard ccm_trix_curva.html e index.html regenerados com sucesso.
echo.

echo [2/5] Executando Portao de Auditoria Completo (Testes, AST e Proveniencia)...
call portao_auditoria.bat
if errorlevel 1 (
    echo [ERRO] Portao de auditoria reprovado. Abortando publicacao por seguranca.
    pause
    exit /b 1
)
echo.

echo [3/5] Verificando seguranca de credenciais no repositorio...
python auditar_seguranca.py
if errorlevel 1 (
    echo [ERRO] Auditoria de seguranca reprovada. Abortando publicacao.
    pause
    exit /b 1
)
echo.

echo [4/5] Verificando status do Git e criando commit de atualizacao...
git status --porcelain > "%TEMP%\git_status_check.txt"
set "TEM_MUDANCAS="
for /f "tokens=*" %%i in ("%TEMP%\git_status_check.txt") do (
    set "TEM_MUDANCAS=1"
)
del "%TEMP%\git_status_check.txt" 2>nul

if defined TEM_MUDANCAS (
    echo Alteracoes detectadas. Preparando commit...
    git add -A
    for /f "tokens=1-4 delims=/ " %%a in ("%date%") do set "DATA_HOJE=%%a/%%b/%%c"
    for /f "tokens=1-2 delims=: " %%a in ("%time%") do set "HORA_HOJE=%%a:%%b"
    git commit -m "Deploy: Atualizacao automatica do dashboard e dados da curva CCM (%DATA_HOJE% %HORA_HOJE%)"
    echo [OK] Novo commit registrado com sucesso.
) else (
    echo [OK] Repositorio ja esta atualizado e commitado.
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
    echo Enviando alteracoes para o GitHub (git push)...
    git push
    if errorlevel 1 (
        echo [AVISO] O comando git push retornou codigo de erro. Verifique sua conexao ou permissao de branch.
    ) else (
        echo [OK] Codigo enviado com sucesso ao GitHub. O deploy na Vercel foi acionado automaticamente!
    )
) else (
    echo [INFO] Nenhum remote configurado no Git ainda.
    echo Para conectar seu GitHub a este repositorio local, execute:
    echo   git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
    echo   git push -u origin master
    echo.
    echo Apos configurar o remote uma vez, esta bat fara o push e deploy automaticamente!
)
echo.

echo ======================================================================
echo  PROCESSO CONCLUIDO COM SUCESSO!
echo  Dashboard pronto para visualizacao local e remota.
echo ======================================================================
pause
exit /b 0
