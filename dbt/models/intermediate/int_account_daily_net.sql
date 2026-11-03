-- Net posted movement per account per business date.
select
    account_id,
    business_date,
    sum(signed_amount)  as net_change,
    count(*)            as posted_txn_count
from {{ ref('int_transactions_enriched') }}
where is_posted
group by account_id, business_date
