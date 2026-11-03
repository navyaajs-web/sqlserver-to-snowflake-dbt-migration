-- Savings accounts cannot be overdrawn, so no savings closing balance may be below zero.
-- (Checking accounts can, which is why this is scoped by product rather than global.)
select b.account_id, b.balance_date, b.closing_balance
from {{ ref('fct_daily_balance') }} b
join {{ ref('dim_account') }} a on a.account_key = b.account_key
where a.product_type = 'SAVINGS'
  and b.closing_balance < 0
