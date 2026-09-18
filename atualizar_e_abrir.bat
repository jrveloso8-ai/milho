@echo off
chcp 1252 > nul
echo ============================================================
echo   MILHO TRADER - SISTEMA NOVO (Sentinel-Corn 360)
echo   Atualizacao de Dados da B3 e Abertura do Sistema
echo ============================================================
echo.

set "PASTA=C:\Projetos Phyton\Milho"
cd /d "%PASTA%"
if errorlevel 1 (
    echo.
    echo ERRO: Pasta nao encontrada: %PASTA%
    pause
    exit /b 1
)

echo [1/2] Rodando analise da Curva CCM, TRIX v5 e Sentinel-Corn 360...
py -3.13 "%PASTA%\ccm_trix_curva.py"
if errorlevel 1 (
    echo.
    echo ERRO durante a atualizacao dos dados. Verifique as mensagens acima.
    pause
    exit /b 1
)
echo.

echo [2/2] Abrindo Sistema Sentinel-Corn 360 no navegador...
start "" "%PASTA%\sistema_sentinel.html"
echo.
echo Sistema atualizado e aberto com sucesso!
timeout /t 3 > nul
