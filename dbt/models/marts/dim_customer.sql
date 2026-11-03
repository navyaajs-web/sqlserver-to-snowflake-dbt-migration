-- SCD2 customer dimension built on the snap_customers snapshot.
-- One row per customer *version*; valid_to is null for the current version.
select
    {{ surrogate_key(['CUST_NO', 'dbt_valid_from']) }}     as customer_key,
    CUST_NO                                                as customer_id,
    CUST_NM                                                as customer_name,
    EMAIL_ADDR                                             as email_address,
    SEGMENT_CD                                             as segment_code,
    CITY_NM                                                as city,
    cast(dbt_valid_from as timestamp)                      as valid_from,
    cast(dbt_valid_to as timestamp)                        as valid_to,
    dbt_valid_to is null                                   as is_current
from {{ ref('snap_customers') }}
