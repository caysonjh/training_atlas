import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Activity


def persist_track_and_new_coverage(db: Session, activity: Activity, points: list[list[float]]) -> bool:
    if not activity.atlas_type or activity.is_private or len(points) < 2:
        return False

    inserted_id = db.scalar(
        text(
            """
            with raw_points as (
                select
                    ordinality as ord,
                    (value->>0)::double precision as lat,
                    (value->>1)::double precision as lon
                from jsonb_array_elements(cast(:points_json as jsonb)) with ordinality
            ), valid_points as (
                select ord, lat, lon
                from raw_points
                where lat between -90 and 90 and lon between -180 and 180
            ), line as (
                select ST_Simplify(
                    ST_SetSRID(ST_MakeLine(ST_MakePoint(lon, lat) order by ord), 4326),
                    0.00002,
                    true
                ) as geometry
                from valid_points
                having count(*) >= 2
            ), raw_insert as (
                insert into raw_tracks (activity_id, geometry)
                select :activity_id, geometry
                from line
                where geometry is not null and not ST_IsEmpty(geometry) and ST_Length(geometry::geography) > 0
                returning geometry
            ), existing as (
                select ST_Buffer(ST_UnaryUnion(ST_Collect(captured_geometries.geometry)), 0.00003) as geometry
                from captured_geometries
                join raw_insert on captured_geometries.geometry && ST_Expand(raw_insert.geometry, :lookup_degrees)
                where user_id = :user_id and atlas_type = :atlas_type
            ), uncovered as (
                select
                    case
                        when existing.geometry is null then raw_insert.geometry
                        else ST_Difference(raw_insert.geometry, existing.geometry)
                    end as geometry
                from raw_insert
                left join existing on true
            ), lines as (
                select ST_Multi(ST_CollectionExtract(geometry, 2)) as geometry
                from uncovered
            )
            insert into captured_geometries (user_id, atlas_type, source_activity_id, geometry, created_at)
            select :user_id, cast(:atlas_type as activitytype), :activity_id, geometry, now()
            from lines
            where not ST_IsEmpty(geometry) and ST_Length(geometry::geography) > 0
            returning id
            """
        ),
        {
            "points_json": json.dumps(points, separators=(",", ":")),
            "user_id": activity.user_id,
            "atlas_type": activity.atlas_type.value,
            "activity_id": activity.id,
            "lookup_degrees": settings.coverage_lookup_degrees,
        },
    )
    return inserted_id is not None


def coverage_feature_collection(db: Session, user_id: int) -> dict:
    rows = db.execute(
        text(
            """
            select atlas_type, ST_AsGeoJSON(geometry) as geometry
            from captured_geometries
            where user_id = :user_id
            order by id
            """
        ),
        {"user_id": user_id},
    ).all()

    features = []
    for atlas_type, geometry_json in rows:
        if not geometry_json:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {"atlas_type": atlas_type},
                "geometry": json.loads(geometry_json),
            }
        )
    return {"type": "FeatureCollection", "features": features}


def total_unique_distance_meters(db: Session, user_id: int) -> float:
    result = db.scalar(
        text(
            """
            select coalesce(sum(ST_Length(geometry::geography)), 0)
            from captured_geometries
            where user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    return float(result or 0)
