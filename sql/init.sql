CREATE TABLE IF NOT EXISTS indicadores (
    id              SERIAL PRIMARY KEY,
    series_name     VARCHAR(20)     NOT NULL,
    reference_date  DATE            NOT NULL,
    value           NUMERIC(12, 4)  NOT NULL,
    inserted_at     TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_series_date UNIQUE (series_name, reference_date)
);

CREATE INDEX IF NOT EXISTS idx_indicadores_series_name ON indicadores (series_name);

