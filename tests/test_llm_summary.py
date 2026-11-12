"""
Testes unitários para src/llm_summary.py.
Nenhum teste chama a API do Gemini nem o banco: tudo é simulado com mocks.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import requests

from src import llm_summary
from src.llm_summary import (
    SummaryError,
    build_facts,
    call_gemini,
    data_until,
    generate_and_save,
    produce_summary,
    template_summary,
    verify_summary,
)


@pytest.fixture(autouse=True)
def sem_espera():
    """Evita esperar entre tentativas durante os testes."""
    with patch("src.llm_summary.time.sleep"):
        yield


@pytest.fixture
def rows():
    """Linhas no formato que o banco devolve: (série, data, valor)."""
    return [
        ("dolar", date(2026, 10, 12), 5.00),
        ("dolar", date(2026, 11, 5), 5.4621),
        ("dolar", date(2026, 11, 11), 5.5606),
        ("dolar", date(2026, 11, 12), 5.6143),
        ("selic", date(2026, 10, 10), 13.75),
        ("selic", date(2026, 11, 12), 13.75),
        ("ipca", date(2026, 8, 1), 0.60),
        ("ipca", date(2026, 9, 1), 0.82),
    ]


@pytest.fixture
def facts(rows):
    return build_facts(rows)


class TestBuildFacts:
    def test_dolar_valor_atual_e_data(self, facts):
        assert facts["dolar"]["valor_atual"] == 5.6143
        assert facts["dolar"]["data_atual"] == "2026-11-12"

    def test_dolar_variacao_7_dias(self, facts):
        # 7 dias antes de 12/11 é 05/11 (5,4621). (5,6143-5,4621)/5,4621 = 2,79%
        assert facts["dolar"]["valor_7_dias_antes"] == 5.4621
        assert facts["dolar"]["variacao_7_dias_pct"] == 2.79

    def test_dolar_minimo_e_maximo_30_dias(self, facts):
        assert facts["dolar"]["minimo_30_dias"] == 5.4621
        assert facts["dolar"]["maximo_30_dias"] == 5.6143

    def test_selic_sem_mudanca(self, facts):
        assert facts["selic"]["valor_atual"] == 13.75
        assert facts["selic"]["mudou_em_30_dias"] is False

    def test_selic_com_mudanca(self):
        facts = build_facts(
            [("selic", date(2026, 10, 1), 14.00), ("selic", date(2026, 11, 12), 13.75)]
        )
        assert facts["selic"]["mudou_em_30_dias"] is True
        assert facts["selic"]["valor_30_dias_antes"] == 14.0

    def test_ipca_mensal(self, facts):
        assert facts["ipca"]["valor_atual"] == 0.82
        assert facts["ipca"]["mes_referencia"] == "2026-09"
        assert facts["ipca"]["valor_mes_anterior"] == 0.6

    def test_serie_ausente_nao_aparece(self):
        facts = build_facts([("dolar", date(2026, 11, 12), 5.6)])
        assert "selic" not in facts and "ipca" not in facts

    def test_sem_linhas_devolve_vazio(self):
        assert build_facts([]) == {}

    def test_data_until(self, facts):
        assert data_until(facts) == date(2026, 11, 12)


class TestVerifySummary:
    BOM = (
        "O dólar comercial estava em R$ 5,61 em 12/11, com alta de 2,79% em 7 dias. "
        "A Selic seguiu em 13,75% ao ano. O IPCA de setembro foi de 0,82%."
    )

    def test_texto_correto_e_aprovado(self, facts):
        assert verify_summary(self.BOM, facts) == []

    def test_numero_inventado_e_reprovado(self, facts):
        texto = self.BOM.replace("2,79%", "4,10%")
        problemas = verify_summary(texto, facts)
        assert any("4,10" in p for p in problemas)

    def test_selic_errada_e_reprovada(self, facts):
        texto = self.BOM.replace("13,75%", "14,25%")
        assert any("14,25" in p for p in verify_summary(texto, facts))

    def test_inteiro_inventado_e_reprovado(self, facts):
        texto = self.BOM + " O dólar subiu 4 dias seguidos."
        assert any("'4'" in p for p in verify_summary(texto, facts))

    def test_arredondamento_aceito(self, facts):
        texto = "Dólar a R$ 5,6, Selic em 13,8% e IPCA em 0,8%."
        assert verify_summary(texto, facts) == []

    def test_valor_do_dolar_com_4_casas(self, facts):
        texto = "O dólar fechou em R$ 5,6143. Selic em 13,75%. IPCA de 0,82%."
        assert verify_summary(texto, facts) == []

    def test_separador_ingles_e_reprovado(self, facts):
        # '5.61' seria lido como 561, que não existe nos dados
        texto = "O dólar estava em R$ 5.61. Selic em 13,75%. IPCA de 0,82%."
        assert verify_summary(texto, facts) != []

    def test_palavra_de_recomendacao_e_reprovada(self, facts):
        texto = self.BOM + " Recomendamos cautela."
        assert any("recomend" in p for p in verify_summary(texto, facts))

    def test_previsao_e_reprovada(self, facts):
        texto = self.BOM + " O dólar provavelmente seguirá em alta."
        assert any("provavelmente" in p for p in verify_summary(texto, facts))

    def test_serie_faltando_e_reprovada(self, facts):
        texto = "O dólar estava em R$ 5,61 e a Selic em 13,75%."
        assert any("ipca" in p for p in verify_summary(texto, facts))

    def test_texto_vazio_e_reprovado(self, facts):
        assert verify_summary("   ", facts) == ["texto vazio"]

    def test_texto_longo_demais_e_reprovado(self, facts):
        texto = self.BOM + " " + "Texto. " * 200
        assert any("caracteres" in p for p in verify_summary(texto, facts))


class TestTemplateSummary:
    def test_template_passa_na_propria_verificacao(self, facts):
        texto = template_summary(facts)
        assert verify_summary(texto, facts) == []

    def test_template_conteudo(self, facts):
        texto = template_summary(facts)
        assert "R$ 5,6143" in texto
        assert "alta de 2,79% em 7 dias" in texto
        assert "13,75% ao ano, sem mudança em 30 dias" in texto
        assert "09/2026" in texto

    def test_template_com_queda(self):
        facts = build_facts(
            [("dolar", date(2026, 11, 5), 5.50), ("dolar", date(2026, 11, 12), 5.40)]
        )
        assert "queda de 1,82% em 7 dias" in template_summary(facts)

    def test_template_so_com_dolar(self):
        facts = build_facts([("dolar", date(2026, 11, 12), 5.6)])
        texto = template_summary(facts)
        assert "Selic" not in texto and "IPCA" not in texto
        assert verify_summary(texto, facts) == []


class TestProduceSummary:
    BOM = (
        "O dólar comercial estava em R$ 5,61 em 12/11, com alta de 2,79% em 7 dias. "
        "A Selic seguiu em 13,75% ao ano. O IPCA de setembro foi de 0,82%."
    )

    def test_sem_chave_usa_template_sem_chamar_ia(self, facts):
        caller = MagicMock()
        texto, fonte = produce_summary(facts, None, "modelo", caller=caller)
        assert fonte == "template"
        caller.assert_not_called()
        assert texto == template_summary(facts)

    def test_ia_aprovada_na_primeira(self, facts):
        caller = MagicMock(return_value=self.BOM)
        texto, fonte = produce_summary(facts, "chave", "modelo", caller=caller)
        assert fonte == "llm"
        assert texto == self.BOM
        assert caller.call_count == 1

    def test_ia_reprovada_depois_aprovada(self, facts):
        ruim = self.BOM.replace("2,79%", "9,99%")
        caller = MagicMock(side_effect=[ruim, self.BOM])
        texto, fonte = produce_summary(facts, "chave", "modelo", caller=caller)
        assert fonte == "llm"
        assert caller.call_count == 2

    def test_ia_sempre_reprovada_usa_template(self, facts):
        ruim = self.BOM.replace("2,79%", "9,99%")
        caller = MagicMock(return_value=ruim)
        texto, fonte = produce_summary(facts, "chave", "modelo", caller=caller)
        assert fonte == "template"
        assert caller.call_count == llm_summary.MAX_ATTEMPTS
        assert "9,99" not in texto

    def test_erro_de_rede_usa_template(self, facts):
        caller = MagicMock(side_effect=requests.ConnectionError("sem internet"))
        texto, fonte = produce_summary(facts, "chave", "modelo", caller=caller)
        assert fonte == "template"

    def test_resposta_vazia_usa_template(self, facts):
        caller = MagicMock(side_effect=SummaryError("resposta vazia"))
        _, fonte = produce_summary(facts, "chave", "modelo", caller=caller)
        assert fonte == "template"


class TestCallGemini:
    def _resposta(self, json_data, status=200):
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = json_data
        if status >= 400:
            resp.raise_for_status.side_effect = requests.HTTPError(f"{status} erro")
        return resp

    @patch("src.llm_summary.requests.post")
    def test_le_o_texto_e_manda_chave_no_cabecalho(self, mock_post, facts):
        mock_post.return_value = self._resposta(
            {"candidates": [{"content": {"parts": [{"text": "Resumo pronto."}]}}]}
        )
        texto = call_gemini("regras", facts, "CHAVE-SECRETA", "gemini-x")

        assert texto == "Resumo pronto."
        args, kwargs = mock_post.call_args
        assert "gemini-x:generateContent" in args[0]
        assert "CHAVE-SECRETA" not in args[0]  # a chave não vai na URL
        assert kwargs["headers"]["x-goog-api-key"] == "CHAVE-SECRETA"
        assert kwargs["json"]["systemInstruction"]["parts"][0]["text"] == "regras"

    @patch("src.llm_summary.requests.post")
    def test_ignora_partes_de_pensamento(self, mock_post, facts):
        mock_post.return_value = self._resposta(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "raciocínio interno", "thought": True},
                                {"text": "Texto final."},
                            ]
                        }
                    }
                ]
            }
        )
        assert call_gemini("regras", facts, "k", "m") == "Texto final."

    @patch("src.llm_summary.requests.post")
    def test_resposta_sem_candidatos_gera_erro(self, mock_post, facts):
        mock_post.return_value = self._resposta({"promptFeedback": {"blockReason": "X"}})
        with pytest.raises(SummaryError):
            call_gemini("regras", facts, "k", "m")

    @patch("src.llm_summary.requests.post")
    def test_erro_http_propaga(self, mock_post, facts):
        mock_post.return_value = self._resposta({}, status=429)
        with pytest.raises(requests.HTTPError):
            call_gemini("regras", facts, "k", "m")


class TestGenerateAndSave:
    def _conn(self, rows):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        conn.cursor.return_value.__enter__.return_value = cursor
        return conn, cursor

    def test_grava_template_quando_sem_chave(self, rows):
        conn, cursor = self._conn(rows)
        result = generate_and_save(conn, None, "modelo", today=date(2026, 11, 12))

        assert result["source"] == "template"
        conn.commit.assert_called_once()
        # a última chamada ao cursor é o INSERT do resumo
        sql, params = cursor.execute.call_args[0]
        assert "INSERT INTO resumos_diarios" in sql
        assert params[0] == date(2026, 11, 12)  # summary_date
        assert params[1] == date(2026, 11, 12)  # data_until
        assert params[3] == "template"
        assert params[4] is None  # sem modelo quando não usou IA

    def test_sem_dados_nao_grava(self):
        conn, cursor = self._conn([])
        assert generate_and_save(conn, "chave", "modelo", today=date(2026, 11, 12)) is None
        conn.commit.assert_not_called()

    def test_grava_modelo_quando_usa_ia(self, rows):
        conn, cursor = self._conn(rows)
        bom = (
            "O dólar estava em R$ 5,61 em 12/11. A Selic seguiu em 13,75% ao ano. "
            "O IPCA de setembro foi de 0,82%."
        )
        with patch("src.llm_summary.call_gemini", return_value=bom):
            result = generate_and_save(conn, "chave", "gemini-x", today=date(2026, 11, 12))
        assert result["source"] == "llm"
        params = cursor.execute.call_args[0][1]
        assert params[3] == "llm" and params[4] == "gemini-x"
