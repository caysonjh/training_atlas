#!/usr/bin/env python3
import os
from decimal import Decimal

import psycopg


QUERIES = {
    "users": "select count(*) from users",
    "connections": "select count(*) from strava_connections",
    "activities": "select count(*) from activities",
    "raw_tracks": "select count(*) from raw_tracks",
    "captured_geometries": "select count(*) from captured_geometries",
    "photos": "select count(*) from photo_markers",
    "import_jobs": "select count(*) from import_jobs",
    "unique_distance_meters": "select coalesce(ST_Length(ST_UnaryUnion(ST_Collect(geometry))::geography), 0) from captured_geometries",
}


def pg_url(value: str) -> str:
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def snapshot(url: str) -> dict[str, Decimal | int]:
    with psycopg.connect(pg_url(url)) as connection, connection.cursor() as cursor:
        result = {}
        for key, query in QUERIES.items():
            cursor.execute(query)
            result[key] = cursor.fetchone()[0]
        return result


def main() -> None:
    local_url = os.environ["LOCAL_DATABASE_URL"]
    production_url = os.environ["PRODUCTION_DATABASE_URL"]
    local = snapshot(local_url)
    production = snapshot(production_url)

    for key in QUERIES:
        print(f"{key}: local={local[key]} production={production[key]}")

    count_keys = [key for key in QUERIES if key != "unique_distance_meters"]
    counts_match = all(local[key] == production[key] for key in count_keys)
    distance_delta = abs(float(local["unique_distance_meters"]) - float(production["unique_distance_meters"]))
    if not counts_match or distance_delta > 1.0:
        raise SystemExit(f"Migration verification failed; distance delta={distance_delta:.3f}m")
    print(f"Migration verification passed; distance delta={distance_delta:.3f}m")


if __name__ == "__main__":
    main()
