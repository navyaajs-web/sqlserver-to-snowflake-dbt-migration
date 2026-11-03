-- Every transaction with the legacy business rules applied once:
--   R1 is_posted, R2 business_date cut-off, R3 signed amount, [MIG-5] account home branch.
with transactions as (
    select * from {{ ref('stg_transactions') }}
),

accounts as (
    select account_id, customer_id, branch_id from {{ ref('stg_accounts') }}
)

select
    t.transaction_id,
    t.account_id,
    a.customer_id,
    a.branch_id,
    t.transacted_at,
    {{ business_date('t.transacted_at') }}                  as business_date,
    t.transaction_type,
    t.channel,
    t.debit_credit_indicator,
    t.status_code,
    t.status_code = 'P'                                     as is_posted,
    t.amount,
    case when t.debit_credit_indicator = 'D' then -t.amount else t.amount end as signed_amount
from transactions t
join accounts a on a.account_id = t.account_id
