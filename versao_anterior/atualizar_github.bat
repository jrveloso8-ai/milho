@echo off
chcp 65001 > nul
setlocal

set "PASTA=C:\Projetos Phyton\Milho"
cd /d "%PASTA%"
if errorlevel 1 (
    echo [ERRO] Nao foi possivel acessar a pasta %PASTA%
    pause
    exit /b 1
)

python publicar.py
if errorlevel 1 (
    echo.
    echo [ERRO] A atualizacao foi interrompida devido a falha em uma das etapas.
    pause
    exit /b 1
)

echo.
pause
exit /b 0
