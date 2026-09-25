-- ============================================================
-- Consultas de exemplo sobre a tabela `indicadores`
-- Pipeline de Dados Automatizado - Indicadores Financeiros (BCB)
-- ============================================================

-- 1. Últimos valores registrados de cada indicador
SELECT DISTINCT ON (series_name)
    series_name,
    reference_date,
    value
FROM indicadores
ORDER BY series_name, reference_date DESC;


-- 2. Cotação média mensal do dólar
SELECT
    DATE_TRUNC('month', reference_date) AS mes,
    ROUND(AVG(value), 4) AS cotacao_media
FROM indicadores
WHERE series_name = 'dolar'
GROUP BY mes
ORDER BY mes;


-- 3. Variação do dólar entre o primeiro e o último dia de cada mês
SELECT
    DATE_TRUNC('month', reference_date) AS mes,
    MIN(value) AS menor_valor,
    MAX(value) AS maior_valor,
    ROUND(MAX(value) - MIN(value), 4) AS variacao
FROM indicadores
WHERE series_name = 'dolar'
GROUP BY mes
ORDER BY mes;


-- 4. Evolução da taxa Selic ao longo do tempo (sem repetir valores iguais consecutivos)
SELECT
    reference_date,
    value AS taxa_selic
FROM indicadores
WHERE series_name = 'selic'
ORDER BY reference_date;


-- 5. Histórico do IPCA mensal
SELECT
    reference_date,
    value AS variacao_ipca
FROM indicadores
WHERE series_name = 'ipca'
ORDER BY reference_date;


-- 6. Quantidade de registros e período coberto, por indicador
SELECT
    series_name,
    COUNT(*) AS total_registros,
    MIN(reference_date) AS data_inicial,
    MAX(reference_date) AS data_final
FROM indicadores
GROUP BY series_name;