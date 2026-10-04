-- Staging model for daily BRL -> EUR exchange rates
-- Purpose: turn business-day-only ECB rates into a complete daily series.
-- Weekends/holidays have no published rate, so we forward-fill:
-- each missing day reuses the most recent previous business-day rate.

with rates as (
    select
        rate_date,
        brl_to_eur
    from {{ source('olist_raw', 'fx_rates') }}
),

-- One row for every calendar day, from the first rate up to today
date_spine as (
    select calendar_date
    from unnest(generate_date_array(
        (select min(rate_date) from rates),
        current_date()
    )) as calendar_date
),

-- Attach rates to the calendar; weekends/holidays get NULL here
joined as (
    select
        d.calendar_date,
        r.brl_to_eur
    from date_spine as d
    left join rates as r
        on d.calendar_date = r.rate_date
)

select
    calendar_date as rate_date,
    -- Forward-fill: take the last non-null rate up to and including this day
    last_value(brl_to_eur ignore nulls) over (
        order by calendar_date
        rows between unbounded preceding and current row
    ) as brl_to_eur,
    brl_to_eur is null as is_filled   -- true = no published rate that day, value carried forward
from joined