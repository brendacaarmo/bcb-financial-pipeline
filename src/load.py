"""
Camada de carga (Load) do pipeline.
Recebe os registros limpos do transform.py e grava no PostgreSQL,
usando upsert para evitar duplicatas em execuções repetidas.
"""

import psycopg2
from psycopg2.extras import execute_values

from src.config import (
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)
from src.logger import get_logger
from src.transform import CleanRecord

logger = get_logger(__name__)

UPSERT_QUERY = """
    INSERT INTO indicadores (series_name, reference_date, value)
    VALUES %s
    ON CONFLICT (series_name, reference_date)
    DO UPDATE SET value = EXCLUDED.value
"""


def get_connection():
    """Abre uma conexão com o PostgreSQL usando as configs do .env."""
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )


def load_records(records: list[CleanRecord]) -> int:
    """
    Grava os registros no banco via upsert.
    Retorna a quantidade de registros processados.
    Toda a operação roda em uma única transação: ou tudo é gravado, ou nada é.
    """
    if not records:
        logger.warning("Nenhum registro para carregar. Encerrando sem gravar.")
        return 0

    values = [(r["series_name"], r["reference_date"], r["value"]) for r in records]

    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            execute_values(cursor, UPSERT_QUERY, values)
        conn.commit()
        logger.info(f"{len(records)} registros gravados/atualizados com sucesso.")
        return len(records)

    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Erro ao gravar no banco, transação revertida: {e}")
        raise

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    from datetime import date, timedelta

    from src.extract import fetch_all_series
    from src.transform import clean_all_series

    today = date.today().strftime("%d/%m/%Y")
    three_months_ago = (date.today() - timedelta(days=90)).strftime("%d/%m/%Y")

    raw = fetch_all_series(start_date=three_months_ago, end_date=today)
    clean = clean_all_series(raw)
    load_records(clean)