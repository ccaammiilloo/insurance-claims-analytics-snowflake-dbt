-- Template for a stage based Snowflake load. The Python loader uses
-- write_pandas instead. Use this file only if you prefer COPY INTO.
-- Create the stage and run PUT from a machine that can see the CSV files.
-- Do not put credentials, account identifiers, or passwords in this file.

-- Example:
--   create file format if not exists raw.csv_format
--       type = csv
--       skip_header = 1
--       field_optionally_enclosed_by = '"';
--   create stage if not exists raw.file_stage
--       file_format = raw.csv_format;
--   -- PUT file://data/warehouse/policies.csv @raw.file_stage;
--   -- Repeat for vehicles.csv, drivers.csv, and claims.csv.

copy into raw.policies (
    policy_sk,
    policy_id,
    claim_count,
    exposure_years,
    area,
    bonus_malus,
    density,
    region,
    src_system,
    src_file_name,
    src_row_number,
    loaded_at
)
from @raw.file_stage/policies.csv
file_format = (type = csv skip_header = 1 field_optionally_enclosed_by = '"');

copy into raw.vehicles (
    vehicle_sk,
    policy_sk,
    policy_id,
    veh_power,
    veh_age,
    veh_brand,
    veh_gas,
    src_system,
    src_file_name,
    src_row_number,
    loaded_at
)
from @raw.file_stage/vehicles.csv
file_format = (type = csv skip_header = 1 field_optionally_enclosed_by = '"');

copy into raw.drivers (
    driver_sk,
    policy_sk,
    policy_id,
    driv_age,
    src_system,
    src_file_name,
    src_row_number,
    loaded_at
)
from @raw.file_stage/drivers.csv
file_format = (type = csv skip_header = 1 field_optionally_enclosed_by = '"');

copy into raw.claims (
    claim_sk,
    claim_sequence,
    policy_id,
    policy_sk,
    claim_amount,
    src_system,
    src_file_name,
    src_row_number,
    loaded_at
)
from @raw.file_stage/claims.csv
file_format = (type = csv skip_header = 1 field_optionally_enclosed_by = '"');
