"""
Testes unitários para src/extract.py.
Usa mocks para simular respostas da API sem fazer chamadas de rede reais.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.extract import fetch_series


class TestFetchSeries:
    @patch("src.extract.requests.get")
    def test_resposta_200_retorna_dados(self, mock_get):
        # Arrange: simula uma resposta bem-sucedida da API
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"data": "01/09/2026", "valor": "5.20"}]
        mock_get.return_value = mock_response

        # Act
        result = fetch_series("dolar", "01/09/2026", "25/09/2026")

        # Assert
        assert result == [{"data": "01/09/2026", "valor": "5.20"}]
        mock_get.assert_called_once()  # confirma que a API foi chamada só 1 vez

    @patch("src.extract.requests.get")
    def test_resposta_404_retorna_lista_vazia_sem_retry(self, mock_get):
        # Simula o caso do IPCA sem dado publicado no período
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = fetch_series("ipca", "01/09/2026", "25/09/2026")

        assert result == []
        mock_get.assert_called_once()  # 404 não deve acionar retry

    @patch("src.extract.time.sleep", return_value=None)  # evita esperar de verdade
    @patch("src.extract.requests.get")
    def test_erro_de_conexao_aciona_retry(self, mock_get, mock_sleep):
        # Simula falha de rede nas 3 tentativas
        mock_get.side_effect = requests.exceptions.ConnectionError("Falha simulada")

        with pytest.raises(requests.exceptions.ConnectionError):
            fetch_series("dolar", "01/09/2026", "25/09/2026")

        assert mock_get.call_count == 3  # confirma que tentou 3 vezes

    def test_serie_invalida_lanca_value_error(self):
        with pytest.raises(ValueError):
            fetch_series("bitcoin", "01/09/2026", "25/09/2026")