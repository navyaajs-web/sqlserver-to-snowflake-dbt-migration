select
    cast(TXN_ID as bigint)             as transaction_id,
    ACCT_NO                            as account_id,
    cast(TXN_DTTM as timestamp)        as transacted_at,
    cast(TXN_AMT as decimal(18, 2))    as amount,
    DR_CR_IND                          as debit_credit_indicator,
    TXN_TYPE_CD                        as transaction_type,
    CHANNEL_CD                         as channel,
    TXN_STAT_CD                        as status_code
from {{ source('raw', 'transactions') }}
