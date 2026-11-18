-- Snowflake DDL for the raw landing tables.
-- Column meanings and derivation rules are documented in docs/data_profile.md.
-- Business dates, premium, VIN, and driver identifiers are intentionally absent.

create schema if not exists raw;

create table if not exists raw.policies (
    policy_sk varchar(32) not null,
    policy_id number(18, 0) not null,
    claim_count number(10, 0) not null,
    exposure_years float not null,
    area varchar(10) not null,
    bonus_malus number(10, 0) not null,
    density number(10, 0) not null,
    region varchar(10) not null,
    src_system varchar(100) not null,
    src_file_name varchar(200) not null,
    src_row_number number(18, 0) not null,
    loaded_at timestamp_ntz not null
);

create table if not exists raw.vehicles (
    vehicle_sk varchar(32) not null,
    policy_sk varchar(32) not null,
    policy_id number(18, 0) not null,
    veh_power number(10, 0) not null,
    veh_age number(10, 0) not null,
    veh_brand varchar(10) not null,
    veh_gas varchar(20) not null,
    src_system varchar(100) not null,
    src_file_name varchar(200) not null,
    src_row_number number(18, 0) not null,
    loaded_at timestamp_ntz not null
);

create table if not exists raw.drivers (
    driver_sk varchar(32) not null,
    policy_sk varchar(32) not null,
    policy_id number(18, 0) not null,
    driv_age number(10, 0) not null,
    src_system varchar(100) not null,
    src_file_name varchar(200) not null,
    src_row_number number(18, 0) not null,
    loaded_at timestamp_ntz not null
);

create table if not exists raw.claims (
    claim_sk varchar(32) not null,
    claim_sequence number(10, 0) not null,
    policy_id number(18, 0) not null,
    policy_sk varchar(32),
    claim_amount number(18, 2) not null,
    src_system varchar(100) not null,
    src_file_name varchar(200) not null,
    src_row_number number(18, 0) not null,
    loaded_at timestamp_ntz not null
);
