@echo off
chcp 1252 > nul
echo ============================================================
echo  MILHO TRADER - Pipeline de Dados v1.0
echo ============================================================
echo.

REM Define pasta dos dados
set "PASTA=C:\Projetos Phyton\Milho"

REM Vai para a pasta (aspas obrigatorias por causa do espaco no nome)
cd /d "%PASTA%"
if errorlevel 1 (
    echo.
    echo ERRO: Pasta nao encontrada:
    echo %PASTA%
    echo.
    echo Verifique se o caminho esta correto e tente novamente.
    echo.
    pause
    exit /b 1
)

echo Pasta localizada: %PASTA%
echo.

REM Verifica Python
python --version
if errorlevel 1 (
    echo.
    echo ERRO: Python nao encontrado no PATH.
    pause
    exit /b 1
)

REM Verifica pipeline.py
if not exist "%PASTA%\pipeline.py" (
    echo.
    echo ERRO: pipeline.py nao encontrado em:
    echo %PASTA%
    echo.
    echo Copie todos os arquivos .py para esta pasta.
    pause
    exit /b 1
)

echo Rodando pipeline...
echo.
python "%PASTA%\pipeline.py" "%PASTA%" "%PASTA%"

echo.
if exist "%PASTA%\dados_milho.json" (
    echo ============================================================
    echo  SUCESSO - dados_milho.json gerado com sucesso!
    echo ============================================================
) else (
    echo ============================================================
    echo  ATENCAO - JSON nao foi gerado. Veja os erros acima.
    echo ============================================================
)

echo.
pause