#!/usr/bin/env python3
import argparse
from decimal import Decimal

from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal

SUMMARY_SQL = text(
    """
    with parts as (
      select id, ST_Length((ST_Dump(geometry)).geom::geography) as meters
      from captured_geometries
    )
    select
      count(*) as total_parts,
      count(*) filter (where meters < :threshold) as removable_parts,
      round(coalesce(sum(meters) filter (where meters < :threshold), 0)::numeric, 1) as removable_meters,
      round((coalesce(sum(meters) filter (where meters < :threshold), 0) / nullif(sum(meters), 0) * 100)::numeric, 3) as removable_pct
    from parts
    """
)

DELETE_EMPTY_SQL = text(
    """
    with kept as (
      select captured_geometries.id
      from captured_geometries
      cross join lateral ST_Dump(captured_geometries.geometry) as dump
      where ST_Length(dump.geom::geography) >= :threshold
      group by captured_geometries.id
    )
    delete from captured_geometries
    where id not in (select id from kept)
    """
)

UPDATE_CLEANED_SQL = text(
    """
    with parts as (
      select captured_geometries.id, dump.geom as geometry
      from captured_geometries
      cross join lateral ST_Dump(captured_geometries.geometry) as dump
      where ST_Length(dump.geom::geography) >= :threshold
    ), cleaned as (
      select id, ST_Multi(ST_CollectionExtract(ST_Collect(geometry), 2)) as geometry
      from parts
      group by id
    )
    update captured_geometries
    set geometry = cleaned.geometry
    from cleaned
    where captured_geometries.id = cleaned.id
    """
)


def decimal_to_float(value):
    return float(value) if isinstance(value, Decimal) else value


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove tiny internal line fragments from captured Atlas geometry.")
    parser.add_argument("--threshold-meters", type=float, default=settings.captured_min_segment_meters)
    parser.add_argument("--apply", action="store_true", help="Write changes. Without this, only prints a dry run.")
    args = parser.parse_args()

    with SessionLocal() as db:
        before = dict(db.execute(SUMMARY_SQL, {"threshold": args.threshold_meters}).one()._mapping)
        print({key: decimal_to_float(value) for key, value in before.items()})
        if not args.apply:
            print("Dry run only. Re-run with --apply to clean captured geometry.")
            return
        db.execute(DELETE_EMPTY_SQL, {"threshold": args.threshold_meters})
        db.execute(UPDATE_CLEANED_SQL, {"threshold": args.threshold_meters})
        db.commit()
        after = dict(db.execute(SUMMARY_SQL, {"threshold": args.threshold_meters}).one()._mapping)
        print({key: decimal_to_float(value) for key, value in after.items()})


if __name__ == "__main__":
    main()
