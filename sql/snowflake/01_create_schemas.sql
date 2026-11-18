-- Snowflake schema setup for the insurance portfolio project.
-- Run in the project database. This file has no credentials.
-- The loader writes raw tables into RAW. dbt writes staging, intermediate,
-- marts, and seeds into their own schemas.

create schema if not exists raw;
create schema if not exists staging;
create schema if not exists intermediate;
create schema if not exists marts;
create schema if not exists seeds;
create schema if not exists analytics;
