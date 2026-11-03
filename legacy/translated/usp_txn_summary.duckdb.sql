-- DuckDB translation of legacy/usp_txn_summary.sql (see the dialect mapping in
-- usp_load_daily_balances.duckdb.sql). Runs once with $start_date / $as_of_date bound.

-- step: setup
CREATE SCHEMA IF NOT EXISTS legacy;
CREATE OR REPLACE TABLE legacy.txn_summary (
    bus_dt       DATE,
    br_cd        VARCHAR,
    txn_type_cd  VARCHAR,
    txn_cnt      INTEGER,
    total_amt    DECIMAL(18, 2)
);

-- step: once
INSERT INTO legacy.txn_summary (bus_dt, br_cd, txn_type_cd, txn_cnt, total_amt)
WITH posted AS (
    SELECT
        t.TXN_ID,
        a.BR_CD,
        t.TXN_TYPE_CD,
        CAST(t.TXN_AMT AS DECIMAL(18, 2)) AS TXN_AMT,
        CASE WHEN hour(CAST(t.TXN_DTTM AS TIMESTAMP)) >= 20
             THEN CAST(CAST(t.TXN_DTTM AS TIMESTAMP) AS DATE) + INTERVAL 1 DAY
             ELSE CAST(CAST(t.TXN_DTTM AS TIMESTAMP) AS DATE)
        END::DATE AS BUS_DT
    FROM raw.transactions t
    JOIN raw.accounts a ON a.ACCT_NO = t.ACCT_NO
    WHERE t.TXN_STAT_CD = 'P'
)
SELECT BUS_DT, BR_CD, TXN_TYPE_CD, COUNT(*), SUM(abs(TXN_AMT))
FROM posted
WHERE BUS_DT BETWEEN $start_date::DATE AND $as_of_date::DATE
GROUP BY BUS_DT, BR_CD, TXN_TYPE_CD;
