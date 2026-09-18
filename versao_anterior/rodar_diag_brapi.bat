@echo off
REM ============================================================
REM  rodar_diag_brapi.bat
REM  Projeto: Milho Trader (GPM v2.0) - Fase 3B
REM  Diagnostico pontual do formato de resposta da BRAPI
REM  (uso unico para descobrir o schema real de /v2/futures/list)
REM ============================================================

setlocal

set PASTA_DADOS=C:\Projetos Phyton\Milho

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
echo  Milho Trader - Diagnostico BRAPI
echo  Pasta de dados: %PASTA_DADOS%
echo ============================================================
echo.

cd /d "%PASTA_DADOS%"
python diag_brapi.py > diag_brapi_output.txt 2>&1
type diag_brapi_output.txt

echo.
echo ============================================================
echo  Diagnostico salvo tambem em: %PASTA_DADOS%\diag_brapi_output.txt
echo  Copie o conteudo e envie de volta na conversa.
echo ============================================================
pause
