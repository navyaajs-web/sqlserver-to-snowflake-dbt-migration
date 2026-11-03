-- DuckDB translation of legacy/usp_load_daily_balances.sql, statement for statement.
-- The Python runner (datagen/legacy.py) plays the part of the T-SQL WHILE loop, executing
-- the per_day step once per date with $balance_date bound, so the translation keeps the
-- legacy row-by-day shape and does NOT borrow anything from the dbt models.
--
-- Dialect mapping used below:
--   DATEPART(HOUR, x)            -> hour(x)
--   DATEADD(DAY, 1, x)           -> x + INTERVAL 1 DAY
--   CONVERT(DATE, s, 112)        -> strptime(s, '%Y%m%d')::DATE
--   ISNULL(a, b)                 -> coalesce(a, b)
--   CAST(.. AS DATETIME2)        -> CAST(.. AS TIMESTAMP)

-- step: setup
CREATE SCHEMA IF NOT EXISTS legacy;
CREATE OR REPLACE TABLE legacy.daily_balance (
    acct_no     VARCHAR,
    bal_dt      DATE,
    close_bal   DECIMAL(18, 2),
    txn_cnt     INTEGER
);

-- step: per_day
INSERT INTO legacy.daily_balance (acct_no, bal_dt, close_bal, txn_cnt)
SELECT
    a.ACCT_NO,
    $balance_date::DATE,
    CAST(a.OPEN_BAL AS DECIMAL(18, 2))
      + coalesce(SUM(CASE WHEN t.DR_CR_IND = 'D'
                          THEN -CAST(t.TXN_AMT AS DECIMAL(18, 2))
                          ELSE  CAST(t.TXN_AMT AS DECIMAL(18, 2)) END), 0),
    SUM(CASE WHEN t.BUS_DT = $balance_date::DATE THEN 1 ELSE 0 END)
FROM raw.accounts a
LEFT JOIN (
    SELECT
        ACCT_NO, TXN_AMT, DR_CR_IND,
        CASE WHEN hour(CAST(TXN_DTTM AS TIMESTAMP)) >= 20
             THEN CAST(CAST(TXN_DTTM AS TIMESTAMP) AS DATE) + INTERVAL 1 DAY
             ELSE CAST(CAST(TXN_DTTM AS TIMESTAMP) AS DATE)
        END::DATE AS BUS_DT
    FROM raw.transactions
    WHERE TXN_STAT_CD = 'P'
) t
  ON  t.ACCT_NO = a.ACCT_NO
  AND t.BUS_DT <= $balance_date::DATE
WHERE strptime(a.OPEN_DT, '%Y%m%d')::DATE <= $balance_date::DATE
GROUP BY a.ACCT_NO, a.OPEN_BAL;
