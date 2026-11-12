"""
Camada de resumo diário com IA (Gemini).

Fluxo:
    1. Lê do banco os indicadores recentes (dólar, Selic, IPCA).
    2. Calcula os fatos em Python (valor atual, variações, mínimo e máximo).
    3. Pede a um modelo de IA um parágrafo curto com base SÓ nesses fatos.
    4. VERIFICA o texto: todo número citado precisa existir nos fatos.
    5. Se o texto for reprovado (ou a IA falhar), usa um texto gerado por regras,
       sem IA. O dashboard sempre recebe um resumo confiável.
    6. Salva o resultado na tabela `resumos_diarios`.

Este módulo não importa o config.py de propósito: a chave e o modelo chegam
por parâmetro, o que facilita os testes (sem variáveis de ambiente).
"""

import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

import requests

from src.logger import get_logger

logger = get_logger(__name__)

PROMPT_VERSION = "v1"
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / f"daily_summary_{PROMPT_VERSION}.txt"
)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

HISTORY_DAYS = 120  # janela lida do banco (cobre ao menos 2 valores mensais do IPCA)
MAX_ATTEMPTS = 2  # tentativas com a IA antes de usar o texto sem IA
RETRY_WAIT_SECONDS = 3
REQUEST_TIMEOUT = 30
MAX_CHARS = 800

# Palavras que indicam recomendação, previsão ou explicação de causa.
# É uma checagem simples (heurística), complementar à regra do prompt.
FORBIDDEN_WORDS = [
    "recomend",
    "aconselh",
    "invista",
    "investir",
    "comprar",
    "previs",
    "provavelmente",
    "deve subir",
    "deve cair",
    "devido",
    "por causa",
    "em função",
]

# Termos que o texto precisa conter para cada série presente nos fatos.
REQUIRED_TERMS = {
    "dolar": "dólar",
    "selic": "selic",
    "ipca": "ipca",
}

DATE_LIKE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
NUMBER_IN_TEXT = re.compile(r"\d[\d.]*(?:,\d+)?")


class SummaryError(Exception):
    """Falha ao obter um texto da IA (rede, resposta vazia, etc.)."""


# --------------------------------------------------------------------------
# 1. Leitura do banco e cálculo dos fatos
# --------------------------------------------------------------------------

SELECT_QUERY = """
    SELECT series_name, reference_date, value
    FROM indicadores
    WHERE reference_date >= %s
    ORDER BY series_name, reference_date
"""


def fetch_rows(conn, today: date | None = None) -> list[tuple]:
    """Busca os indicadores dos últimos HISTORY_DAYS dias."""
    today = today or date.today()
    since = today - timedelta(days=HISTORY_DAYS)
    with conn.cursor() as cursor:
        cursor.execute(SELECT_QUERY, (since,))
        return cursor.fetchall()


def _group_by_series(rows: list[tuple]) -> dict[str, list[tuple[date, float]]]:
    grouped: dict[str, list[tuple[date, float]]] = {}
    for series_name, ref_date, value in rows:
        grouped.setdefault(series_name, []).append((ref_date, float(value)))
    for points in grouped.values():
        points.sort(key=lambda p: p[0])
    return grouped


def _last_on_or_before(points: list[tuple[date, float]], limit: date):
    """Último ponto com data menor ou igual a `limit`."""
    for ref_date, value in reversed(points):
        if ref_date <= limit:
            return ref_date, value
    return None


def _pct_change(new: float, old: float) -> float | None:
    if old == 0:
        return None
    return round((new - old) / old * 100, 2)


def _dolar_facts(points: list[tuple[date, float]]) -> dict:
    last_date, last_value = points[-1]
    facts = {
        "descricao": "Dólar comercial (venda)",
        "valor_atual": round(last_value, 4),
        "data_atual": last_date.isoformat(),
    }

    week = _last_on_or_before(points, last_date - timedelta(days=7))
    if week:
        facts["valor_7_dias_antes"] = round(week[1], 4)
        facts["data_7_dias_antes"] = week[0].isoformat()
        change = _pct_change(last_value, week[1])
        if change is not None:
            facts["variacao_7_dias_pct"] = change

    month = _last_on_or_before(points, last_date - timedelta(days=30))
    if month:
        change = _pct_change(last_value, month[1])
        if change is not None:
            facts["variacao_30_dias_pct"] = change

    last_30 = [v for d, v in points if d > last_date - timedelta(days=30)]
    if len(last_30) >= 2:
        facts["minimo_30_dias"] = round(min(last_30), 4)
        facts["maximo_30_dias"] = round(max(last_30), 4)
    return facts


def _selic_facts(points: list[tuple[date, float]]) -> dict:
    last_date, last_value = points[-1]
    facts = {
        "descricao": "Meta Selic",
        "valor_atual": round(last_value, 2),
        "data_atual": last_date.isoformat(),
    }
    month = _last_on_or_before(points, last_date - timedelta(days=30))
    if month:
        changed = abs(last_value - month[1]) > 1e-9
        facts["mudou_em_30_dias"] = changed
        if changed:
            facts["valor_30_dias_antes"] = round(month[1], 2)
    return facts


