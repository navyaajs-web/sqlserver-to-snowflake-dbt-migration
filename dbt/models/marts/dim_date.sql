with spine as (
    {{ date_spine(var('dim_date_start', '2020-01-01'), var('dim_date_end', '2027-12-31')) }}
)

select
    {{ date_key('date_day') }}                                   as date_key,
    date_day,
    cast(extract(year from date_day) as integer)                 as calendar_year,
    cast(extract(quarter from date_day) as integer)              as calendar_quarter,
    cast(extract(month from date_day) as integer)                as calendar_month,
    cast(extract(day from date_day) as integer)                  as day_of_month,
    cast({{ iso_day_of_week('date_day') }} as integer)           as iso_day_of_week,
    {{ iso_day_of_week('date_day') }} in (6, 7)                  as is_weekend
from spine
