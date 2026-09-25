"""
Testes unitários para src/transform.py.
Não dependem de rede nem de banco — só testam a lógica pura de limpeza.
"""

from src.transform import _parse_date, _parse_value, clean_series


class TestParseDate:
    def test_data_valida_converte_para_iso(self):
        assert _parse_date("25/09/2026") == "2026-09-25"

    def test_data_invalida_retorna_none(self):
        assert _parse_date("data-invalida") is None

    def test_data_vazia_retorna_none(self):
        assert _parse_date("") is None


class TestParseValue:
    def test_valor_com_ponto_converte_corretamente(self):
        assert _parse_value("5.1950") == 5.1950

    def test_valor_com_virgula_converte_corretamente(self):
        assert _parse_value("5,1950") == 5.1950

    def test_valor_invalido_retorna_none(self):
        assert _parse_value("abc") is None

    def test_valor_vazio_retorna_none(self):
        assert _parse_value("") is None


class TestCleanSeries:
    def test_registros_validos_sao_mantidos(self):
        raw = [
            {"data": "01/09/2026", "valor": "5.10"},
            {"data": "02/09/2026", "valor": "5.20"},
        ]
        result = clean_series("dolar", raw)

        assert len(result) == 2
        assert result[0]["series_name"] == "dolar"
        assert result[0]["reference_date"] == "2026-09-01"
        assert result[0]["value"] == 5.10

    def test_registro_com_data_invalida_e_descartado(self):
        raw = [
            {"data": "data-invalida", "valor": "5.10"},
            {"data": "02/09/2026", "valor": "5.20"},
        ]
        result = clean_series("dolar", raw)

        assert len(result) == 1
        assert result[0]["reference_date"] == "2026-09-02"

    def test_registro_com_valor_invalido_e_descartado(self):
        raw = [
            {"data": "01/09/2026", "valor": "N/D"},
            {"data": "02/09/2026", "valor": "5.20"},
        ]
        result = clean_series("dolar", raw)

        assert len(result) == 1

    def test_lista_vazia_retorna_lista_vazia(self):
        assert clean_series("dolar", []) == []