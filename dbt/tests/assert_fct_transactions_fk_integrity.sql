-- FK integrity across the whole star in one place: any fact row whose keys do not resolve to
-- a dimension row is returned (an orphan). Complements the per-column relationships tests and
-- also checks the account->customer link is consistent between dim_account and dim_customer.
select f.transaction_id, 'account' as missing
from {{ ref('fct_transactions') }} f
left join {{ ref('dim_account') }} a on a.account_key = f.account_key
where a.account_key is null

union all
select f.transaction_id, 'customer'
from {{ ref('fct_transactions') }} f
left join {{ ref('dim_customer') }} c on c.customer_key = f.customer_key
where c.customer_key is null

union all
select f.transaction_id, 'customer_mismatch'
from {{ ref('fct_transactions') }} f
join {{ ref('dim_account') }} a on a.account_key = f.account_key
join {{ ref('dim_customer') }} c on c.customer_key = f.customer_key
where c.customer_id <> a.customer_id

union all
select f.transaction_id, 'branch'
from {{ ref('fct_transactions') }} f
left join {{ ref('dim_branch') }} b on b.branch_key = f.branch_key
where b.branch_key is null

union all
select f.transaction_id, 'date'
from {{ ref('fct_transactions') }} f
left join {{ ref('dim_date') }} d on d.date_key = f.business_date_key
where d.date_key is null
