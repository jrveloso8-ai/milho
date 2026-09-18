@echo off
chcp 1252 > nul
echo ============================================================
echo   MILHO TRADER - SISTEMA NOVO (Sentinel-Corn 360)
echo ============================================================
echo.
set "PASTA=C:\Projetos Phyton\Milho"
cd /d "%PASTA%"
echo Abrindo Sistema Novo Sentinel-Corn 360 no navegador...
start "" "%PASTA%\sistema_sentinel.html"
echo.
echo Sistema aberto com sucesso!
