"""
Camada de transformação (Transform) do pipeline.
Recebe os dados brutos do extract.py e devolve registros limpos e tipados,
prontos para serem carregados no banco pelo load.py.
"""

from datetime import datetime
from typing import TypedDict

from src.logger import get_logger

logger = get_logger(__name__)


class CleanRecord(TypedDict):
    series_name: str
    reference_date: str  # formato ISO: YYYY-MM-DD, padrão para bancos de dados
    value: float


def _parse_date(raw_date: str) -> str | None:
    """Converte 'dd/mm/aaaa' para 'aaaa-mm-dd' (formato ISO, padrão SQL)."""
    try:
        parsed = datetime.strptime(raw_date, "%d/%m/%Y")
        return parsed.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _parse_value(raw_value: str) -> float | None:
    """Converte o valor em string para float, tratando vírgula como decimal."""
    try:
        normalized = str(raw_value).replace(",", ".")
        return float(normalized)
    except (ValueError, TypeError):
        return None


def clean_series(series_name: str, raw_records: list[dict]) -> list[CleanRecord]:
    """
    Limpa e valida os registros brutos de uma série.
    Registros inválidos são descartados e registrados em log — não interrompem o pipeline.
    """
    clean_records: list[CleanRecord] = []
    discarded_count = 0

    for raw in raw_records:
        reference_date = _parse_date(raw.get("data", ""))
        value = _parse_value(raw.get("valor", ""))

        if reference_date is None or value is None:
            discarded_count += 1
            logger.warning(
                f"Registro descartado na série '{series_name}': "
                f"data='{raw.get('data')}', valor='{raw.get('valor')}'"
            )
            continue

        clean_records.append(
            CleanRecord(series_name=series_name, reference_date=reference_date, value=value)
        )

    logger.info(
        f"Série '{series_name}': {len(clean_records)} registros válidos, "
        f"{discarded_count} descartados."
    )
    return clean_records


def clean_all_series(raw_data: dict[str, list[dict]]) -> list[CleanRecord]:
    """Limpa todas as séries e retorna uma única lista consolidada de registros."""
    all_clean: list[CleanRecord] = []
    for series_name, raw_records in raw_data.items():
        all_clean.extend(clean_series(series_name, raw_records))
    return all_clean


if __name__ == "__main__":
    from datetime import date, timedelta

    from src.extract import fetch_all_series

    today = date.today().strftime("%d/%m/%Y")
    three_months_ago = (date.today() - timedelta(days=90)).strftime("%d/%m/%Y")

    raw = fetch_all_series(start_date=three_months_ago, end_date=today)
    clean = clean_all_series(raw)

    print(f"\nTotal de registros limpos: {len(clean)}")
    for record in clean[-5:]:
        print(" ", record)