def _ipca_facts(points: list[tuple[date, float]]) -> dict:
    last_date, last_value = points[-1]
    facts = {
        "descricao": "IPCA (variação mensal)",
        "valor_atual": round(last_value, 2),
        "mes_referencia": last_date.strftime("%Y-%m"),
    }
    if len(points) >= 2:
        prev_date, prev_value = points[-2]
        facts["valor_mes_anterior"] = round(prev_value, 2)
        facts["mes_anterior"] = prev_date.strftime("%Y-%m")
    return facts


def build_facts(rows: list[tuple]) -> dict:
    """Transforma as linhas do banco nos fatos que a IA pode citar."""
    grouped = _group_by_series(rows)
    builders = {"dolar": _dolar_facts, "selic": _selic_facts, "ipca": _ipca_facts}
    facts = {}
    for name, builder in builders.items():
        if grouped.get(name):
            facts[name] = builder(grouped[name])
    return facts


def data_until(facts: dict) -> date | None:
    """Data mais recente entre as séries diárias dos fatos."""
    dates = [facts[s]["data_atual"] for s in ("dolar", "selic") if s in facts]
    return date.fromisoformat(max(dates)) if dates else None


# --------------------------------------------------------------------------
# 2. Texto sem IA (plano B) e formatação
# --------------------------------------------------------------------------


def _fmt(value: float, decimals: int) -> str:
    """Formata no padrão brasileiro: 1.234,56."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _dd_mm(iso_date: str) -> str:
    return date.fromisoformat(iso_date).strftime("%d/%m")


def _mm_yyyy(iso_month: str) -> str:
    year, month = iso_month.split("-")
    return f"{month}/{year}"


def template_summary(facts: dict) -> str:
    """Resumo escrito por regras fixas, sem IA. Sempre passa na verificação."""
    sentences = []

    if "dolar" in facts:
        d = facts["dolar"]
        text = f"O dólar comercial estava em R$ {_fmt(d['valor_atual'], 4)} em {_dd_mm(d['data_atual'])}"
        change = d.get("variacao_7_dias_pct")
        if change is not None:
            direction = "alta" if change > 0 else "queda" if change < 0 else "variação"
            if change == 0:
                text += ", sem variação em 7 dias"
            else:
                text += f", com {direction} de {_fmt(abs(change), 2)}% em 7 dias"
        sentences.append(text + ".")

    if "selic" in facts:
        s = facts["selic"]
        text = f"A meta Selic estava em {_fmt(s['valor_atual'], 2)}% ao ano"
        if s.get("mudou_em_30_dias") is False:
            text += ", sem mudança em 30 dias"
        elif s.get("mudou_em_30_dias") is True:
            text += f", ante {_fmt(s['valor_30_dias_antes'], 2)}% 30 dias antes"
        sentences.append(text + ".")

    if "ipca" in facts:
        i = facts["ipca"]
        text = f"O IPCA de {_mm_yyyy(i['mes_referencia'])} foi de {_fmt(i['valor_atual'], 2)}%"
        if "valor_mes_anterior" in i:
            text += f", ante {_fmt(i['valor_mes_anterior'], 2)}% em {_mm_yyyy(i['mes_anterior'])}"
        sentences.append(text + ".")

    return " ".join(sentences)


# --------------------------------------------------------------------------
# 3. Verificação do texto (a parte mais importante)
# --------------------------------------------------------------------------


def _collect_numbers(obj, out: set[float]) -> None:
    """Junta todos os números dos fatos, inclusive partes de datas (ano, mês, dia)."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(float(obj))
        out.add(abs(float(obj)))
    elif isinstance(obj, str):
        if DATE_LIKE.match(obj):
            out.update(float(n) for n in re.findall(r"\d+", obj))
    elif isinstance(obj, dict):
        for value in obj.values():
            _collect_numbers(value, out)
    elif isinstance(obj, list):
        for value in obj:
            _collect_numbers(value, out)


def allowed_numbers(facts: dict) -> set[float]:
    """Números que o texto pode citar: os dos fatos e os prazos de 7 e 30 dias."""
    numbers: set[float] = {7.0, 30.0}
    _collect_numbers(facts, numbers)
    return numbers


def _parse_br_number(token: str) -> tuple[float, int] | None:
    """Converte '1.234,56' em (1234.56, 2). Retorna None se não for número válido."""
    token = token.rstrip(".")
    if not token:
        return None
    decimals = len(token.split(",")[1]) if "," in token else 0
    normalized = token.replace(".", "").replace(",", ".")
    try:
        return float(normalized), decimals
    except ValueError:
        return None


def _number_is_allowed(value: float, decimals: int, allowed: set[float]) -> bool:
    if decimals == 0:
        # número inteiro no texto: precisa ser um valor dos fatos ou o arredondamento dele
        return any(round(a) == value for a in allowed)
    tolerance = 0.5 * 10 ** (-decimals) + 1e-9
    return any(abs(value - a) <= tolerance for a in allowed)


