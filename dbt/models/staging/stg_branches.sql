select
    BR_CD                              as branch_id,
    BR_NM                              as branch_name,
    REGION_CD                          as region_code,
    {{ parse_yyyymmdd('OPEN_DT') }}    as opened_on
from {{ source('raw', 'branches') }}
