/*
================================================================================
 Harbor Point Bank (fictional) - LEGACY REFERENCE ONLY, NOT EXECUTED
 Procedure : rpt.usp_load_daily_balances
 Called by : SSIS package "RPT_Nightly_Balances" (Execute SQL Task, step 3 of 5)
 Replaced by: dbt model marts.fct_daily_balance
================================================================================
 What it does
   Rebuilds rpt.DailyBalance (one row per account per business date) between
   @StartDate and @AsOfDate by looping one day at a time.

 Business rules that the dbt models must preserve (and that reconciliation checks)
   R1  Only posted transactions count (TXN_STAT_CD = 'P'). Reversed ('R') and
       pending ('N') rows are ignored.
   R2  Business-day cut-off: anything at or after 20:00 posts to the NEXT day.
   R3  Debits (DR_CR_IND = 'D') reduce the balance, credits increase it.
   R4  OPEN_BAL is the balance at the start of the account's first reported day.
   R5  Every account gets a row for every day it is open, even with no activity.

 Migration notes (see the [MIG] markers)
   [MIG-1] The WHILE loop runs 1 query per day. dbt replaces it with a set-based
           date spine plus a window SUM: one query, any warehouse.
   [MIG-2] Amounts land as VARCHAR from the SSIS flat-file source, and the proc
           casts them inline in every query. dbt casts once, in staging.
   [MIG-3] TRUNCATE + reload inside the proc has no tests and no lineage; dbt
           materialises a table with an enforced contract and data tests.
================================================================================
*/
CREATE OR ALTER PROCEDURE rpt.usp_load_daily_balances
    @StartDate DATE,
    @AsOfDate  DATE
AS
BEGIN
    SET NOCOUNT ON;

    -- [MIG-3] Full reload every night.
    TRUNCATE TABLE rpt.DailyBalance;

    DECLARE @d DATE = @StartDate;

    -- [MIG-1] Row-by-agonising-row: one INSERT per calendar day.
    WHILE @d <= @AsOfDate
    BEGIN
        INSERT INTO rpt.DailyBalance (ACCT_NO, BAL_DT, CLOSE_BAL, TXN_CNT)
        SELECT
            a.ACCT_NO,
            @d,
            -- [MIG-2] VARCHAR -> DECIMAL on every pass.  R3 + R4
            CAST(a.OPEN_BAL AS DECIMAL(18,2))
              + ISNULL(SUM(CASE WHEN t.DR_CR_IND = 'D'
                                THEN -CAST(t.TXN_AMT AS DECIMAL(18,2))
                                ELSE  CAST(t.TXN_AMT AS DECIMAL(18,2)) END), 0),
            -- Count of postings on this business date only.
            SUM(CASE WHEN t.BUS_DT = @d THEN 1 ELSE 0 END)
        FROM stg.ACCOUNTS a
        LEFT JOIN (
            SELECT
                ACCT_NO, TXN_AMT, DR_CR_IND,
                -- R2: 20:00 cut-off.  Snowflake: IFF(HOUR(ts) >= 20, DATEADD(day, 1, ts::date), ts::date)
                CASE WHEN DATEPART(HOUR, CAST(TXN_DTTM AS DATETIME2)) >= 20
                     THEN DATEADD(DAY, 1, CAST(CAST(TXN_DTTM AS DATETIME2) AS DATE))
                     ELSE CAST(CAST(TXN_DTTM AS DATETIME2) AS DATE)
                END AS BUS_DT
            FROM stg.TRANSACTIONS
            WHERE TXN_STAT_CD = 'P'                                   -- R1
        ) t
          ON  t.ACCT_NO = a.ACCT_NO
          AND t.BUS_DT <= @d
        -- R5: account must be open on @d (OPEN_DT is 'YYYYMMDD' text).
        WHERE CONVERT(DATE, a.OPEN_DT, 112) <= @d
        GROUP BY a.ACCT_NO, a.OPEN_BAL;

        SET @d = DATEADD(DAY, 1, @d);
    END
END;
GO
