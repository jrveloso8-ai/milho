@echo off
chcp 65001 > nul
setlocal

set "PASTA=C:\Projetos Phyton\Milho"
cd /d "%PASTA%"
if errorlevel 1 exit /b 1

if not exist "logs" mkdir "logs"

set "LOGFILE=logs\publicacao_agendada.log"

echo ====================================================================== >> "%LOGFILE%"
echo [%DATE% %TIME%] INICIANDO PUBLICACAO AGENDADA >> "%LOGFILE%"
echo ====================================================================== >> "%LOGFILE%"

python publicar.py >> "%LOGFILE%" 2>&1
set "CODIGO_RETORNO=%ERRORLEVEL%"

if %CODIGO_RETORNO% equ 0 (
    echo [%DATE% %TIME%] PUBLICACAO CONCLUIDA COM SUCESSO. >> "%LOGFILE%"
) else (
    echo [%DATE% %TIME%] ERRO NA PUBLICACAO (CODIGO: %CODIGO_RETORNO%). >> "%LOGFILE%"
)

echo. >> "%LOGFILE%"
exit /b %CODIGO_RETORNO%
