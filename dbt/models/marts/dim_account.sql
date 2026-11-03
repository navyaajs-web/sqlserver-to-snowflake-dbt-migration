select
    {{ surrogate_key(['account_id']) }}  as account_key,
    account_id,
    customer_id,
    branch_id,
    case product_code
        when 'CHK' then 'CHECKING'
        when 'SAV' then 'SAVINGS'
    end                                  as product_type,
    currency_code,
    opened_on,
    opening_balance,
    status_code
from {{ ref('stg_accounts') }}
