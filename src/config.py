"""
Carrega e valida as variáveis de ambiente usadas em todo o projeto.
Qualquer outro módulo que precisar de uma configuração deve importar
daqui, em vez de ler o .env diretamente.
"""

import os
from dotenv import load_dotenv

# Carrega o arquivo .env para o ambiente do processo Python
load_dotenv()


def _get_env(key: str, required: bool = True, default: str | None = None) -> str:
    """Lê uma variável de ambiente, com validação de obrigatoriedade."""
    value = os.getenv(key, default)
    if required and not value:
        raise RuntimeError(
            f"Variável de ambiente obrigatória ausente: '{key}'. "
            f"Confira se ela está definida no seu arquivo .env."
        )
    return value


# --- PostgreSQL ---
POSTGRES_USER = _get_env("POSTGRES_USER")
POSTGRES_PASSWORD = _get_env("POSTGRES_PASSWORD")
POSTGRES_DB = _get_env("POSTGRES_DB")
POSTGRES_HOST = _get_env("POSTGRES_HOST")
POSTGRES_PORT = _get_env("POSTGRES_PORT")

# --- API do Banco Central (SGS) ---
BCB_API_BASE_URL = _get_env("BCB_API_BASE_URL")

# --- Fase 2: LLM (opcional por enquanto, não obrigatório) ---
LLM_API_KEY = _get_env("LLM_API_KEY", required=False)