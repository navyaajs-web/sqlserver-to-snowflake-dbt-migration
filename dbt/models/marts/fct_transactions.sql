-- One row per transaction (all statuses; filter on is_posted for reporting).
-- branch_key is the ACCOUNT's home branch, matching the legacy report ([MIG-5]).
-- customer_key is the customer version that was valid when the transaction happened.
with txn as (
    select * from {{ ref('int_transactions_enriched') }}
),

customers as (
    select customer_key, customer_id, valid_from, valid_to from {{ ref('dim_customer') }}
)

select
    txn.transaction_id,
    {{ surrogate_key(['txn.account_id']) }}            as account_key,
    c.customer_key,
    {{ surrogate_key(['txn.branch_id']) }}             as branch_key,
    {{ date_key('txn.business_date') }}                as business_date_key,
    txn.business_date,
    txn.transacted_at,
    txn.transaction_type,
    txn.channel,
    txn.debit_credit_indicator,
    txn.status_code,
    txn.is_posted,
    txn.amount,
    txn.signed_amount
from txn
left join customers c
    on  c.customer_id = txn.customer_id
    and txn.transacted_at >= c.valid_from
    and (c.valid_to is null or txn.transacted_at < c.valid_to)
