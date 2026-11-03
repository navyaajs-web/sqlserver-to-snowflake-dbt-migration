{#-
  Business rules lifted out of the legacy procedures. In T-SQL these CASE expressions were
  copy-pasted into every proc ([MIG-4]); here each lives in exactly one place.
-#}

{# R2: anything at or after the cut-off hour posts to the next business day. #}
{% macro business_date(timestamp_column) -%}
    case
        when extract(hour from {{ timestamp_column }}) >= {{ var('business_day_cutoff_hour') }}
            then cast({{ dbt.dateadd('day', 1, 'cast(' ~ timestamp_column ~ ' as date)') }} as date)
        else cast({{ timestamp_column }} as date)
    end
{%- endmacro %}

{# Integer YYYYMMDD key for joining facts to dim_date. #}
{% macro date_key(date_column) -%}
    cast(extract(year from {{ date_column }}) * 10000
         + extract(month from {{ date_column }}) * 100
         + extract(day from {{ date_column }}) as integer)
{%- endmacro %}

{# Deterministic surrogate key: md5 over the natural key parts. Portable across warehouses. #}
{% macro surrogate_key(columns) -%}
    md5(
    {%- for col in columns -%}
        coalesce(cast({{ col }} as varchar), '_null_'){% if not loop.last %} || '|' || {% endif %}
    {%- endfor -%}
    )
{%- endmacro %}
