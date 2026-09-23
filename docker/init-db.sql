-- docker/init-db.sql
-- PostgreSQL / PostGIS initialization script for EcoShield database.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS obm_buildings (
    id BIGINT PRIMARY KEY,
    occupancy TEXT,
    height TEXT,
    floorspace REAL,
    quadkey TEXT,
    source_id INT,
    geom geometry(Polygon, 4326)
);

CREATE INDEX IF NOT EXISTS idx_obm_buildings_geom ON obm_buildings USING GIST (geom);
