select
    CUST_NO                            as customer_id,
    CUST_NM                            as customer_name,
    EMAIL_ADDR                         as email_address,
    SEGMENT_CD                         as segment_code,
    CITY_NM                            as city,
    cast(LAST_UPD_DTTM as timestamp)   as updated_at
from {{ source('raw', 'customers') }}
