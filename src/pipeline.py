"""
Ponto de entrada único do pipeline: Extract -> Transform -> Load.
Este é o arquivo que o Docker e o GitHub Actions executam para
rodar o pipeline completo.
"""

import sys
import time
from datetime import date, timedelta

from src.config import LLM_API_KEY, LLM_MODEL
from src.extract import fetch_all_series
from src.llm_summary import generate_and_save
from src.load import get_connection, load_records
from src.logger import get_logger
from src.transform import clean_all_series

logger = get_logger(__name__)

# Janela de coleta: 90 dias garante que séries mensais (como o IPCA)
# tenham ao menos um valor publicado no período.
LOOKBACK_DAYS = 90


def generate_daily_summary() -> None:
    """
    Gera o resumo diário com IA e grava no banco.
    É um passo extra: se falhar, apenas avisa no log e NÃO derruba o pipeline
    principal (os dados já foram gravados).
    """
    conn = None
    try:
        conn = get_connection()
        generate_and_save(conn, LLM_API_KEY, LLM_MODEL)
    except Exception:
        logger.warning(
            "Resumo diário não foi gerado. O pipeline principal não foi afetado.",
            exc_info=True,
        )
    finally:
        if conn:
            conn.close()


def run() -> None:
    """Executa o pipeline completo e loga um resumo ao final."""
    start_time = time.monotonic()
    logger.info("=== Iniciando pipeline BCB ===")

    today = date.today().strftime("%d/%m/%Y")
    start_date = (date.today() - timedelta(days=LOOKBACK_DAYS)).strftime("%d/%m/%Y")

    try:
        raw_data = fetch_all_series(start_date=start_date, end_date=today)
        clean_data = clean_all_series(raw_data)
        loaded_count = load_records(clean_data)
        generate_daily_summary()

        elapsed = time.monotonic() - start_time
        logger.info(
            f"=== Pipeline concluído com sucesso: {loaded_count} registros "
            f"em {elapsed:.2f}s ==="
        )

    except Exception:
        elapsed = time.monotonic() - start_time
        logger.error(f"=== Pipeline falhou após {elapsed:.2f}s ===", exc_info=True)
        sys.exit(1)  # código de saída != 0, para o CI/CD detectar falha


if __name__ == "__main__":
    run()