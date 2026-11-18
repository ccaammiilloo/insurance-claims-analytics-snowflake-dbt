{% macro driv_age_band(column) -%}
case
    when {{ column }} <= 25 then '18-25'
    when {{ column }} <= 35 then '26-35'
    when {{ column }} <= 45 then '36-45'
    when {{ column }} <= 55 then '46-55'
    when {{ column }} <= 65 then '56-65'
    when {{ column }} <= 75 then '66-75'
    else '76+'
end
{%- endmacro %}

{% macro veh_age_band(column) -%}
case
    when {{ column }} = 0 then '0'
    when {{ column }} <= 4 then '1-4'
    when {{ column }} <= 9 then '5-9'
    when {{ column }} <= 14 then '10-14'
    when {{ column }} <= 19 then '15-19'
    else '20+'
end
{%- endmacro %}

{% macro bonus_malus_band(column) -%}
case
    when {{ column }} = 50 then '50 (maximum bonus)'
    when {{ column }} between 51 and 80 then '51-80'
    when {{ column }} between 81 and 99 then '81-99'
    when {{ column }} = 100 then '100 (reference)'
    when {{ column }} between 101 and 150 then '101-150'
    else '151+'
end
{%- endmacro %}
