select
    ACCT_NO                            as account_id,
    CUST_NO                            as customer_id,
    BR_CD                              as branch_id,
    PROD_CD                            as product_code,
    CCY_CD                             as currency_code,
    {{ parse_yyyymmdd('OPEN_DT') }}    as opened_on,
    -- [MIG-2] cast once here instead of in every legacy query
    cast(OPEN_BAL as decimal(18, 2))   as opening_balance,
    ACCT_STAT_CD                       as status_code
from {{ source('raw', 'accounts') }}
