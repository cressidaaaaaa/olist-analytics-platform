-- Staging model for geolocation
-- Purpose: clean the raw geolocation table (zip prefix -> lat/lng)

select
    geolocation_zip_code_prefix,                    -- zip code prefix (join key to customers/sellers)
    geolocation_lat,                                -- latitude
    geolocation_lng,                                -- longitude
    lower(geolocation_city) as geolocation_city,    -- normalize city to lowercase
    geolocation_state                               -- state abbreviation
from {{ source('olist_raw', 'geolocation') }}