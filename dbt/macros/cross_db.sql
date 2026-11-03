{#-
  Small cross-warehouse helpers. Each one has a DuckDB implementation (exercised locally and in
  CI) and a default implementation written for Snowflake/Redshift (configured, not exercised).
-#}

{# 'YYYYMMDD' text -> DATE. Legacy flat files carry dates in this format (CONVERT(..., 112)). #}
{% macro parse_yyyymmdd(column) -%}
    {{ return(adapter.dispatch('parse_yyyymmdd')(column)) }}
{%- endmacro %}
{% macro duckdb__parse_yyyymmdd(column) -%}
    cast(strptime({{ column }}, '%Y%m%d') as date)
{%- endmacro %}
{% macro default__parse_yyyymmdd(column) -%}
    to_date({{ column }}, 'YYYYMMDD')
{%- endmacro %}

{# ISO day of week, Monday = 1 ... Sunday = 7. #}
{% macro iso_day_of_week(column) -%}
    {{ return(adapter.dispatch('iso_day_of_week')(column)) }}
{%- endmacro %}
{% macro duckdb__iso_day_of_week(column) -%}
    isodow({{ column }})
{%- endmacro %}
{% macro snowflake__iso_day_of_week(column) -%}
    dayofweekiso({{ column }})
{%- endmacro %}
{% macro default__iso_day_of_week(column) -%}
    case extract(dow from {{ column }}) when 0 then 7 else extract(dow from {{ column }}) end
{%- endmacro %}

{# One row per calendar day between two dates (inclusive), column `date_day`. #}
{% macro date_spine(start_date, end_date) -%}
    {{ return(adapter.dispatch('date_spine')(start_date, end_date)) }}
{%- endmacro %}
{% macro duckdb__date_spine(start_date, end_date) -%}
    select cast(range as date) as date_day
    from range(cast('{{ start_date }}' as date), cast('{{ end_date }}' as date) + interval 1 day, interval 1 day)
{%- endmacro %}
{% macro default__date_spine(start_date, end_date) -%}
    with recursive spine (date_day) as (
        select cast('{{ start_date }}' as date)
        union all
        select cast({{ dbt.dateadd('day', 1, 'date_day') }} as date)
        from spine
        where date_day < cast('{{ end_date }}' as date)
    )
    select date_day from spine
{%- endmacro %}
