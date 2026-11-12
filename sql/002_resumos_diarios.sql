-- Tabela do resumo diário escrito pela camada de IA (src/llm_summary.py).
-- Rode uma vez no SQL Editor do Supabase.

CREATE TABLE IF NOT EXISTS resumos_diarios (
    summary_date    DATE PRIMARY KEY,           -- dia em que o resumo foi gerado
    data_until      DATE,                       -- data mais recente dos dados usados
    text            TEXT         NOT NULL,      -- texto do resumo
    source          VARCHAR(20)  NOT NULL,      -- 'llm' (IA) ou 'template' (sem IA)
    model           VARCHAR(80),                -- modelo usado, quando source = 'llm'
    prompt_version  VARCHAR(20)  NOT NULL,      -- versão do prompt (pasta prompts/)
    inserted_at     TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- Leitura pública (o dashboard usa a chave anon); escrita só pelo pipeline.
ALTER TABLE resumos_diarios ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "leitura publica" ON resumos_diarios;
CREATE POLICY "leitura publica"
    ON resumos_diarios
    FOR SELECT
    TO anon
    USING (true);

GRANT SELECT ON resumos_diarios TO anon;
