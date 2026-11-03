select
    {{ surrogate_key(['branch_id']) }}   as branch_key,
    branch_id,
    branch_name,
    region_code,
    opened_on
from {{ ref('stg_branches') }}
