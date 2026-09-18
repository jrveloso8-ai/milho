@echo off
chcp 1252 > nul
echo ============================================================
echo   MILHO TRADER - MOCKUP NOVO SISTEMA (Sentinel-Corn 360)
echo ============================================================
echo.
set "PASTA=C:\Projetos Phyton\Milho"
cd /d "%PASTA%"
echo Abrindo mockup no navegador...
start "" "%PASTA%\mockup_sentinel_sistema_novo.html"
echo.
echo Mockup aberto com sucesso!
