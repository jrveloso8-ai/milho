@echo off
chcp 1252 > nul
echo ============================================================
echo   MILHO TRADER - Dashboard
echo ============================================================
echo.
set PASTA=C:\Projetos Phyton\Milho
cd /d "%PASTA%"
echo [1/2] Verificando dados...
if not exist "dados_milho.json" (
    echo AVISO: dados_milho.json nao encontrado.
    echo Execute rodar_pipeline.bat primeiro para dados reais.
    echo O dashboard abrira em modo demonstracao.
    echo.
)
echo [2/2] Iniciando servidor local...
echo.
echo Dashboard disponivel em: http://localhost:8000/milho_dashboard.html
echo Pressione Ctrl+C para encerrar o servidor.
echo.
start http://localhost:8000/milho_dashboard.html
python -m http.server 8000
