@echo off
chcp 1252 > nul
echo ============================================================
echo   MILHO TRADER - Atualizar dados e abrir Dashboard
echo ============================================================
echo.

set "PASTA=C:\Projetos Phyton\Milho"
cd /d "%PASTA%"
if errorlevel 1 (
    echo.
    echo ERRO: Pasta nao encontrada:
    echo %PASTA%
    echo.
    pause
    exit /b 1
)

echo [1/3] Verificando Python 3.13...
py -3.13 --version
if errorlevel 1 (
    echo.
    echo ERRO: Python 3.13 nao encontrado via "py -3.13".
    echo Este projeto depende do Python 3.13 especificamente - e onde
    echo pandas/numpy estao instalados.
    echo.
    pause
    exit /b 1
)
echo.

echo [2/4] Rodando pipeline - gera dados_milho.json atualizado
echo.
py -3.13 "%PASTA%\pipeline.py" "%PASTA%" "%PASTA%"
echo.

echo [3/4] Rodando analise TRIX curva e Sentinel-Corn - gera dados_curva.json e grafico
echo.
py -3.13 "%PASTA%\ccm_trix_curva.py"
echo.

if not exist "%PASTA%\dados_milho.json" (
    echo ============================================================
    echo  ATENCAO - dados_milho.json nao foi gerado. Veja os erros acima.
    echo ============================================================
    echo.
    pause
)

echo [4/4] Iniciando servidor local e abrindo o Dashboard...
echo.
echo Dashboard disponivel em: http://localhost:8000/milho_dashboard.html
echo.
echo Se esta janela fechar sozinha na proxima etapa, a porta 8000
echo provavelmente ja esta em uso por outra janela aberta antes
echo (ex.: abrir_dashboard.bat rodando em outro terminal). Feche a
echo janela antiga e rode este .bat de novo.
echo.
echo Pressione Ctrl+C para encerrar o servidor quando terminar de usar.
echo.
start http://localhost:8000/milho_dashboard.html
py -3.13 -m http.server 8000

echo.
echo ============================================================
echo  O servidor foi encerrado. Se isso aconteceu sozinho (sem voce
echo  apertar Ctrl+C), o erro real deve estar impresso ACIMA desta
echo  linha - provavelmente porta 8000 ja em uso.
echo ============================================================
pause
