@echo off
chcp 65001 > nul
setlocal

set "PASTA=C:\Projetos Phyton\Milho"
cd /d "%PASTA%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%PASTA%\configurar_agendamento.ps1"

echo.
pause
exit /b 0
