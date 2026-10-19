-- Dimension: calendar dates
-- Grain: one row per calendar day.
-- A continuous date table: every day exists even if no order was placed,
-- so time axes in Power BI have no gaps and time-intelligence functions work.
-- Range: 2016-01-01 to the end of the current year (covers real + simulated orders).

with date_spine as (
    select date_day
    from unnest(generate_date_array(
        date '2016-01-01',
        last_day(current_date(), year)
    )) as date_day
)

select
    date_day,
    extract(year from date_day) as year,
    extract(quarter from date_day) as quarter,
    extract(month from date_day) as month,
    format_date('%B', date_day) as month_name,
    format_date('%Y-%m', date_day) as year_month,
    extract(isoweek from date_day) as iso_week,
    cast(format_date('%u', date_day) as int64) as day_of_week,
    format_date('%A', date_day) as day_name,
    extract(dayofweek from date_day) in (1, 7) as is_weekend
from date_spine