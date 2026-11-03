-- One row per account per calendar day it is open within the reporting window.
-- Replaces the WHILE loop in usp_load_daily_balances with a date spine and a window SUM ([MIG-1]).
with accounts as (
    select account_id, opened_on, opening_balance from {{ ref('stg_accounts') }}
),

daily_net as (
    select * from {{ ref('int_account_daily_net') }}
),

spine as (
    {{ date_spine(var('reporting_start'), var('as_of_date')) }}
),

-- Any posted movement before the window still counts toward the balance (as in the legacy proc).
carried_in as (
    select account_id, sum(net_change) as net_before_window
    from daily_net
    where business_date < cast('{{ var("reporting_start") }}' as date)
    group by account_id
),

account_days as (
    select a.account_id, a.opening_balance, s.date_day as balance_date
    from accounts a
    join spine s on s.date_day >= a.opened_on
),

balances as (
    select
        ad.account_id,
        ad.balance_date,
        coalesce(dn.net_change, 0)                              as net_change,
        cast(coalesce(dn.posted_txn_count, 0) as integer)       as posted_txn_count,
        ad.opening_balance
            + coalesce(ci.net_before_window, 0)
            + sum(coalesce(dn.net_change, 0)) over (
                partition by ad.account_id
                order by ad.balance_date
                rows between unbounded preceding and current row
            )                                                   as closing_balance
    from account_days ad
    left join daily_net dn
        on dn.account_id = ad.account_id and dn.business_date = ad.balance_date
    left join carried_in ci
        on ci.account_id = ad.account_id
)

select
    {{ surrogate_key(['account_id', 'balance_date']) }}   as daily_balance_key,
    {{ surrogate_key(['account_id']) }}                   as account_key,
    {{ date_key('balance_date') }}                        as date_key,
    account_id,
    balance_date,
    cast(net_change as decimal(18, 2))                    as net_change,
    posted_txn_count,
    cast(closing_balance as decimal(18, 2))               as closing_balance
from balances
