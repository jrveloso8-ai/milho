import os
import subprocess
from unittest.mock import patch
import pytest

import auditar_seguranca

def test_auditar_seguranca_detecta_tls_inseguro(tmp_path):
    """Teste de regressão para garantir que o auditar_seguranca pega ssl.CERT_NONE."""
    arquivo_inseguro = tmp_path / "script_inseguro.py"
    arquivo_inseguro.write_text("import ssl\ncontext = ssl.create_default_context()\ncontext.check_hostname = False\n")

    arquivo_seguro = tmp_path / "script_seguro.py"
    arquivo_seguro.write_text("import ssl\ncontext = ssl.create_default_context()\n")

    arquivos_mock = [str(arquivo_inseguro), str(arquivo_seguro)]

    # Ignora saida padrao
    with patch("subprocess.check_output", return_value="\n".join(arquivos_mock)):
        with patch("sys.exit", side_effect=SystemExit) as mock_exit:
            with pytest.raises(SystemExit):
                auditar_seguranca.main()
            mock_exit.assert_called_with(1) # Deve reprovar por causa do script_inseguro

def test_auditar_seguranca_passa_com_tls_seguro(tmp_path):
    """Teste de regressão para garantir que passa quando nao ha ssl.CERT_NONE."""
    arquivo_seguro = tmp_path / "script_seguro.py"
    arquivo_seguro.write_text("import ssl\ncontext = ssl.create_default_context()\n")

    arquivos_mock = [str(arquivo_seguro)]

    with patch("subprocess.check_output", return_value="\n".join(arquivos_mock)):
        with patch("sys.exit", side_effect=SystemExit) as mock_exit:
            with patch("builtins.open", side_effect=open): # permite abrir o .gitignore original
                with pytest.raises(SystemExit):
                    auditar_seguranca.main()
                mock_exit.assert_called_with(0) # Deve passar
