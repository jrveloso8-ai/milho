@echo off
REM ============================================================
REM  rodar_brapi_milho.bat
REM  Projeto: Milho Trader (GPM v2.0) - Fase 3B
REM  Executa o modulo brapi_milho.py e atualiza dados_milho.json
REM ============================================================

setlocal

REM --- Ajuste este caminho se o projeto estiver em outro lugar ---
set PASTA_DADOS=C:\Projetos Phyton\Milho

REM --- Verifica se o token da BRAPI esta definido ---
if "%BRAPI_TOKEN%"=="" (
    echo.
    echo ERRO: variavel de ambiente BRAPI_TOKEN nao definida.
    echo.
    echo Defina uma vez no seu usuario Windows com o comando abaixo
    echo ^(depois feche e abra o terminal para valer^):
    echo.
    echo     setx BRAPI_TOKEN "seu_token_aqui"
    echo.
    pause
    exit /b 1
)

echo ============================================================
echo  Milho Trader - Coleta BRAPI
echo  Pasta de dados: %PASTA_DADOS%
echo ============================================================
echo.

cd /d "%PASTA_DADOS%"
python brapi_milho.py

echo.
echo ============================================================
echo  Execucao finalizada.
echo ============================================================
pause
