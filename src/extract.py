"""
Camada de extração (Extract) do pipeline.
Responsável apenas por buscar os dados brutos na API SGS do Banco Central.
Não faz limpeza nem validação — isso é responsabilidade do transform.py.
"""

import time
from datetime import date, timedelta

import requests

from src.config import BCB_API_BASE_URL
from src.logger import get_logger

logger = get_logger(__name__)

# Códigos das séries que vamos coletar (SGS - Banco Central)
SERIES = {
    "dolar": 1,
    "selic": 432,
    "ipca": 433,
}

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2


def _build_url(series_code: int, start_date: str, end_date: str) -> str:
    """Monta a URL da API SGS para um código de série e intervalo de datas."""
    return (
        f"{BCB_API_BASE_URL}.{series_code}/dados"
        f"?formato=json&dataInicial={start_date}&dataFinal={end_date}"
    )


def fetch_series(series_name: str, start_date: str, end_date: str) -> list[dict]:
    """
    Busca os dados de uma série do SGS entre duas datas (formato dd/mm/aaaa).
    Retorna uma lista de dicts no formato bruto da API: [{"data": ..., "valor": ...}, ...]

    Um 404 é tratado como "sem dados nesse período" (comportamento normal para
    séries mensais como o IPCA quando o mês ainda não foi divulgado) e retorna
    lista vazia, sem contar como falha de rede.
    Erros de conexão/timeout continuam usando retry.
    """
    if series_name not in SERIES:
        raise ValueError(f"Série desconhecida: '{series_name}'. Opções: {list(SERIES.keys())}")

    series_code = SERIES[series_name]
    url = _build_url(series_code, start_date, end_date)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Buscando série '{series_name}' (tentativa {attempt}/{MAX_RETRIES})...")
            response = requests.get(url, timeout=10)

            if response.status_code == 404:
                logger.warning(
                    f"Série '{series_name}': nenhum dado disponível no período "
                    f"{start_date} a {end_date} (404 - normal para séries com defasagem, "
                    f"como o IPCA)."
                )
                return []

            response.raise_for_status()  # levanta erro se status for outro 4xx/5xx

            data = response.json()
            logger.info(f"Série '{series_name}': {len(data)} registros recebidos.")
            return data

        except requests.exceptions.RequestException as e:
            logger.warning(f"Falha ao buscar '{series_name}' (tentativa {attempt}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS * attempt)  # espera progressiva
            else:
                logger.error(f"Todas as tentativas falharam para a série '{series_name}'.")
                raise

    return []  # nunca deve chegar aqui, mas evita warning de tipagem


def fetch_all_series(start_date: str, end_date: str) -> dict[str, list[dict]]:
    """Busca todas as séries configuradas e retorna um dict {nome_serie: dados}."""
    results = {}
    for series_name in SERIES:
        results[series_name] = fetch_series(series_name, start_date, end_date)
    return results


if __name__ == "__main__":
    # Teste manual: usa uma janela de 90 dias para garantir que séries
    # mensais (como o IPCA) tenham pelo menos um valor publicado no período.
    today = date.today().strftime("%d/%m/%Y")
    three_months_ago = (date.today() - timedelta(days=90)).strftime("%d/%m/%Y")

    all_data = fetch_all_series(start_date=three_months_ago, end_date=today)
    for name, records in all_data.items():
        print(f"\n{name.upper()} ({len(records)} registros):")
        for r in records[-3:]:  # mostra os 3 MAIS RECENTES como amostra
            print(" ", r)