{#-
  SCD2 integrity for one business key:
    * exactly one open (current) version, and
    * no two versions whose [valid_from, valid_to) windows overlap.
-#}
{% test scd2_no_overlap(model, key, valid_from, valid_to) %}
with open_versions as (
    select {{ key }}, count(*) as n
    from {{ model }}
    where {{ valid_to }} is null
    group by {{ key }}
    having count(*) <> 1
),

overlapping_versions as (
    select a.{{ key }}
    from {{ model }} a
    join {{ model }} b
      on  a.{{ key }} = b.{{ key }}
      and a.{{ valid_from }} < b.{{ valid_from }}
      and (a.{{ valid_to }} is null or a.{{ valid_to }} > b.{{ valid_from }})
)

select {{ key }}, 'open_versions' as problem from open_versions
union all
select {{ key }}, 'overlap' as problem from overlapping_versions
{% endtest %}
