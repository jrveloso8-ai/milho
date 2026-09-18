# gerar_bat.py — gera rodar_pipeline.bat com cp1252 + CRLF
# Executar uma vez: python gerar_bat.py

import os

conteudo = (
    "@echo off\r\n"
    "chcp 1252 > nul\r\n"
    "echo ============================================================\r\n"
    "echo  MILHO TRADER - Pipeline de Dados v1.0\r\n"
    "echo ============================================================\r\n"
    "echo.\r\n"
    "\r\n"
    "REM Define pasta dos dados\r\n"
    'set PASTA_DADOS=C:\\Projetos Python\\Milho\r\n'
    "\r\n"
    "REM Ativa ambiente virtual se existir\r\n"
    'if exist "%PASTA_DADOS%\\venv\\Scripts\\activate.bat" (\r\n'
    '    call "%PASTA_DADOS%\\venv\\Scripts\\activate.bat"\r\n'
    ")\r\n"
    "\r\n"
    "REM Vai para a pasta do projeto\r\n"
    'cd /d "%PASTA_DADOS%"\r\n'
    "\r\n"
    "REM Roda o pipeline\r\n"
    "echo Rodando pipeline...\r\n"
    'python pipeline.py "%PASTA_DADOS%" "%PASTA_DADOS%"\r\n'
    "\r\n"
    "REM Verifica se JSON foi gerado\r\n"
    'if exist "%PASTA_DADOS%\\dados_milho.json" (\r\n'
    "    echo.\r\n"
    "    echo Pipeline concluido com sucesso!\r\n"
    '    echo JSON gerado em: %PASTA_DADOS%\\dados_milho.json\r\n'
    ") else (\r\n"
    "    echo.\r\n"
    "    echo ERRO: JSON nao foi gerado. Verifique os logs acima.\r\n"
    ")\r\n"
    "\r\n"
    "echo.\r\n"
    "pause\r\n"
)

pasta_saida = os.path.dirname(os.path.abspath(__file__))
path_bat = os.path.join(pasta_saida, 'rodar_pipeline.bat')

with open(path_bat, 'w', encoding='cp1252', newline='') as f:
    f.write(conteudo)

print(f'✅ BAT gerado: {path_bat}')
print(f'   Encoding: cp1252 | Line endings: CRLF')
