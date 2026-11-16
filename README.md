# Pipeline Automatizado de Indicadores Financeiros (BCB)

[![Pipeline diário](https://github.com/brendacaarmo/bcb-financial-pipeline/actions/workflows/daily_pipeline.yml/badge.svg)](https://github.com/brendacaarmo/bcb-financial-pipeline/actions/workflows/daily_pipeline.yml)

Pipeline de dados que coleta diariamente indicadores econômicos do
**Banco Central do Brasil** (Dólar, Selic, IPCA) via API pública (SGS), valida e
transforma os dados e os armazena em um banco **PostgreSQL** na nuvem. Depois da
carga, uma camada de **IA (Gemini)** escreve um resumo diário em texto, com os
números **verificados contra o banco** antes de serem gravados.

A execução é agendada no **GitHub Actions** e roda todos os dias. O resultado
pode ser visto no [dashboard](https://brendacaarmo.github.io/bcb-dashboard)
([repositório](https://github.com/brendacaarmo/bcb-dashboard)).

## Arquitetura

```text
API SGS (Banco Central)
        │
        ▼
extract.py ──▶ transform.py ──▶ load.py
 busca, retry   limpa, tipa      upsert (sem duplicar)
                e valida             │
                                     ▼
                        Supabase (PostgreSQL na nuvem)
                         ├─ indicadores
                         └─ resumos_diarios ◀── llm_summary.py
                                │               fatos em Python, texto do Gemini,
                                │               verificação dos números, plano B
                                ▼
              Dashboard web / Power BI / outras ferramentas
```

Toda a execução é orquestrada pelo `pipeline.py` e disparada pelo **GitHub Actions**
(`.github/workflows/daily_pipeline.yml`). Veja mais detalhes técnicos em
[`docs/architecture.md`](docs/architecture.md).

## Resumo diário com IA

Depois de gravar os dados, o pipeline gera um parágrafo curto sobre o dia
(dólar, Selic e IPCA) e salva na tabela `resumos_diarios`, de onde o dashboard lê.

- **Os números são calculados em Python, não pela IA.** Valor atual, variação em
  7 e 30 dias, mínimo e máximo viram um JSON, e o modelo só escreve o texto em
  cima desses fatos.
- **O texto é verificado antes de ser gravado.** Todo número citado precisa
  existir nos fatos (aceitando arredondamento). O texto também é reprovado se
  tiver recomendação, previsão ou explicação de causa, se passar do tamanho ou se
  esquecer uma das séries.
- **Existe um plano B sem IA.** Se a API falhar ou o texto for reprovado duas
  vezes, o resumo é montado por regras fixas. A coluna `source` guarda `llm` ou
  `template`, e `prompt_version` guarda a versão do prompt (pasta `prompts/`).
- **A falha do resumo não derruba o pipeline.** Os dados já foram gravados antes;
  se o resumo quebrar, o log registra um aviso e a execução segue verde.

Exemplo real de saída (12/11/2026):

> O dólar comercial encerrou o dia 12/11 cotado a R$ 5,61, registrando alta de
> 2,79% em relação ao dia 05/11, quando o valor era de R$ 5,46. A meta Selic
> manteve-se em 13,75% ao ano na data de 12/11, sem alteração nos últimos trinta
> dias. O IPCA registrou variação mensal de 0,14% em outubro de 2026, ficando
> abaixo do resultado de 0,82% observado em setembro de 2026.

### Como configurar

1. Rode `sql/002_resumos_diarios.sql` no **SQL Editor do Supabase** (cria a tabela
   e a regra de leitura pública). Esse arquivo usa o perfil `anon`, que existe no
   Supabase mas não num PostgreSQL comum.
2. Crie uma chave de API no [Google AI Studio](https://aistudio.google.com) e
   guarde no GitHub como secret `LLM_API_KEY`. O modelo padrão é
   `gemini-3.5-flash-lite` e pode ser trocado com a variável `LLM_MODEL`.
3. Sem a chave, o projeto funciona do mesmo jeito e usa o resumo por regras.

Mais detalhes e limites conhecidos em [`docs/llm_summary.md`](docs/llm_summary.md).

## Stack

- **Linguagem:** Python 3.11
- **Banco de dados:** PostgreSQL (Supabase, em produção / Docker, localmente)
- **IA:** Gemini, pela API REST do Google (chamada com `requests`)
- **Containerização:** Docker & Docker Compose
- **CI/CD:** GitHub Actions (agendamento diário via cron)
- **Testes:** pytest, com mocks para as chamadas de API (Banco Central e Gemini)

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
# (LLM_API_KEY é opcional: sem ela, o resumo é gerado por regras)

# 5. Suba o banco local com Docker
docker compose up -d postgres

# 6. Rode o pipeline
python3 -m src.pipeline
```

O banco local do Docker cria só a tabela `indicadores`. Sem a tabela
`resumos_diarios`, o passo do resumo registra um aviso no log e o restante do
pipeline roda normalmente.

### Rodando tudo via Docker (aplicação + banco)

```bash
docker compose up --build
```

### Rodando os testes

```bash
pip install -r requirements-dev.txt
pytest -v
```

Os testes não usam rede nem banco: as APIs e a conexão são simuladas.

## Automação (GitHub Actions)

O workflow [`daily_pipeline.yml`](.github/workflows/daily_pipeline.yml) executa
o pipeline todos os dias às 09:00 UTC (06:00 horário de Brasília), gravando os
dados diretamente no banco de produção (Supabase). As credenciais, inclusive a
chave da IA, são gerenciadas via GitHub Secrets, nunca expostas no código.

Também pode ser disparado manualmente pela aba **Actions** do repositório
(`workflow_dispatch`).

A cada execução o pipeline busca os últimos 90 dias e grava com upsert. Por isso,
se algum dia falhar, a execução seguinte preenche o intervalo sozinha, sem
duplicar dados.

## Limitações conhecidas e próximos passos

- O plano gratuito do Supabase pausa projetos com pouca atividade. Enquanto o
  projeto está pausado, a execução diária falha (e o selo no topo fica vermelho);
  depois de reativar o projeto, a próxima execução recupera o intervalo.
- A verificação do resumo confere números e palavras proibidas, mas não entende o
  sentido do texto (por exemplo, "alta" no lugar de "queda"). Veja
  [`docs/llm_summary.md`](docs/llm_summary.md).
- Planejado: alerta de falha da execução e uma chamada diária que mantenha o
  projeto do Supabase ativo.
- Planejado: um agente "Pergunte ao BCB", que transforma perguntas em linguagem
  natural em consultas SQL somente leitura.

## Consultas de exemplo

Veja [`sql/queries.sql`](sql/queries.sql) para exemplos de análises que podem
ser feitas diretamente no banco, como cotação média mensal e variação do dólar.

## Autora

Brenda Carmo - [LinkedIn](https://www.linkedin.com/in/brenda-carmo-151b12208/)
