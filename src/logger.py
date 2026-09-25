"""
Configuração central de logging do projeto.
Qualquer módulo deve importar `get_logger` e usá-lo em vez de print().
"""

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """Cria (ou reaproveita) um logger configurado para o módulo informado."""
    logger = logging.getLogger(name)

    # Evita adicionar handlers duplicados se a função for chamada mais de uma vez
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger