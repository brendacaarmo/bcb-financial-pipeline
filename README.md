# Pipeline de Dados Automatizado — Indicadores Financeiros (BCB)

Pipeline de dados automatizado que coleta diariamente indicadores econômicos do
**Banco Central do Brasil** (Dólar, Selic, IPCA) via API pública (SGS), valida e
transforma os dados, e os armazena em um banco **PostgreSQL** na nuvem — pronto
para consumo em ferramentas de BI como Power BI.

A execução é 100% automatizada via **GitHub Actions**, rodando diariamente sem
intervenção manual.

## Arquitetura

API SGS (Banco Central)
│
▼
extract.py → busca os dados brutos, com retry e tratamento de erros
│
▼
transform.py → limpa, tipa e valida os dados
│
▼
load.py → grava via upsert (sem duplicar) no PostgreSQL
│
▼
Supabase (PostgreSQL na nuvem)
│
▼
Power BI / outras ferramentas de análise


Toda a execução é orquestrada pelo `pipeline.py` e disparada automaticamente
todos os dias pelo **GitHub Actions** (`.github/workflows/daily_pipeline.yml`).
Veja mais detalhes técnicos em [`docs/architecture.md`](docs/architecture.md).

## Stack

- **Linguagem:** Python 3.11
- **Banco de dados:** PostgreSQL (Supabase, em produção / Docker, localmente)
- **Containerização:** Docker & Docker Compose
- **CI/CD:** GitHub Actions (agendamento diário via cron)
- **Testes:** pytest, com mocks para chamadas de API

## Indicadores coletados

| Indicador | Código SGS | Frequência |
|---|---|---|
| Dólar comercial (venda) | 1 | Diária |
| Selic (meta) | 432 | Diária |
| IPCA (variação mensal) | 433 | Mensal |

## Como rodar localmente

### Pré-requisitos
- Python 3.11+
- Docker e Docker Compose

### Passos

```bash
# 1. Clone o repositório
git clone https://github.com/brendacaarmo/bcb-financial-pipeline.git
cd bcb-financial-pipeline

# 2. Crie e ative o ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure as variáveis de ambiente
cp .env.example .env
# edite o .env com suas credenciais de banco

# 5. Suba o banco local com Docker
docker compose up -d postgres

# 6. Rode o pipeline
python3 -m src.pipeline
```

### Rodando tudo via Docker (aplicação + banco)

```bash
docker compose up --build
```

### Rodando os testes

```bash
pip install -r requirements-dev.txt
pytest -v
```

## Automação (GitHub Actions)

O workflow [`daily_pipeline.yml`](.github/workflows/daily_pipeline.yml) executa
o pipeline todos os dias às 09:00 UTC (06:00 horário de Brasília), gravando os
dados diretamente no banco de produção (Supabase). As credenciais são
gerenciadas via GitHub Secrets, nunca expostas no código.

Também pode ser disparado manualmente pela aba **Actions** do repositório
(`workflow_dispatch`).

## Consultas de exemplo

Veja [`sql/queries.sql`](sql/queries.sql) para exemplos de análises que podem
ser feitas diretamente no banco, como cotação média mensal e variação do dólar.

## Próximos passos

- [ ] Dashboard em Power BI consumindo os dados deste pipeline
- [ ] Camada de resumo diário automatizado via API de LLM

## Autora

Brenda Julia Carmo Silva — [LinkedIn](https://www.linkedin.com/in/brenda-carmo-151b12208/)