def verify_summary(text: str, facts: dict) -> list[str]:
    """
    Confere o texto da IA. Devolve a lista de problemas (vazia = texto aprovado).

    Regras:
      - não pode ser vazio nem passar de MAX_CHARS;
      - todo número citado precisa existir nos fatos (com arredondamento);
      - não pode conter palavras de recomendação, previsão ou causa;
      - precisa citar cada série presente nos fatos (dólar, Selic, IPCA).
    """
    problems = []
    clean = text.strip()

    if not clean:
        return ["texto vazio"]
    if len(clean) > MAX_CHARS:
        problems.append(f"texto com {len(clean)} caracteres (máximo {MAX_CHARS})")

    allowed = allowed_numbers(facts)
    for token in NUMBER_IN_TEXT.findall(clean):
        parsed = _parse_br_number(token)
        if parsed is None:
            continue
        value, decimals = parsed
        if not _number_is_allowed(value, decimals, allowed):
            problems.append(f"número '{token.rstrip('.')}' não existe nos dados")

    lowered = clean.lower()
    for word in FORBIDDEN_WORDS:
        if word in lowered:
            problems.append(f"expressão proibida: '{word}'")

    for series, term in REQUIRED_TERMS.items():
        if series in facts and term not in lowered:
            problems.append(f"não cita {term}")

    return problems


# --------------------------------------------------------------------------
# 4. Chamada à IA (Gemini, via API REST)
# --------------------------------------------------------------------------


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _extract_text(data: dict) -> str:
    """Lê o texto da resposta do Gemini, ignorando partes de 'pensamento'."""
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SummaryError(f"resposta sem texto: {str(data)[:200]}") from exc
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text.strip():
        raise SummaryError("resposta vazia da IA")
    return text.strip()


def call_gemini(system_prompt: str, facts: dict, api_key: str, model: str) -> str:
    """Envia os fatos ao Gemini e devolve o texto gerado."""
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": "Dados do dia (JSON):\n" + json.dumps(facts, ensure_ascii=False, indent=2)}
                ],
            }
        ],
    }
    # A chave vai no cabeçalho (nunca na URL), para não aparecer em logs.
    response = requests.post(
        GEMINI_URL.format(model=model),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return _extract_text(response.json())


def produce_summary(facts: dict, api_key: str | None, model: str, caller=None):
    """
    Devolve (texto, fonte), onde fonte é 'llm' ou 'template'.
    Tenta a IA até MAX_ATTEMPTS vezes; se falhar ou for reprovada, usa o plano B.
    """
    caller = caller or call_gemini
    if not api_key:
        logger.warning("LLM_API_KEY não definida. Usando resumo sem IA.")
        return template_summary(facts), "template"

    system_prompt = load_prompt()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            text = caller(system_prompt, facts, api_key, model)
        except (requests.RequestException, SummaryError) as exc:
            logger.warning(f"IA indisponível (tentativa {attempt}/{MAX_ATTEMPTS}): {exc}")
        else:
            problems = verify_summary(text, facts)
            if not problems:
                return text.strip(), "llm"
            logger.warning(
                f"Texto da IA reprovado (tentativa {attempt}/{MAX_ATTEMPTS}): "
                + "; ".join(problems)
            )
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_WAIT_SECONDS)

    logger.warning("Usando o resumo sem IA como plano B.")
    return template_summary(facts), "template"


# --------------------------------------------------------------------------
# 5. Gravação e orquestração
# --------------------------------------------------------------------------

UPSERT_SUMMARY = """
    INSERT INTO resumos_diarios
        (summary_date, data_until, text, source, model, prompt_version)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (summary_date) DO UPDATE SET
        data_until = EXCLUDED.data_until,
        text = EXCLUDED.text,
        source = EXCLUDED.source,
        model = EXCLUDED.model,
        prompt_version = EXCLUDED.prompt_version,
        inserted_at = NOW()
"""


def save_summary(conn, summary_date: date, until: date | None, text: str, source: str, model: str) -> None:
    model_used = model if source == "llm" else None
    with conn.cursor() as cursor:
        cursor.execute(
            UPSERT_SUMMARY,
            (summary_date, until, text, source, model_used, PROMPT_VERSION),
        )
    conn.commit()


def generate_and_save(conn, api_key: str | None, model: str, today: date | None = None) -> dict | None:
    """Gera o resumo do dia e grava no banco. Devolve o que foi gravado."""
    today = today or date.today()
    facts = build_facts(fetch_rows(conn, today))
    if not facts:
        logger.warning("Sem dados no banco para resumir. Nada foi gravado.")
        return None

    text, source = produce_summary(facts, api_key, model)
    save_summary(conn, today, data_until(facts), text, source, model)
    logger.info(f"Resumo diário gravado (fonte={source}): {text}")
    return {"text": text, "source": source}
