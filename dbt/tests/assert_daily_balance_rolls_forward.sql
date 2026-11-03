-- Each day's closing balance equals the previous day's closing balance plus the day's net change.
with ordered as (
    select
        account_id,
        balance_date,
        net_change,
        closing_balance,
        lag(closing_balance) over (partition by account_id order by balance_date) as prev_close
    from {{ ref('fct_daily_balance') }}
)

select *
from ordered
where prev_close is not null
  and closing_balance <> prev_close + net_change
