# Arquitetura do Pipeline

## Visão geral

┌─────────────────┐
│ API SGS (BCB) │ Fonte pública, sem autenticação
└────────┬─────────┘
│ HTTPS
▼
┌─────────────────┐
│ extract.py │ Busca dados brutos, com retry (3x) e
│ │ tratamento de 404 para séries mensais
└────────┬─────────┘
│ lista de dicts (bruto)
▼
┌─────────────────┐
│ transform.py │ Converte tipos, valida, descarta
│ │ registros inválidos (com log)
└────────┬─────────┘
│ lista de dicts (limpo, tipado)
▼
┌─────────────────┐
│ load.py │ Upsert transacional no PostgreSQL
│ │ (evita duplicatas em reexecuções)
└────────┬─────────┘
│
▼
┌─────────────────┐
│ Supabase │ PostgreSQL gerenciado, persistente,
│ (PostgreSQL) │ acessível externamente (ex: Power BI)
└────────┬─────────┘
│ lê `indicadores`
▼
┌─────────────────┐
│ llm_summary.py │ Calcula os fatos em Python, pede o texto ao
│ │ Gemini, verifica os números e grava em
│ │ `resumos_diarios` (com plano B sem IA)
└──────────────────┘

Orquestração: pipeline.py (ponto de entrada único)
Agendamento: GitHub Actions, diariamente às 09:00 UTC


## Decisões técnicas e por quê

### Uma tabela única, não três
As três séries (dólar, selic, ipca) ficam na mesma tabela `indicadores`,
diferenciadas pela coluna `series_name`. Isso simplifica o schema e facilita
consultas comparativas entre indicadores, ao custo de uma coluna a mais por
linha — uma troca razoável para o volume de dados deste projeto.

### Upsert em vez de insert simples
A constraint `UNIQUE (series_name, reference_date)` combinada com
`ON CONFLICT ... DO UPDATE` torna o pipeline **idempotente**: rodá-lo várias
vezes no mesmo dia não duplica dados, apenas atualiza o valor mais recente.
Isso é essencial para uma automação diária confiável.

### Tratamento especial para HTTP 404 no IPCA
O IPCA é uma série mensal, divulgada com defasagem. Pedir dados do mês corrente
antes da divulgação retorna 404 na API do BCB — um comportamento esperado, não
um erro de sistema. O `extract.py` trata esse caso especificamente, retornando
lista vazia em vez de consumir tentativas de retry ou lançar exceção.

### Retry com backoff progressivo
Falhas de rede (timeout, instabilidade momentânea) são tratadas com até 3
tentativas, com espera crescente entre elas (2s, 4s). Isso torna o pipeline mais
resiliente a instabilidades transitórias da API externa, sem mascarar falhas
persistentes (que seguem sendo levantadas como erro após a 3ª tentativa).

### Banco em nuvem (Supabase) em vez de efêmero no CI
Inicialmente, o banco poderia rodar apenas dentro do próprio GitHub Actions,
existindo só durante a execução. Optou-se por um PostgreSQL gerenciado e
persistente (Supabase) para que os dados acumulem histórico real dia após dia,
e para permitir que ferramentas externas (como o Power BI) se conectem
diretamente ao banco.

### Camada de configuração e logging centralizadas
`config.py` valida a presença de variáveis de ambiente obrigatórias na
inicialização, falhando cedo e com mensagem clara em vez de erros confusos no
meio da execução. `logger.py` centraliza o logging estruturado, usado por
todos os módulos em vez de `print()`, facilitando debugging em produção
(os logs do GitHub Actions dependem inteiramente disso).

### Resumo com IA: a IA escreve, o código calcula e confere
Os números do resumo (valor atual, variações, mínimo e máximo) são calculados em
Python e entregues ao modelo como JSON. O modelo só escreve o texto. Antes de
gravar, `verify_summary` confere se todo número citado existe nos fatos (aceitando
arredondamento) e reprova textos com recomendação, previsão ou explicação de
causa. Isso reduz o risco de a IA inventar valores, mas não elimina todos os
erros: a verificação não entende o sentido do texto. Detalhes em
[`llm_summary.md`](llm_summary.md).

### Plano B sem IA e falha isolada
Se a API do Gemini falhar, ficar fora do ar ou o texto for reprovado duas vezes,
o resumo é montado por regras fixas (`template_summary`). A coluna `source` da
tabela `resumos_diarios` registra se o texto veio de `llm` ou de `template`.
Esse passo roda depois da carga dos dados e qualquer falha nele vira apenas um
aviso no log: o pipeline principal não é derrubado.

### Prompt versionado
O prompt fica em `prompts/daily_summary_v1.txt` e a versão usada é gravada na
coluna `prompt_version`. Assim é possível comparar resultados quando o prompt mudar.

## Possíveis evoluções futuras

- Migrar a execução do GitHub Actions de "instalar Python direto" para rodar
  via imagem Docker publicada, garantindo paridade total entre ambiente local
  e produção.
- Adicionar alertas (ex.: notificação) em caso de falha do pipeline.
- Manter o projeto do Supabase ativo com uma chamada diária (o plano gratuito
  pausa projetos com pouca atividade).
- Agente "Pergunte ao BCB": perguntas em linguagem natural convertidas em
  consultas SQL somente leitura, com validação e conjunto de testes de acurácia.