import json

from geoalchemy2.shape import from_shape
from shapely import GeometryCollection, LineString, MultiLineString, unary_union
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models import Activity, RawTrack


def normalize_track(points: list[list[float]]) -> LineString | None:
    valid = [(lon, lat) for lat, lon in points if -90 <= lat <= 90 and -180 <= lon <= 180]
    if len(valid) < 2:
        return None
    line = LineString(valid)
    if line.is_empty or line.length == 0:
        return None
    return line.simplify(0.00002, preserve_topology=True)


def _as_multiline(geometry) -> MultiLineString | None:
    if geometry.is_empty:
        return None
    if isinstance(geometry, LineString):
        return MultiLineString([geometry])
    if isinstance(geometry, MultiLineString):
        return geometry
    if isinstance(geometry, GeometryCollection):
        lines = [part for part in geometry.geoms if isinstance(part, LineString)]
        return MultiLineString(lines) if lines else None
    return None


def calculate_new_coverage(line: LineString, existing_geometries: list) -> MultiLineString | None:
    existing = unary_union(existing_geometries) if existing_geometries else None
    uncovered = line if existing is None else line.difference(existing.buffer(0.00003))
    uncovered_multi = _as_multiline(uncovered)
    return uncovered_multi if uncovered_multi and uncovered_multi.length > 0 else None


def persist_track_and_new_coverage(db: Session, activity: Activity, points: list[list[float]]) -> bool:
    line = normalize_track(points)
    if not line or not activity.atlas_type or activity.is_private:
        return False

    raw = RawTrack(activity_id=activity.id, geometry=from_shape(line, srid=4326))
    db.add(raw)
    db.flush()

    inserted_id = db.scalar(
        text(
            """
            with incoming as (
                select ST_SetSRID(ST_GeomFromText(:line_wkt), 4326) as geometry
            ), existing as (
                select ST_Buffer(ST_UnaryUnion(ST_Collect(geometry)), 0.00003) as geometry
                from captured_geometries
                where user_id = :user_id and atlas_type = :atlas_type
            ), uncovered as (
                select
                    case
                        when existing.geometry is null then incoming.geometry
                        else ST_Difference(incoming.geometry, existing.geometry)
                    end as geometry
                from incoming
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
            "line_wkt": line.wkt,
            "user_id": activity.user_id,
            "atlas_type": activity.atlas_type.value,
            "activity_id": activity.id,
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
