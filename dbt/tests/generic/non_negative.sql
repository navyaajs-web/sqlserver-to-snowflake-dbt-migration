{#- Fails for any row where the column is below zero. Use `config: where:` to scope it. -#}
{% test non_negative(model, column_name) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} < 0
{% endtest %}
