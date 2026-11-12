# Resumo diário com IA

Depois que o pipeline grava os dados, um passo extra gera um parágrafo curto
sobre o dia (dólar, Selic e IPCA) e salva na tabela `resumos_diarios`, de onde
o dashboard lê. O código está em `src/llm_summary.py`.

## Como funciona

1. **Fatos em Python, não na IA.** Valor atual, variação em 7 e 30 dias,
   mínimo e máximo são calculados por código. A IA só recebe esses números
   prontos e escreve o texto.
2. **Chamada ao Gemini** (API REST, modelo configurável pela variável
   `LLM_MODEL`), com o prompt versionado em `prompts/daily_summary_v1.txt`.
3. **Verificação antes de gravar.** Todo número do texto precisa existir nos
   fatos (aceitando arredondamento). O texto também é reprovado se tiver
   recomendação, previsão ou explicação de causa, se passar do tamanho ou se
   esquecer uma das séries.
4. **Plano B sem IA.** Se a IA falhar, ficar fora do ar ou for reprovada duas
   vezes, o resumo é montado por regras fixas. A coluna `source` guarda
   `llm` ou `template`, então dá para medir quantas vezes a IA foi aprovada.
5. **Falha isolada.** Se este passo quebrar, o pipeline de dados continua
   verde: os dados já foram gravados antes.

## Decisões

- Sem chave configurada, o projeto funciona do mesmo jeito (usa o plano B).
- A chave vai no cabeçalho da requisição e fica em GitHub Secrets.
- O prompt tem versão (`prompt_version` na tabela) para comparar mudanças.

## Limites conhecidos

- A verificação confere números e palavras proibidas, mas não entende o
  sentido: ela não percebe se o texto diz "alta" quando os dados mostram queda.
  Esse ponto é coberto só pela instrução no prompt.
- Números inteiros aceitam arredondamento (um "3" passa se algum dado vale 2,79).

## Testes

`pytest -v` roda os testes de `tests/test_llm_summary.py` e
`tests/test_pipeline.py`. Nenhum deles chama a API real nem o banco.
