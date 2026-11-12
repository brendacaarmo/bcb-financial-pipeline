"""
Testes unitários para src/pipeline.py (integração do resumo diário).
Usam mocks: não acessam banco nem rede.
"""

from unittest.mock import MagicMock, patch

import pytest

from src import pipeline


class TestGenerateDailySummary:
    @patch("src.pipeline.get_connection", side_effect=Exception("banco fora do ar"))
    def test_falha_de_conexao_nao_levanta_erro(self, mock_conn):
        pipeline.generate_daily_summary()  # não pode lançar exceção

    @patch("src.pipeline.generate_and_save", side_effect=Exception("tabela não existe"))
    @patch("src.pipeline.get_connection")
    def test_falha_no_resumo_nao_levanta_e_fecha_conexao(self, mock_conn, mock_generate):
        conn = MagicMock()
        mock_conn.return_value = conn

        pipeline.generate_daily_summary()  # não pode lançar exceção

        conn.close.assert_called_once()

    @patch("src.pipeline.generate_and_save")
    @patch("src.pipeline.get_connection")
    def test_sucesso_fecha_conexao(self, mock_conn, mock_generate):
        conn = MagicMock()
        mock_conn.return_value = conn

        pipeline.generate_daily_summary()

        mock_generate.assert_called_once()
        conn.close.assert_called_once()


class TestRun:
    @patch("src.pipeline.generate_daily_summary")
    @patch("src.pipeline.load_records", return_value=155)
    @patch("src.pipeline.clean_all_series", return_value=[])
    @patch("src.pipeline.fetch_all_series", return_value={})
    def test_resumo_roda_depois_da_carga(self, mock_fetch, mock_clean, mock_load, mock_summary):
        pipeline.run()
        mock_load.assert_called_once()
        mock_summary.assert_called_once()

    @patch("src.pipeline.generate_daily_summary")
    @patch("src.pipeline.load_records", side_effect=Exception("falha ao gravar"))
    @patch("src.pipeline.clean_all_series", return_value=[])
    @patch("src.pipeline.fetch_all_series", return_value={})
    def test_falha_na_carga_ainda_derruba_o_pipeline(
        self, mock_fetch, mock_clean, mock_load, mock_summary
    ):
        with pytest.raises(SystemExit) as exc:
            pipeline.run()
        assert exc.value.code == 1
        mock_summary.assert_not_called()
