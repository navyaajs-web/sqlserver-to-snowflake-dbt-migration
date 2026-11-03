/*
================================================================================
 Harbor Point Bank (fictional) - LEGACY REFERENCE ONLY, NOT EXECUTED
 Procedure : rpt.usp_txn_summary
 Called by : SSIS package "RPT_Nightly_Balances" (Execute SQL Task, step 4 of 5)
 Replaced by: dbt model marts.fct_transactions (aggregated in reconciliation)
================================================================================
 What it does
   Daily posted-transaction counts and amounts by branch and transaction type,
   used by the branch performance report.

 Business rules
   R1  Posted only.   R2  20:00 business-day cut-off (same as daily balances).
   R6  TOTAL_AMT is the sum of ABSOLUTE amounts (volume, not net flow).
   R7  Transactions whose business date falls after @AsOfDate are excluded;
       they belong to tomorrow's report.

 Migration notes
   [MIG-4] The cut-off CASE expression is copy-pasted from usp_load_daily_balances.
           In dbt it lives once, in int_transactions_posted, and both marts
           reuse it.
   [MIG-5] The branch is taken from the ACCOUNT's home branch, not from where
           the transaction happened. This is kept on purpose to match the report,
           and it is documented in the fct_transactions model description.
================================================================================
*/
CREATE OR ALTER PROCEDURE rpt.usp_txn_summary
    @StartDate DATE,
    @AsOfDate  DATE
AS
BEGIN
    SET NOCOUNT ON;

    DELETE FROM rpt.TxnSummary WHERE BUS_DT BETWEEN @StartDate AND @AsOfDate;

    ;WITH posted AS (
        SELECT
            t.TXN_ID,
            a.BR_CD,                                                  -- [MIG-5]
            t.TXN_TYPE_CD,
            CAST(t.TXN_AMT AS DECIMAL(18,2)) AS TXN_AMT,
            -- [MIG-4] duplicated cut-off logic
            CASE WHEN DATEPART(HOUR, CAST(t.TXN_DTTM AS DATETIME2)) >= 20
                 THEN DATEADD(DAY, 1, CAST(CAST(t.TXN_DTTM AS DATETIME2) AS DATE))
                 ELSE CAST(CAST(t.TXN_DTTM AS DATETIME2) AS DATE)
            END AS BUS_DT
        FROM stg.TRANSACTIONS t
        JOIN stg.ACCOUNTS a ON a.ACCT_NO = t.ACCT_NO
        WHERE t.TXN_STAT_CD = 'P'                                     -- R1
    )
    INSERT INTO rpt.TxnSummary (BUS_DT, BR_CD, TXN_TYPE_CD, TXN_CNT, TOTAL_AMT)
    SELECT BUS_DT, BR_CD, TXN_TYPE_CD, COUNT(*), SUM(ABS(TXN_AMT))   -- R6
    FROM posted
    WHERE BUS_DT BETWEEN @StartDate AND @AsOfDate                     -- R7
    GROUP BY BUS_DT, BR_CD, TXN_TYPE_CD;
END;
GO
