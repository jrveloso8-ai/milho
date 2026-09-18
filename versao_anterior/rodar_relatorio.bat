@echo off
chcp 1252 > nul
echo ============================================================
echo   MILHO TRADER — GERADOR DE RELATORIO SEMANAL
echo ============================================================
echo.

REM Verificar variavel de ambiente
if "%ANTHROPIC_API_KEY%"=="" (
    echo ERRO: ANTHROPIC_API_KEY nao definida.
    echo.
    echo Configure com o comando abaixo e reabra o terminal:
    echo   setx ANTHROPIC_API_KEY "sk-ant-..."
    echo.
    pause
    exit /b 1
)

REM Definir pasta do projeto
set PASTA=C:\Projetos Phyton\Milho
set SCRIPT=%PASTA%\gerar_relatorio.py

REM Verificar se o JSON existe
if not exist "%PASTA%\dados_milho.json" (
    echo ERRO: dados_milho.json nao encontrado.
    echo Execute rodar_pipeline.bat primeiro.
    echo.
    pause
    exit /b 1
)

REM Executar gerador
python "%SCRIPT%"

if errorlevel 1 (
    echo.
    echo ERRO na geracao do relatorio. Verifique a conexao e a chave de API.
    pause
    exit /b 1
)

pause
