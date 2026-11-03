-- Point-in-time correctness: the customer version on each transaction must have been valid
-- when the transaction happened.
select f.transaction_id, f.transacted_at, c.valid_from, c.valid_to
from {{ ref('fct_transactions') }} f
join {{ ref('dim_customer') }} c on c.customer_key = f.customer_key
where f.transacted_at < c.valid_from
   or (c.valid_to is not null and f.transacted_at >= c.valid_to)
